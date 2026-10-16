#!/usr/bin/env python3
"""SR-97 #5935: .text 内で、指定 VA を指すメモリ参照を列挙する。
rip 相対の直接参照と、lea reg,[rip+X] で得たアドレスを経由する参照 (mov [reg],... 等) を対象にする。
読み/書きは capstone の op.access (CS_AC_WRITE / CS_AC_READ) で区別する (WRITE / RW / READ)。
限界: 線形走査で、reg を書き換える命令・分岐命令で追跡を打ち切る。分岐先から来る lea の値は追わない (件数は下界)。
usage: xref_slot_writes.py <pe> <target_va_hex>
       xref_slot_writes.py --selftest"""
import sys
from collections import Counter

from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_AC_READ, CS_AC_WRITE
from capstone.x86 import X86_OP_MEM, X86_OP_REG, X86_REG_RIP

FAMILY = {
    "rax": "rax", "eax": "rax", "ax": "rax", "al": "rax", "ah": "rax",
    "rbx": "rbx", "ebx": "rbx", "bx": "rbx", "bl": "rbx", "bh": "rbx",
    "rcx": "rcx", "ecx": "rcx", "cx": "rcx", "cl": "rcx", "ch": "rcx",
    "rdx": "rdx", "edx": "rdx", "dx": "rdx", "dl": "rdx", "dh": "rdx",
    "rsi": "rsi", "esi": "rsi", "si": "rsi", "sil": "rsi",
    "rdi": "rdi", "edi": "rdi", "di": "rdi", "dil": "rdi",
    "rbp": "rbp", "ebp": "rbp", "bp": "rbp", "bpl": "rbp",
    "rsp": "rsp", "esp": "rsp", "sp": "rsp", "spl": "rsp",
}
FAMILY.update({f"r{i}": f"r{i}" for i in range(8, 16)})
FAMILY.update({f"r{i}{s}": f"r{i}" for i in range(8, 16) for s in ("d", "w", "b")})


def kind(access):
    w, r = access & CS_AC_WRITE, access & CS_AC_READ
    if w and r:
        return "RW"
    return "WRITE" if w else "READ"


def scan(raw, base, tgt):
    cs = Cs(CS_ARCH_X86, CS_MODE_64)
    cs.detail = True
    lea = {}  # 64bit レジスタ名 -> lea で得た絶対アドレス
    hits = []
    for ins in cs.disasm(raw, base):
        ops = ins.operands
        if ins.mnemonic == "lea" and len(ops) == 2 and ops[0].type == X86_OP_REG \
                and ops[1].type == X86_OP_MEM and ops[1].mem.base == X86_REG_RIP and ops[1].mem.index == 0:
            lea[FAMILY[cs.reg_name(ops[0].reg)]] = ins.address + ins.size + ops[1].mem.disp
            continue
        for op in ops:
            if op.type != X86_OP_MEM or op.mem.index != 0:
                continue
            if op.mem.base == X86_REG_RIP:
                addr = ins.address + ins.size + op.mem.disp
            elif op.mem.base and FAMILY.get(cs.reg_name(op.mem.base)) in lea:
                addr = lea[FAMILY[cs.reg_name(op.mem.base)]] + op.mem.disp
            else:
                continue
            if addr == tgt:
                hits.append((kind(op.access), ins.address, f"{ins.mnemonic} {ins.op_str}"))
        for op in ops:
            if op.type == X86_OP_REG and op.access & CS_AC_WRITE:
                lea.pop(FAMILY.get(cs.reg_name(op.reg)), None)
        if ins.mnemonic.startswith(("j", "call", "ret", "loop")):
            lea.clear()
    return hits


def selftest():
    T = 0x1817BF760
    BASE = 0x180001000

    def rel(a, n):
        return (T - (a + n)).to_bytes(4, "little", signed=True)

    # (長さ, 命令バイト列を作る関数, 期待する分類 (None = ヒットしない))
    cases = [
        (7, lambda a: b"\x48\x89\x05" + rel(a, 7), "WRITE"),        # mov [rip+X], rax
        (8, lambda a: b"\x48\x83\x3d" + rel(a, 8) + b"\x00", "READ"),  # cmp qword [rip+X], 0
        (6, lambda a: b"\xff\x15" + rel(a, 6), "READ"),             # call [rip+X]
        (7, lambda a: b"\x48\x8d\x0d" + rel(a, 7), None),           # lea rcx,[rip+X] (参照ではない)
        (3, lambda a: b"\x48\x89\x01", "WRITE"),                    # mov [rcx], rax (lea 経由)
        (3, lambda a: b"\x48\x8b\x01", "READ"),                     # mov rax, [rcx] (lea 経由)
        (7, lambda a: b"\x48\x01\x05" + rel(a, 7), "RW"),           # add [rip+X], rax
        (5, lambda a: b"\xb9\x00\x00\x00\x00", None),               # mov ecx, 0 (rcx を書き換える)
        (3, lambda a: b"\x48\x89\x01", None),                       # mov [rcx], rax (追跡打ち切り後)
    ]
    code, a, expect = b"", BASE, []
    for n, f, k in cases:
        b = f(a)
        assert len(b) == n, (n, len(b))
        code += b
        if k:
            expect.append(k)
        a += n
    got = [k for k, _, _ in scan(code, BASE, T)]
    assert got == expect, (got, expect)
    print(f"selftest OK: {got}", file=sys.stderr)


def main():
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        return
    import pefile

    pe = pefile.PE(sys.argv[1])
    IMG = pe.OPTIONAL_HEADER.ImageBase
    tgt = int(sys.argv[2], 16)
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    hits = scan(text.get_data(), IMG + text.VirtualAddress, tgt)
    for k, a, t in hits:
        print(f"{k}\t0x{a:x}\t{t}")
    c = Counter(k for k, _, _ in hits)
    print(f"total_refs={len(hits)} WRITE={c['WRITE']} RW={c['RW']} READ={c['READ']}", file=sys.stderr)


if __name__ == "__main__":
    main()
