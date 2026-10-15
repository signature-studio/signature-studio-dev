#!/usr/bin/env python3
"""0xfdd2c0 (UI 側ディスパッチャ) を op ごとに到達解析する解析補助 (PY-140 / #3035)。

op (ecx)・arg (edx)・mode (r8b) の値を与え、その値で決まる分岐だけを具体値で追う。
決まらない分岐 (メモリ・呼出しの戻り値に依存するもの) は両方を辿る。出力は op ごとに
到達した call 命令 (呼出し先・call 直前の rcx/rdx/r8/r9 の既知値) と、ret 時の eax の既知値。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_ui_dispatch_probe.py <op(16進)> [...] \
      [--arg N|-] [--mode N|-]

既定の fn = 0xfdd2c0・end = 0xfde8ad (.pdata の終端)。arg・mode の既定は - (未知)。
mode 未知のとき test al,2 の両方を辿るので、-1 を返す経路も出る。
r9 = 0xf は [rbp+0x48] に保存される (セクション選択ビット)。
setcc は上位ビットを 0 とみなす (後続が movzx rax,al・test al,al の形のときだけ使われる)。
フラグ (ZF/SF/CF/OF) は演算幅 (8/16/32bit) から求める。幅や値が未知なら両分岐を辿る (64bit は未知扱い)。
呼出しで書き換えられ得るのは lea で取られた [rbp+X] のみとみなす (lea 一覧は走査時に求める)。
"""
import os
import re
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
FN = 0xFDD2C0
END = 0xFDE8AD
REG = {
    "rax": "a", "eax": "a", "ax": "a", "al": "a",
    "rcx": "c", "ecx": "c", "cx": "c", "cl": "c",
    "rdx": "d", "edx": "d", "dx": "d", "dl": "d",
    "rbx": "b", "ebx": "b", "bx": "b", "bl": "b",
    "r8": "r8", "r8d": "r8", "r8b": "r8",
    "r9": "r9", "r9d": "r9", "r9b": "r9",
}
LOW8 = {"al", "cl", "dl", "bl", "r8b", "r9b"}
CALL_CLOBBER = ("a", "c", "d", "r8", "r9")
JCC = {
    "je": "e", "jz": "e", "jne": "ne", "jnz": "ne",
    "jg": "g", "jnle": "g", "jge": "ge", "jnl": "ge",
    "jl": "l", "jnge": "l", "jle": "le", "jng": "le",
    "ja": "a", "jnbe": "a", "jae": "ae", "jnb": "ae", "jb": "b", "jnae": "b",
    "jbe": "be", "jna": "be",
}
SETCC = {
    "sete": "e", "setz": "e", "setne": "ne", "setnz": "ne",
    "setg": "g", "setge": "ge", "setl": "l", "setle": "le",
    "seta": "a", "setae": "ae", "setb": "b", "setbe": "be",
}
ARITH = ("sub", "add", "xor", "or", "and")
FLAG_KEEP = frozenset(
    ("nop", "endbr64", "push", "pop", "mov", "movzx", "movsx", "movsxd", "lea") + tuple(SETCC)
)


def width(opnd):
    """オペランドの幅 (bit)。8/16/32 以外 (64bit・幅の不明) は None。"""
    if "byte ptr" in opnd or opnd in LOW8:
        return 8
    if "word ptr" in opnd or opnd in ("ax", "cx", "dx", "bx"):
        return 16
    if "dword ptr" in opnd or opnd in ("eax", "ecx", "edx", "ebx", "r8d", "r9d"):
        return 32
    return None


def opwidth(ops):
    for o in ops:
        if o in REG or "ptr" in o:
            return width(o)
    return None


def alu(kind, a, b, w):
    """演算 kind の (結果, (ZF, SF, CF, OF))。値か幅が未知なら (None, None)。test/and/or/xor は CF=OF=0。"""
    if a is None or b is None or w is None:
        return None, None
    mask = (1 << w) - 1
    sign = 1 << (w - 1)
    ua, ub = a & mask, b & mask
    cf = of = False
    if kind == "add":
        raw = ua + ub
        res = raw & mask
        cf = raw > mask
        of = bool(~(ua ^ ub) & (ua ^ res) & sign)
    elif kind == "sub":
        res = (ua - ub) & mask
        cf = ua < ub
        of = bool((ua ^ ub) & (ua ^ res) & sign)
    else:
        res = {"and": ua & ub, "test": ua & ub, "or": ua | ub, "xor": ua ^ ub}[kind]
    return res, (res == 0, bool(res & sign), cf, of)


def cond(kind, flags):
    if flags is None:
        return None
    zf, sf, cf, of = flags
    table = {
        "e": zf, "ne": not zf, "g": not zf and sf == of, "ge": sf == of,
        "l": sf != of, "le": zf or sf != of, "a": not cf and not zf, "ae": not cf,
        "b": cf, "be": cf or zf,
    }
    return table[kind]


def mem_slot(opnd):
    """[rbp + 0xNN] のオフセット。rbp 以外や式が複雑なら None。"""
    if "[" not in opnd:
        return None
    inner = opnd[opnd.index("[") + 1:opnd.index("]")].replace(" ", "")
    parts = inner.split("+")
    if len(parts) != 2 or parts[0] != "rbp":
        return None
    return int(parts[1], 16)


def rip_const(opnd, next_va, read):
    """[rip + X] の定数 (PE の静的値)。読めないときは None。"""
    m = re.search(r"(word|dword|byte|qword) ptr \[rip ([+-]) (0x[0-9a-f]+)\]", opnd)
    if not m:
        return None
    size = {"byte": 1, "word": 2, "dword": 4, "qword": 8}[m.group(1)]
    disp = int(m.group(3), 16) * (1 if m.group(2) == "+" else -1)
    raw = read(next_va + disp, size)
    return None if raw is None else int.from_bytes(raw, "little")


def load(opnd, regs, mem):
    if opnd in REG:
        v = regs.get(REG[opnd])
        if opnd in LOW8 and v is not None:
            return v & 0xFF
        return v
    if opnd[:1].isdigit() or opnd.startswith("-"):
        return int(opnd, 0) & 0xFFFFFFFF
    slot = mem_slot(opnd)
    return mem.get(slot) if slot is not None else None


def addr_taken(insns):
    taken = set()
    for i in insns:
        if i.mnemonic == "lea" and "[rbp" in i.op_str:
            taken.add(mem_slot(i.op_str.split(", ", 1)[1]))
    return taken


def run(insns, op, arg, mode, read):
    by_addr = {i.address: i for i in insns}
    taken = addr_taken(insns)
    init_regs = {"a": None, "b": None, "c": op, "d": arg, "r8": mode, "r9": 0xF}
    init_mem = {0x40: op, 0x44: arg, 0x48: 0xF}
    init_mem = {k: v for k, v in init_mem.items() if v is not None}
    calls = {}
    rets = set()
    stack = [(FN, init_regs, None, init_mem)]
    seen = set()
    steps = 0
    while stack:
        steps += 1
        if steps > 3_000_000:
            raise SystemExit(f"op {op:#x}: 走査が上限 (3e6) を超えた")
        addr, regs, flags, mem = stack.pop()
        key = (addr, tuple(sorted(regs.items())), flags, tuple(sorted(mem.items())))
        if key in seen or addr not in by_addr:
            continue
        seen.add(key)
        i = by_addr[addr]
        m = i.mnemonic
        ops = [o.strip() for o in i.op_str.split(", ")] if i.op_str else []
        nxt = i.address + i.size
        if m == "ret":
            rets.add(regs["a"])
            continue
        if m == "call":
            rec = (regs.get("c"), regs.get("d"), regs.get("r8"), regs.get("r9"))
            calls.setdefault((i.address, i.op_str), set()).add(rec)
            nr = dict(regs)
            for r in CALL_CLOBBER:
                nr[r] = None
            nm = {k: v for k, v in mem.items() if k not in taken}
            stack.append((nxt, nr, None, nm))
            continue
        if m == "jmp":
            if ops[0].startswith("0x"):
                stack.append((int(ops[0], 16), regs, flags, mem))
            else:
                calls.setdefault((i.address, "jmp " + ops[0]), set()).add(())
            continue
        if m in JCC:
            target = int(ops[0], 16)
            r = cond(JCC[m], flags)
            if r is None:
                stack.append((target, regs, flags, mem))
                stack.append((nxt, regs, flags, mem))
            else:
                stack.append((target if r else nxt, regs, flags, mem))
            continue
        nr = dict(regs)
        nm = dict(mem)
        nf = flags if m in FLAG_KEEP else None
        if m in ("nop", "endbr64", "push"):
            pass
        elif m == "pop" and ops and ops[0] in REG:
            nr[REG[ops[0]]] = None
        elif m == "cmp" and len(ops) == 2:
            a, b = load(ops[0], regs, mem), load(ops[1], regs, mem)
            nf = alu("sub", a, b, opwidth(ops))[1]
        elif m == "test" and len(ops) == 2:
            a, b = load(ops[0], regs, mem), load(ops[1], regs, mem)
            nf = alu("test", a, b, opwidth(ops))[1]
        elif m in SETCC and ops and ops[0] in REG:
            r = cond(SETCC[m], flags)
            nr[REG[ops[0]]] = None if r is None else int(r)
        elif m in ("mov", "movzx", "movsxd", "movsx") and len(ops) == 2:
            dst, src = ops
            v = load(src, regs, mem)
            if "[rip" in src:
                v = rip_const(src, i.address + i.size, read)
            if dst in REG:
                if dst in LOW8:
                    base = nr[REG[dst]]
                    nr[REG[dst]] = None if base is None or v is None else (base & ~0xFF) | (v & 0xFF)
                else:
                    nr[REG[dst]] = v
            else:
                slot = mem_slot(dst)
                if slot is not None:
                    if v is None:
                        nm.pop(slot, None)
                    else:
                        nm[slot] = v & (0xFF if "byte ptr" in dst else 0xFFFFFFFF)
        elif m == "lea" and ops and ops[0] in REG:
            nr[REG[ops[0]]] = None
        elif m in ARITH + ("imul", "shl", "shr", "sar") and len(ops) == 2 and ops[0] in REG:
            d = REG[ops[0]]
            a, b = regs[d], load(ops[1], regs, mem)
            if m in ARITH:
                w = opwidth(ops)
                res, nf = alu(m, a, b, w)
                if res is None:
                    nr[d] = None
                elif w == 32:
                    nr[d] = res
                else:
                    nr[d] = (a & ~((1 << w) - 1) & 0xFFFFFFFF) | res
            else:
                nr[d] = None
        elif ops and ops[0] in REG:
            nr[REG[ops[0]]] = None
        stack.append((nxt, nr, nf, nm))
    return calls, rets


def main():
    args = sys.argv[1:]
    arg_v = mode_v = None
    ops = []
    i = 0
    while i < len(args):
        if args[i] == "--arg":
            arg_v = None if args[i + 1] == "-" else int(args[i + 1], 0)
            i += 2
        elif args[i] == "--mode":
            mode_v = None if args[i + 1] == "-" else int(args[i + 1], 0)
            i += 2
        else:
            ops.append(int(args[i], 16))
            i += 1
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData)
            for s in pe.sections]

    def v2o(va):
        rva = va - base
        for vaddr, vsz, praw, rsz in secs:
            if vaddr <= rva < vaddr + max(vsz, rsz):
                return praw + (rva - vaddr)
        return None

    fo = v2o(FN)

    def read(va, size):
        off = v2o(va)
        return None if off is None else raw[off:off + size]

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    insns = list(md.disasm(raw[fo:fo + (END - FN)], FN))
    def fmt(v):
        return "?" if v is None else f"{v:#x}"

    for op in ops:
        calls, rets = run(insns, op, arg_v, mode_v, read)
        ret_s = sorted(fmt(r) for r in rets)
        print(f"== op {op:#x} arg={fmt(arg_v)} mode={fmt(mode_v)} ret={ret_s}")
        for (addr, what), recs in sorted(calls.items()):
            for c, d, r8, r9 in sorted(recs, key=lambda r: tuple(-1 if x is None else x for x in r)):
                print(f"  {addr:#x} call {what} rcx={fmt(c)} rdx={fmt(d)} r8={fmt(r8)} r9={fmt(r9)}")


if __name__ == "__main__":
    main()
