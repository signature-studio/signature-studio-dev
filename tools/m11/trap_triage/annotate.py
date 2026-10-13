#!/usr/bin/env python3
"""survey_units.mjs の JSON を wasm export 名で注釈し, trap の最上位 frame / halt0 の stub 相関を集計する (#130)"""
import json, re, subprocess, sys, os, collections
HERE = os.path.dirname(os.path.abspath(__file__)); W = os.path.join(HERE, '..', 'work')
wasm = os.path.join(W, 'm11_boot.cjs.wasm')
def leb(b, i):
    r = s = 0
    while True:
        x = b[i]; i += 1; r |= (x & 0x7f) << s; s += 7
        if not x & 0x80: return r, i
def export_names(path):
    b = open(path, 'rb').read(); i = 8; out = {}
    while i < len(b):
        sid = b[i]; sz, i = leb(b, i + 1); end = i + sz
        if sid == 7:
            n, j = leb(b, i)
            for _ in range(n):
                l, j = leb(b, j); nm = b[j:j + l].decode(); j += l
                kind = b[j]; idx, j = leb(b, j + 1)
                if kind == 0: out.setdefault(idx, nm)
        i = end
    return out
names = export_names(wasm)
per = json.load(open(sys.argv[1]))
def nm(f):
    m = re.search(r'wasm-function\[(\d+)\]', f)
    return names.get(int(m.group(1)), '?') if m else f
tops = collections.defaultdict(list)
for r in per:
    if r['kind'] in ('oob', 'other', 'abort'):
        fr = [nm(f) for f in r.get('frames', [])]
        r['named'] = fr
        tops[fr[0] if fr else '-'].append(r['unit'])
for k, v in sorted(tops.items(), key=lambda x: -len(x[1])): print(len(v), k, v)
print('--- chains (first 6 frames)')
for r in per:
    if 'named' in r: print(r['unit'], r['va'], r['kind'], ' <- '.join(r['named'][:6]))
print('--- halt0 stubs/err')
c = collections.Counter()
for r in per:
    if r['kind'] == 'halt0': c[tuple(sorted((r.get('stubs') or {}).keys()))] += 1
for k, v in c.most_common(): print(v, k)
print('--- halt0 callers (Halt0 直上 4 frame)')
hc = collections.defaultdict(list)
for r in per:
    if r['kind'] == 'halt0':
        fr = [nm(f) for f in r.get('frames', [])]
        hc[' <- '.join(fr[3:8])].append(r['unit'])
for k, v in sorted(hc.items(), key=lambda x: -len(x[1])): print(len(v), k, v[:6])
print('--- halt0 Error() 呼出元 (409730 / 412a60 の直上 frame)')
ec = collections.defaultdict(list)
for r in per:
    if r['kind'] == 'halt0':
        fr = [nm(f) for f in r.get('frames', [])]
        i = fr.index('function_409730') if 'function_409730' in fr else (fr.index('function_412a60') if 'function_412a60' in fr else -1)
        ec[fr[i + 1] if 0 <= i + 1 < len(fr) else '?'].append(r['unit'])
for k, v in sorted(ec.items(), key=lambda x: -len(x[1])): print(len(v), k, v[:12])
print('--- halt0 Error 呼出元の更に 3 段上')
ec = collections.defaultdict(list)
for r in per:
    if r['kind'] == 'halt0':
        fr = [nm(f) for f in r.get('frames', [])]
        i = fr.index('function_409730') if 'function_409730' in fr else (fr.index('function_412a60') if 'function_412a60' in fr else -1)
        ec[' <- '.join(fr[i + 1:i + 4])].append(r['unit'])
for k, v in sorted(ec.items(), key=lambda x: -len(x[1])): print(len(v), k, v[:8])
print('--- halt0: Error 呼出元 (409730/412a60 の次) から m11_tr_* までの鎖')
ec = collections.defaultdict(list)
for r in per:
    if r['kind'] == 'halt0':
        fr = [nm(f) for f in r.get('frames', [])]
        i = next((fr.index(x) for x in ('function_409730', 'function_412a60', 'function_4096d0') if x in fr), 0)
        ch = []
        for f in fr[i + 1:]:
            if f.startswith('m11_'): break
            ch.append(f.replace('function_', ''))
        ec[' < '.join(ch[:3]) + ' ... ' + ch[-1]].append(r['unit'])
for k, v in sorted(ec.items(), key=lambda x: -len(x[1])): print(len(v), k, v[:6])
if len(sys.argv) > 2:
    print('--- full chains for units', sys.argv[2:])
    for r in per:
        if str(r['unit']) in sys.argv[2:]:
            fr = [nm(f).replace('function_', '') for f in r.get('frames', [])]
            print(r['unit'], r['va'], r['kind'], ' < '.join(f for f in fr if not f.startswith('m11_'))[:400])
