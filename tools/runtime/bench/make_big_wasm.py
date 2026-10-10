#!/usr/bin/env python3
"""実 lifted wasm (M11) の関数本体を K 倍に複製して巨大 wasm を合成する (FLEngine 22MB × lift 膨張のスケール試験用)。
複製関数は元の関数 index だけを call するので妥当 (到達はしないが validate/compile 対象)。
usage: make_big_wasm.py in.wasm out.wasm K"""
import sys
def leb_u(b, o):
    r = s = 0
    while True:
        x = b[o]; o += 1; r |= (x & 0x7f) << s; s += 7
        if not x & 0x80: return r, o
def enc_u(v):
    out = bytearray()
    while True:
        x = v & 0x7f; v >>= 7
        if v: out.append(x | 0x80)
        else: out.append(x); return bytes(out)
src, dst, K = sys.argv[1], sys.argv[2], int(sys.argv[3])
b = open(src, 'rb').read(); o = 8; secs = []
while o < len(b):
    sid = b[o]; o += 1; size, o2 = leb_u(b, o); secs.append((sid, b[o2:o2 + size])); o = o2 + size
out = bytearray(b[:8])
for sid, body in secs:
    if sid == 3:   # function section: 型 index 列を K 回複製
        n, p = leb_u(body, 0); idx = body[p:]
        body = enc_u(n * (K + 1)) + idx * (K + 1)
    elif sid == 10:  # code section: 関数本体を K 回複製
        n, p = leb_u(body, 0); bodies = body[p:]
        body = enc_u(n * (K + 1)) + bodies * (K + 1)
    out += bytes([sid]) + enc_u(len(body)) + body
open(dst, 'wb').write(out)
print(f"{dst}: {len(out)/1048576:.1f} MiB (K={K})")
