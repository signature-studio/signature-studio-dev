#!/usr/bin/env python3
"""wasm_imports.py — wasm の import セクションから未解決 shim/GUI import を数える (GUI-16 / #741).

wasm-objdump (wabt) に依存しない。runner に無い道具を `|| true` で空振りさせないため、
wasm バイナリを直接読む (MVP 以降の import 形式のみ)。

usage: wasm_imports.py <file.wasm>          -> 一致 import 数を stdout へ (rc 0)
       wasm_imports.py --selftest           -> 合成 wasm で数え方を検証 (rc 0 = OK, 不一致は rc 1)

一致条件 (sigprobe.sh の旧 grep と同じ): module == "env" かつ field 名が "gui_" で始まる / 大文字で始まる。
"""
import re
import struct
import sys

PAT = re.compile(r"^(gui_|[A-Z])")


def _leb(b, p):
    r = s = 0
    while True:
        x = b[p]
        p += 1
        r |= (x & 0x7F) << s
        s += 7
        if not x & 0x80:
            return r, p


def _name(b, p):
    n, p = _leb(b, p)
    return b[p:p + n].decode("utf-8"), p + n


def _limits(b, p):
    flag = b[p]
    p += 1
    _, p = _leb(b, p)
    if flag & 1:
        _, p = _leb(b, p)
    return p


def imports(data):
    if data[:4] != b"\0asm":
        raise ValueError("not a wasm binary")
    p = 8
    out = []
    while p < len(data):
        sid = data[p]
        size, q = _leb(data, p + 1)
        end = q + size
        if sid == 2:
            n, r = _leb(data, q)
            for _ in range(n):
                mod, r = _name(data, r)
                fld, r = _name(data, r)
                kind = data[r]
                r += 1
                if kind == 0:
                    _, r = _leb(data, r)
                elif kind == 1:
                    r = _limits(data, r + 1)
                elif kind == 2:
                    r = _limits(data, r)
                elif kind == 3:
                    r += 2
                elif kind == 4:
                    r += 1
                    _, r = _leb(data, r)
                else:
                    raise ValueError("unknown import kind %d" % kind)
                out.append((mod, fld))
        p = end
    return out


def count(data):
    return sum(1 for mod, fld in imports(data) if mod == "env" and PAT.match(fld))


def _sec(sid, body):
    return bytes([sid]) + _uleb(len(body)) + body


def _uleb(v):
    o = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        o.append(b | (0x80 if v else 0))
        if not v:
            return bytes(o)


def _str(s):
    e = s.encode()
    return _uleb(len(e)) + e


def _synth(entries):
    body = _uleb(len(entries))
    for mod, fld, kind in entries:
        body += _str(mod) + _str(fld) + bytes([kind])
        if kind == 0:
            body += _uleb(0)
        elif kind == 2:
            body += b"\x00" + _uleb(1)
    return b"\0asm" + struct.pack("<I", 1) + _sec(2, body)


def selftest():
    # 未解決の shim import 2 件 (gui_ 接頭辞 / 大文字 API) が数えられ、
    # 他 module・小文字 API・memory は数えないこと。
    w = _synth([
        ("env", "gui_reach_hit", 0),
        ("env", "CreateWindowExW", 0),
        ("env", "memory", 2),
        ("env", "malloc", 0),
        ("wasi", "CreateWindowExW", 0),
    ])
    got = count(w)
    if got != 2:
        print("[wasm_imports] selftest FAIL: expected 2 got %d" % got)
        return 1
    print("[wasm_imports] selftest OK (negative: 2 unresolved imports detected)")
    return 0


def main(argv):
    if len(argv) == 2 and argv[1] == "--selftest":
        return selftest()
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    with open(argv[1], "rb") as f:
        print(count(f.read()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
