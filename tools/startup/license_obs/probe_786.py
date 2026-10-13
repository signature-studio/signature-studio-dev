"""#786: gradeChar 書込み経路の個別確認 (読取専用)。usage: python probe_786.py

1) 0x10d3a30 / 0x11cb000 の gradeChar 書込み (`mov byte ptr [rcx], 0x3f`) の直接呼出し元
2) 0x11cb000 / 0x10d50d0 の参照元 (関数ポインタ表の有無)
3) 0x10d50d0 のループ条件 (`add byte [rax],1` ... `cmp ecx,0x4a`)
"""
import os, re, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from peidx import Image  # noqa: E402

img = Image()
RIP = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')


def calls_to(t):
    out = []
    for lo, hi, ins_list in img.iter_insns():
        for ins in ins_list:
            if ins.mnemonic == 'call' and ins.op_str.startswith('0x') and int(ins.op_str, 16) == t:
                out.append((lo, ins.address))
    return out


def rip_refs(t):
    out = []
    for lo, hi, ins_list in img.iter_insns():
        for ins in ins_list:
            m = RIP.search(ins.op_str)
            if m and ins.address + ins.size + int(m.group(2), 16) * (1 if m.group(1) == '+' else -1) == t:
                out.append((lo, ins.address))
    return out


def file_to_va(o):
    s = next(s for s in img.pe.sections if s.PointerToRawData <= o < s.PointerToRawData + s.SizeOfRawData)
    return img.base + s.VirtualAddress + (o - s.PointerToRawData)


def abs64_refs(t):
    q = struct.pack('<Q', t)
    out, i = [], img.raw.find(q)
    while i != -1:
        out.append(file_to_va(i))
        i = img.raw.find(q, i + 1)
    return out


print('== 1) 直接 call 元 (gradeChar 書込みを含む関数)')
for t in [0x10d3a30, 0x11cb000, 0x10d50d0, 0x10c7cd0]:
    cs = calls_to(t)
    print(f'  {hex(t)}: call {len(cs)} 件 ' + ', '.join(f'{hex(a)} (in {hex(f)})' for f, a in cs))

print('== 2) 参照元 (rip 相対 / 絶対 64bit)')
for t in [0x11cb000, 0x10d50d0, 0x10d3a30]:
    r = rip_refs(t)
    a = abs64_refs(t)
    print(f'  {hex(t)}: rip-relative {len(r)} 件 / abs64 {len(a)} 件 ' + ' '.join(hex(v) for v in a[:3]))

print('== 3) 0x10d50d0 のループ (0x10d52f9-0x10d531b) の命令')
f = 0x10d50d0
hi = [e for b, e in img.funcs if b == f][0]
for ins in img.disasm_func(f, hi):
    if 0x10d52e3 <= ins.address <= 0x10d531b:
        print(f'  {hex(ins.address)}: {ins.mnemonic} {ins.op_str}')
