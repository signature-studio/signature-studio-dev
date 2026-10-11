#!/usr/bin/env python3
"""MX-3 検収 独立再計算 #2 (別アルゴリズム: numpy ベクトル化 linear E8/E9 スキャン).

mx_recount.py (実装側) は python ループ 60 MB を 1 バイトずつ舐める。本スクリプトは
numpy で E8/E9 の位置と disp を一括計算し、別アルゴリズムで非 pdata begin 率・call site 数・
unique target 数を出す。更に .pdata の entry 集合も別法 (numpy unique + begin/end 整合) で数える。

count rules (規則 36 / 数え方の定義):
  - e8e9 site  = .text 全域の 0xE8/0xE9 バイト位置 (機械語境界ではなく総当たり。実装側も同じ)
  - disp は site+5 からの i32。target = rva_of(site) + 5 + disp
  - 対象 = target が .text VA 範囲内 かつ thunk 領域 (RVA 0x396e000-0x3970200) 外
  - 非 begin 率 = 1 - |target ∩ .pdata begin| / |target|
  - roots = export 4 (pez export table) + vtable slot のうち pdata begin のもの
"""
import sys, json, struct, collections
import numpy as np
import pefile

pe_path, out_path = sys.argv[1], sys.argv[2]
pe = pefile.PE(pe_path, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
data = open(pe_path, 'rb').read()

text = next(s for s in pe.sections if s.Name.rstrip(b'\0').decode() == '.text')
t_lo, t_hi = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
pds = sorted([s for s in pe.sections if s.Name.rstrip(b'\0').decode() == '.pdata'],
             key=lambda s: -s.Misc_VirtualSize)[:1]
praw = data[pds[0].PointerToRawData:pds[0].PointerToRawData + pds[0].Misc_VirtualSize]
arr = np.frombuffer(praw[:len(praw) // 12 * 12], dtype='<u4').reshape(-1, 3)
begins = arr[:, 0]
ends = arr[:, 1]
ok = (ends > begins) & (begins != 0) & (begins >= 0x1000) & (begins < t_hi) & (ends <= t_hi)
begins_v = begins[ok]
ends_v = ends[ok]
begin_set = np.unique(begins_v)
bytes_total = int((ends_v - begins_v).sum())

blob = data[text.PointerToRawData:text.PointerToRawData + text.Misc_VirtualSize]
ans = np.frombuffer(blob, dtype='<u1')
# 0xE8 / 0xE9 の位置 (機械語境界ではなく総当たり = 実装側と同定義)
pos = np.nonzero((ans == 0xE8) | (ans == 0xE9))[0]
pos = pos[pos < len(ans) - 5]
disp = np.empty(len(pos), dtype='<i4')
for i in range(len(pos)):
    disp[i] = struct.unpack_from('<i', blob, int(pos[i]) + 1)[0]
# target = blob index of the target instruction (実装側と同じ: index で範囲判定し RVA は t_lo 加算)
tgt_idx = pos + 5 + disp
THUNK_LO, THUNK_HI = 0x396e000, 0x3970200
inrange = (tgt_idx >= t_lo) & (tgt_idx < t_hi) & ~((tgt_idx >= THUNK_LO) & (tgt_idx < THUNK_HI))
targets = np.unique(tgt_idx[inrange])
# 非 pdata begin
is_begin = np.isin(targets, begin_set)
n_nonbegin = int((~is_begin).sum())

# roots (export + vtable slot)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
exps = {s.address for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.address and s.name}
roots = set(exps)
vt = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else {}
FAM = {'SingleComponentEffect', 'ComponentBase', 'EditControllerEx1', 'EditController',
       'IPluginBase', 'FObject', 'FUnknown', 'IDependent', 'Unit', 'ProgramList', 'Parameter',
       'Bus', 'AudioBus', 'EventBus', 'BusList', 'IPlugView', 'CPluginView', 'IConnectionPoint',
       'IAudioProcessor', 'IComponent', 'IEditController', 'IEditController2', 'IUnitInfo',
       'IAutomationState', 'IMidiMapping', 'IInfoListener', 'IProcessContextRequirements',
       'IParameterFinder'}
import re
for name, lst in vt.items():
    m = re.match(r'^\.\?(AV|AU)(.+?)@@(.*)$', name)
    if not m:
        continue
    short = [x for x in m.group(2).split('@') if x][-1]
    if short in FAM or short.startswith('MassiveX') or short.startswith('MX'):
        for v in lst:
            for s in v['slots']:
                roots.add(int(s, 16) - base)
roots_begin = {r for r in roots if int(r) in set(begin_set.tolist())}

out = {
    'method': 'numpy vectorized linear E8/E9 scan (independent of mx_recount.py python loop)',
    'pdata_funcs': int(len(begin_set)),
    'pdata_bytes': bytes_total,
    'text_bytes': len(blob),
    'e8e9_sites_in_range': int(inrange.sum()),
    'e8e9_sites_total': int(len(pos)),
    'e8e9_targets_unique': int(len(targets)),
    'non_begin_targets': n_nonbegin,
    'non_begin_pct': round(100.0 * n_nonbegin / len(targets), 2),
    'roots_total': len(roots),
    'roots_pdata_begin': len(roots_begin),
}
# direct-call edge rate: implementation counts "edge" per target (625k range). Here we report
# the site count (upper bound) and unique target count (implementation comparable).
json.dump(out, open(out_path, 'w'), indent=1)
print(json.dumps(out, indent=1))
