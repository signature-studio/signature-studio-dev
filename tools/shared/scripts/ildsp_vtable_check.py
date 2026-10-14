#!/usr/bin/env python3
"""ildsp_vtable.py の結果を、別の逆アセンブラ (GNU objdump) で検算する。

usage: ildsp_vtable_check.py <vtable.json> [PE]
  既定 PE: $FL_WIN64_DIR/extracted/block24360_PE.bin (tools/shared/paths.py)
検算の方法:
  - ildsp_vtable.py の JSON から、export ごとの到達関数 (function_rvas) の一覧を読む。
  - 各関数の範囲 [b, end) は ildsp_vtable.py と同じ定義 (.pdata の終端。無ければ次の .pdata 先頭) を使う。
  - 範囲ごとに `objdump -d -M intel --start-address --stop-address` で逆アセンブルし、命令数・SIMD
    (xmm/ymm/zmm を含む)・間接 call (`call` の即値でない形) を数える。`(bad)` と `.byte` 行は数えない
    (capstone は復号できないバイトを 1 byte 飛ばして数えないため、そろえる)。
  - export ごとの和集合の命令数・間接 call 数・SIMD 比を、ildsp_vtable.py の値と照合する。
    命令数の差は KNOWN_DATA_IN_CODE に列挙した既知の 1 件 (データ埋め込み) のみ許す。
不一致が 1 件でもあれば非 0 で終了する。"""
import sys, os, re, json, struct, subprocess, argparse, bisect
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from paths import FL_WIN64_DIR
import pefile

LINE_RE = re.compile(r"^\s*([0-9a-f]+):\t(.*)$")
DIRECT_CALL_RE = re.compile(r"^call\s+0x[0-9a-f]+$")
SIMD_RE = re.compile(r"\b(xmm|ymm|zmm)\d")
# 既知差分: 関数内に埋め込まれたデータ (switch のジャンプテーブル = 4 byte RVA の並び) を capstone が命令として
# 数える分。TransientLooper の 0x190fa0 (範囲 0x190fa0-0x191c80) では 0x191c20 付近の表を capstone が
# `int 0x10` 等として 1 命令数え、objdump は数えない。これ以外の差分は許さない。
KNOWN_DATA_IN_CODE = {"TransientLooper_CreateInstance": 1}


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

    def end_of(b):
        if b in funcs:
            return funcs[b]
        i = bisect.bisect_right(fn_sorted, b)
        return fn_sorted[i] if i < len(fn_sorted) else t_hi

    cache = {}

    def objdump_range(b):
        if b in cache:
            return cache[b]
        e = end_of(b)
        out = subprocess.run(["objdump", "-d", "-M", "intel", "--no-show-raw-insn",
                              f"--start-address=0x{ib + b:x}", f"--stop-address=0x{ib + e:x}", a.pe],
                             capture_output=True, text=True, check=True, timeout=120).stdout
        n = simd = ic = 0
        for line in out.splitlines():
            m = LINE_RE.match(line)
            if not m:
                continue
            body = m.group(2).strip()
            if not body or body.startswith("(bad)") or body.startswith(".byte"):
                continue
            n += 1
            if SIMD_RE.search(body):
                simd += 1
            if body.startswith("call") and not DIRECT_CALL_RE.match(body):
                ic += 1
        cache[b] = (n, simd, ic)
        return cache[b]

    ok = True
    for row in res["exports"]:
        v = row["vtable"]
        if v is None:
            continue
        n_tot = s_tot = i_tot = 0
        for fh in v["function_rvas"]:
            n, s, c = objdump_range(int(fh, 16))
            n_tot += n
            s_tot += s
            i_tot += c
        simd_ratio = round(s_tot / max(n_tot, 1), 4)
        delta = v["instructions"] - n_tot
        match = (delta == KNOWN_DATA_IN_CODE.get(row["export"], 0) and i_tot == v["indirect_calls"]
                 and simd_ratio == v["simd_ratio"])
        ok &= match
        print(f"[check] {row['export']}: insns capstone={v['instructions']} objdump={n_tot} delta={delta} | "
              f"indirect capstone={v['indirect_calls']} objdump={i_tot} | "
              f"simd capstone={v['simd_ratio']} objdump={simd_ratio} -> {'OK' if match else 'MISMATCH'}")
    print("[check] ALL OK" if ok else "[check] MISMATCH")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
