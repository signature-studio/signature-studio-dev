#!/usr/bin/env python3
"""cmp_text.py — GUI-9 (#186): shim のテキスト出力 (text_golden) と独立オラクル (ft_oracle = native FreeType) を比較する。
usage: cmp_text.py <actual.ppm> <actual.tsv> <oracle.ppm> <oracle.tsv> [--tamper]
  画素: 完全一致 (差 0)。metrics 表: 全セル完全一致。--tamper = 期待側を壊す (ネガティブコントロール; 一致したら呼出側が FAIL にする)。
exit 0 = 一致 / 1 = 不一致 / 2 = 入力不正 (空画像・前景画素が少なすぎる等、合格しようがない入力も 2)。"""
import sys

def ppm(path):
    d = open(path, "rb").read()
    parts = d.split(b"\n", 3)
    if parts[0] != b"P6":
        sys.exit(2)
    w, h = map(int, parts[1].split())
    return w, h, bytearray(parts[3])

def main():
    a_ppm, a_tsv, o_ppm, o_tsv = sys.argv[1:5]
    tamper = "--tamper" in sys.argv
    aw, ah, ap = ppm(a_ppm)
    ow, oh, op = ppm(o_ppm)
    ot = open(o_tsv).read().splitlines()
    at = open(a_tsv).read().splitlines()
    if tamper:
        op[(ow * 40 + 10) * 3] ^= 0x10   # 1 画素 (R) を壊す
        ot[7] = ot[7].replace("\t", "\t9", 1)   # metrics 1 行の高さ列を壊す
    if (aw, ah) != (ow, oh) or len(ap) != len(op) or len(ot) < 30:
        print("FAIL: size/rows mismatch"); sys.exit(2)
    bg = bytes((32, 32, 48))
    fgpx = sum(1 for i in range(0, len(op), 3) if op[i:i + 3] != bg)
    if fgpx < 800:
        print("FAIL: oracle scene has too few foreground pixels (%d)" % fgpx); sys.exit(2)
    diff = [i // 3 for i in range(0, len(ap), 3) if ap[i:i + 3] != op[i:i + 3]]
    mdiff = [(k, x, y) for k, (x, y) in enumerate(zip(at, ot)) if x != y] + ([("len", len(at), len(ot))] if len(at) != len(ot) else [])
    print("pixels: %d fg px in scene, %d differing; metrics: %d rows, %d differing" % (fgpx, len(diff), len(ot), len(mdiff)))
    for p in diff[:5]:
        print("  px (%d,%d) actual=%s oracle=%s" % (p % ow, p // ow, tuple(ap[p * 3:p * 3 + 3]), tuple(op[p * 3:p * 3 + 3])))
    for m in mdiff[:5]:
        print("  metrics row", m)
    sys.exit(0 if not diff and not mdiff else 1)

main()
