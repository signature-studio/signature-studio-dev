#!/usr/bin/env python3
"""Recover the FLP *load* switch of FLEngine_x64.dll (Win, FL 26.1.7): event id -> handler VA.

The reader loop is FlpLoad = VA 0xf46490..0xf50e06 (43,382 B). Each iteration calls the stream reader
0xa9e7a0 (reads the id byte, or 0xAC + u32 for extended ids, then the payload into stream+0x100020..) and
dispatches on `eax = [stream + 0x100020]` at VA 0xf46bff. The compiler lowered the `case` to a binary tree of
cmp/sub/test + jcc, so the table is recovered by *executing that tree symbolically* for every id 0..0x100.
Handlers that fall to the epilogue VA 0xf4ec9c without touching state are "default" (id ignored on load).

Usage: load_switch.py [FLEngine_x64.dll] [out.json]     (needs: pip install pefile capstone)
"""
import json, struct, sys
import capstone
import pefile

DLL = sys.argv[1] if len(sys.argv) > 1 else 'extracted/block00031_PE.bin'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'corpus/load_switch.json'
FUNC, FUNC_SIZE = 0xF46490, 43382  # FlpLoad (from .pdata RUNTIME_FUNCTION containing the 0xa9e7a0 call at 0xf46ba4)
DISPATCH = 0xF46BFF  # `mov eax, [rax+0x100020]` right before the first compare
DEFAULT_ARM = 0xF4EC9C  # shared epilogue of every handler = also the target of ids with no case

pe = pefile.PE(DLL, fast_load=True)
data = open(DLL, 'rb').read()
base = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
tva = base + text.VirtualAddress
code = data[text.PointerToRawData:text.PointerToRawData + text.Misc_VirtualSize]
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
off = FUNC - tva
ins = {i.address: i for i in md.disasm(code[off:off + FUNC_SIZE], FUNC)}
s32 = lambda x: x - (1 << 32) if x & 0x80000000 else x
imm = lambda i: int(i.op_str.split(',')[1].strip(), 0) & 0xFFFFFFFF


def walk(v):
    """follow the compare tree for id v; returns the handler VA (or raises on an unmodelled jcc)"""
    a, cur, fl = DISPATCH, v & 0xFFFFFFFF, None
    for _ in range(400):
        i = ins[a]
        m, o = i.mnemonic, i.op_str
        if m == 'mov' and o == 'eax, dword ptr [rax + 0x100020]':
            cur = v
        elif m == 'cmp' and o.startswith(('eax, ', 'ecx, ')):
            fl = (cur, imm(i), 'cmp')
        elif m == 'test' and o == 'eax, eax':
            fl = (cur, 0, 'test')
        elif m == 'sub' and o.startswith('eax, '):
            cur = (cur - imm(i)) & 0xFFFFFFFF
            fl = (cur, 0, 'res')
        elif m == 'add' and o.startswith('eax, '):
            cur = (cur + imm(i)) & 0xFFFFFFFF
            fl = (cur, 0, 'res')
        elif m == 'jmp' and i.operands[0].type == capstone.x86.X86_OP_IMM:
            a = i.operands[0].imm
            continue
        elif m.startswith('j') and fl:
            l, r, k = fl
            sl, sr = (s32(l), s32(r)) if k == 'cmp' else (s32(l), 0)
            ul, ur = (l, r) if k == 'cmp' else (l, 0)
            c = {'je': l == r if k == 'cmp' else l == 0, 'jne': l != r if k == 'cmp' else l != 0, 'jg': sl > sr, 'jge': sl >= sr, 'jl': sl < sr, 'jle': sl <= sr}.get(m)
            if c is None and k != 'res':
                c = {'ja': ul > ur, 'jae': ul >= ur, 'jb': ul < ur, 'jbe': ul <= ur}.get(m)
            if c is None:
                raise RuntimeError(f'unmodelled {m} at {a:#x} for id {v:#x}')
            a = i.operands[0].imm if c else a + i.size
            continue
        else:
            return a
        a += i.size
    raise RuntimeError(f'no terminal for id {v:#x}')


table = {}
for v in range(0, 0x101):
    t = walk(v)
    table[v] = t
handled = {v: a for v, a in table.items() if a != DEFAULT_ARM}
out = {
    'dll': 'FLEngine_x64.dll 26.1.7 (win64 installer block00031_PE.bin)',
    'imageBase': hex(base),
    'flpLoad': {'va': hex(FUNC), 'size': FUNC_SIZE, 'streamReader': '0xa9e7a0', 'dispatchVa': hex(DISPATCH), 'defaultArmVa': hex(DEFAULT_ARM)},
    'counts': {'idsProbed': len(table), 'handled': len(handled), 'defaultArm': len(table) - len(handled)},
    'handlers': {str(v): hex(a) for v, a in sorted(handled.items())},
    'defaultArmIds': [v for v, a in sorted(table.items()) if a == DEFAULT_ARM],
}
json.dump(out, open(OUT, 'w'), indent=1)
print(f"{len(handled)} ids have a case handler, {len(table) - len(handled)} fall to the default arm (ids 0..0x100)")
