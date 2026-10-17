#!/usr/bin/env python3
# indirect_slots_5655.py: #5655 (LD-282) callee_closure_5655.py の閉包内の間接 call `call [rip+disp]` の slot を
# PE ファイル上の値に突き合わせる。slot の値が閉包内の関数 VA か、import (.idata) か、0 (未初期化) かを分類する。
# 使い方: python3 indirect_slots_5655.py <block00031_PE.bin> [深さ上限]
# 限界: 実行時に書き換えられる slot (GetProcAddress 結果・初期化コードの代入) は、ファイル上の値では確定しない。
#       その場合は種別 'runtime-written?' を付ける (閉包内で slot への store を検出したものだけ)。
import sys
import capstone
import pefile

ROOTS = [0x40f910, 0x4493b0]
DEPTH = int(sys.argv[2]) if len(sys.argv) > 2 else 40

pe = pefile.PE(sys.argv[1], fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
secs = [(base + s.VirtualAddress, base + s.VirtualAddress + s.Misc_VirtualSize,
         s.Name.rstrip(b'\0').decode(errors='replace')) for s in pe.sections]
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
X86 = capstone.x86


def sec(va):
    for lo, hi, n in secs:
        if lo <= va < hi:
            return n
    return '?'


def body(va):
    out = []
    for i in md.disasm(pe.get_data(va - base, 0x8000), va):
        if i.mnemonic == 'int3':
            break
        out.append(i)
    return out


def direct_calls(ins):
    return [i.operands[0].imm for i in ins
            if i.mnemonic == 'call' and i.operands and i.operands[0].type == X86.X86_OP_IMM]


def indirect_slots(ins):
    slots = []
    for i in ins:
        if i.mnemonic == 'call' and i.operands and i.operands[0].type == X86.X86_OP_MEM \
                and i.operands[0].mem.base == X86.X86_REG_RIP:
            slots.append((i.address, i.address + i.size + i.operands[0].mem.disp))
    return slots


# 閉包 (callee_closure_5655.py と同じ direct call の BFS)
seen, order = {}, []
queue = [(r, 0) for r in ROOTS]
while queue:
    fn, d = queue.pop(0)
    if fn in seen:
        continue
    ins = body(fn)
    seen[fn] = ins
    order.append(fn)
    if d < DEPTH:
        for c in direct_calls(ins):
            if c not in seen:
                queue.append((c, d + 1))

# store 先が slot かどうか (閉包内の RIP 相対 store)
store_targets = {}
for fn in order:
    for i in seen[fn]:
        if i.operands and i.operands[0].type == X86.X86_OP_MEM and i.operands[0].mem.base == X86.X86_REG_RIP \
                and i.mnemonic in ('mov', 'lea', 'xchg', 'add', 'sub', 'or', 'and', 'xor'):
            t = i.address + i.size + i.operands[0].mem.disp
            store_targets.setdefault(t, []).append((fn, i.address))

rows = []
for fn in order:
    for call_va, slot in indirect_slots(seen[fn]):
        raw = pe.get_data(slot - base, 8)
        val = int.from_bytes(raw, 'little')
        if slot in store_targets:
            kind = 'runtime-written?'
        elif sec(slot) == '.idata' or sec(slot) == '?':
            kind = 'import-or-unknown'
        elif val == 0:
            kind = 'zero-in-file'
        elif any(lo <= val < hi for lo, hi, n in secs if n == '.text'):
            kind = 'text-pointer'
        else:
            kind = 'other'
        rows.append((hex(fn), hex(call_va), hex(slot), sec(slot), hex(val), kind,
                     [hex(f) for f, _ in store_targets.get(slot, [])][:3]))

print('indirect call sites in closure: %d (distinct slots: %d)'
      % (len(rows), len({r[2] for r in rows})))
for r in rows:
    print('fn=%s call=%s slot=%s(%s) file_value=%s kind=%s stored_by=%s' % r)
