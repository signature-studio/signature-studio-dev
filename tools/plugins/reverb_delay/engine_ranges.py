#!/usr/bin/env python3
"""MSVC C++ engine DLL の全 .pdata 関数を RetDec --select-ranges 形式 (VA) で出力する。
usage: engine_ranges.py <block> [--only SEC[,SEC...]] [--exclude SEC[,SEC...]] [--exclude-ranges FILE]   → stdout: 0xA-0xB,...  (stderr: 関数数 / バイト数 / section 別内訳)
  --only / --exclude は関数の開始 RVA が属する section 名で絞る (例: Multiband Delay engine は IPPCODE section = 静的リンクされた Intel IPP)。
  --exclude-ranges FILE は FILE 内の `0xA-0xB` 行 (engine_bisect.py の出力) に完全一致する range を落とす。
"""
import os, sys, struct, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
a = sys.argv[1:]
only = exclude = None
drop = set()
while len(a) > 1 and a[1].startswith('--'):
    if a[1] == '--only':
        only = set(a[2].split(','))
    elif a[1] == '--exclude':
        exclude = set(a[2].split(','))
    elif a[1] == '--exclude-ranges':
        drop = {l.strip() for l in open(a[2]) if l.startswith('0x')}
    a = a[:1] + a[3:]
pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % int(a[0])), fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
data = pd.get_data()[:pd.Misc_VirtualSize]


def sec_of(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            return s.Name.rstrip(b'\0').decode()
    return '?'


rs, nb = [], 0
cnt = collections.Counter()
for i in range(len(data) // 12):
    b, e, u = struct.unpack_from('<III', data, 12 * i)
    if b and not (u & 1) and e > b:
        sn = sec_of(b)
        if (only and sn not in only) or (exclude and sn in exclude):
            continue
        rg = '0x%x-0x%x' % (base + b, base + e - 1)
        if rg in drop:
            continue
        rs.append(rg)
        nb += e - b
        cnt[sn] += 1
print(','.join(rs))
print('%d funcs / %d bytes (section: %s)' % (len(rs), nb, dict(cnt)), file=sys.stderr)
