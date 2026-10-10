#!/usr/bin/env python3
"""wasm_dup.py — 実 wasm (既定: M11 boot closure 5.65MB / 8,936 関数) の関数群を K 倍に複製して巨大 wasm を合成する。

  複製コピーの call 先は元の関数 index のまま (= 常に有効)。型/import/memory/global/table/export は不変。
  K 個目以降は到達しない (export/elem 非参照) が、V8 は全関数を検証・コンパイル対象とするので
  compile 時間 / コードサイズ測定には「実コード分布を保った K 倍規模」として妥当。
  --pad-to BYTES : 末尾に custom section を足して正確にそのサイズにする (サイズ上限テスト用)
  --hint lazy|eager|bg  : compilationHints custom section を関数全数分挿入 (Code section の直前)
  --uniq : 末尾にランダム custom section (キャッシュ回避)
"""
import argparse, os, struct, sys

def rleb(b, p):
    r = 0; s = 0
    while True:
        c = b[p]; p += 1
        r |= (c & 0x7f) << s; s += 7
        if not c & 0x80: return r, p

def wleb(n):
    out = bytearray()
    while True:
        c = n & 0x7f; n >>= 7
        if n: out.append(c | 0x80)
        else: out.append(c); return bytes(out)

def custom(name, payload):
    nb = name.encode(); body = wleb(len(nb)) + nb + payload
    return b'\x00' + wleb(len(body)) + body

def parse(b):
    assert b[:4] == b'\0asm'
    p = 8; secs = []
    while p < len(b):
        sid = b[p]; p += 1
        sz, p = rleb(b, p)
        secs.append((sid, b[p:p+sz])); p += sz
    return secs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('-k', type=int, default=1)
    ap.add_argument('--pad-to', type=int, default=0)
    ap.add_argument('--hint', choices=['lazy', 'eager', 'bg', 'lazybase'], default=None)
    ap.add_argument('--uniq', action='store_true')
    ap.add_argument('--strip-exports', action='store_true', help='export section を 先頭 N 件に縮小しない (未実装; 常に原本)')
    a = ap.parse_args()
    src = open(a.src, 'rb').read()
    secs = parse(src)
    nfunc = 0
    out = open(a.dst, 'wb')
    out.write(src[:8])
    total = 8
    # 先に function count を得る
    for sid, pl in secs:
        if sid == 3: nfunc, _ = rleb(pl, 0)
    HINT = {'lazy': 0x01, 'eager': 0x02, 'bg': 0x00, 'lazybase': 0x03}
    for sid, pl in secs:
        if sid == 3:
            n, p = rleb(pl, 0); body = pl[p:]
            npl = wleb(n * a.k) + body * a.k
        elif sid == 10:
            n, p = rleb(pl, 0); body = pl[p:]
            if a.hint:
                h = custom('compilationHints', wleb(n * a.k) + bytes([HINT[a.hint]]) * (n * a.k))
                out.write(h); total += len(h)
            npl = wleb(n * a.k) + body * a.k
        else:
            npl = pl
        hdr = bytes([sid]) + wleb(len(npl))
        out.write(hdr); out.write(npl); total += len(hdr) + len(npl)
    if a.uniq:
        c = custom('uniq', os.urandom(16)); out.write(c); total += len(c)
    if a.pad_to:
        need = a.pad_to - total
        # custom section オーバヘッド: 1 + leb(size) + leb(namelen)+name
        for pad_payload in range(max(need - 16, 0), need + 1):
            nb = b'pad'; body_len = len(wleb(len(nb))) + len(nb) + pad_payload
            tot = 1 + len(wleb(body_len)) + body_len
            if tot == need: break
        else:
            sys.exit('cannot pad exactly')
        hdr = b'\x00' + wleb(body_len) + wleb(3) + b'pad'
        out.write(hdr)
        chunk = b'\0' * (1 << 24); rem = pad_payload
        while rem > 0:
            w = min(rem, len(chunk)); out.write(chunk[:w]); rem -= w
        total += tot
    out.close()
    print(f'{a.dst}: {os.path.getsize(a.dst)} bytes, functions={nfunc * a.k}')

if __name__ == '__main__': main()
