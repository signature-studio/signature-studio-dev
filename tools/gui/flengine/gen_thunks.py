#!/usr/bin/env python3
"""GUI-3 (#174): PE の import thunk (`jmp [rip+IAT]`) のうち WNDPROC として渡され得る DefWindowProc{A,W} の VA を列挙し C 表にする。
FLEngine は WNDCLASS.lpfnWndProc に DefWindowProcW の import thunk (例 TApplication: 0x24920) をそのまま置く。thunk は lift closure の関数ではない
(m11_icall が miss する) ため、GUI shim の icall hook 側で shim の DefWindowProc に解決する。
  gen_thunks.py <PE> <out.c> [lb_base]   (LVA = RVA + lb_base)"""
import re, struct, sys
import pefile
pe_path, out = sys.argv[1], sys.argv[2]
lb = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
pe = pefile.PE(pe_path, fast_load=False)
ib = pe.OPTIONAL_HEADER.ImageBase
want = {b'DefWindowProcW': 1, b'DefWindowProcA': 2}
slots = {}
for ent in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
    for imp in ent.imports:
        if imp.name in want and imp.address:
            slots[imp.address - ib] = want[imp.name]
rows = []
for s in pe.sections:
    if not (s.Characteristics & 0x20000000):   # IMAGE_SCN_MEM_EXECUTE
        continue
    d = s.get_data()
    for m in re.finditer(rb'\xff\x25(....)', d, re.S):
        rva = s.VirtualAddress + m.start()
        tgt = rva + 6 + struct.unpack('<i', m.group(1))[0]
        if tgt in slots:
            rows.append((rva + lb, slots[tgt]))
with open(out, 'w') as f:
    f.write('/* gen_thunks.py 生成: WNDPROC として渡され得る import thunk の LVA。kind 1=DefWindowProcW 2=DefWindowProcA */\n')
    f.write('const unsigned long long gf_thunk_va[] = {%s};\nconst int gf_thunk_kind[] = {%s};\nconst int gf_thunk_n = %d;\n' % (
        ', '.join('0x%x' % r[0] for r in rows) or '0', ', '.join(str(r[1]) for r in rows) or '0', len(rows)))
print('[gen_thunks] DefWindowProc import slots=%d thunks=%d -> %s' % (len(slots), len(rows), out))
