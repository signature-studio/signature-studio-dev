#!/usr/bin/env python3
"""#4547: lift-8 の on/off wasm の section 単位の差分 (kh656_window_measure.py の出力を読む)。

  python3 scripts/kh4547_section_diff.py work/m4670_lift8_off/mod.wasm work/m4670_lift8_on/mod.wasm

出力: section ごとの byte 数・global の値の差 (多重集合)・data の配置・code の差分関数。
code の関数は export 名 `function_<VA>` で VA を引く。export されていない関数は VA が引けず None。
"""
import sys
from collections import Counter


def leb(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1
        r |= (c & 0x7f) << s; s += 7
        if not c & 0x80:
            return r, i


def sleb(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1
        r |= (c & 0x7f) << s; s += 7
        if not c & 0x80:
            break
    if c & 0x40:
        r -= 1 << s
    return r, i


def name_of(b, i):
    n, i = leb(b, i)
    return b[i:i + n].decode('utf8', 'replace'), i + n


def sections(b):
    assert b[:4] == b'\0asm'
    i, out = 8, []
    while i < len(b):
        sid = b[i]; i += 1
        size, i = leb(b, i)
        out.append((sid, i, size))
        i += size
    return out


def parse(path):
    b = open(path, 'rb').read()
    secs = sections(b)
    info = {'bytes': len(b), 'size': {sid: size for sid, _, size in secs},
            'globals': [], 'code': [], 'func_export': {}, 'data': [], 'func_imports': 0}
    for sid, off, _ in secs:
        i = off
        if sid == 2:
            cnt, i = leb(b, i)
            for _ in range(cnt):
                _, i = name_of(b, i); _, i = name_of(b, i)
                k = b[i]; i += 1
                if k == 0:
                    info['func_imports'] += 1
                    _, i = leb(b, i)
                elif k == 1:
                    i += 1; flag = b[i]; i += 1
                    _, i = leb(b, i)
                    if flag & 1:
                        _, i = leb(b, i)
                elif k == 2:
                    flag = b[i]; i += 1
                    _, i = leb(b, i)
                    if flag & 1:
                        _, i = leb(b, i)
                else:
                    i += 1; _, i = leb(b, i)
        elif sid == 6:
            cnt, i = leb(b, i)
            for _ in range(cnt):
                st = i; i += 2
                while b[i] != 0x0b:
                    i = sleb(b, i + 1)[1] if b[i] in (0x41, 0x42) else (
                        i + 5 if b[i] == 0x43 else i + 9 if b[i] == 0x44 else leb(b, i + 1)[1])
                info['globals'].append(bytes(b[st:i + 1]))
                i += 1
        elif sid == 7:
            cnt, i = leb(b, i)
            for _ in range(cnt):
                n, i = name_of(b, i); k = b[i]; i += 1
                idx, i = leb(b, i)
                if k == 0 and n.startswith('function_'):
                    info['func_export'][idx] = n[len('function_'):]
        elif sid == 10:
            cnt, i = leb(b, i)
            for _ in range(cnt):
                sz, i = leb(b, i)
                info['code'].append(bytes(b[i:i + sz])); i += sz
        elif sid == 11:
            cnt, i = leb(b, i)
            for _ in range(cnt):
                flag, i = leb(b, i)
                assert flag == 0 and b[i] == 0x41
                base, j = sleb(b, i + 1)
                assert b[j] == 0x0b
                n, j = leb(b, j + 1)
                info['data'].append((base, bytes(b[j:j + n])))
                i = j + n
    return info


def global_value(g):
    init = g[2:]
    assert init[0] == 0x41
    return sleb(init, 1)[0]


def main():
    a, c = parse(sys.argv[1]), parse(sys.argv[2])
    print('total bytes off %d on %d (diff %+d)' % (a['bytes'], c['bytes'], c['bytes'] - a['bytes']))
    print('section size (id: off -> on, diff):')
    for sid in sorted(set(a['size']) | set(c['size'])):
        x, y = a['size'].get(sid, 0), c['size'].get(sid, 0)
        print('  %2d: %6d -> %6d (%+d)' % (sid, x, y, y - x))
    ga = [global_value(g) for g in a['globals']]
    gc = [global_value(g) for g in c['globals']]
    ca, cc = Counter(ga), Counter(gc)
    print('globals %d -> %d' % (len(ga), len(gc)))
    print('  off-only values:', sorted(hex(v) for v in ca - cc))
    print('  on-only values :', sorted(hex(v) for v in cc - ca))
    print('  unchanged values: %d' % sum((ca & cc).values()))
    print('data segments off:', [(hex(bs), len(d)) for bs, d in a['data']])
    print('data segments on :', [(hex(bs), len(d)) for bs, d in c['data']])
    print('code funcs %d -> %d' % (len(a['code']), len(c['code'])))
    rows = []
    for i, (x, y) in enumerate(zip(a['code'], c['code'])):
        if x != y:
            ndiff = sum(1 for k in range(len(x)) if x[k] != y[k])
            rows.append((a['func_export'].get(i + a['func_imports']), len(x), ndiff))
    print('code funcs differing %d, differing bytes %d' % (len(rows), sum(r[2] for r in rows)))
    print('  (VA or None, size, differing bytes):')
    for r in rows:
        print('   ', r)


if __name__ == '__main__':
    main()
