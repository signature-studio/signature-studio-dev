#!/usr/bin/env python3
"""snap-in ごとの DSP closure 見積。

roots   = <ns>::*Dsp / *MasterDsp / *DspModel の vtable slot 全部
closure = roots から直接 call/jmp を辿った到達集合 (間接 call は辿らない = 過小評価の下限)
infra   = 到達 snap-in 数 >= INFRA_K の関数 (alloc / vector / param model 等の共通基盤)
unique  = closure - infra  (snap-in 固有 + 少数共有ライブラリ)
usage: closures.py callgraph.pkl rtti_vtables.json out.json
"""
import sys, json, pickle, re, collections

INFRA_K = 8

PROD = {  # namespace -> (id, displayName)
    'bitcrush': ('ksbc', 'Bitcrush'), 'chorus': ('ksch', 'Chorus'), 'combfilter': ('kscf', 'Comb Filter'),
    'compactor': ('kscc', 'Compactor'), 'compressor': ('kscp', 'Compressor'), 'convolver': ('ksco', 'Convolver'),
    'delay': ('ksdl', 'Delay'), 'dirtyfilter': ('ksdf', 'Nonlinear Filter'), 'disperser': ('kdsp', 'Disperser'),
    'distortion': ('ksdt', 'Distortion'), 'dualdelay': ('ksdd', 'Dual Delay'), 'dynamics': ('ksot', 'Dynamics'),
    'quickeq': ('ksqe', '3-Band EQ'), 'graphiceq': ('ksge', 'Carve EQ'), 'equalizer': ('kpeq', 'Slice EQ'),
    'faturator': ('kfat', 'Faturator'), 'filter': ('ksfi', 'Filter'), 'filtertable': ('ksft', 'Filter Table'),
    'flanger': ('ksfl', 'Flanger'), 'frequencyshifter': ('ksfs', 'Frequency Shifter'), 'gain': ('ksgn', 'Gain'),
    'gate': ('ksgt', 'Gate'), 'haas': ('ksha', 'Haas'), 'ladder': ('ksla', 'Ladder Filter'), 'limiter': ('kslt', 'Limiter'),
    'matrix': ('kscm', 'Channel Mixer'), 'multipass': ('kmup', 'Multipass'), 'phasedistortion': ('kspd', 'Phase Distortion'),
    'phaseplant': ('kphp', 'Phase Plant'), 'phaser': ('ksph', 'Phaser'), 'pitchshift': ('ksps', 'Pitch Shifter'),
    'resonator': ('ksre', 'Resonator'), 'reverb': ('ksrv', 'Reverb'), 'reverser': ('ksrr', 'Reverser'),
    'ringmod': ('ksrm', 'Ring Mod'), 'shaper': ('kssr', 'Shaper'), 'micropass': ('kmic', 'Snap Heap'),
    'stereo': ('ksst', 'Stereo'), 'tapestop': ('ksts', 'Tape Stop'), 'trancegate': ('kstg', 'Trance Gate'),
    'transientshaper': ('kstr', 'Transient Shaper'), 'unison': ('ksun', 'Ensemble'), 'vocalfilter': ('ksvf', 'Formant Filter'),
    'waveshaper': ('ksws', 'Shaper Table'), 'clipper': ('kclp', 'Clipper'),
    'snapingroup': ('(group)', 'kHs Group'), 'hostproxy': ('(proxy)', 'kHs Host Proxy'),
}


def main(cgp, vtp, outp):
    cg = pickle.load(open(cgp, 'rb'))
    base, res = cg['base'], cg['res']
    vt = json.load(open(vtp))
    roots = collections.defaultdict(set)
    rootcls = collections.defaultdict(dict)
    for k, lst in vt.items():
        rest = k[4:]
        rest = rest[:-2] if rest.endswith('@@') else rest
        if '?' in rest or '$' in rest:
            continue
        parts = [p for p in rest.split('@') if p]
        if len(parts) < 2:
            continue
        name, ns = parts[0], parts[-1]
        if ns not in PROD:
            continue
        if re.search(r'(MasterDsp|Dsp|DspModel)$', name) and len(parts) == 2:
            for v in lst:
                for s in v['slots']:
                    roots[ns].add(int(s, 16) - base)
            rootcls[ns][name] = sum(1 for _ in lst)

    def reach(rs):
        seen, st = set(), list(rs)
        while st:
            f = st.pop()
            if f in seen or f not in res:
                continue
            seen.add(f)
            r = res[f]
            st.extend(r['calls'])
            st.extend(r['jmps'])
        return seen

    reached = {ns: reach(r) for ns, r in roots.items()}
    cnt = collections.Counter()
    for ns, s in reached.items():
        if ns in ('phaseplant', 'multipass', 'micropass', 'snapingroup', 'hostproxy'):
            continue
        for f in s:
            cnt[f] += 1
    nsn = len([n for n in reached if n not in ('phaseplant', 'multipass', 'micropass', 'snapingroup', 'hostproxy')])
    infra = {f for f, c in cnt.items() if c >= INFRA_K}
    sets = {}
    out = {'infra_funcs': len(infra), 'infra_bytes': sum(res[f]['size'] for f in infra), 'n_snapins': nsn, 'ns': {}}
    for ns, s in sorted(reached.items()):
        uniq = s - infra
        sets[ns] = sorted(uniq)
        # 固有: 他 snap-in から到達されない (cnt==1)
        own = {f for f in uniq if cnt.get(f, 0) <= 1}
        simd = collections.Counter()
        indir = iat = cpuid = 0
        for f in uniq:
            r = res[f]
            for kk, vv in r['simd'].items():
                simd[kk] += vv
            indir += r['indir']
            iat += r['iat']
            cpuid += r['cpuid']
        rootsz = sum(res[r]['size'] for r in roots[ns] if r in res)
        out['ns'][ns] = dict(
            id=PROD[ns][0], name=PROD[ns][1], roots=len(roots[ns]), root_bytes=rootsz,
            closure_funcs=len(s), closure_bytes=sum(res[f]['size'] for f in s),
            unique_funcs=len(uniq), unique_bytes=sum(res[f]['size'] for f in uniq),
            own_funcs=len(own), own_bytes=sum(res[f]['size'] for f in own),
            simd=dict(simd), indirect_calls=indir, iat_calls=iat, cpuid=cpuid,
            avx=simd.get('avx128', 0) + simd.get('avx256', 0) + simd.get('fma', 0) + simd.get('avx512', 0))
    json.dump(out, open(outp, 'w'), indent=1)
    pickle.dump({'sets': sets, 'infra': sorted(infra), 'base': base}, open(outp.replace('.json', '_sets.pkl'), 'wb'))
    print('infra', out['infra_funcs'], out['infra_bytes'], 'n', nsn)


if __name__ == '__main__':
    main(*sys.argv[1:4])
