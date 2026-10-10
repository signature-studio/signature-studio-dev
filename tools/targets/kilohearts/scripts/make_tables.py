#!/usr/bin/env python3
"""バイナリ表・製品表・難度ランキングの生成 (work/ 配下に TSV/MD)。 usage: make_tables.py"""
import json, os, sys, glob, collections, struct

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
W = os.path.join(HERE, 'work')


def sz(p):
    return os.path.getsize(p)


def main():
    idx = json.load(open(f'{W}/blobs/index.json'))['releases'][0]
    plugins = [p for p in idx['plugins'] if 'formats' in p and 'snapin' in p.get('formats', []) or p.get('id') == 'kphp']
    allp = idx['plugins']
    prods = [p for p in allp if p['id'] not in ('core',) and p.get('formats') != ['bank']]
    banks = [p for p in allp if p.get('formats') == ['bank']]
    out = [f"release version={idx['version']} date={idx['date']}", f"plugins(non-bank, non-core)={len(prods)} banks={len(banks)} snapin-capable={len([p for p in prods if 'snapin' in p['formats']])}"]
    # Windows 表
    wp = f'{W}/winpkg'
    rows = []
    for ext, tag in (('vst2_64', 'VST2'), ('vst3_64', 'VST3'), ('aaxplugin', 'AAX')):
        fs = []
        for f in sorted(glob.glob(f'{wp}/*.{ext}')):
            if os.path.isdir(f):
                fs += glob.glob(f + '/Contents/x64/*')
            else:
                fs.append(f)
        sizes = collections.Counter(sz(f) for f in fs)
        rows.append((tag, 'win x64 PE32+ DLL', len(fs), dict(sizes)))
    core = f'{wp}/HeartCore.core_64'
    rows.append(('core', 'win x64 PE32+ DLL', 1, {sz(core): 1}))
    out.append('WIN ' + json.dumps(rows))
    mp = f'{W}/macpkg'
    mrows = []
    for ext in ('vst', 'vst3', 'component', 'aaxplugin'):
        fs = [p for p in glob.glob(f'{mp}/*.{ext}')]
        sizes = collections.Counter()
        for f in fs:
            b = glob.glob(f + '/Contents/MacOS/*')
            if b:
                sizes[sz(b[0])] += 1
        mrows.append((ext, len(fs), dict(sizes)))
    out.append('MAC ' + json.dumps(mrows))
    out.append('MACCORE ' + json.dumps({'universal': sz(f'{mp}/HeartCore.core/Contents/MacOS/HeartCore'), 'x86_64': sz(f'{W}/mac_slices/HeartCore_x86_64'), 'arm64': sz(f'{W}/mac_slices/HeartCore_arm64')}))
    open(f'{W}/tables.txt', 'w').write('\n'.join(out))
    print('\n'.join(out)[:3000])

    # ランキング
    cl = json.load(open(f'{W}/closures.json'))['ns']
    cs = json.load(open(f'{W}/simd_census.json'))['per_ns']
    rank = []
    for ns, r in cl.items():
        if ns in ('snapingroup', 'hostproxy'):
            continue
        s = cs[ns]
        # 難度スコア: 固有バイト + SIMD 命令量 + 未被覆 mnemonic 種 + 間接呼/IAT/AVX の罰則
        score = r['own_bytes'] / 1000.0 + s['total'] / 100.0 + len(s['uncovered']) * 0.3 + max(0, r['indirect_calls'] - 1) * 0.5 + r['iat_calls'] * 1.0 + (r['avx'] > 0) * 0.5
        rank.append((score, ns, r, s))
    rank.sort(key=lambda x: x[0])
    lines = ['| # | snap-in (id) | ns | 固有コード B | 固有関数 | SIMD命令 | 種 | 未被覆種 | AVX/FMA | 間接call | IAT | 難度スコア |', '|--:|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|']
    for i, (sc, ns, r, s) in enumerate(rank, 1):
        lines.append(f"| {i} | {r['name']} ({r['id']}) | {ns} | {r['own_bytes']} | {r['own_funcs']} | {s['total']} | {s['distinct']} | {len(s['uncovered'])} | {r['avx']} | {r['indirect_calls']} | {r['iat_calls']} | {sc:.1f} |")
    open(f'{W}/ranking.md', 'w').write('\n'.join(lines))
    print('\n'.join(lines[:14]))


if __name__ == '__main__':
    main()
