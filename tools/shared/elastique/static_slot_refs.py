#!/usr/bin/env python3
"""thunk 頭 33 本の枠 (.data/.rdata の 8 byte 値) を RIP 相対で読む命令を静的に数える (T-SH-69 / #3334・付録 §9.6)。

入力: ELASTIQUE_DLL = tools/shared/work/win/elastique_x64.dll (FL 素材 block24357_PE.bin の複製)
手順:
  1. .data/.rdata の 8 byte 値 (8 byte 整列) のうち、.text を指し、先頭命令が `call 0x1803e71b0` のものを thunk 頭とする
     (dyn_trace.py と同じ条件)。その 8 byte の番地を枠とする。
  2. thunk 本体 = [最小の頭, 最大の頭を含む 4 KiB ページの末尾)。枠の範囲 = [最小の枠, 最大の枠 + 0x40)
     (付録 §9.6 の範囲。末尾を +8 にすると範囲内の mov 1 件 (0x1804b08f8) が外れる)。
  3. .text を線形走査 (invalid byte は 1 byte 飛ばす) し、rip 相対のメモリ参照の参照先 (次命令の番地 + 変位) が
     枠の範囲に入るものを数える。thunk 本体の内外に分け、命令の種別・参照先の 8 byte 値を出す。
出力: 標準出力 (件数と一覧)。
"""
import collections
import os
import struct

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.environ.get('ELASTIQUE_DLL', os.path.join(HERE, '..', 'work', 'win', 'elastique_x64.dll'))
ENTRY_INIT = '0x1803e71b0'
STRIDE = 0x40
CH = 1 << 16


def main():
    pe = pefile.PE(DLL, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    mem = pe.get_memory_mapped_image()
    secs = {s.Name.rstrip(b'\0').decode(errors='replace'): s for s in pe.sections}
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    t = secs['.text']
    t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize

    heads, slots = set(), []
    for name in ('.data', '.rdata'):
        s = secs[name]
        for rva in range(s.VirtualAddress, s.VirtualAddress + s.Misc_VirtualSize - 7, 8):
            v = struct.unpack_from('<Q', mem, rva)[0]
            if not (ib + t_lo <= v < ib + t_hi):
                continue
            ins = next(md.disasm(mem[v - ib:v - ib + 16], v), None)
            if ins is not None and ins.mnemonic == 'call' and ins.op_str == ENTRY_INIT:
                heads.add(v)
                slots.append(ib + rva)
    slots.sort()
    thunk_lo = min(heads)
    thunk_hi = (max(heads) + 0xFFF) & ~0xFFF
    slot_lo, slot_hi = slots[0], slots[-1] + STRIDE
    print(f'thunk 頭: {len(heads)} 本 (distinct) / 枠: {len(slots)} 個')
    print(f'thunk 本体: [{thunk_lo:#x}, {thunk_hi:#x}) / 枠の範囲: [{slot_lo:#x}, {slot_hi:#x})')

    counts = collections.Counter()
    refs = []

    def on(ins):
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                tgt = ins.address + ins.size + op.mem.disp
                if slot_lo <= tgt < slot_hi:
                    inside = thunk_lo <= ins.address < thunk_hi
                    counts[(inside, ins.mnemonic)] += 1
                    refs.append((ins.address, ins.mnemonic, ins.op_str, tgt, inside))

    pos = t_lo
    while pos < t_hi:
        end = min(t_hi, pos + CH)
        last = None
        for ins in md.disasm(mem[pos:min(end + 16, len(mem))], ib + pos):
            rva = ins.address - ib
            if rva >= end:
                break
            last = rva + ins.size
            on(ins)
        pos = last if last is not None and last > pos else pos + 1

    n_in = sum(v for (i, _), v in counts.items() if i)
    n_out = sum(v for (i, _), v in counts.items() if not i)
    print(f'枠を指す rip 相対の参照 (.text 全体): 本体の内 {n_in}・本体の外 {n_out}')
    for (i, m), v in sorted(counts.items()):
        print(f'  {"内" if i else "外"} {m}: {v}')
    for a, m, op, tgt, inside in refs:
        if inside and m != 'lea':
            val = struct.unpack_from('<Q', mem, tgt - ib)[0]
            print(f'  本体内の {m} 以外: {a:#x} {m} {op} -> {tgt:#x} (枠か: {tgt in slots}・値 {val:#x})')
    for a, m, op, tgt, inside in refs:
        if not inside:
            print(f'  本体の外: {a:#x} {m} {op} -> {tgt:#x}')


if __name__ == '__main__':
    main()
