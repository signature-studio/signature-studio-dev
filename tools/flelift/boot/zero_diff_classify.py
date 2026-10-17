#!/usr/bin/env python3
# zero_diff_classify.py — FLE-51 (#6054): 残骸除去 (zero 変種) と既定 (base) の出力メモリ差を分類する。
#   python3 tools/flelift/boot/zero_diff_classify.py <PE> <dump dir> [label_base] [label_zero]
# 入力: <dump dir> の outmem_<label>_r<i>.bin (fle_boot.mjs の FLE_OUTMEM_DUMP)。label 既定 rsz_base / rsz_zero・i は 1..3。
# 分類 (書込み可能セクション内, 4 バイト単位):
#   unstable : base または zero の run 間で値が揺れる位置 (非決定。マスクの候補)
#   placement: base と zero の両方が heap 範囲 (HEAP_LO〜HEAP_HI) のポインタ (配置のずれ。内容差ではない)。
#              スタック範囲のうち heap 範囲外の部分 (HEAP_LO 未満) の差はここに入らず content に数える。
#   content  : それ以外で base と zero が違う位置 (内容の差。残骸の影響の候補)
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from outmem_compare import pe_sections, IMG

HEAP_LO, HEAP_HI = 0x11D00000, 0x13400000


def main():
    pe, ddir = sys.argv[1], sys.argv[2]
    lb = sys.argv[3] if len(sys.argv) > 3 else "rsz_base"
    lz = sys.argv[4] if len(sys.argv) > 4 else "rsz_zero"
    secs = [s for s in pe_sections(pe) if s[3]]
    rd = lambda lab, i: open(os.path.join(ddir, f"outmem_{lab}_r{i}.bin"), "rb").read()
    B = [rd(lb, i) for i in (1, 2, 3)]
    Z = [rd(lz, i) for i in (1, 2, 3)]
    unstable = placement = content = 0
    content_rows = []
    for n, va, vsz, w in secs:
        a = IMG + va
        for d in range(a, a + vsz - 3, 4):
            bv = [int.from_bytes(x[d:d + 4], "little") for x in B]
            zv = [int.from_bytes(x[d:d + 4], "little") for x in Z]
            if len(set(bv)) > 1 or len(set(zv)) > 1:
                unstable += 1
                continue
            if bv[0] == zv[0]:
                continue
            if all(HEAP_LO <= v < HEAP_HI for v in (bv[0], zv[0])):
                placement += 1
                continue
            content += 1
            if len(content_rows) < 30:
                content_rows.append((n, hex(d - IMG), hex(bv[0]), hex(zv[0])))
    print(f"unstable (run 間で揺れる 4B 語): {unstable}")
    print(f"placement (両方ヒープ/スタックのポインタ): {placement}")
    print(f"content (それ以外の差): {content}")
    for r in content_rows:
        print("  ", r)


if __name__ == "__main__":
    main()
