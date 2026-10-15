#!/usr/bin/env python3
# outmem_compare.py — PERF-P22 (#3330): boot 停止時点の出力メモリ sha256 を変種間で比べる。
#   python3 tools/flelift/boot/outmem_compare.py <variant dir> --dump <dir> --pe <PE> --labels plain o2 o2lto --negctl plain_negctl
# 入力: <variant dir> の boot_<label>_r<i>.json のトップレベル outmem (fle_boot.mjs: 停止時の C スタック範囲と各範囲の sha256)。
#       <dir> の outmem_boot_<label>_r<i>.bin (FLE_OUTMEM_DUMP で書いた線形メモリ全体)。
# 計算は Python hashlib で dump から範囲を読み直す (node:crypto 版との二重計算。full / no_cstack が両者で一致しないと FAIL)。
#   full           = 線形メモリ全体
#   no_cstack      = 全体から C スタック [stack.end, stack.base) を除いた範囲
#   image_writable = PE の書込み可能セクション (IMAGE_SCN_MEM_WRITE) を guest VA = 0x400000 + VirtualAddress で連結
#   sections       = 上の各セクションの sha256
# 判定 (rc): 受入 1 だけで決める。変種 (--labels) の全 run で image_writable と各書込み可能セクションが一致し、
#           node 版と python 版の full / no_cstack が一致すること。
#           full / no_cstack の変種間・run 間の一致は参考表示 (C heap・C data の非決定と変種差がここに出る)。rc には入れない。
#           ネガコン (--negctl) の判別結果は別行で出す (受入 2)。rc には入れない。
import glob, hashlib, json, os, re, struct, sys

IMG = 0x400000


def pe_sections(path):
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec, opt = struct.unpack_from("<HH", d, pe + 6)[0], struct.unpack_from("<H", d, pe + 20)[0]
    out = []
    for i in range(nsec):
        s = pe + 24 + opt + 40 * i
        name = d[s:s + 8].rstrip(b"\0").decode()
        vsz, va = struct.unpack_from("<II", d, s + 8)
        ch = struct.unpack_from("<I", d, s + 36)[0]
        out.append((name, va, vsz, bool(ch & 0x80000000)))
    return out


def compute(dump, secs, stack):
    data = open(dump, "rb").read()
    h = hashlib.sha256(); h.update(data)
    full = h.hexdigest()
    h = hashlib.sha256(); h.update(data[0:stack[0]]); h.update(data[stack[1]:len(data)])
    no_cstack = h.hexdigest()
    h = hashlib.sha256(); per = {}
    for name, va, vsz, w in secs:
        if not w:
            continue
        a = IMG + va
        h.update(data[a:a + vsz])
        per[name] = hashlib.sha256(data[a:a + vsz]).hexdigest()
    return {"mem_bytes": len(data), "full": full, "no_cstack": no_cstack, "image_writable": h.hexdigest(), "sections": per}


def main():
    args = sys.argv[1:]
    vdir = args.pop(0)
    labels, negctl, dump, pe = [], None, None, os.environ.get("FL_WIN64_DIR", "") + "/extracted/block00031_PE.bin"
    while args:
        k = args.pop(0)
        if k == "--labels":
            while args and not args[0].startswith("--"):
                labels.append(args.pop(0))
        elif k == "--negctl":
            negctl = args.pop(0)
        elif k == "--dump":
            dump = args.pop(0)
        elif k == "--pe":
            pe = args.pop(0)
    secs = pe_sections(pe)
    print("PE 書込み可能セクション: " + ", ".join(f"{n}(VA 0x{va:x}, {vsz} B)" for n, va, vsz, w in secs if w))
    ok = True
    runs = []  # (label, run, node_om, py)
    for p in sorted(glob.glob(os.path.join(vdir, "boot_*.json"))):
        m = re.match(r"boot_(.+)_r(\d+)\.json$", os.path.basename(p)) or re.match(r"boot_(.+)\.json$", os.path.basename(p))
        if not m:
            continue
        label = m.group(1); run = m.group(2) if m.lastindex == 2 else "1"
        if label not in labels and label != negctl:
            continue
        om = json.load(open(p)).get("outmem")
        if om is None:
            print(f"# {label} r{run}: outmem 無し", file=sys.stderr); ok = False; continue
        dp = os.path.join(dump, "outmem_" + os.path.basename(p)[:-5] + ".bin") if dump else None
        if not dp or not os.path.exists(dp):
            print(f"# {label} r{run}: dump 無し", file=sys.stderr); ok = False; continue
        stack = (int(om["stack"]["end"], 16), int(om["stack"]["base"], 16))
        py = compute(dp, secs, stack)
        agree = py["full"] == om["full"] and py["no_cstack"] == om["no_cstack"]
        ok = ok and agree
        runs.append((label, run, om, py))
        print(f"# {label} r{run}: node 版と python 版の full/no_cstack 一致 = {agree} (stack end 0x{stack[0]:x} base 0x{stack[1]:x})")
    print()
    print("| label | run | 線形メモリ (B) | full (全体) | no_cstack (C スタック除く) | image_writable |")
    print("|---|---|--:|---|---|---|")
    for label, run, om, py in runs:
        print(f"| {label} | {run} | {py['mem_bytes']} | {py['full'][:16]} | {py['no_cstack'][:16]} | {py['image_writable'][:16]} |")
    print()
    var = [r for r in runs if r[0] in labels]
    neg = [r for r in runs if r[0] == negctl]
    # 受入 1 (rc を決める)
    vals = {r[3]["image_writable"] for r in var}
    print(f"image_writable: 変種 {','.join(labels)} の全 run で一致 = {len(vals) == 1} (異なる値 {len(vals)} 件)")
    ok = ok and len(vals) == 1
    for name in [n for n, va, vsz, w in secs if w]:
        vals = {r[3]["sections"][name] for r in var}
        print(f"section {name}: 一致 = {len(vals) == 1} (異なる値 {len(vals)} 件)")
        ok = ok and len(vals) == 1
    # 参考 (rc に入れない): 全体・C スタック除外の一致。非決定 (run 間) と変種差 (C data) の所在を見る
    for key in ("no_cstack", "full"):
        vals = {r[3][key] for r in var}
        print(f"参考 {key}: 変種 {','.join(labels)} の全 run で一致 = {len(vals) == 1} (異なる値 {len(vals)} 件)")
    # 受入 2 (ネガコン・rc に入れない): FLE_IPP=0 で image_writable が変種と異なれば判別力あり
    if negctl:
        base = {r[3]["image_writable"] for r in var}
        changed = bool(neg) and all(r[3]["image_writable"] not in base for r in neg)
        print(f"negctl {negctl}: image_writable が変種と異なる = {changed} (受入 2 {'達成' if changed else '未達'})")
    print("RESULT", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
