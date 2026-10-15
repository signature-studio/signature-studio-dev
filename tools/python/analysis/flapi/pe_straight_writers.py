#!/usr/bin/env python3
"""FLEngine PE の .text 全体で、フラグ用スロット (ポインタ格納先) を `mov reg, [rip+slot]` で読んだ直後の
直線区間から、そのレジスタを基底にした `mov byte ptr [reg], 値` を全数列挙する (PY-110 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_straight_writers.py [スロット VA(16進)[,...]]

既定のスロット: flagA 0x15e04a8 (→ 0x16baff0)・flagB 0x15e0ff0 (→ 0x16baff1)・flagC 0x15e1890 (→ 0x13e7628)。
走査: ロード命令の直後から逆アセンブルし、分岐・call・ret・int で止まる。
同じ族のレジスタ (rax/eax/ax/al/ah を同一視) を明示オペランドで書く命令、または暗黙に書く命令 (regs_write) で止まる。
書込み = 明示メモリオペランドで `op.access & CS_AC_WRITE`、基底がその族・index なし・disp 0。
走査は 0x200 バイトで打ち切る。
ネガティブコントロール: 暗黙オペランド (regs_write) だけで止める旧方式 (明示オペランドの書換えを見ない) の件数も出す。
検算の入口: スロットのロード数 (mov) と RIP 相対の参照総数 (pe_xref.py と同じ列挙) が一致することを確認する。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import sys
import time

import capstone
import pefile
from capstone import CS_AC_WRITE
from capstone.x86 import X86_OP_MEM, X86_OP_REG, X86_GRP_JUMP, X86_GRP_CALL, X86_GRP_RET, X86_GRP_INT, X86_GRP_IRET

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CHUNK = 1 << 16
MAXLEN = 0x200
FLAGS = {0x15E04A8: "A", 0x15E0FF0: "B", 0x15E1890: "C"}

FAMILY = {}
for _fam, _names in [
    ("rax", ("rax", "eax", "ax", "al", "ah")),
    ("rbx", ("rbx", "ebx", "bx", "bl", "bh")),
    ("rcx", ("rcx", "ecx", "cx", "cl", "ch")),
    ("rdx", ("rdx", "edx", "dx", "dl", "dh")),
    ("rsi", ("rsi", "esi", "si", "sil")),
    ("rdi", ("rdi", "edi", "di", "dil")),
    ("rbp", ("rbp", "ebp", "bp", "bpl")),
    ("rsp", ("rsp", "esp", "sp", "spl")),
] + [(f"r{i}", (f"r{i}", f"r{i}d", f"r{i}w", f"r{i}b")) for i in range(8, 16)]:
    for _n in _names:
        FAMILY[_n] = _fam


def fam_of(md, reg):
    name = md.reg_name(reg)
    return FAMILY.get(name, name)


def va_to_fo(pe, base, va):
    rva = va - base
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    raise ValueError(f"VA 0x{va:x} が section 外")


def is_branch(ins):
    return any(ins.group(g) for g in (X86_GRP_JUMP, X86_GRP_CALL, X86_GRP_RET, X86_GRP_INT, X86_GRP_IRET))


def walk(md, raw, pe, base, start, fam, explicit):
    """start から直線区間を走査し、fam 族を基底にした disp 0 の書込み命令 (ins) の列を返す。"""
    code = raw[va_to_fo(pe, base, start):][:MAXLEN + 16]
    out = []
    for ins in md.disasm(code, start):
        if ins.address - start >= MAXLEN or is_branch(ins):
            break
        ops = ins.operands
        for op in ops:
            if op.type == X86_OP_MEM and op.access & CS_AC_WRITE and op.mem.base != 0 \
                    and op.mem.index == 0 and op.mem.disp == 0 and fam_of(md, op.mem.base) == fam:
                out.append(ins)
                break
        stop = any(fam_of(md, r) == fam for r in ins.regs_write)
        if explicit:
            stop = stop or any(op.type == X86_OP_REG and op.access & CS_AC_WRITE and fam_of(md, op.reg) == fam
                               for op in ops)
        if stop:
            break
    return out


def main():
    slots = [int(x, 16) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else list(FLAGS)
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    t0 = time.time()
    n_ins = 0
    loads = []
    refs = {s: 0 for s in slots}
    for s in pe.sections:
        if not s.Characteristics & 0x20000000:
            continue
        start = base + s.VirtualAddress
        data = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        off = 0
        while off < len(data):
            end = off
            for ins in md.disasm(data[off:off + CHUNK + 16], start + off):
                if ins.address - start - off + ins.size > CHUNK:
                    break
                n_ins += 1
                end = ins.address - start + ins.size
                ops = ins.operands
                for i, op in enumerate(ops):
                    if op.type != X86_OP_MEM or op.mem.base != capstone.x86.X86_REG_RIP:
                        continue
                    tgt = ins.address + ins.size + op.mem.disp
                    if tgt not in refs:
                        continue
                    refs[tgt] += 1
                    if ins.mnemonic == "mov" and i == 1 and ops[0].type == X86_OP_REG:
                        loads.append((ins.address, ins.size, fam_of(md, ops[0].reg), tgt))
            off = end if end > off else off + 1
    loads.sort()
    t_sweep = time.time() - t0
    rows = {}
    naive = {}
    for la, lsz, fam, slot in loads:
        flag = FLAGS[slot]
        for st in walk(md, raw, pe, base, la + lsz, fam, explicit=True):
            rows.setdefault((flag, st.address), (st, la))
        for st in walk(md, raw, pe, base, la + lsz, fam, explicit=False):
            naive.setdefault((flag, st.address), st)
    print(f"instructions={n_ins} sweep_sec={t_sweep:.1f}")
    for s in slots:
        n_load = sum(1 for x in loads if x[3] == s)
        print(f"slot=0x{s:x} flag={FLAGS[s]} mov_loads={n_load} rip_refs={refs[s]}")
    for (flag, a), (st, la) in sorted(rows.items()):
        print(f"flag={flag} store=0x{a:x} {st.mnemonic} {st.op_str} <- load 0x{la:x}")
    for f in sorted(set(FLAGS[s] for s in slots)):
        print(f"flag={f} stores={sum(1 for k in rows if k[0] == f)} (naive regs_write のみ: {sum(1 for k in naive if k[0] == f)})")
    print(f"total stores={len(rows)} (naive regs_write のみ: {len(naive)}) sec={time.time() - t0:.1f}")


if __name__ == "__main__":
    main()
