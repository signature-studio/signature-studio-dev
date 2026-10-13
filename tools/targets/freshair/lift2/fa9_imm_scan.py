#!/usr/bin/env python3
"""fa9_imm_scan.py <SlateCore.core_64> — FA-9 (4): 即値 0x157/0x158/0x15a を持つ関数の列挙 (.pdata 関数境界 × capstone 即値オペランド)。
各関数について (関数 VA, 関数サイズ, 即値 ID, 命令 VA) を表示する。ID の意味は本スクリプトでは確定しない (手掛かり列挙のみ)。
除外: imul (ハッシュ/係数の偽陽性) と rsp を含む命令 (フレームサイズ 0x158 の偽陽性)。
exit 0 = 列挙完了 (件数 0 でも失敗扱いにしない: 件数はレポートで判断)。読めない場合のみ非 0。"""
import struct, sys, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM

core = sys.argv[1]
pe = pefile.PE(core)
base = pe.OPTIONAL_HEADER.ImageBase
IDS = {0x157, 0x158, 0x15a}
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
funcs = []
for e in pe.DIRECTORY_ENTRY_EXCEPTION:
    s = e.struct
    funcs.append((base + s.BeginAddress, base + s.EndAddress))
funcs = sorted(set(funcs))
hits = {}
for (a, b) in funcs:
    try:
        code = pe.get_data(a - base, b - a)
    except Exception:
        continue
    for ins in md.disasm(code, a):
        for op in ins.operands:
            if op.type == CS_OP_IMM and (op.imm & 0xffffffff) in IDS and ins.mnemonic != 'imul' and 'rsp' not in ins.op_str:
                hits.setdefault(a, []).append((ins.address, ins.mnemonic, ins.op_str, op.imm & 0xffffffff))
print('functions scanned: %d (pdata)' % len(funcs))
print('functions with immediate 0x157/0x158/0x15a: %d' % len(hits))
print('%-12s %6s  %s' % ('func VA', 'size', 'hits (VA mnemonic operands -> ID)'))
for a in sorted(hits):
    b = [e for e in funcs if e[0] == a][0][1]
    h = hits[a]
    print('0x%x %6d  %s' % (a, b - a, '; '.join('0x%x %s %s -> 0x%x' % (x[0], x[1], x[2], x[3]) for x in h[:4]) + (' ...(+%d)' % (len(h) - 4) if len(h) > 4 else '')))
