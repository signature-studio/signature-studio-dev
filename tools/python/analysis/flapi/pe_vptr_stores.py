#!/usr/bin/env python3
"""FLEngine PE の .text 全体で、`lea reg, [rip+V]` の直後 (8 命令以内) に `mov qword ptr [reg2+disp], reg` で
V を格納する箇所を列挙し、V の vtable の slot +0x20 と +8 の関数 VA を出す (PY-103 / #2887 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_vptr_stores.py <disp(16進)>

- 対象: vptr (vtable 先頭の VA) を `[obj+disp]` に書く箇所。disp は埋め込み基底のオフセット (例: 0x48)。
- 出力: 格納先 VA・格納する V (vtable の VA)・V の slot +0x20 と +8 の内容 (ファイル上の値)。
- 追跡は直線区間だけ (call・ret・jmp で打ち切る)。レジスタの書換えは 32/16/8 bit 別名を同一視して無効化する。
- 線形走査は無効バイトで止まるため、止まったら 1 バイト進めて再同期する (pe_xref.py と同じ方式)。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import struct
import sys
import time

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CHUNK = 1 << 16
WIN = 8


def family_map():
    fam = {}
    for x in "abcd":
        full = "r" + x + "x"
        for name in (full, "e" + x + "x", x + "x", x + "l", x + "h"):
            fam[name] = full
    for s in ("si", "di", "bp", "sp"):
        full = "r" + s
        for name in (full, "e" + s, s, s + "l"):
            fam[name] = full
    for n in range(8, 16):
        full = f"r{n}"
        for name in (full, full + "d", full + "w", full + "b"):
            fam[name] = full
    return fam


FAM = family_map()


def read_qword(raw, sections, base, va):
    rva = va - base
    for s in sections:
        size = max(s.Misc_VirtualSize, s.SizeOfRawData)
        if s.VirtualAddress <= rva < s.VirtualAddress + size and rva - s.VirtualAddress + 8 <= s.SizeOfRawData:
            fo = s.PointerToRawData + (rva - s.VirtualAddress)
            return struct.unpack_from("<Q", raw, fo)[0]
    return None


def is_vtable(raw, sections, base, va):
    first = read_qword(raw, sections, base, va)
    if first is None:
        return False
    for s in sections:
        if s.Characteristics & 0x20000000 and base + s.VirtualAddress <= first < base + s.VirtualAddress + s.Misc_VirtualSize:
            return True
    return False


def main():
    disp = int(sys.argv[1], 16)
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    t0 = time.time()
    n_ins = 0
    hits = []
    for s in pe.sections:
        if not s.Characteristics & 0x20000000:
            continue
        start = base + s.VirtualAddress
        data = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        off = 0
        lea = {}
        seq = 0
        while off < len(data):
            end = off
            for ins in md.disasm(data[off:off + CHUNK + 16], start + off):
                if ins.address - start - off + ins.size > CHUNK:
                    break
                n_ins += 1
                end = ins.address - start + ins.size
                seq += 1
                ops = ins.operands
                if ins.mnemonic == "mov" and len(ops) == 2 and ops[0].type == capstone.x86.X86_OP_MEM \
                        and ops[0].mem.base not in (capstone.x86.X86_REG_RIP, capstone.x86.X86_REG_RBP,
                                                    capstone.x86.X86_REG_RSP) \
                        and ops[0].mem.disp == disp and ops[0].mem.index == 0 and ops[0].size == 8 \
                        and ops[1].type == capstone.x86.X86_OP_REG:
                    src = FAM.get(ins.reg_name(ops[1].reg))
                    if src in lea and seq - lea[src][1] <= WIN and is_vtable(raw, pe.sections, base, lea[src][0]):
                        hits.append((ins.address, lea[src][0], ins.op_str))
                if ins.mnemonic in ("call", "ret", "jmp"):
                    lea.clear()
                elif ins.mnemonic == "lea" and len(ops) == 2 and ops[1].type == capstone.x86.X86_OP_MEM \
                        and ops[1].mem.base == capstone.x86.X86_REG_RIP and ops[0].type == capstone.x86.X86_OP_REG:
                    v = ins.address + ins.size + ops[1].mem.disp
                    lea[FAM.get(ins.reg_name(ops[0].reg))] = (v, seq)
                elif ops and ops[0].type == capstone.x86.X86_OP_REG and ins.mnemonic not in ("cmp", "test", "push"):
                    lea.pop(FAM.get(ins.reg_name(ops[0].reg)), None)
            off = end if end > off else off + 1
    for addr, v, ops in hits:
        s0 = read_qword(raw, pe.sections, base, v + 0x20)
        s8 = read_qword(raw, pe.sections, base, v + 8)
        f = lambda x: "-" if x is None else f"0x{x:x}"
        print(f"0x{addr:x} vtbl=0x{v:x} slot+0x20={f(s0)} slot+8={f(s8)} | mov [..+0x{disp:x}], {ops}")
    print(f"instructions={n_ins} hits={len(hits)} disp=0x{disp:x} sec={time.time() - t0:.1f}")


if __name__ == "__main__":
    main()
