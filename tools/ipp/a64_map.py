#!/usr/bin/env python3
"""arm64 dsp_ippv2 の各 export 関数が呼ぶ Accelerate/libc スタブと命令数・SIMD 使用を抽出 (work/a64_map.json)。"""
import re, json, collections, sys
dis = open('work/dsp_ippv2.arm64.dis').read().split('\n')
funcs = {}; cur = None
rl = re.compile(r'^(_[^\s:]+):$')
for ln in dis:
    m = rl.match(ln)
    if m: cur = m.group(1); funcs[cur] = []; continue
    if cur and ln.startswith(' '): funcs[cur].append(ln)
exports = set(l.strip() for l in open('work/a64.syms'))
out = {}
simd = re.compile(r'\t(f(add|sub|mul|div|sqrt|max|min|abs|neg|cvt\w*|rint\w*|mla|mls)|ld[1-4]|st[1-4]|addv|dup|ins|zip|uzp|trn|ext|bsl|bit|bif|cm\w+|fcm\w+)\.\d+[sd]\b|\.4s|\.2d|\.8h|\.16b')
for f, body in funcs.items():
    stubs = collections.Counter(); internal = collections.Counter(); calls_ext = collections.Counter()
    nsimd = 0
    for ln in body:
        m = re.search(r'symbol stub for: (\S+)', ln)
        if m: stubs[m.group(1)] += 1; continue
        m = re.search(r'\tbl\t0x[0-9a-f]+ <?(_\w+)', ln)
        if m: internal[m.group(1)] += 1
        if re.search(r'\.(2d|4s|2s|8h|16b|8b|4h)\b', ln): nsimd += 1
    out[f] = {'ninsn': len(body), 'stubs': dict(stubs), 'internal_calls': dict(internal), 'neon_insn': nsimd, 'exported': f in exports}
json.dump(out, open('work/a64_map.json', 'w'), indent=0)
ex = {k: v for k, v in out.items() if v['exported']}
print('functions', len(out), 'exported', len(ex))
cl = collections.Counter()
for k, v in ex.items():
    s = set(v['stubs'])
    if any(x.startswith('_vDSP') for x in s): c = 'vDSP'
    elif any(x.startswith('_vImage') for x in s): c = 'vImage'
    elif any(x.startswith('_vv') for x in s): c = 'vForce'
    elif s: c = 'libc/other:' + ','.join(sorted(s))[:30]
    elif v['neon_insn'] > 4: c = 'own NEON'
    else: c = 'own scalar/other'
    cl[c if c.startswith(('vDSP','vImage','vForce','own')) else 'libc/other'] += 1
print(cl)
tot = sum(v['ninsn'] for v in ex.values()); print('exported insn total', tot, ' all funcs insn', sum(v['ninsn'] for v in out.values()))

# data/ に export 名→実装クラスの対応表を保存 (名前は ipp 名、_ 接頭辞なし)
def klass(v):
    st = set(v['stubs'])
    if any(x.startswith('_vDSP') for x in st): return 'vDSP'
    if any(x.startswith('_vImage') for x in st): return 'vImage'
    if any(x.startswith('_vv') for x in st): return 'vForce'
    if st: return 'libc/libm/LAPACK'
    if v['neon_insn'] > 4: return 'own NEON'
    return 'own scalar'
import os
os.makedirs('data', exist_ok=True)
json.dump({k[1:]: {'class': klass(v), 'accelerate_libc_calls': sorted(x.lstrip('_') for x in v['stubs']), 'insns': v['ninsn']} for k, v in sorted(ex.items())}, open('data/arm64_ipp_map.json', 'w'), indent=0)
u = json.load(open('data/ipp_usage_summary.json')) if os.path.exists('data/ipp_usage_summary.json') else None
if u:
    used = set(u['win64']['used_functions']) | set(u['mac_x86_64']['used_functions']) | set(u['mac_arm64']['used_functions'])
    c = collections.Counter(klass(v) for k, v in ex.items() if k[1:] in used)
    print('arm64 slice: classes of exports that FL actually uses:', dict(c))
