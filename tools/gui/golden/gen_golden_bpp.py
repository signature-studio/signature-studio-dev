#!/usr/bin/env python3
"""gen_golden_bpp.py — GUI-5 (#181) bpp シーン (test/bpp_golden.c) の期待画像と比較する独立オラクル。

shim の C 実装とは無関係に、シーンの描画仕様 (各 bpp のビット配置・色テーブル・nearest 拡縮・ROP・AlphaBlend 式) だけから期待ピクセルを計算する。
共有するのはシーンのパターン式のみ。usage: gen_golden_bpp.py <actual.ppm> [--tamper] (--tamper = 期待値の 1 画素を壊す: ネガティブコントロール)
一致なら exit 0 / 不一致なら exit 1 (不一致画素数と先頭 5 件を表示)。
"""
import sys
W, H = 160, 100
img = [[(32, 32, 48)] * W for _ in range(H)]

def put(x, y, c):
    if 0 <= x < W and 0 <= y < H:
        img[y][x] = c

def stretch(src, sw, sh, dx, dy, dw, dh):          # src[y][x] (top-down) -> nearest 拡縮
    for y in range(dh):
        for x in range(dw):
            put(dx + x, dy + y, src[y * sh // dh][x * sw // dw])

# 1. 24bpp 8x6 -> 16x12 at (4,4)  (px = (B,G,R) の式; 表示色は (R,G,B))
s1 = [[((x * 13 + y * 7) & 255, (x * 5 + y * 29) & 255, (x * 37 + y * 11) & 255) for x in range(8)] for y in range(6)]
stretch(s1, 8, 6, 4, 4, 16, 12)
# 2. 8bpp 8x6 palette(8) -> 24x18 at (40,4)
pal8 = [(i * 32, 255 - i * 32, (i * 77) & 255) for i in range(8)]
s2 = [[pal8[(x + 2 * y) % 8] for x in range(8)] for y in range(6)]
stretch(s2, 8, 6, 40, 4, 24, 18)
# 3. 4bpp 8x4 -> 16x8 at (4,40)
pal4g = [(i * 17, i * 17, 255 - i * 17) for i in range(16)]
s3 = [[pal4g[(x * 3 + y) % 16] for x in range(8)] for y in range(4)]
stretch(s3, 8, 4, 4, 40, 16, 8)
# 4. 1bpp 16x8 1:1 at (40,40)
pal1 = [(200, 40, 40), (40, 200, 40)]
s4 = [[pal1[((x >> 2) + (y >> 1)) & 1] for x in range(16)] for y in range(8)]
stretch(s4, 16, 8, 40, 40, 16, 8)
# 5. 24bpp section 16x8: 背景パターン + FillRect(4,2,12,6) 黄 + 対角線 (0,0)->(15,7) 黒 (終点除外) -> (80,4)
sec24 = [[((x * 16) & 255, (y * 32) & 255, 128) for x in range(16)] for y in range(8)]
for y in range(2, 6):
    for x in range(4, 12):
        sec24[y][x] = (255, 255, 0)
def line(x0, y0, x1, y1, c, buf):
    adx, ady = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = adx - ady
    while not (x0 == x1 and y0 == y1):
        buf[y0][x0] = c
        e2 = 2 * err
        if e2 > -ady: err -= ady; x0 += sx
        if e2 < adx: err += adx; y0 += sy
line(0, 0, 15, 7, (0, 0, 0), sec24)
stretch(sec24, 16, 8, 80, 4, 16, 8)
# 6. 8bpp section 16x8 palette(4): index (x+y)&3 ; FillRect(2,2,10,6)=赤に最近傍 / (10,2,14,6)=青に最近傍 -> (80,40)
pal4 = [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]
idx = [[(x + y) & 3 for x in range(16)] for y in range(8)]
for y in range(2, 6):
    for x in range(2, 10): idx[y][x] = 1
    for x in range(10, 14): idx[y][x] = 3
sec8 = [[pal4[idx[y][x]] for x in range(16)] for y in range(8)]
stretch(sec8, 16, 8, 80, 40, 16, 8)
# 7. mono 16x8: 行 y のバイト = (0xA5 << (y&3)) & 255, 0x3C >> (y&3); bit1 = bk 青, bit0 = text 赤 -> (4,70)
for y in range(8):
    b0, b1 = (0xA5 << (y & 3)) & 255, 0x3C >> (y & 3)
    for x in range(16):
        bit = ((b0 if x < 8 else b1) >> (7 - (x & 7))) & 1
        put(4 + x, 70 + y, (0, 0, 255) if bit else (255, 0, 0))
# 8. sec24 を 2x SRCINVERT -> (40,70) (dst ^= src, RGB のみ)
for y in range(16):
    for x in range(32):
        s = sec24[y * 8 // 16][x * 16 // 32]; d = img[70 + y][40 + x]
        put(40 + x, 70 + y, tuple(a ^ b for a, b in zip(d, s)))
# 9. sec8 を AlphaBlend 定数 sca=100 -> (80,70) 16x8 1:1。丸め: round(x/255) = (x+127)//255
for y in range(8):
    for x in range(16):
        s = sec8[y][x]; d = img[70 + y][80 + x]
        put(80 + x, 70 + y, tuple(min(255, (sc * 100 + 127) // 255 + (dc * 155 + 127) // 255) for sc, dc in zip(s, d)))

if "--tamper" in sys.argv:
    img[10][10] = tuple((v + 1) & 255 for v in img[10][10])
data = open(sys.argv[1], "rb").read()
hdr = b"P6\n%d %d\n255\n" % (W, H)
assert data.startswith(hdr), "bad ppm header"
px = data[len(hdr):]
bad = []
for y in range(H):
    for x in range(W):
        a = tuple(px[(y * W + x) * 3:(y * W + x) * 3 + 3])
        if a != img[y][x]:
            bad.append((x, y, img[y][x], a))
if bad:
    print("MISMATCH %d px of %d (expected vs actual): %s" % (len(bad), W * H, bad[:5]))
    sys.exit(1)
print("bpp golden: EXACT MATCH (%d px, 0 diff)" % (W * H))
