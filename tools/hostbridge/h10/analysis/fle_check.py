#!/usr/bin/env python3
"""fle_check.py — event 212 (52 B) の u32@16 flags (0x10 = generator / 0x80) に関する FLEngine 側の主張を PE バイトから検査する.

対象: FLEngine_x64.dll (fl-win64 block00031_PE.bin)。pefile + capstone のみ (Ghidra 非依存)。
usage: fle_check.py <block00031_PE.bin> [--break <key>]   (key: flag80 | caller | type31)
"""
import re, struct, sys
import pefile, capstone

path = sys.argv[1]
brk = sys.argv[sys.argv.index('--break') + 1] if '--break' in sys.argv else None
pe = pefile.PE(path)
base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.skipdata = True
fails = 0


def check(name, ok, detail=''):
    global fails
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''))
    if not ok:
        fails += 1


def dis(va, n):
    return [(i.address, i.mnemonic, i.op_str) for i in md.disasm(img[va - base: va - base + n], va)]


def seq(ins, pats):
    """ins 内に pats (mnemonic, op_str の正規表現) が連続して現れる位置を返す"""
    for k in range(len(ins) - len(pats) + 1):
        if all(ins[k + j][1] == m and re.fullmatch(o, ins[k + j][2]) for j, (m, o) in enumerate(pats)):
            return ins[k][0]
    return None


# --- 1. 212 の書込 (fle:0xaac1e0): 52 B 領域 = [rbp+0x3c..], flags = +0x10 (rbp+0x4c), kind table → +8 (rbp+0x44)
w = dis(0xaac1e0, 0x110)
check('212 writer: 52 B (0x34) 領域を rbp+0x3c に確保', seq(w, [('lea', r'rcx, \[rbp \+ 0x3c\]'), ('mov', r'edx, 0x34')]) is not None)
f80 = '0x20' if brk == 'flag80' else '0x80'
a80 = seq(w, [('cmp', r'byte ptr \[rbx \+ 0x88\], 0'), ('je', r'.*'), ('or', rf'dword ptr \[rbp \+ 0x4c\], {f80}')])
check('212 writer: (writer ctx +0x88 != 0) → flags(+0x10) |= 0x80', a80 is not None)
a10 = seq(w, [('cmp', r'byte ptr \[rsi \+ 0x24\], 0'), ('je', r'.*'), ('or', r'dword ptr \[rbp \+ 0x4c\], 0x10')])
check('212 writer: (entry+0x24 = generator 判定 != 0) → flags(+0x10) |= 0x10', a10 is not None)
check('212 writer: u32@8 = kind table[kind] (rbp+0x44)', seq(w, [('mov', r'eax, dword ptr \[rcx \+ rax\*4\]'), ('mov', r'dword ptr \[rbp \+ 0x44\], eax')]) is not None)
check('212 writer: event id 0xd4 (=212)・長さ 0x34 で出力', seq(w, [('mov', r'rcx, qword ptr \[rbx \+ 0x38\]'), ('mov', r'edx, 0xd4'), ('lea', r'r8, \[rbp \+ 0x3c\]'), ('mov', r'r9d, 0x34')]) is not None)
tbl = struct.unpack('<4I', img[0x14e11d0 - base: 0x14e11d0 - base + 16])
check('212 u32@8 の kind table: kind 2,3 → 2 (DB の fx/gen 共通で 2)', tbl[2] == 2 and tbl[3] == 2, f'table[0..3]={tbl}')

# --- 2. 呼出元: fle:0xaac300 は fle:0xaba880 の 1 箇所のみ、4 番目引数 (= writer ctx +0x88 = 0x80 flag の源) は 0
c300 = dis(0xaac300, 0x60)
check('aac300: 4 番目引数 r9b を ctx+0x88 へ格納 (= 0x80 flag の源)', seq(c300, [('mov', r'byte ptr \[rbp \+ 0x88\], r9b')]) is not None)
refs = []
text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
lo = base + text.VirtualAddress
blob = img[lo - base: lo - base + max(text.Misc_VirtualSize, text.SizeOfRawData)]
for m in re.finditer(rb'[\xe8\xe9](....)', blob, re.S):
    if lo + m.start() + 5 + struct.unpack('<i', m.group(1))[0] == 0xaac300:
        refs.append(lo + m.start())
check('aac300 への直接 call は 1 件 (fle:0xababff)', refs == [0xababff] if brk != 'caller' else len(refs) == 2, str([hex(r) for r in refs]))
cs = dis(0xababe9, 0x20)
check('caller: edx=0x30 (plugin-state 形式), r9=0 (4 番目引数) で aac300 を呼ぶ → DB 生成経路で 0x80 は立たない',
      seq(cs, [('mov', r'edx, 0x30'), ('lea', r'r8, \[rbp \+ 0xc8\]'), ('xor', r'r9, r9'), ('call', r'0xaac300')]) is not None)
tbl28 = img[0x14e11c8 - base: 0x14e11c8 - base + 1][0]
check('event 28 の値 = table[param_4=0] = 1', tbl28 == 1, f'DAT_014e11c8[0]={tbl28}')

# --- 3. 読込側: .fst の種別判定 (fle:0xf54900) — 212 を peek して flags & 0x10 → 0x31 (generator) / 0x32 (effect)
r = dis(0xf54b01, 0x200)
ev = '0x31' if brk == 'type31' else '0x32'
chk = seq(r, [('mov', r'eax, dword ptr \[rbp \+ 0x6c\]'), ('test', r'eax, 0x10'), ('jne', r'.*'), ('mov', rf'dword ptr \[rip \+ 0x[0-9a-f]+\], {ev}')])
check('fst 種別判定: 212(len>0x14) の flags(+0x10) & 0x10 == 0 → type 0x32 (effect)', chk is not None)
chk2 = seq(r, [('mov', r'dword ptr \[rip \+ 0x[0-9a-f]+\], 0x31')])
check('fst 種別判定: flags & 0x10 != 0 → type 0x31 (generator)', chk2 is not None)
check('fst 種別判定: 212 は event 0xd4 かつ len == 0x34 の場合のみ解釈', seq(r, [('sub', r'eax, 0xd4'), ('test', r'eax, eax'), ('jne', r'.*'), ('mov', r'rax, qword ptr \[rbp \+ 0xa8\]'), ('cmp', r'qword ptr \[rax \+ 0x100024\], 0x34')]) is not None)

# --- 4. project 側 writer (fle:0xf3c870): 0x80 は「native kind==2 && cap 0x8000 && !(mode&4)」のみ
p = dis(0xf3c870 + 0x0, 0x500)
check('project writer: flags = ctx+0x34 & 0x30d (window state bits)', any(m == 'and' and o.endswith('0x30d') for _, m, o in p))
ors = sorted({o.split(', ')[1] for _, m, o in p if m == 'or' and o.startswith('dword ptr [rbp') and o.split(', ')[1] in ('0x10', '0x20', '0x40', '0x80')})
check('project writer: flags へ OR される bit = {0x10, 0x20, 0x40, 0x80}', ors == ['0x10', '0x20', '0x40', '0x80'], str(ors))

print(f'\nSUMMARY fle checks fails={fails} break={brk}')
sys.exit((0 if fails > 0 else 1) if brk else (1 if fails else 0))
