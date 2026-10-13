#!/usr/bin/env python3
"""gen_golden_ncpe.py — GUI-7 (#183) テスト PE (test/gui_nc_app.c) の期待画像 (独立オラクル; shim と共有するものなし)。
usage: gen_golden_ncpe.py <actual.ppm> [--tamper]   exit 0 = 一致 (差 0) / 1 = 不一致。--tamper は期待値を 1 画素壊す (ネガコン)。
窓 (desktop 200x140, 作成順 popup -> main -> tooltip で z は popup < main < tooltip):
  popup  : (90,50) 80x50 青 (30,60,200)
  main   : (10,10) 130x113 WS_POPUP|WS_CAPTION|WS_THICKFRAME。枠 5px (0x646464)・caption 23px (COLORREF 0xD1B499)・client (15,38) 120x80 (50,50,60)
  tooltip: (70,40) 60x14 薄黄 (255,255,225), TOPMOST (最前面)
NC の色と寸法は PROTOCOL.md (非クライアント領域) の規約。
"""
import re, sys
W, H = 200, 140
FRAME, CAP, CLIENT, POP, TIP = (100, 100, 100), (153, 180, 209), (50, 50, 60), (30, 60, 200), (255, 255, 225)
img = [[(0, 0, 0)] * W for _ in range(H)]
def fill(l, t, r, b, c):
    for y in range(max(t, 0), min(b, H)):
        for x in range(max(l, 0), min(r, W)): img[y][x] = c
fill(90, 50, 170, 100, POP)                                  # popup (main の下; main の右にはみ出た部分だけ見える)
fill(10, 10, 140, 15, FRAME); fill(10, 118, 140, 123, FRAME)  # main 枠 上・下
fill(10, 15, 15, 118, FRAME); fill(135, 15, 140, 118, FRAME)  # main 枠 左・右
fill(15, 15, 135, 38, CAP)                                    # caption 帯
fill(15, 38, 135, 118, CLIENT)                                # client (WM_PAINT)
fill(70, 40, 130, 54, TIP)                                    # tooltip (TOPMOST, 最前面)
def read_ppm(p):
    b = open(p, "rb").read()
    m = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\s", b)
    return int(m[1]), int(m[2]), b[m.end():]
w, h, d = read_ppm(sys.argv[1])
if (w, h) != (W, H): print("size mismatch", w, h); sys.exit(1)
exp = bytearray(v for row in img for p in row for v in p)
if "--tamper" in sys.argv: exp[(70 * W + 20) * 3] ^= 1
diff = [i // 3 for i in range(len(exp)) if exp[i] != d[i]]
npx = len(set(diff))
if npx:
    i = diff[0]; print("MISMATCH %d px of %d (first at %d,%d)" % (npx, W * H, i % W, i // W)); sys.exit(1)
print("nc pe golden: EXACT MATCH (%d px, 0 diff)" % (W * H))
