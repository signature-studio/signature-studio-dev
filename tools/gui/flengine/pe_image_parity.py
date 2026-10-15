#!/usr/bin/env python3
"""pe_image_parity.py — GUI-12 (#566): tools/gui/lift/pe_image.py (共通規則) が tools/m11/m11_data_gen.py と
実 FLEngine PE 上でバイト一致することの検査 + ネガティブコントロール。

  python3 pe_image_parity.py --pe <FLEngine PE> [--lb 0 --lb 0x10000] [--m11-data work/m11_data.c (lb=0 の既存生成物と比較)]
終了コード: 0 = 全 PASS (ネガコンが期待どおり FAIL を含む) / 1 = FAIL / 2 = 前提欠如
m11 は読取専用: m11_data_gen.py は M11_DATA_OUT / M11_LB_BASE 環境変数で一時ディレクトリに出力させて実行する。
"""
import argparse, os, re, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GUI = os.path.dirname(HERE)
M11 = os.path.join(GUI, "..", "m11")
sys.path.insert(0, os.path.join(GUI, "lift"))
import pe_image

rc = 0


def P(msg): print("[parity] PASS " + msg)


def F(msg):
    global rc
    rc = 1
    print("[parity] FAIL " + msg)


def parse_m11_data(path):
    """m11_data.c -> {section: (lo, bytes)}。配列本体 (dlld_<sec>[]) と #define <SEC>_LO / memcpy 先から復元する。"""
    s = open(path).read()
    out = {}
    for m in re.finditer(r"static const unsigned char dlld_(\w+)\[\] = \{\n(.*?)\n\};", s, re.S):
        sym = m.group(1)                       # _data / _rdata
        body = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})", m.group(2)))
        lo = int(re.search(r"#define %s_LO 0x([0-9a-f]+)u" % sym.upper(), s).group(1), 16)
        n = int(re.search(r"#define %s_LEN (\d+)u" % sym.upper(), s).group(1))
        assert len(body) == n, "%s: 配列長 %d != LEN %d" % (sym, len(body), n)
        out["." + sym.lstrip("_")] = (lo, body)
    return out


def gen_m11(pe_path, lb, outdir):
    out = os.path.join(outdir, "m11_data_lb%x.c" % lb)
    env = dict(os.environ, M11_DATA_OUT=out, M11_LB_BASE=hex(lb))
    r = subprocess.run([sys.executable, os.path.join(M11, "m11_data_gen.py"), pe_path], env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout + r.stderr)
        raise SystemExit("m11_data_gen.py 失敗 (lb=0x%x)" % lb)
    return out, r.stdout.strip().splitlines()[0]


def compare(shared, m11):
    """-> (一致 bool, 詳細)。セクション名・lo・長さ・全バイトを比較し、最初の差分位置を返す"""
    if sorted(n for n, *_ in shared) != sorted(m11):
        return False, "セクション集合が違う shared=%s m11=%s" % (sorted(n for n, *_ in shared), sorted(m11))
    for (n, lo, sd, _fx) in shared:
        mlo, mb = m11[n]
        if mlo != lo or len(mb) != len(sd):
            return False, "%s: lo/len 不一致 shared=(0x%x,%d) m11=(0x%x,%d)" % (n, lo, len(sd), mlo, len(mb))
        if bytes(sd) != mb:
            i = next(k for k in range(len(mb)) if sd[k] != mb[k])
            return False, "%s: +0x%x で不一致 shared=%s m11=%s" % (n, i, bytes(sd[i:i + 8]).hex(), mb[i:i + 8].hex())
    return True, ", ".join("%s len=%d" % (n, len(sd)) for (n, _lo, sd, _fx) in shared)


def main():
    global rc
    ap = argparse.ArgumentParser()
    ap.add_argument("--pe", required=True)
    ap.add_argument("--lb", action="append", default=None)
    ap.add_argument("--m11-data", default=None, help="既存の m11_data.c (lb=0 で生成済み) とも比較する")
    a = ap.parse_args()
    if not os.path.isfile(a.pe):
        print("[parity] 前提欠如: PE %s" % a.pe); return 2
    lbs = [int(x, 0) for x in (a.lb or ["0", "0x10000"])]
    pe = pe_image.PE(a.pe)
    print("[parity] PE base=0x%x size_of_image=0x%x DIR64=%d" % (pe.base, pe.size_of_image, len(pe.dir64_relocs())))
    with tempfile.TemporaryDirectory() as td:
        for lb in lbs:
            path, line = gen_m11(a.pe, lb, td)
            m11 = parse_m11_data(path)
            shared = pe_image.rebase_sections(pe, (".rdata", ".data"), lb)
            ok, why = compare(shared, m11)
            fixed = {n: fx for (n, _lo, _sd, fx) in shared}
            (P if ok else F)("P1 LB=0x%x: 共通モジュール == m11_data_gen.py 出力 (%s) | 補正件数 %s | m11: %s" % (lb, why, fixed, line))
            if sum(fixed.values()) == 0:
                F("P2 LB=0x%x: 補正件数が 0 (DIR64 補正が空振り → 一致しても無意味)" % lb)
            else:
                P("P2 LB=0x%x: 補正件数 %d > 0" % (lb, sum(fixed.values())))
            if lb == lbs[0]:
                # ---- ネガティブコントロール (全て「一致してはならない」) ----
                bad_sh = [(n, lo, bytearray(sd), fx) for (n, lo, sd, fx) in shared]
                for (n, lo, sd, fx) in bad_sh:
                    if n == ".data":
                        base = lo - lb
                        for r in pe.dir64_relocs():
                            if base <= r <= base + len(sd) - 8:
                                off = r - base
                                v = struct.unpack_from("<Q", sd, off)[0]
                                if pe.base < v < pe.base + pe_image.IMG_SPAN_M11:
                                    sd[off] ^= 1      # 補正済み 1 スロットの最下位ビットを反転
                                    break
                ok2, why2 = compare(bad_sh, m11)
                (F if ok2 else P)("N1 補正値を 1 bit 壊すと比較が FAIL する (%s)" % ("検出できない!" if ok2 else why2))
                nofix = pe_image.rebase_sections(pe, (".rdata", ".data"), lb, span=pe.base)   # span=base → 条件 v < base+span を満たさず補正ゼロ
                ok3, why3 = compare(nofix, m11)
                (F if ok3 else P)("N2 補正を全く行わない実装は FAIL する (%s)" % ("検出できない!" if ok3 else why3))
                ok4, why4 = compare([s for s in shared if s[0] != ".rdata"], m11)
                (F if ok4 else P)("N3 セクション欠落は FAIL する (%s)" % ("検出できない!" if ok4 else why4))
                if a.m11_data:
                    if not os.path.isfile(a.m11_data):
                        print("[parity] 前提欠如: %s" % a.m11_data); return 2
                    if lb == 0:
                        ok5, why5 = compare(shared, parse_m11_data(a.m11_data))
                        (P if ok5 else F)("P3 既存 work/m11_data.c (m11_build.sh が使う実物) とも一致 (%s)" % why5)
        # 状態の突合: runtime 方式 (RetDec 経路) の補正数が lva 方式と整合する
        img, offs, st = pe_image.runtime_image(pe, skip=(".text",))
        ds = [s for s in pe.sections if s[0] in (".data", ".rdata")]
        n_in = sum(1 for r in pe.dir64_relocs() if any(lo <= r <= lo + vs - 8 for (_n, lo, vs, _d) in ds))
        lva_fixed = sum(fx for (_n, _lo, _sd, fx) in pe_image.rebase_sections(pe, (".rdata", ".data"), 0))
        print("[parity] INFO runtime 方式 (.text 除外・image 内宛のみ): %s / data 系 DIR64 スロット %d / lva 方式の補正 %d" % (st, n_in, lva_fixed))
    print("[parity] done → exit %d" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
