#!/usr/bin/env python3
"""gen_golden_text8.py — text_wasm_app.c (GUI_NO_FT=1 = 内蔵 8x8) の最終フレームの期待画像 (独立オラクル)。

shim の C 実装 (src/gui_gdi.c の TextOut / DrawText / 8x8 経路) は読まず、Windows GDI の公開仕様
(TA_* による基点配置・OPAQUE の背景矩形・DT_* による配置と行分割) と 8x8 フォントの寸法
(advance 8・高さ 8・ascent 7) だけから期待ピクセルを計算する。共有するのは src/gui_font8x8.h の
公開ドメインのビットマップだけ (gen_golden.py と同じ)。シーンの値は tools/gui/test/text_scene.inc から手で写した。
usage: gen_golden_text8.py -   (標準出力へ RGB のバイト列 320x120x3 を書く)
"""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 320, 120
TA_RIGHT, TA_CENTER, TA_BASELINE, TA_BOTTOM = 2, 6, 24, 8
DT_CENTER, DT_RIGHT, DT_VCENTER, DT_BOTTOM, DT_SINGLELINE = 0x1, 0x2, 0x4, 0x8, 0x20
CELL, ASCENT = 8, 7
BG = (32, 32, 48)

def load_font():
    s = open(os.path.join(HERE, "..", "src", "gui_font8x8.h")).read()
    rows = re.findall(r"\{((?:\s*0x[0-9A-Fa-f]{2},?){8})\}", s)
    assert len(rows) == 128
    return [[int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", r)] for r in rows]

FONT = load_font()
img = [[BG] * W for _ in range(H)]

def fill(l, t, r, b, c):
    for y in range(max(t, 0), min(b, H)):
        for x in range(max(l, 0), min(r, W)):
            img[y][x] = c

def glyphs(x, y, s, c):
    for i, ch in enumerate(s):
        g = FONT[ord(ch) if ord(ch) < 128 else ord("?")]
        for row in range(8):
            for col in range(8):
                if (g[row] >> col) & 1:
                    px, py = x + i * CELL + col, y + row
                    if 0 <= px < W and 0 <= py < H:
                        img[py][px] = c

def text_out(x, y, s, fg, opaque_bg=None, align=0):
    w = CELL * len(s)
    if (align & 6) == TA_CENTER: x -= w // 2
    elif (align & 6) == TA_RIGHT: x -= w
    if (align & 24) == TA_BASELINE: y -= ASCENT
    elif (align & 24) == TA_BOTTOM: y -= CELL
    if opaque_bg is not None:
        fill(x, y, x + w, y + CELL, opaque_bg)
    glyphs(x, y, s, fg)

def draw_text(s, rc, fmt, fg):
    l, t, r, b = rc
    lines = [s] if fmt & DT_SINGLELINE else s.split("\n")
    th = CELL * len(lines)
    y0 = t
    if fmt & DT_VCENTER: y0 = t + ((b - t) - th) // 2
    elif fmt & DT_BOTTOM: y0 = b - th
    for i, ln in enumerate(lines):
        lw = CELL * len(ln)
        x0 = l
        if fmt & DT_CENTER: x0 = l + ((r - l) - lw) // 2
        elif fmt & DT_RIGHT: x0 = r - lw
        glyphs(x0, y0 + CELL * i, ln, fg)

fill(0, 0, W, H, BG)
text_out(4, 4, "Hello, World! gjpqy 0123", (255, 255, 255))
text_out(4, 24, "Barlow OPAQUE", (255, 255, 0), opaque_bg=(200, 40, 40))
draw_text("Centered", (170, 4, 310, 44), DT_CENTER | DT_VCENTER | DT_SINGLELINE, (0, 255, 128))
draw_text("Line one\nsecond line", (170, 50, 310, 100), 0, (255, 160, 0))
text_out(120, 70, "baseline", (255, 255, 255), align=TA_BASELINE | TA_RIGHT)
text_out(80, 80, "TA_CENTER", (180, 220, 255), align=TA_CENTER)

if len(sys.argv) != 2 or sys.argv[1] != "-":
    sys.exit("usage: gen_golden_text8.py -")
sys.stdout.buffer.write(bytes(v for row in img for p in row for v in p))
