#!/usr/bin/env python3
"""gen_golden.py — gui_app の最終フレームの期待画像 (独立オラクル)。

shim の C/JS 実装とは無関係に、アプリ (test/gui_app.c render()) と PROTOCOL.md の描画規約だけから
期待ピクセルを計算する (フォントは src/gui_font8x8.h の公開ドメインデータを共有)。
シナリオ最終状態: cnt=3, tick=3(timer-done), keys="Ab", ドラッグ線 (30,150)->(150,180)。
出力: golden/final.ppm, golden/final.png
"""
import os, re, struct, sys, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 320, 200
CNT, TICK, KEYS, LINE = 3, 3, "Ab", ((30, 150), (150, 180))

def load_font():
    s = open(os.path.join(HERE, "..", "src", "gui_font8x8.h")).read()
    rows = re.findall(r"\{((?:\s*0x[0-9A-Fa-f]{2},?){8})\}", s)
    assert len(rows) == 128
    return [[int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", r)] for r in rows]

FONT = load_font()
img = [[(0, 0, 0)] * W for _ in range(H)]

def fill(l, t, r, b, c):
    for y in range(max(t, 0), min(b, H)):
        for x in range(max(l, 0), min(r, W)):
            img[y][x] = c

def text(x, y, s, c):
    for i, ch in enumerate(s):
        g = FONT[ord(ch) if ord(ch) < 128 else ord("?")]
        for row in range(8):
            for col in range(8):
                if (g[row] >> col) & 1:
                    px, py = x + i * 8 + col, y + row
                    if 0 <= px < W and 0 <= py < H:
                        img[py][px] = c

def line(x0, y0, x1, y1, c):
    adx, ady = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = adx - ady
    while True:
        if x0 == x1 and y0 == y1:
            break
        if 0 <= x0 < W and 0 <= y0 < H:
            img[y0][x0] = c
        e2 = 2 * err
        if e2 > -ady:
            err -= ady; x0 += sx
        if e2 < adx:
            err += adx; y0 += sy

fill(0, 0, W, H, (32, 32, 48))
for y in range(10, 26):
    for x in range(0, 128):
        img[y][x] = (x * 2, 255 - x * 2, 128)
# Rectangle(10,40,110,90): pen yellow, brush (0,64,128)
fill(11, 41, 109, 89, (0, 64, 128))
fill(10, 40, 110, 41, (255, 255, 0)); fill(10, 89, 110, 90, (255, 255, 0))
fill(10, 40, 11, 90, (255, 255, 0)); fill(109, 40, 110, 90, (255, 255, 0))
fill(120, 40, 220, 90, ((CNT * 60) & 255, 128, 0))
fill(230, 40, 250, 60, (0, 200, 0) if TICK >= 3 else (60, 60, 60))
text(12, 100, "Count: %d" % CNT, (255, 255, 255))
text(12, 120, "Key: " + KEYS, (255, 255, 255))
line(LINE[0][0], LINE[0][1], LINE[1][0], LINE[1][1], (255, 255, 255))
for y in range(32):
    for x in range(32):
        i = (y >> 2) * 8 + (x >> 2)
        img[100 + y][260 + x] = (255, 128, 0) if ((i & 1) ^ ((i >> 3) & 1)) else (0, 128, 255)

with open(os.path.join(HERE, "final.ppm"), "wb") as f:
    f.write(b"P6\n%d %d\n255\n" % (W, H))
    for row in img:
        f.write(bytes(v for p in row for v in p))
def png(path):
    raw = b"".join(b"\x00" + bytes(v for p in row for v in p) for row in img)
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
png(os.path.join(HERE, "final.png"))
print("golden written: %dx%d" % (W, H))
