#!/usr/bin/env python3
"""count_icall.py [IR.ll]: native 実行済み命令 (ref/cov_all.json) 中の間接 call/jmp を capstone で数え, RetDec IR (!insn.addr 付き) と突合する。
   D1 (RetDec が間接 call/jmp を落とす) の独立検査。IR 既定 = tools/m6/work/full_t1.drc.ll (raw RetDec 出力)。"""
import json, os, re, sys, bisect, collections
import pefile, capstone
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import PLUGINS_DIR
DLL = os.path.join(PLUGINS_DIR, 'ott', 'binaries', 'OTT_vst2_win64.dll')
IR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'm6', 'work', 'full_t1.drc.ll')
pe = pefile.PE(DLL); base = pe.OPTIONAL_HEADER.ImageBase
cov = json.load(open(os.path.join(HERE, '..', 'ref', 'cov_all.json')))
va = lambda x: x if x >= base else x + base
ins = sorted(set(va(x) for x in cov['insn']))
ents = sorted(set([0x18011d400, 0x180120af0, 0x180120800, 0x18011ec20] + [va(x) for x in cov['calltgt']]))
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); md.detail = True
sites = {}
for a in ins:
    c = next(md.disasm(pe.get_data(a - base, 15), a, 1))
    if c.mnemonic in ('call', 'jmp') and c.operands[0].type != capstone.x86.X86_OP_IMM:
        sites[a] = (c.mnemonic, c.op_str, ents[bisect.bisect_right(ents, a) - 1])
iat = {a for a, s in sites.items() if 'rip' in s[1]}
print('実行済み命令 %d / entry 関数 %d / 間接 call+jmp %d (うち IAT 経由 import call %d → 対象外 %d)' % (len(ins), len(ents), len(sites), len(iat), len(sites) - len(iat)))
print('  関数別:', dict(sorted(collections.Counter(hex(s[2]) for a, s in sites.items() if a not in iat).items())))
mdaddr = {}; byaddr = collections.defaultdict(list)
lines = open(IR).read().split('\n')
for ln in lines:
    m = re.match(r'^!(\d+) = !\{i64 (\d+)\}', ln)
    if m: mdaddr[int(m.group(1))] = int(m.group(2))
for ln in lines:
    if ln.startswith('  '):
        m = re.search(r'!insn\.addr !(\d+)', ln)
        if m and mdaddr.get(int(m.group(1))) in sites: byaddr[mdaddr[int(m.group(1))]].append(ln.strip())
kinds = collections.Counter()
for a, s in sites.items():
    if a in iat: kinds['IAT import call (RetDec は call を保持)'] += 1; continue
    ir = byaddr.get(a, [])
    if not ir: kinds['IR に命令なし (完全脱落)'] += 1
    elif any(re.search(r'\bcall\b', l) for l in ir): kinds['固定 target の call に化ける (間接 target 喪失)'] += 1
    elif any(l.startswith('ret') for l in ir): kinds['jmp → ret (tail 間接 jmp が return 化)'] += 1
    else: kinds['br のみ'] += 1
for k, v in kinds.items(): print('  %3d  %s' % (v, k))
print('IR 内 レジスタ/メモリ間接 call (call ... %reg( ) 数:', sum(1 for l in lines if re.search(r'\bcall\b[^@]*%[A-Za-z0-9_.]+\(', l) and '@' not in l.split('call', 1)[1].split('(')[0]))
