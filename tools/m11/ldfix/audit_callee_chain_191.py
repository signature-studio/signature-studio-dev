#!/usr/bin/env python3
"""audit_callee_chain_191.py — #3228 残件 (LD-191) の 6 site の呼び出し先を機械語で記録する (#4086)。

判定器 audit_frame_store_callee_3228.py が打ち切った call の先を、同じ PE から再現して記録する。
各呼び出し先について次を出す:
  IAT_THUNK   : `jmp qword ptr [rip+X]` だけの関数 (外部 DLL への転送)。IAT slot の RVA を出す。
  calls       : 呼び出し先の全 call 命令。間接 call は参照先を `[rip+X]` のグローバルの初期値 (PE の生データ) で出す。
  first_store : 呼び出し先で最初に [mem] へ書く命令と、その前にある分岐の有無。
判定は行わない (判定は audit_frame_store_callee_3228.py・REPORT_3228.md)。

使い方: python3 audit_callee_chain_191.py PE.bin OUT.json
"""
import json
import os
import sys

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ldmach  # noqa: E402
from ldmach import Machine  # noqa: E402

# (元の関数, 打ち切りの call 命令 VA, 呼び出し先 VA)  — REPORT_3228.md §3.2 / LD-191 の表
SITES = [
    ('1006ec0', 0x1006fa9, None),
    ('1354630', 0x135477f, 0x12b0020),
    ('441730', 0x44177b, 0x441530),
    ('4488f0', 0x448928, 0x423d20),
    ('454090', 0x454524, 0x41c820),
    ('5c4dc0', 0x5c4e3e, 0x424300),
]


def rip_target(cs, ins):
    """[rip+X] の参照先 VA。無ければ None。"""
    for op in ins.operands:
        if op.type == capstone.CS_OP_MEM and op.mem.base and cs.reg_name(op.mem.base) == 'rip':
            return ins.address + ins.size + op.mem.disp
    return None


def global_value(m, va):
    rva = va - m.base
    try:
        raw = m.pef.get_data(rva, 8)
    except Exception:
        return None
    return int.from_bytes(raw, 'little')


def iat_names(m):
    """IAT slot RVA -> 'dll!name' (pefile の import 表から)。"""
    import pefile
    m.pef.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    names = {}
    for ent in getattr(m.pef, 'DIRECTORY_ENTRY_IMPORT', []):
        dll = ent.dll.decode('latin1')
        for imp in ent.imports:
            nm = imp.name.decode('latin1') if imp.name else 'ordinal%d' % imp.ordinal
            names['%x' % (imp.address - m.base)] = '%s!%s' % (dll, nm)
    return names


def describe(m, va):
    seq = m.disasm_fn(va) or []
    rec = dict(va='%x' % va, n_ins=len(seq))
    if not seq:
        raw = m.read(va - m.base, 6)
        if len(raw) == 6 and raw[:2] == b'\xff\x25':
            tgt = va + 6 + int.from_bytes(raw[2:6], 'little', signed=True)
            slot = '%x' % (tgt - m.base)
            rec['IAT_THUNK'] = True
            rec['iat_slot_rva'] = slot
            rec['import'] = m.iat.get(slot)
            return rec
        rec['note'] = 'NO_FUNCTION_BOUNDARY'
        return rec
    if len(seq) >= 1 and seq[0].mnemonic == 'jmp' and 'rip' in seq[0].op_str:
        tgt = rip_target(m.cs, seq[0])
        rec['IAT_THUNK'] = True
        rec['iat_slot_rva'] = '%x' % (tgt - m.base)
        rec['import'] = m.iat.get(rec['iat_slot_rva'])
        return rec
    calls = []
    for x in seq:
        if not x.mnemonic.startswith('call'):
            continue
        c = dict(at='%x' % x.address, op='%s %s' % (x.mnemonic, x.op_str))
        if x.operands[0].type == capstone.CS_OP_IMM:
            c['direct'] = '%x' % x.operands[0].imm
        else:
            g = rip_target(m.cs, x)
            if g is not None:
                c['indirect_global'] = '%x' % g
                c['global_value_in_pe'] = None if global_value(m, g) is None else '%x' % global_value(m, g)
        calls.append(c)
    rec['calls'] = calls
    first = None
    branch_before = False
    for x in seq:
        if x.mnemonic.startswith('j'):
            branch_before = True
        if x.operands and x.operands[0].type == capstone.CS_OP_MEM and x.mnemonic.startswith(('mov', 'add', 'sub', 'and', 'or', 'xor')):
            first = dict(at='%x' % x.address, op='%s %s' % (x.mnemonic, x.op_str), branch_before=branch_before)
            break
    rec['first_store'] = first
    return rec


def main():
    pe, out = sys.argv[1], sys.argv[2]
    m = Machine(pe)
    m.iat = iat_names(m)
    rows = []
    for fn, call_at, callee in SITES:
        row = dict(fn=fn, call_at='%x' % call_at)
        if callee is None:
            ins0 = next(m.cs.disasm(m.read(call_at - m.base, 16), call_at))
            row['indirect_call_in_site'] = '%s %s' % (ins0.mnemonic, ins0.op_str)
        else:
            row['callee'] = describe(m, callee)
        rows.append(row)
    json.dump(dict(sites=rows), open(out, 'w'), indent=1)
    for r in rows:
        print(r['fn'], r['call_at'], r.get('callee', {}).get('IAT_THUNK', ''), len(r.get('callee', {}).get('calls', [])))


if __name__ == '__main__':
    main()
