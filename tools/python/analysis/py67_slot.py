#!/usr/bin/env python3
"""PY-71 (#2501): スロット (RIP 相対で指す .data/.bss の値) の参照を列挙し、値の流れを近似で追う (実機不要)。

  python3 analysis/py67_slot.py <PE.bin> <slot VA hex>[,...] [fwd_insns] [back_insns]

1. .text を 1 回だけ線形走査し、RIP 相対の disp が slot と一致する命令を出す (load / store / lea)。
   fn= は関数先頭の近似 (int3 パディングの直後の命令)。
2. 各参照の前後 0x100 バイトを逆アセンブルした窓の中で:
   - load (mov reg, [slot]) / lea (lea reg, [slot]): reg に slot (またはその値のアドレス) が入ったとみなし、
     後続 fwd_insns 命令で reg の伝播を追う。reg 経由の STORE (書込み先 [slot値+d])・
     間接 call (call [reg+d])・直接 call の引数レジスタ (rcx/rdx/r8/r9) への受け渡しを出す。
   - store (mov [slot], reg): reg を最後に書いた命令を直前 back_insns 命令から探す (値の出所)。
制限: 窓外・メモリ経由の別名・ポインタの再読込みは追わない。call で caller-saved を捨てる近似。
窓の先頭が命令境界とずれた場合は alignment miss と出す。
"""
import sys

import capstone
import pefile

X = capstone.x86
path = sys.argv[1]
slots = [int(v, 0) for v in sys.argv[2].split(",")]
fwd = int(sys.argv[3], 0) if len(sys.argv) > 3 else 16
back = int(sys.argv[4], 0) if len(sys.argv) > 4 else 16
PRE = POST = 0x100
ARG = ("rcx", "rdx", "r8", "r9")
CALLER_SAVED = ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11")
MOV = ("mov", "movzx", "movsx", "movsxd", "movd", "movq")
S32 = {"eax": "rax", "ebx": "rbx", "ecx": "rcx", "edx": "rdx", "esi": "rsi",
       "edi": "rdi", "ebp": "rbp", "esp": "rsp"}

pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
tdata = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
tbase = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True


def canon(name):
    if name in S32:
        return S32[name]
    if name.startswith("r") and name[-1] in "dwb" and name[1:-1].isdigit():
        return name[:-1]
    return name


def rname(reg):
    return canon(md.reg_name(reg))


def fmt(ins):
    return f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}"


def sweep():
    refs = []
    fn = None
    pad = True
    off = 0
    while off < len(tdata):
        ins = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
        if ins is None:
            off += 1
            pad = True
            continue
        off += ins.size
        if ins.mnemonic == "int3":
            pad = True
            continue
        if pad:
            fn = ins.address
            pad = False
        for op in ins.operands:
            if op.type != X.X86_OP_MEM or op.mem.base != X.X86_REG_RIP:
                continue
            tgt = ins.address + ins.size + op.mem.disp
            if tgt not in slots:
                continue
            if ins.mnemonic == "lea":
                kind = "lea"
            elif op.access & capstone.CS_AC_WRITE:
                kind = "store"
            else:
                kind = "load"
            refs.append((ins.address, tgt, kind, fn))
    return refs


def window(ref):
    start = max(tbase, ref - PRE)
    off = start - tbase
    chunk = tdata[off:off + PRE + POST + 15]
    insns = list(md.disasm(chunk, start))
    k = next((i for i, ins in enumerate(insns) if ins.address == ref), None)
    return insns, k


def forward(insns, k, taint, slot):
    for ins in insns[k + 1:k + 1 + fwd]:
        ops = ins.operands
        if ins.mnemonic == "ret":
            break
        if ins.mnemonic in ("call", "jmp"):
            if ops and ops[0].type == X.X86_OP_MEM and ops[0].mem.base and rname(ops[0].mem.base) in taint:
                print(f"      {fmt(ins)}   <== indirect call via [{taint[rname(ops[0].mem.base)]}]+{ops[0].mem.disp:#x}")
            elif ins.mnemonic == "call" and ops and ops[0].type == X.X86_OP_IMM:
                args = [r for r in ARG if r in taint]
                if args:
                    desc = ", ".join(f"{r}={taint[r]}" for r in args)
                    print(f"      {fmt(ins)}   <== direct call, args: {desc}")
            if ins.mnemonic == "call":
                for r in CALLER_SAVED:
                    taint.pop(r, None)
            continue
        for op in ops:
            if op.type == X.X86_OP_MEM and op.mem.base and op.access & capstone.CS_AC_WRITE:
                b = rname(op.mem.base)
                if b in taint:
                    print(f"      {fmt(ins)}   <== STORE [{taint[b]}]+{op.mem.disp:#x}")
        if ops and ops[0].type == X.X86_OP_REG and ops[0].access & capstone.CS_AC_WRITE:
            dst = rname(ops[0].reg)
            chain = None
            if len(ops) > 1 and ins.mnemonic in MOV + ("lea",):
                s = ops[1]
                if s.type == X.X86_OP_MEM and s.mem.base and rname(s.mem.base) in taint:
                    base = taint[rname(s.mem.base)]
                    if ins.mnemonic == "lea":
                        chain = f"({base})+{s.mem.disp:#x}"
                    else:
                        chain = f"[({base})+{s.mem.disp:#x}]"
                elif s.type == X.X86_OP_REG and rname(s.reg) in taint:
                    chain = taint[rname(s.reg)]
            if chain:
                taint[dst] = chain
            else:
                taint.pop(dst, None)


def provenance(insns, k, reg):
    for ins in reversed(insns[max(0, k - back):k]):
        ops = ins.operands
        if ops and ops[0].type == X.X86_OP_REG and rname(ops[0].reg) == reg and ops[0].access & capstone.CS_AC_WRITE:
            print(f"      back: {fmt(ins)}")
            return
        if ins.mnemonic == "call" and reg in CALLER_SAVED:
            print(f"      back: {fmt(ins)}  (call boundary: {reg} は戻り値の可能性)")
            return
    print(f"      back: (no writer of {reg} within {back} insns)")


refs = sweep()
for slot in slots:
    mine = [r for r in refs if r[1] == slot]
    print(f"===== slot {slot:#x}: {len(mine)} RIP-relative ref(s) =====")
    for ref, _, kind, fn in mine:
        insns, k = window(ref)
        print(f"[{kind}] {ref:#x} fn={fn:#x}")
        if k is None:
            print("      alignment miss (window が命令境界とずれた)")
            continue
        ins = insns[k]
        print(f"      {fmt(ins)}")
        ops = ins.operands
        if kind in ("load", "lea") and ops and ops[0].type == X.X86_OP_REG:
            taint = {rname(ops[0].reg): f"{'&' if kind == 'lea' else ''}slot {slot:#x}"}
            forward(insns, k, taint, slot)
        elif kind == "store" and len(ops) > 1 and ops[1].type == X.X86_OP_REG:
            provenance(insns, k, rname(ops[1].reg))
