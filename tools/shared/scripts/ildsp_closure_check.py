#!/usr/bin/env python3
"""ildsp_closure.py の結果を、別の逆アセンブラ (GNU objdump) で検算する。

usage: ildsp_closure_check.py <vtable.json> [PE]
  既定 PE: $FL_WIN64_DIR/extracted/block24360_PE.bin (tools/shared/paths.py)
検算の範囲と限界:
  - 検算するのは命令の復号だけ。関数集合 (JSON の function_rvas) は ildsp_closure.py と共有する。
    closure の辿り方 (.pdata の無い直接 call/jmp 先の扱いを含む) は検算しないので、取りこぼしは検出できない。
  - 関数範囲は ildsp_closure.py と同じ定義 (.pdata の終端。無ければ次の .pdata 先頭か .text 末尾)。
  - 各範囲を `objdump -d -M intel --start-address --stop-address` で逆アセンブルし、命令開始アドレス (RVA) の
    集合を capstone (ildsp_survey.sweep) の集合と比べる。
  - 命令ごとに SIMD (xmm/ymm/zmm を含む) と間接 call (`call` の即値でない形) の判定も比べる。
    `(bad)` 行と `.byte` 行は命令として数えない。
  - 集合の差は KNOWN_DATA_IN_CODE の RVA と完全一致する場合のみ許す。それ以外の差は非 0 で終了する。
  - JSON の命令数・SIMD 比・間接 call 数は、上の capstone 集合から再計算した値と一致しなければならない。
  - 参考値として、同じ関数集合の末尾 jmp (即値でない jmp) を objdump の出力から分類し `[tail]` 行に出す
    (IAT / 画像内ポインタ / reg / vcall 形 `[reg+disp]` / switch 形 `[base+idx*8]`)。判定には使わない。
不一致が 1 件でもあれば非 0 で終了する。"""
import sys, os, re, json, struct, subprocess, argparse, bisect
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from paths import FL_WIN64_DIR
import pefile, capstone
import ildsp_survey as S

LINE_RE = re.compile(r"^\s*([0-9a-f]+):\t(.*)$")
DIRECT_CALL_RE = re.compile(r"^call\s+0x[0-9a-f]+$")
SIMD_RE = re.compile(r"\b(xmm|ymm|zmm)\d")
# 既知差分 (RVA): 命令開始アドレスが capstone 側だけに現れる箇所。
# TransientLooper の関数 0x190fa0 (範囲 0x190fa0-0x191c80) 内の 0x191c20 付近には switch 用の 4 byte RVA 表が埋まる。
# 0x191c1f の `add ch,cl` (00 cd) は両者で同じ位置から復号される。0x191c28 の `c5 11 19` は不正な VEX 接頭辞で、
# capstone は 1 byte 飛ばして 0x191c29 から `adc dword ptr [rcx], ebx` を 1 件数える。objdump は 0x191c28 を
# `(bad)` として 3 byte を 1 行で消費し、0x191c29 を命令として出さない。
KNOWN_DATA_IN_CODE = {"TransientLooper_CreateInstance": {0x191c29}}
JMP_RE = re.compile(r"^(?:\S+ )*?jmp\s+([^#]*?)\s*(?:#\s*0x([0-9a-f]+).*)?$")
DIRECT_JMP_RE = re.compile(r"^0x[0-9a-f]+$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("pe", nargs="?", default=os.path.join(FL_WIN64_DIR, "extracted", "block24360_PE.bin"))
    a = ap.parse_args()
    res = json.load(open(a.json))

    pe = pefile.PE(a.pe, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    text = {s.Name.rstrip(b"\0").decode(): s for s in pe.sections}[".text"]
    t_hi = text.VirtualAddress + text.Misc_VirtualSize
    exc = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]]
    image = pe.get_memory_mapped_image()
    funcs = {}
    for i in range(exc.Size // 12):
        b, e, _ = struct.unpack_from("<III", image, exc.VirtualAddress + i * 12)
        funcs[b] = e
    fn_sorted = sorted(funcs)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def end_of(b):
        if b in funcs:
            return funcs[b]
        i = bisect.bisect_right(fn_sorted, b)
        return fn_sorted[i] if i < len(fn_sorted) else t_hi

    iat = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IAT"]]
    iat_lo, iat_hi = iat.VirtualAddress, iat.VirtualAddress + iat.Size

    def jmp_kind(m):
        # 末尾 jmp の分類 (即値の jmp は None)。rip 相対は objdump の `# 0x...` (絶対アドレス) で参照先を見る
        g = re.sub(r"<.*>", "", m.group(1)).strip()
        if DIRECT_JMP_RE.match(g):
            return None
        if "[rip+" in g:
            if m.group(2) is None:
                return "imgptr"
            t = int(m.group(2), 16) - ib
            return "IAT" if iat_lo <= t < iat_hi else "imgptr"
        if "[" in g:
            return "switch" if "*" in g else "vcall"
        return "reg"

    cap_cache, obj_cache, jmp_cache = {}, {}, {}

    def capstone_range(b):
        # RVA -> (simd, indirect call)
        if b not in cap_cache:
            cap_cache[b] = {addr: (S.classify(m, ops) == "simd", m.startswith("call") and not S.is_direct(ops))
                            for addr, m, ops in S.sweep(md, bytes(image[b:end_of(b)]), b)}
        return cap_cache[b]

    def objdump_range(b):
        # RVA -> (simd, indirect call)
        if b not in obj_cache:
            e = end_of(b)
            out = subprocess.run(["objdump", "-d", "-M", "intel", "--no-show-raw-insn",
                                  f"--start-address=0x{ib + b:x}", f"--stop-address=0x{ib + e:x}", a.pe],
                                 capture_output=True, text=True, check=True, timeout=120).stdout
            insns, jmps = {}, {}
            for line in out.splitlines():
                m = LINE_RE.match(line)
                if not m:
                    continue
                body = m.group(2).strip()
                if not body or body.startswith("(bad)") or body.startswith(".byte"):
                    continue
                addr = int(m.group(1), 16) - ib
                insns[addr] = (bool(SIMD_RE.search(body)),
                               body.startswith("call") and not DIRECT_CALL_RE.match(body))
                jm = JMP_RE.match(body)
                kind = jmp_kind(jm) if jm else None
                if kind is not None:
                    jmps[addr] = kind
            obj_cache[b] = insns
            jmp_cache[b] = jmps
        return obj_cache[b]

    ok = True
    for row in res["exports"]:
        v = row["vtable"]
        if v is None:
            continue
        cap, obj = {}, {}
        for fh in v["function_rvas"]:
            b = int(fh, 16)
            for addr, f in capstone_range(b).items():
                cap.setdefault(addr, f)
            for addr, f in objdump_range(b).items():
                obj.setdefault(addr, f)
        only_cap = set(cap) - set(obj)
        only_obj = set(obj) - set(cap)
        known = KNOWN_DATA_IN_CODE.get(row["export"], set())
        flags_ok = all(cap[x] == obj[x] for x in set(cap) & set(obj))
        n_cap = len(cap)
        simd_cap = sum(1 for s, _ in cap.values() if s)
        ind_cap = sum(1 for _, c in cap.values() if c)
        simd_ratio = round(simd_cap / max(n_cap, 1), 4)
        ind_obj = sum(1 for _, c in obj.values() if c)
        match = (only_cap == known and not only_obj and flags_ok and n_cap == v["instructions"]
                 and ind_cap == v["indirect_calls"] and simd_ratio == v["simd_ratio"])
        ok &= match
        fmt = lambda s: "{" + ",".join(hex(x) for x in sorted(s)) + "}" if s else "{}"
        print(f"[check] {row['export']}: insns json={v['instructions']} capstone={n_cap} objdump={len(obj)} | "
              f"only_capstone={fmt(only_cap)} only_objdump={fmt(only_obj)} flags={'same' if flags_ok else 'DIFF'} | "
              f"indirect capstone={ind_cap} objdump={ind_obj} | simd capstone={simd_ratio} json={v['simd_ratio']} "
              f"-> {'OK' if match else 'MISMATCH'}")
        tails = {}
        for fh in v["function_rvas"]:
            objdump_range(int(fh, 16))
            for addr, k in jmp_cache[int(fh, 16)].items():
                tails.setdefault(addr, k)
        tc = {k: sum(1 for x in tails.values() if x == k) for k in ("IAT", "imgptr", "reg", "vcall", "switch")}
        print(f"[tail] {row['export']}: IAT={tc['IAT']} imgptr={tc['imgptr']} reg={tc['reg']} "
              f"vcall={tc['vcall']} switch={tc['switch']}")
    print("[check] ALL OK" if ok else "[check] MISMATCH")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
