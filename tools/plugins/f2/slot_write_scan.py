"""PE 内の実行可能セクション (IMAGE_SCN_MEM_EXECUTE) 全てを走査し、指定 VA 範囲への直接アクセス (RIP 相対 / 絶対 disp) と再配置の有無を数える。

使い方: python3 slot_write_scan.py <block_PE.bin> <lo_hex> <hi_hex>
逆アセンブルは capstone の線形スイープ (失敗時 1 バイト進む)。間接ポインタ経由の書込みは対象外。
実行不能セクション (データ・再配置等) は命令を持たないため走査しない。
"""
import sys

import capstone
import pefile

IMAGE_SCN_MEM_EXECUTE = 0x20000000

pe = pefile.PE(sys.argv[1], fast_load=False)
base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
lo, hi = int(sys.argv[2], 16), int(sys.argv[3], 16)
exec_secs = [s for s in pe.sections if s.Characteristics & IMAGE_SCN_MEM_EXECUTE]

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
X86_MEM = capstone.x86.X86_OP_MEM
X86_RIP = capstone.x86.X86_REG_RIP


def sweep(code, sva):
    off = 0
    while off < len(code):
        got = list(md.disasm(code[off:off + 16], sva + off, count=1))
        if not got:
            off += 1
            continue
        yield got[0]
        off += got[0].size


rw = []
for sec in exec_secs:
    sva = base + sec.VirtualAddress
    code = img[sec.VirtualAddress:sec.VirtualAddress + sec.Misc_VirtualSize]
    for ins in sweep(code, sva):
        for i, op in enumerate(ins.operands):
            if op.type != X86_MEM:
                continue
            if op.mem.base == X86_RIP:
                ea = ins.address + ins.size + op.mem.disp
            elif op.mem.base == 0 and op.mem.index == 0:
                ea = op.mem.disp & 0xFFFFFFFFFFFFFFFF
            else:
                continue
            if lo <= ea < hi and ins.mnemonic != "lea":
                kind = "W" if i == 0 and ins.mnemonic.startswith("mov") else "RW?"
                rw.append((hex(ins.address), kind, ins.mnemonic, ins.op_str))

reloc = 0
for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
    for e in b.entries:
        if e.type == 0:
            continue
        rva = b.struct.VirtualAddress + (e.struct.Data & 0xFFF)
        if lo - base <= rva < hi - base:
            reloc += 1

print("exec sections:", ", ".join(s.Name.rstrip(b"\0").decode() for s in exec_secs))
print("range", hex(lo), hex(hi), "relocs overlapping:", reloc)
print("direct accesses (rip/abs disp), excluding lea:", len(rw))
for r in rw:
    print(*r)
