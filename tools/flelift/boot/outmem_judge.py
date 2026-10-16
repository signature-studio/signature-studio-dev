#!/usr/bin/env python3
# outmem_judge.py — FLE-43 (#5177): 既定経路 (FLE_IPP 未指定) の出力指標の判定。
#   python3 tools/flelift/boot/outmem_judge.py <dump dir> --pe <PE>
# 入力: <dump dir> の outmem_boot_plain_r<i>.bin (fle_boot.mjs の FLE_OUTMEM_DUMP で書いた線形メモリ全体)。
# 判定指標 = image_writable (PE の書込み可能セクションの連結) から NONDET の 9 バイトを 0 にして sha256 を取った値。
#   NONDET は 8 run の実測で run 間に差が出た位置 (.data 4 バイト + 1 ・.bss 3 バイト・VA)。出典は REPORT_APPENDIX_5177.md。
#   stack・heap (C の一時値) は image_writable の範囲外なので、この指標は見ない。
# 判定 (rc): 全 run で指標が一致し、かつマスク外の 1 バイト変更で指標が変わること (検出力) を満たせば 0。
import glob, hashlib, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from outmem_compare import pe_sections, IMG

# 既定経路の run 間非決定 (build 固定・8 run の和集合)。.data 0x13a5010〜13 (時刻風)・0x13e4d58 (カウンタ風)、
# .bss 0x15f26e8〜ea (カウンタ風)・0x16bcbf0 (カウンタ風)。
NONDET = [0x13a5010, 0x13a5011, 0x13a5012, 0x13a5013, 0x13e4d58, 0x15f26e8, 0x15f26e9, 0x15f26ea, 0x16bcbf0]


def indicator(data, secs, mask=()):
    h = hashlib.sha256()
    for name, va, vsz, w in secs:
        if not w:
            continue
        a = IMG + va
        b = bytearray(data[a:a + vsz])
        for x in mask:
            if a <= x < a + vsz:
                b[x - a] = 0
        h.update(bytes(b))
    return h.hexdigest()


def main():
    args = sys.argv[1:]
    ddir = args.pop(0)
    pe = os.environ.get("FL_WIN64_DIR", "") + "/extracted/block00031_PE.bin"
    if args[:1] == ["--pe"]:
        pe = args[1]
    secs = pe_sections(pe)
    dumps = sorted(glob.glob(os.path.join(ddir, "outmem_boot_plain_r*.bin")),
                   key=lambda p: int(re.search(r"_r(\d+)\.bin$", p).group(1)))
    if len(dumps) < 2:
        print("dump が 2 本未満", file=sys.stderr); sys.exit(2)
    vals = []
    for p in dumps:
        v = indicator(open(p, "rb").read(), secs, NONDET)
        vals.append(v)
        print(f"{os.path.basename(p)}: 判定指標 {v[:16]}")
    same = len(set(vals)) == 1
    print(f"判定指標: 全 {len(vals)} run で一致 = {same}")
    # 検出力: マスク外の 1 バイト (.data 内の固定位置) を変えると指標が変わること
    d = bytearray(open(dumps[0], "rb").read())
    off = IMG + [va for n, va, vsz, w in secs if n == ".data"][0] + 0x20
    d[off] ^= 0xFF
    sensitive = indicator(bytes(d), secs, NONDET) != vals[0]
    print(f"検出力: マスク外 1 バイト (0x{off:x}) の変更で指標が変わる = {sensitive}")
    ok = same and sensitive
    print("RESULT", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
