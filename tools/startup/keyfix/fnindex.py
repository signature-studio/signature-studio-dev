#!/usr/bin/env python3
"""fnindex.py — .pdata から関数境界索引 + VA→関数 マップ (FLEngine)"""
import struct, bisect
import feparse as F

_data = None


def funcs():
    """[(start_va, end_va)] sorted; .pdata RUNTIME_FUNCTION (begin,end,unwind)"""
    global _data
    if _data is not None:
        return _data
    F.load()
    sec = [s for s in F.sections() if s['name'] == '.pdata'][0]
    raw = F._RAW[sec['roff']:sec['roff'] + sec['rsize']]
    base = F.image_base() + sec['va']
    out = []
    for i in range(0, len(raw) - 11, 12):
        b, e, u = struct.unpack_from('<III', raw, i)
        if b == 0 and e == 0:
            break
        out.append((F.image_base() + b, F.image_base() + e))
    out.sort()
    _data = out
    return out


_starts = None


def _starts_list():
    global _starts
    if _starts is None:
        _starts = [f[0] for f in funcs()]
    return _starts


def func_of(va):
    """va を含む関数 (start, end) or None"""
    ss = _starts_list()
    i = bisect.bisect_right(ss, va) - 1
    if i < 0:
        return None
    s, e = funcs()[i]
    if s <= va < e:
        return (s, e)
    return None


if __name__ == '__main__':
    fs = funcs()
    print('functions:', len(fs))
    f = func_of(0x651330)
    print('func_of 0x651330:', hex(f[0]), hex(f[1]))
