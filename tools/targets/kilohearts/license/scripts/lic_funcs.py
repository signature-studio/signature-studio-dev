#!/usr/bin/env python3
"""関数単位の詳細: 文字列参照 / 直接 call / IAT call / caller / callee の文字列 (1段)。

usage:
  lic_funcs.py <pe> <strings.json> <xrefs.pkl> <callgraph.pkl> <VA...> [--depth N] [--callers]
  lic_funcs.py cluster <pe> <strings.json> <xrefs.pkl> <callgraph.pkl> <VA> <radius_pages>  # 前後の関数を一覧
"""
import sys, json, pickle, collections
import pefile

pe = None
data = None
base = None
strings = None
xrefs = None
cg = None
res = None


def load(pep, strp, xrp, cgp):
    global pe, data, base, strings, xrefs, cg, res
    pe = pefile.PE(pep, fast_load=True)
    data = open(pep, 'rb').read()
    base = pe.OPTIONAL_HEADER.ImageBase
    strings = {int(k, 16): v for k, v in json.load(open(strp)).items()}
    xrefs = pickle.load(open(xrp, 'rb'))
    cg = pickle.load(open(cgp, 'rb'))
    res = cg['res']


def fn_strings(fnva):
    """関数が rip 相対で参照する .rdata/.data 文字列"""
    out = []
    for tgt, refs in xrefs['rip'].items():
        va = tgt + base
        if va not in strings:
            continue
        for insn, fn in refs:
            if fn == fnva:
                out.append((insn, va, strings[va]))
    return sorted(out)


def fn_iat(fnva):
    out = []
    for tgt, refs in xrefs['iat'].items():
        for insn, fn in refs:
            if fn == fnva:
                out.append((insn, tgt))
    return sorted(out)


def iat_name(tgt_rva):
    try:
        for d in pe.DIRECTORY_ENTRY_IMPORT:
            for imp in d.imports:
                if imp.address - base == tgt_rva:
                    return f'{d.dll.decode()}!{imp.name.decode() if imp.name else imp.ordinal}'
    except Exception:
        pass
    return f'iat:{tgt_rva:#x}'


def callers_of(fnva):
    out = []
    for s, r in res.items():
        if (fnva - base) in r['calls'] or (fnva - base) in r['jmps']:
            out.append(s + base)
    return sorted(out)


def callees_of(fnva):
    r = res.get(fnva - base)
    if not r:
        return []
    return sorted(c + base for c in set(r['calls'] + r['jmps']))


def show(fnva, depth=0, seen=None, maxdepth=1):
    if seen is None:
        seen = set()
    if fnva in seen or depth > maxdepth:
        return
    seen.add(fnva)
    r = res.get(fnva - base)
    sz = r['size'] if r else '?'
    ind = '  ' * depth
    print(f'{ind}== func {fnva:#x} (size {sz})')
    for insn, tgt, info in fn_strings(fnva)[:24]:
        print(f'{ind}   str@{insn:#x} {info["enc"]} {info["s"][:100]!r}')
    for insn, tgt in fn_iat(fnva)[:24]:
        print(f'{ind}   iat@{insn:#x} {iat_name(tgt)}')
    if depth < maxdepth:
        for c in callees_of(fnva)[:40]:
            rr = res.get(c - base)
            if rr and rr['size'] and rr['size'] < 0x3000:
                show(c, depth + 1, seen, maxdepth)


def cluster(fnva, npage=2):
    """前後 npage*4096B の関数一覧 + 各自の文字列"""
    lo, hi = fnva - npage * 0x1000, fnva + npage * 0x1000
    fns = sorted(s + base for s in res if lo <= s + base < hi)
    print(f'--- cluster around {fnva:#x}: {len(fns)} funcs')
    for f in fns:
        r = res[f - base]
        ss = fn_strings(f)
        ssum = ' | '.join(i['s'][:42] for _, _, i in ss[:5])
        print(f'{f:#x} size={r["size"]:6d} str={len(ss):2d} {ssum}')


if __name__ == '__main__':
    args = sys.argv[1:]
    mode = 'func'
    if args[0] == 'cluster':
        mode = 'cluster'
        args = args[1:]
    load(args[0], args[1], args[2], args[3])
    rest = args[4:]
    depth = 1
    while '--depth' in rest:
        i = rest.index('--depth')
        depth = int(rest[i + 1]); del rest[i:i + 2]
    for a in rest:
        va = int(a, 16)
        if mode == 'cluster':
            cluster(va, depth)
        else:
            show(va, maxdepth=depth)
            print(f'   callers: {[hex(c) for c in callers_of(va)][:20]}')
