#!/usr/bin/env python3
"""PLG-G1 (#206): closure_facts.py (host_calls.py の taint 追跡) の Dispatcher ID を別アルゴリズムで検算する。
taint を使わず、閉包 ranges を線形逆アセンブルして「`mov r8d, imm` / `xor r8d, r8d` の後 8 命令以内にある
`call qword ptr [reg]` (disp 0, index 無し, base が rip でない)」を全数拾う。 host 以外の vtable slot0 呼出も拾うため上位集合になる。
前提: g1_e2e.sh 実行済み + `source g1/env.sh`。  usage: ids_crosscheck.py [facts.json]
合格条件: 各プラグインで taint 版の即値 ID の件数が、本走査の同 ID の件数以下 (取りこぼしなし)。 facts の plugin 集合が common.PLUGINS と違う場合も不合格。
不合格なら exit 1。
"""
import os, sys, json, collections
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(P, '..', 'shared'))
sys.path.insert(0, HERE)
from common import PLUGINS
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG

F = json.load(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(P, 'work', 'g1', 'facts.json')))
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
HS = json.load(open(os.path.join(P, 'framework', 'hostshim', 'hs_ids.json')))['ids']
notes = []
bad = 0
if set(F) != {n for n, sh, _ in PLUGINS if sh is not None}:
    bad += 1
    print('NG facts の plugin 集合が common.PLUGINS と違う:', sorted(F))
for name, f in F.items():
    blk = f['block']
    c = json.load(open(os.path.join(P, 'work', 'closure', 'block%05d.json' % blk)))
    pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % blk), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    found = collections.Counter()
    for r in c['ranges']:
        a, b = (int(x, 16) for x in r.split('-'))
        code = pe.get_data(a - base, b - a + 1)
        r8, age = None, 99
        for ins in md.disasm(code, a):
            age += 1
            if ins.mnemonic == 'call':
                op = ins.operands[0]
                if op.type == X86_OP_MEM and op.mem.disp == 0 and op.mem.index == 0 and ins.reg_name(op.mem.base) not in ('rip', ''):
                    found['dyn' if (r8 is None or age > 8) else r8] += 1
                r8 = None
                continue
            if len(ins.operands) == 2 and ins.operands[0].type == X86_OP_REG and ins.reg_name(ins.operands[0].reg) == 'r8d':
                if ins.mnemonic == 'mov' and ins.operands[1].type == X86_OP_IMM:
                    r8, age = ins.operands[1].imm, 0
                elif ins.mnemonic == 'xor' and ins.operands[1].type == X86_OP_REG and ins.reg_name(ins.operands[1].reg) == 'r8d':
                    r8, age = 0, 0
                else:
                    r8 = None
    ok = True
    for k, v in f['host']['ids'].items():
        if k == 'dyn':
            continue
        if found.get(int(k), 0) < v:
            ok = False
    bad += not ok
    extra_ids = sorted(k for k in found if k != 'dyn' and str(k) not in HS)
    if extra_ids:
        notes.append('%s: 独立走査で見つかった ID のうち hs_ids.json に無いもの = %s' % (name, extra_ids))
    print('%-28s taint(imm ID: site)=%s  独立走査(imm ID: site)=%s  %s' % (
        name, {k: v for k, v in f['host']['ids'].items() if k != 'dyn'},
        {str(k): v for k, v in sorted(found.items(), key=lambda x: str(x[0])) if k != 'dyn'}, 'OK' if ok else 'NG'))
for nt in notes:
    print('NOTE', nt)
print('ids_crosscheck: %d/%d プラグインで取りこぼしなし' % (len(F) - bad, len(F)))
sys.exit(1 if bad else 0)
