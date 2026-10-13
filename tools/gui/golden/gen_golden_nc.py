#!/usr/bin/env python3
"""gen_golden_nc.py — GUI-7 (#183) FL 非依存部の期待画像 (独立オラクル; shim と共有するものなし)。
usage: gen_golden_nc.py <actual.ppm> [--tamper]   exit 0 = 一致 (差 0) / 1 = 不一致。--tamper は期待値を 1 画素壊す (ネガコン)。
シーン (200x140 desktop, z 昇順 popup < main < tooltip: caption クリックで main が activate され popup の上へ。tooltip は TOPMOST で常に最前面):
  main  : window (10,10) 130x113, 枠 5px・caption 23px => client (15,38) 120x80。client は 1 回目 (50,50,60) 全面 -> 2 回目は無効 2 矩形だけ (200,40,40)
  popup : (90,50) 80x50 青, tooltip: (70,40) 60x14 薄黄。"""
import sys
W, H = 200, 140
img = [[(0, 0, 0)] * W for _ in range(H)]
def fill(l, t, r, b, c):
    for y in range(max(t, 0), min(b, H)):
        for x in range(max(l, 0), min(r, W)): img[y][x] = c
fill(90, 50, 170, 100, (30, 60, 200))                               # popup (NC クリックで main が activate されるまでは最前面; 以後は main の下)
# main
mx, my, mw, mh = 10, 10, 130, 113
fill(mx, my, mx + mw, my + 5, (100, 100, 100)); fill(mx, my + mh - 5, mx + mw, my + mh, (100, 100, 100))
fill(mx, my + 5, mx + 5, my + mh - 5, (100, 100, 100)); fill(mx + mw - 5, my + 5, mx + mw, my + mh - 5, (100, 100, 100))
fill(mx + 5, my + 5, mx + mw - 5, my + 28, (153, 180, 209))      # caption: COLORREF 0xD1B499
cx, cy = mx + 5, my + 28
fill(cx, cy, cx + 120, cy + 80, (50, 50, 60))
for (l, t, r, b) in ((10, 10, 40, 30), (70, 50, 110, 70)): fill(cx + l, cy + t, cx + r, cy + b, (200, 40, 40))
fill(70, 40, 130, 54, (255, 255, 225))                              # tooltip (最前面)
def read_ppm(p):
    b = open(p, "rb").read(); import re
    m = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\s", b); w, h = int(m[1]), int(m[2]); d = b[m.end():]
    return w, h, d
w, h, d = read_ppm(sys.argv[1])
if (w, h) != (W, H): print("size mismatch", w, h); sys.exit(1)
exp = bytearray(v for row in img for p in row for v in p)
if "--tamper" in sys.argv: exp[(70 * W + 20) * 3] ^= 1
diff = [i // 3 for i in range(len(exp)) if exp[i] != d[i]]
npx = len(set(diff))
if npx:
    i = diff[0]; print("MISMATCH %d px of %d (first at %d,%d)" % (npx, W * H, i % W, i // W)); sys.exit(1)
print("nc golden: EXACT MATCH (%d px, 0 diff)" % (W * H))
