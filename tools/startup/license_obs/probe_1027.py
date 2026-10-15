"""#1027: 関数ポインタ表 (T1 = 0x11740f5 idx27 ∋ 0x11cb000 / T2 = 0x1378820 idx660 ∋ 0x10d50d0) の起動元 (読取専用)。usage: python probe_1027.py

表の参照形を全て走査する:
  a) 命令オペランドに表範囲 (VA) を含む命令 (絶対 disp32 / 即値 / rip 相対の解決先)
  b) 同じ範囲を RVA で書いた命令 (`[rip+disp]` の変位ではなく、即値・disp の RVA 値)
  c) 対象アドレスの rva32 / abs64 がデータとして現れる箇所 (所属セクションを表示)
"""
import os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from peidx import RIP, Image, rip_target  # noqa: E402

img = Image()
HEX = re.compile(r'0x[0-9a-f]+')
TABLES = [('T1', 0x11740f5, 42, 0x11cb000), ('T2', 0x1378820, 826, 0x10d50d0)]


def sec_name(off):
    s = next((s for s in img.pe.sections if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData), None)
    return s.Name.rstrip(b'\0').decode() if s else '?'


for name, lo, n, tgt in TABLES:
    hi = lo + n * 8
    print(f'== {name} {hex(lo)}..{hex(hi)}')
    a = []
    b = []
    for flo, fhi, ins_list in img.iter_insns():
        for ins in ins_list:
            vals = [int(h, 16) for h in HEX.findall(ins.op_str)]
            rt = rip_target(ins)
            if rt is not None:
                vals.append(rt)
            if any(lo <= v < hi for v in vals):
                a.append((flo, ins))
            if ins.mnemonic.startswith('j') or ins.mnemonic == 'call':
                continue
            imm = [int(h, 16) for h in HEX.findall(RIP.sub('', ins.op_str))]
            if any(lo - img.base <= v < hi - img.base for v in imm):
                b.append((flo, ins))
    print(f'  a) VA 参照 {len(a)} 件')
    for f, ins in a[:10]:
        print(f'     {hex(ins.address)} in {hex(f)}: {ins.mnemonic} {ins.op_str}')
    print(f'  b) RVA 参照 {len(b)} 件')
    for f, ins in b[:10]:
        print(f'     {hex(ins.address)} in {hex(f)}: {ins.mnemonic} {ins.op_str}')
    for label, q in [('rva32', struct.pack('<I', tgt - img.base)), ('abs64', struct.pack('<Q', tgt))]:
        i = img.raw.find(q)
        locs = []
        while i != -1:
            locs.append(f'{hex(i)}({sec_name(i)})')
            i = img.raw.find(q, i + 1)
        print(f'  c) {label} of {hex(tgt)}: {locs}')
    for label, q in [('rva32', struct.pack('<I', lo - img.base)), ('abs64', struct.pack('<Q', lo))]:
        i = img.raw.find(q)
        locs = []
        while i != -1:
            locs.append(f'{hex(i)}({sec_name(i)})')
            i = img.raw.find(q, i + 1)
        print(f'  d) {label} of table base {hex(lo)}: {locs}')
