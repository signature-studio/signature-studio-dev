#!/usr/bin/env python3
"""m11_wasmnames.py: wasm の export section / name section から {関数 index: 名前} を取る (wabt の wasm-objdump が無い環境用, #513). export section 優先: build が --export-all のため全関数名が export にある.
 使い方: python3 m11_wasmnames.py [wasm] [idx ...]   → 'idx name' を印字 (idx 省略で全件)
 import: from m11_wasmnames import func_names"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _leb(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1
        r |= (c & 0x7f) << s; s += 7
        if not c & 0x80:
            return r, i


def func_names(path=None):
    """Export section (--export-all で関数名が export される) と name section (あれば) から {関数 index: 名前}."""
    b = open(path or os.path.join(HERE, 'work', 'm11_boot.cjs.wasm'), 'rb').read()
    i = 8
    out = {}
    while i < len(b):
        sid = b[i]; i += 1
        sz, i = _leb(b, i)
        end = i + sz
        if sid == 7:
            cnt, k = _leb(b, i)
            for _ in range(cnt):
                ln, k = _leb(b, k)
                name = b[k:k + ln].decode('utf8', 'replace'); k += ln
                kind = b[k]; k += 1
                idx, k = _leb(b, k)
                if kind == 0:
                    out.setdefault(idx, name)
        elif sid == 0:
            n, j = _leb(b, i)
            if b[j:j + n] == b'name':
                j += n
                while j < end:
                    sub = b[j]; j += 1
                    ssz, j = _leb(b, j)
                    if sub == 1:
                        cnt, k = _leb(b, j)
                        for _ in range(cnt):
                            idx, k = _leb(b, k)
                            ln, k = _leb(b, k)
                            out[idx] = b[k:k + ln].decode('utf8', 'replace'); k += ln
                    j += ssz
        i = end
    return out


if __name__ == '__main__':
    args = sys.argv[1:]
    path = args.pop(0) if args and not args[0].isdigit() else None
    n = func_names(path)
    for a in (args or sorted(n)):
        print(a, n.get(int(a), '?'))
