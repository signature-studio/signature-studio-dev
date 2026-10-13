#!/usr/bin/env python3
"""閉包 (vtable override から `call/jmp rel32` で到達する固有関数) に入らない「framework 非共通の固有関数」が、
.rdata/.data に関数開始 VA の 8 バイト値として載っているか (= vtable / コールバック表経由で間接呼出の到達先になりうるか) を数える。
閉包は間接呼出を辿らない (plugin_closure.py の仕様) ため、閉包 lift だけでは wasm リンクに足りない関数量の下限を与える。
定義: 非共通 = PE の `.pdata` 関数のうち、ハッシュの出現 DLL 数が plugin_closure.py の FWTHR (13) 未満のもの。
      データ参照 = 関数開始 VA (ImageBase+RVA) が .pdata 以外の節 (Delphi は vtable を .text に置くためコード節を含む) に、節先頭から 8 バイト整列の qword として載っている。
正の対照: 各殻の vtable override entry (closure の entries) が全てデータ参照として検出されること (検出できなければ exit 1)。
前提: sampler_e2e.sh 実行済み + `source sampler/env.sh`。 出力: stdout 表 + work/sampler/unreached.json
"""
import json, os, struct, sys
import numpy as np
import pefile
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(P, '..', 'shared'))
import targets
from paths import FL_WIN64_DIR

FWTHR = 13
cnt = json.load(open(os.path.join(P, 'work', 'fw_hash_counts.json')))
out, bad = {}, 0
print('| プラグイン | 非共通 関数 / B | 閉包 関数 / B | 閉包外 関数 / B | うちデータ参照あり 関数 / B | データ参照なし 関数 / B | 正の対照 (entry のデータ参照検出) |')
print('|---|--:|--:|--:|--:|--:|--:|')
for name, blk, _ in targets.SHELLS:
    fn = 'block%05d_PE.bin' % blk
    pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', fn), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    fj = json.load(open(os.path.join(P, 'work', 'winfuncs', 'block%05d.json' % blk)))
    clo = json.load(open(os.path.join(P, 'work', 'closure', 'block%05d.json' % blk)))
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    pdata = pd.get_data()[:pd.Misc_VirtualSize]
    size = {}
    for i in range(len(pdata) // 12):
        b, e, u = struct.unpack_from('<III', pdata, 12 * i)
        if b and not (u & 1):
            size[b] = e - b
    nonfw = {f[0]: size.get(f[0], f[1]) for f in fj['funcs'] if cnt.get(f[2], 0) < FWTHR and f[0] in size}
    inclo = {int(r.split('-')[0], 16) - base for r in clo['ranges']}
    vals = []
    for s in pe.sections:
        nm = s.Name.rstrip(b'\0')
        if nm == b'.pdata' or not (s.Characteristics & 0x40 or s.Characteristics & 0x20):   # 初期化済みデータ + コード節 (Delphi は vtable を .text に置く)
            continue
        d = s.get_data()[:s.Misc_VirtualSize]
        n = len(d) // 8
        if n > 0:
            vals.append(np.frombuffer(d[:8 * n], dtype='<u8'))
    allv = np.unique(np.concatenate(vals)) if vals else np.array([], dtype='<u8')
    hit = lambda rvas: np.isin(np.array([base + r for r in rvas], dtype='<u8'), allv)
    rest = {r: s for r, s in nonfw.items() if r not in inclo}
    rl = list(rest)
    dref = {r: rest[r] for r, h in zip(rl, hit(rl)) if h} if rl else {}
    entries = [int(v, 16) - base for v in clo['entries'].values()]
    found = int(hit(entries).sum()) if entries else 0
    pos_ok = found == len(entries) and len(entries) > 0
    bad += not pos_ok
    out[name] = {'nonfw_funcs': len(nonfw), 'nonfw_bytes': sum(nonfw.values()), 'closure_funcs': len(inclo), 'closure_bytes': sum(size[r] for r in inclo if r in size),
                 'outside_funcs': len(rest), 'outside_bytes': sum(rest.values()), 'dataref_funcs': len(dref), 'dataref_bytes': sum(dref.values()),
                 'nodataref_funcs': len(rest) - len(dref), 'nodataref_bytes': sum(rest.values()) - sum(dref.values()), 'entries': len(entries), 'entries_found': found}
    o = out[name]
    f = lambda k: '%s / %s' % (format(o[k + '_funcs'], ','), format(o[k + '_bytes'], ','))
    print('| %s | %s | %s | %s | %s | %s | %d/%d%s |' % (name, f('nonfw'), f('closure'), f('outside'), f('dataref'), f('nodataref'), found, len(entries), '' if pos_ok else ' **NG**'))
json.dump(out, open(os.path.join(P, 'work', 'sampler', 'unreached.json'), 'w'), indent=1)
sys.exit(1 if bad else 0)
