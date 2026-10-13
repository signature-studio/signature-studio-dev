#!/usr/bin/env python3
"""Generator 入口 (abi.impl) のうち、plugin_closure.py が「framework 既定実装 (関数ハッシュが 13 DLL 以上で共通)」として入口から外したスロットの
実装関数サイズ (.pdata) を出す (PLG-G1 / #206)。 閉包の外に DSP が隠れていないかの目安 (小さい = 空 stub と推定、大きい = 要確認)。
  python3 dropped_entries.py     → markdown 表 (stdout)。 前提: g1_e2e.sh 実行済み (work/closure/, work/win_abi.json)
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(P, '..', 'shared'))
sys.path.insert(0, HERE)
from paths import FL_WIN64_DIR
from common import PLUGINS
import pefile
A = {r['file']: r for r in json.load(open(os.path.join(P, 'work', 'win_abi.json')))}
print('| plugin | block | 入口から外れた slot | 実装 VA | .pdata サイズ B | 機械語 (先頭 32 B) |')
print('|---|--:|---|---|--:|---|')
seen = set()
for name, b, _ in PLUGINS:
    if b is None or b in seen:
        continue
    seen.add(b)
    fn = 'block%05d_PE.bin' % b
    abi = A[fn]
    c = json.load(open(os.path.join(P, 'work', 'closure', 'block%05d.json' % b)))
    pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', fn), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    ends = {}
    for i in range(len(pd) // 12):
        s, e, u = struct.unpack_from('<III', pd, 12 * i)
        if s and not (u & 1):
            ends[s] = e
    for slot, va in abi['impl'].items():
        if slot in c['entries']:
            continue
        rva = int(va, 16) - base
        n = ends[rva] - rva if rva in ends else None
        print('| %s | %d | %s | %s | %s | %s |' % (name, b, slot, va, n if n is not None else '.pdata 無し', pe.get_data(rva, min(n, 32)).hex() if n else '-'))
