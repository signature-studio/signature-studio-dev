#!/usr/bin/env python3
"""#5164: name section 付きの lift-8 (on/off) から code index → 関数名 (VA) を引き、差分 71 関数の VA 対応を取る。

  python3 scripts/kh5164_name_map.py

emcc の `-g2` は name section を出す (`-sEMIT_NAME_SECTION` は内部設定で指定できない)。
同じ build を name section 無し (既定の `-O1`) でも行い、code 本体が一致することを確かめる。
出力は license/work/m5164_* (gitignore)。関数名 `kh_<VA>` / `function_<VA>` から VA を引く。
"""
import json, os, re, sys
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
LIC = os.path.dirname(HERE)
sys.path.insert(0, LIC)
os.chdir(LIC)
import lic_build as L

LIFT8 = ['180ef7fc0', '18004c780', '180045130', '1800b4ac0', '1800b4ae0', '180054bd0', '1800524e0', '1800b4b10']


def leb(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1
        r |= (c & 0x7f) << s; s += 7
        if not c & 0x80:
            return r, i


def parse(path):
    """(bodies: func_index → (code_index, name, body), name section の有無)"""
    b = open(path, 'rb').read()
    assert b[:4] == b'\0asm'
    i, nimp, bodies, names = 8, 0, [], {}
    while i < len(b):
        sid = b[i]; i += 1
        size, i = leb(b, i)
        end = i + size
        if sid == 2:
            cnt, j = leb(b, i)
            for _ in range(cnt):
                for _k in range(2):
                    n, j = leb(b, j); j += n
                k = b[j]; j += 1
                if k == 0:
                    nimp += 1; _, j = leb(b, j)
                elif k == 1:
                    j += 1; fl, j = leb(b, j); _, j = leb(b, j)
                    if fl & 1: _, j = leb(b, j)
                elif k == 2:
                    fl, j = leb(b, j); _, j = leb(b, j)
                    if fl & 1: _, j = leb(b, j)
                else:
                    j += 1; _, j = leb(b, j)
        elif sid == 10:
            cnt, j = leb(b, i)
            for _ in range(cnt):
                n, j = leb(b, j); bodies.append(bytes(b[j:j + n])); j += n
        elif sid == 0:
            n, j = leb(b, i)
            if b[j:j + n] == b'name':
                j += n
                while j < end:
                    sub = b[j]; j += 1
                    sl, j = leb(b, j)
                    se = j + sl
                    if sub == 1:
                        cnt, k = leb(b, j)
                        for _ in range(cnt):
                            idx, k = leb(b, k)
                            n2, k = leb(b, k)
                            names[idx] = b[k:k + n2].decode('utf8', 'replace'); k += n2
                    j = se
        i = end
    return {ci + nimp: (ci, names.get(ci + nimp), body) for ci, body in enumerate(bodies)}, bool(names), len(b)


def va_of(name):
    m = re.match(r'^(?:kh|function)_([0-9a-f]+)$', name or '')
    return m.group(1) if m else '-'


def main():
    mod = L.CFG['modules']['F']
    vas = {int(v, 16) for v in LIFT8}
    kw = dict(apply_stub=True, module='F', abi=mod.get('abi'), shims=dict(mod.get('shims') or {}),
              raw_va=mod.get('raw_va', False), volatile_ret=mod.get('volatile_ret', False),
              emcc_opt=mod.get('emcc_opt', '-O1'))
    stats, wasm = {}, {}
    for mode in ('off', 'on'):
        extra = dict(rdata_str=(mode == 'on'), rdata_raw_allow=(mod.get('rdata_raw_allow', '') if mode == 'on' else ''))
        for named in (True, False):
            tag = 'm5164_%s_%s' % (mode, 'named' if named else 'plain')
            opt = kw['emcc_opt'] + (' -g2' if named else '')
            st = L.build(vas, os.path.join(LIC, 'work', tag), tag, **dict(kw, emcc_opt=opt), **extra)
            stats[tag] = {k: st[k] for k in ('wasm_bytes', 'wasm_sha256', 'globals')}
            wasm[tag] = os.path.join(LIC, 'work', tag, 'mod.wasm')
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    for mode in ('off', 'on'):
        a, na, _ = parse(wasm['m5164_%s_named' % mode])
        b, nb, _ = parse(wasm['m5164_%s_plain' % mode])
        assert na and not nb, 'name section の有無が想定と違う'
        same = all(a[k][2] == b[k][2] for k in b)
        print('%s: code 本体は name 無し build と一致: %s (関数 %d)' % (mode, same, len(a)))
    off, _, _ = parse(wasm['m5164_off_named'])
    on, _, _ = parse(wasm['m5164_on_named'])
    rows = []
    for fi in sorted(off):
        ci, nm, ba = off[fi]; _, _, bb = on[fi]
        if ba != bb:
            nd = sum(1 for x, y in zip(ba, bb) if x != y) + abs(len(ba) - len(bb))
            rows.append((ci, nm, va_of(nm), len(ba), nd))
    print('差分関数 %d・差分 %d B (off 本体 %d B)' % (len(rows), sum(r[4] for r in rows), sum(r[3] for r in rows)))
    print('code_idx\tname\tVA\toff_B\tdiff_B')
    for r in rows:
        print('%d\t%s\t%s\t%d\t%d' % (r[0], r[1], r[2], r[3], r[4]))
    agg = defaultdict(lambda: [0, 0])
    for r in rows:
        k = 'VA あり (kh_/function_)' if r[2] != '-' else 'VA なし (runtime・libc 系)'
        agg[k][0] += 1; agg[k][1] += r[4]
    for k, (n, d) in agg.items():
        print('%s: %d 関数 / %d B' % (k, n, d))


if __name__ == '__main__':
    main()
