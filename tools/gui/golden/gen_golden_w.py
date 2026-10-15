#!/usr/bin/env python3
"""gen_golden_w.py — W 版ゲスト (test/gui_app_w.c render()) の最終フレームの期待画像 (独立オラクル, #3508)。

shim の C 実装とは無関係に、ゲストの描画手順 (背景 FillRect → DIB への直接書込み → 矩形 FillRect → ExtTextOutW)
だけから期待ピクセルを計算する。フォントは src/gui_font8x8.h の公開ドメインデータだけを共有する。
DIB 直書きの式は ((x*3)<<16) の上位ビットが alpha 側へ溢れることを含めて、C の式をそのまま再現する (R は (3x)&0xFF)。

usage:
  gen_golden_w.py compare <actual.ppm>            期待画像と画素比較。差 0 で exit 0・差ありで exit 1
  gen_golden_w.py compare <actual.ppm> --tamper   ネガコン: 期待画像の 1 画素を改竄して比較 (exit 1 になること)
  gen_golden_w.py emit <out.ppm> [--tamper]       期待画像を P6 で書き出す (e2e.mjs の W 版モードが読む)
"""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 320, 200
TEXT, TX, TY = "Wide Text 42", 12, 100
BG = (24, 40, 56)            # RGB(24,40,56)
ORANGE = (230, 120, 20)      # RGB(230,120,20)
WHITE = (255, 255, 255)      # TextColor RGB(255,255,255)


def load_font():
    s = open(os.path.join(HERE, "..", "src", "gui_font8x8.h")).read()
    rows = re.findall(r"\{((?:\s*0x[0-9A-Fa-f]{2},?){8})\}", s)
    assert len(rows) == 128
    return [[int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", r)] for r in rows]


def oracle(tamper=False):
    font = load_font()
    img = [[BG] * W for _ in range(H)]
    for y in range(20, 60):
        for x in range(160):
            img[y][x] = ((3 * x) & 0xFF, (200 - y) & 0xFF, 64)
    for y in range(20, 70):
        for x in range(180, 300):
            img[y][x] = ORANGE
    for i, ch in enumerate(TEXT):
        for row in range(8):
            bits = font[ord(ch)][row]
            for col in range(8):
                if (bits >> col) & 1:
                    img[TY + row][TX + i * 8 + col] = WHITE
    if tamper:
        img[1][1] = (img[1][1][0] ^ 1, img[1][1][1], img[1][1][2])
    return img


def read_ppm(path):
    data = open(path, "rb").read()
    m = re.match(rb"P6\n(\d+) (\d+)\n255\n", data)
    assert m, "P6 ではない"
    w, h = int(m.group(1)), int(m.group(2))
    px = data[m.end():]
    assert len(px) == w * h * 3, "画素数が一致しない"
    return w, h, [[tuple(px[(y * w + x) * 3:(y * w + x) * 3 + 3]) for x in range(w)] for y in range(h)]


def write_ppm(path, img):
    with open(path, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (W, H))
        f.write(bytes(c for row in img for px in row for c in px))


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "emit":
        tamper = "--tamper" in sys.argv[3:]
        write_ppm(sys.argv[2], oracle(tamper))
        print("[golden_w] wrote %s%s" % (sys.argv[2], " [tamper]" if tamper else ""))
        return 0
    if len(sys.argv) < 3 or sys.argv[1] != "compare":
        print(__doc__); return 2
    w, h, act = read_ppm(sys.argv[2])
    tamper = "--tamper" in sys.argv[3:]
    exp = oracle(tamper)
    if (w, h) != (W, H):
        print("[golden_w] size mismatch %dx%d" % (w, h)); return 1
    diff = sum(1 for y in range(H) for x in range(W) if tuple(act[y][x]) != tuple(exp[y][x]))
    total = W * H
    if diff == 0:
        print("[golden_w] EXACT MATCH (0 differing pixels of %d)%s" % (total, " [tamper]" if tamper else ""))
        return 0
    print("[golden_w] MISMATCH (%d differing pixels of %d)%s" % (diff, total, " [tamper]" if tamper else ""))
    return 1


if __name__ == "__main__":
    sys.exit(main())
