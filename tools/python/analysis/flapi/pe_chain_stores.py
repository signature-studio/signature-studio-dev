#!/usr/bin/env python3
"""FLEngine PE の .text 全体で、ポインタの二重間接 (大域 G → Q スロット → Q 本体 → [Q+disp]) を追い、
その先の書込み (`mov [Q+disp], X`) と読出しを列挙する (PY-169 / #3212 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_chain_stores.py <G VA(16進)> [disp(16進, 既定 8)]

- G の PE ファイル上の値を Q スロットの VA とする (`[G] = Q スロットの VA`)。
- タグ: `QS` = Q スロットの VA (`mov r,[G]` の直後)、`QO` = Q の値 (`mov r,[QS]` または `mov r,[QS-ptr]`)、
  `QO+d` = Q 本体 + d の VA (`lea`)、`O` = `[Q+disp]` の値。
- 出力: (a) 同一関数内で `[QO+disp] ← X` の書込み (X が imm 0 か否か)、(b) `[QO+disp]` の読出し、
  (c) rcx に QO を載せて直接 call した先で `mov [rcx+disp], X` を行う箇所 (先頭 40 命令・rcx が
  書き換わるまで)。(c) の範囲は直接 E8 の call 先のみ。
- 走査は線形。ret・jmp で全タグを消し、call で caller-saved (rax,rcx,rdx,r8-r11) を消す。
  分岐の合流は考慮しない (タグは保守的に残るため、候補は手で逆アセして確定する)。

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import re
import struct
import sys
import time

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CHUNK = 1 << 16
CALLEE_WINDOW = 40
CALLER_SAVED = ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11")
X86 = capstone.x86


def canon(name):
    if name in ("ah", "bh", "ch", "dh"):
        return "r" + name[0] + "x"
    if name in ("al", "bl", "cl", "dl"):
        return "r" + name[0] + "x"
    if name in ("ax", "bx", "cx", "dx"):
        return "r" + name
    if name in ("sil", "dil", "bpl", "spl"):
        return "r" + name[:-1]
    if name in ("si", "di", "bp", "sp"):
        return "r" + name
    if re.fullmatch(r"e(ax|bx|cx|dx|si|di|bp|sp)", name):
        return "r" + name[1:]
    m = re.fullmatch(r"(r\d+)[dwb]", name)
    if m:
        return m.group(1)
    return name


def rip_target(ins, op):
    return ins.address + ins.size + op.mem.disp

def step(ins, tags, rows, callee_refs, g_va, q_slot, disp_want):
    ops = ins.operands
    mn = ins.mnemonic
    if mn == "ret" or mn == "jmp":
        tags.clear()
        return
    if mn == "call":
        if ops and ops[0].type == X86.X86_OP_IMM and tags.get("rcx") == ("QO", 0):
            callee_refs.append((ins.address, ops[0].imm))
        for r in CALLER_SAVED:
            tags.pop(r, None)
        return
    if len(ops) == 2 and ops[0].type == X86.X86_OP_REG and ops[0].size == 8 \
            and mn == "mov" and ops[1].type == X86.X86_OP_MEM:
        dst = canon(ins.reg_name(ops[0].reg))
        m = ops[1].mem
        new = None
        if m.base == X86.X86_REG_RIP and m.index == 0 and ops[1].size == 8:
            t = rip_target(ins, ops[1])
            if t == g_va:
                new = ("QS", 0)
            elif t == q_slot:
                new = ("QO", 0)
        elif m.base != 0 and m.index == 0:
            bt = tags.get(canon(ins.reg_name(m.base)))
            if bt == ("QS", 0) and m.disp == 0:
                new = ("QO", 0)
            elif bt and bt[0] == "QO" and bt[1] + m.disp == disp_want:
                new = ("O", 0)
                rows.append((ins.address, "load", f"{ins.mnemonic} {ins.op_str}", "-"))
        tags.pop(dst, None)
        if new is not None:
            tags[dst] = new
        return
    if len(ops) == 2 and mn == "mov" and ops[0].type == X86.X86_OP_MEM and ops[0].size == 8 \
            and ops[0].mem.base != 0 and ops[0].mem.base != X86.X86_REG_RIP and ops[0].mem.index == 0:
        b = canon(ins.reg_name(ops[0].mem.base))
        bt = tags.get(b)
        if bt and bt[0] == "QO" and bt[1] + ops[0].mem.disp == disp_want:
            if ops[1].type == X86.X86_OP_IMM:
                kind = "zero" if ops[1].imm == 0 else f"imm 0x{ops[1].imm & (2**64 - 1):x}"
            elif ops[1].type == X86.X86_OP_REG:
                kind = f"reg {ins.reg_name(ops[1].reg)}"
            else:
                kind = "mem"
            rows.append((ins.address, "store", f"{ins.mnemonic} {ins.op_str}", kind))
        return
    if mn == "lea" and len(ops) == 2 and ops[0].type == X86.X86_OP_REG and ops[1].type == X86.X86_OP_MEM:
        dst = canon(ins.reg_name(ops[0].reg))
        m = ops[1].mem
        new = None
        if m.base != 0 and m.base != X86.X86_REG_RIP and m.index == 0:
            bt = tags.get(canon(ins.reg_name(m.base)))
            if bt and bt[0] == "QO":
                new = ("QO", bt[1] + m.disp)
        tags.pop(dst, None)
        if new is not None:
            tags[dst] = new
        return
    if mn == "mov" and len(ops) == 2 and ops[0].type == X86.X86_OP_REG and ops[1].type == X86.X86_OP_REG \
            and ops[0].size == 8 and ops[1].size == 8:
        dst = canon(ins.reg_name(ops[0].reg))
        src = canon(ins.reg_name(ops[1].reg))
        t = tags.get(src)
        tags.pop(dst, None)
        if t is not None:
            tags[dst] = t
        return
    if ops and ops[0].type == X86.X86_OP_REG:
        tags.pop(canon(ins.reg_name(ops[0].reg)), None)


def main():
    g_va = int(sys.argv[1], 16)
    disp_want = int(sys.argv[2], 16) if len(sys.argv) > 2 else 8
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(base + s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData),
             s.PointerToRawData, s.SizeOfRawData, s) for s in pe.sections]

    def read_va(va, n):
        for st, sz, praw, rsz, _ in secs:
            if st <= va < st + sz:
                off = va - st
                if off + n > rsz:
                    return None
                return raw[praw + off:praw + off + n]
        return None

    q_slot = struct.unpack("<Q", read_va(g_va, 8))[0]
    print(f"G=0x{g_va:x} file_value(Q slot)=0x{q_slot:x} disp=0x{disp_want:x}")
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    t0 = time.time()
    n_ins = 0
    rows = []
    callee_refs = []
    text = [s for s in secs if s[4].Characteristics & 0x20000000]

    for st, sz, praw, rsz, s in text:
        data = raw[praw:praw + rsz]
        off = 0
        tags = {}
        while off < len(data):
            end = off
            for ins in md.disasm(data[off:off + CHUNK + 16], st + off):
                if ins.address - st - off + ins.size > CHUNK:
                    break
                n_ins += 1
                end = ins.address - st + ins.size
                step(ins, tags, rows, callee_refs, g_va, q_slot, disp_want)
            if end > off:
                off = end
            else:
                off += 1
                tags = {}

    callee_hits = []
    for call_va, callee in callee_refs:
        cb = read_va(callee, CALLEE_WINDOW * 16)
        if cb is None:
            continue
        rcx_live = True
        for ins in md.disasm(cb, callee):
            if ins.mnemonic in ("ret", "jmp", "call"):
                break
            ops = ins.operands
            if rcx_live and len(ops) == 2 and ops[0].type == X86.X86_OP_MEM and ops[0].size == 8 \
                    and ops[0].mem.base != 0 and canon(ins.reg_name(ops[0].mem.base)) == "rcx" \
                    and ops[0].mem.index == 0 and ops[0].mem.disp == disp_want:
                kind = ("zero" if ops[1].type == X86.X86_OP_IMM and ops[1].imm == 0
                        else f"imm 0x{ops[1].imm & (2**64 - 1):x}" if ops[1].type == X86.X86_OP_IMM
                        else f"reg {ins.reg_name(ops[1].reg)}" if ops[1].type == X86.X86_OP_REG else "mem")
                callee_hits.append((ins.address, call_va, callee, f"{ins.mnemonic} {ins.op_str}", kind))
            if ops and ops[0].type == X86.X86_OP_REG and canon(ins.reg_name(ops[0].reg)) == "rcx":
                rcx_live = False
            if not rcx_live:
                break

    for a, kind, op, val in rows:
        print(f"0x{a:x} {kind} {op} ; {val}")
    for a, call_va, callee, op, val in callee_hits:
        print(f"0x{a:x} callee-store {op} ; {val} (rcx=QO at call 0x{call_va:x} -> callee 0x{callee:x})")
    n_store = sum(1 for r in rows if r[1] == "store")
    n_load = sum(1 for r in rows if r[1] == "load")
    print(f"instructions={n_ins} intra_store={n_store} intra_load={n_load} "
          f"callee_refs={len(callee_refs)} callee_store={len(callee_hits)} sec={time.time() - t0:.1f}")


if __name__ == "__main__":
    main()
