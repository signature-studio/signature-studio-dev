#!/usr/bin/env python3
"""hs_native_check.py — CAB-195 検収: CreatePlugInstance→ctor 連鎖の native 独立照合 (capstone)。

hs_e2e.mjs の GOLDEN.dispatchIds = [0x47, 0x56, 0x0d, 0x2e, 0x47, 0x1d] と
REPORT §3.2 の site 表 (0x6bd253 / 0x6bd197 / 0x6bd2a4 / 0x6b8f4b / 0x6b8fdd / 0x6b90ff /
0x6b9151) を、A検収素材 block18983_PE.bin (Balance) の逆アセンブルで独立に確認する。
hs_e2e の wasm トレースとは別経路 (native x86 を capstone で読み直す) の検算。

数え方の定義:
  * site VA = wasm トレースに出る `call` 命令の VA (fw_table.py が IR の call site として記録)。
  * ID 即値 = その call 命令より前で、dst が r8/r8d かつ src が即値の最後の `mov`
    (hs_ids.py / host_calls.py と同じ taint 規約。`xor r8d,r8d` は 0 と見なす)。
  * 0x6be800 (TTestPlug.Create) は関数先頭から 0x140B 逆アセンブルし
    `call 0x6b8e80` (TDelphiFruityPlug base ctor) の存在を確認する。

使い方: python3 hs_native_check.py [PEパス]
  PE パス既定 = $FL_WIN64_DIR/extracted/block18983_PE.bin
"""
import sys
import capstone
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_REG, X86_OP_IMM, X86_OP_MEM
import pefile

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', '..', 'shared'))
from paths import FL_WIN64_DIR, REPO_ROOT
PE = sys.argv[1] if len(sys.argv) > 1 else _os.path.join(FL_WIN64_DIR, 'extracted', 'block18983_PE.bin')

SITES = [
    (0x6bd253, 0x47, 'Balance init 0x6bd210: Host.Dispatcher(Tag, 0x47, 0, 0)'),
    (0x6bd197, None, 'slot6: [resp] の vtable+0x30 BOOL 仮想呼出 (edx=0x40f 期待)'),
    (0x6bd2a4, 0x56, 'Balance init 0x6bd210: Host.Dispatcher(Tag, 0x56, 0, 0)'),
    (0x6b8f4b, 0x0d, 'TDelphiFruityPlug base ctor 突入 (Create)'),
    (0x6b8fdd, 0x2e, 'base ctor Continue'),
    (0x6b90ff, 0x47, 'base ctor'),
    (0x6b9151, 0x1d, 'base ctor'),
]

d = open(PE, 'rb').read()
pe = pefile.PE(data=d)
base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True


def at(va, n=0x60):
    o = pe.get_offset_from_rva(va - base)
    return list(md.disasm(d[o:o + n], va))


def window(site):
    """site-0x40 〜 site+0x10 を逆アセンブル (site が命令境界にある前提)"""
    insns = at(site - 0x40, 0x40 + 0x10)
    while insns and insns[-1].address + insns[-1].size < site + 8:
        more = at(insns[-1].address + insns[-1].size, 0x20)
        if not more:
            break
        insns += more
    return insns


def last_r8_imm(insns, upto):
    imm, mn = None, None
    for i in insns:
        if i.address >= upto:
            break
        ops = i.operands
        if len(ops) == 2 and ops[0].type == X86_OP_REG and i.reg_name(ops[0].reg) in ('r8', 'r8d'):
            if i.mnemonic == 'mov' and ops[1].type == X86_OP_IMM:
                imm, mn = ops[1].imm, i.address
            elif i.mnemonic == 'xor':
                imm, mn = 0, i.address
    return imm, mn


def edx_imm(insns, upto):
    for i in insns:
        if i.address >= upto:
            break
        ops = i.operands
        if len(ops) == 2 and ops[0].type == X86_OP_REG and i.reg_name(ops[0].reg) == 'edx' \
           and i.mnemonic == 'mov' and ops[1].type == X86_OP_IMM:
            return ops[1].imm, i.address
    return None, None


ok = fail = 0
print('[native] PE=%s ImageBase=0x%x' % (PE, base))
for (site, want, desc) in SITES:
    insns = window(site)
    call = [i for i in insns if i.address == site]
    if not call:
        print('  NG  site 0x%x: 命令境界に call が見つからない (%s)' % (site, desc))
        fail += 1
        continue
    c = call[0]
    imm, mn = last_r8_imm(insns, site)
    line = '  site 0x%-8x %-6s %-22s r8_imm=%s@0x%x' % (
        site, c.mnemonic, c.op_str, ('0x%x' % imm) if imm is not None else 'None', mn or 0)
    if site == 0x6bd197:
        e, ea = edx_imm(insns, site)
        line += '  edx_imm=%s@0x%x' % (('0x%x' % e) if e is not None else 'None', ea or 0)
        if e == 0x40f:
            line += '  <- OK (REPORT §3.2: edx=0x40f)'; ok += 1
        else:
            line += '  <- 不一致'; fail += 1
    elif want is None:
        line += '  (ID 期待なし)'; ok += 1
    elif imm == want:
        line += '  <- OK (期待 0x%x)' % want; ok += 1
    else:
        line += '  <- 不一致 (期待 0x%x)' % want; fail += 1
    print(line)
    print('        %s' % desc)

# 0x6be800 (TTestPlug.Create) → base ctor 0x6b8e80
ins = at(0x6be800, 0x180)
calls = [i for i in ins if i.mnemonic == 'call' and i.operands
         and i.operands[0].type == X86_OP_IMM]
hit = [i for i in calls if i.operands[0].imm == 0x6b8e80]
print('  0x6be800 (TTestPlug.Create) の先頭 0x180B 内 call 即値: %s'
      % [('0x%x@0x%x' % (i.operands[0].imm, i.address)) for i in calls][:8])
if hit:
    print('    -> call 0x6b8e80 @0x%x を確認 <- OK (base ctor 到達)' % hit[0].address); ok += 1
else:
    print('    -> call 0x6b8e80 が見つからない <- 不一致'); fail += 1

print('[native] OK=%d NG=%d' % (ok, fail))
sys.exit(1 if fail else 0)
