#!/usr/bin/env python3
"""ui の UI 側ディスパッチャ (0xfdd2c0 など) の op 別の到達先を PE から抜く解析補助 (PY-140 / #3761)。

op の値を定数として与え、関数先頭から .pdata の終端まで制御フローを辿る。`cmp`/`sub`/`test` と
`jcc` は、オペランドが既知のときだけ確定させる。既知にならない条件 (メモリ・呼出しの戻り値・
部分レジスタへの書込み) は両方向に辿る。よって出力は「到達しうる呼出し」の上位集合であり、
各呼出しの条件列 (`cond=`) で経路の出所を確かめられる。`cond` のうち `--from` 以降の確定分岐
(`T`/`F` が付くもの) は op による振り分けを表す。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_ui_dispatch_probe.py <fn VA(16進)> <op[,op...]> [--from <VA>]

既定は関数 0xfdd2c0・op 0x0〜0x30 の一覧。`FL_WIN64_DIR` 直下の `extracted/block00031_PE.bin` を読む。
"""
import argparse
import os
import re

import capstone
import pefile
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP

MASK = {64: (1 << 64) - 1, 32: (1 << 32) - 1, 16: 0xFFFF, 8: 0xFF}
CALLER_SAVED = ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11")
JCC = {
    "je": "ZF", "jz": "ZF", "jne": "!ZF", "jnz": "!ZF",
    "jg": "G", "jnle": "G", "jge": "GE", "jnl": "GE",
    "jl": "L", "jnge": "L", "jle": "LE", "jng": "LE",
    "ja": "A", "jnbe": "A", "jae": "AE", "jnb": "AE", "jnc": "AE",
    "jb": "B", "jnae": "B", "jc": "B", "jbe": "BE", "jna": "BE",
    "js": "SF", "jns": "!SF",
}
SETCC = {"sete": "je", "setz": "je", "setne": "jne", "setnz": "jne", "setg": "jg", "setge": "jge",
         "setl": "jl", "setle": "jle", "seta": "ja", "setae": "jae", "setb": "jb", "setbe": "jbe"}
REG64 = {"rax": "rax", "eax": "rax", "ax": "rax", "al": "rax", "ah": "rax",
         "rbx": "rbx", "ebx": "rbx", "bx": "rbx", "bl": "rbx", "bh": "rbx",
         "rcx": "rcx", "ecx": "rcx", "cx": "rcx", "cl": "rcx", "ch": "rcx",
         "rdx": "rdx", "edx": "rdx", "dx": "rdx", "dl": "rdx", "dh": "rdx",
         "rsi": "rsi", "esi": "rsi", "si": "rsi", "sil": "rsi",
         "rdi": "rdi", "edi": "rdi", "di": "rdi", "dil": "rdi",
         "rbp": "rbp", "ebp": "rbp", "bp": "rbp", "bpl": "rbp",
         "rsp": "rsp", "esp": "rsp", "sp": "rsp", "spl": "rsp"}
for _k in range(8, 16):
    for _suf in ("", "d", "w", "b"):
        REG64[f"r{_k}{_suf}"] = f"r{_k}"


def width_of(name):
    if name in ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp") or re.fullmatch(r"r\d+", name):
        return 64
    if name[0] == "e" or re.fullmatch(r"r\d+d", name):
        return 32
    if name in ("ax", "bx", "cx", "dx", "si", "di", "bp", "sp") or re.fullmatch(r"r\d+w", name):
        return 16
    return 8


class Image:
    def __init__(self, path):
        self.raw = open(path, "rb").read()
        self.pe = pefile.PE(data=self.raw, fast_load=True)
        self.pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.ends = {e.struct.BeginAddress: e.struct.EndAddress for e in self.pe.DIRECTORY_ENTRY_EXCEPTION}
        self.secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData,
                      s.Name.rstrip(b"\0").decode(errors="replace")) for s in self.pe.sections]
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True

    def sec(self, va):
        rva = va - self.base
        for vaddr, vsz, praw, rsz, name in self.secs:
            if vaddr <= rva < vaddr + max(vsz, rsz):
                return vaddr, vsz, praw, rsz, name
        return None

    def read_ro(self, va, size):
        """読み取り専用の .text・.rdata だけ値を確定する。.data・.bss は実行時に変わるため読まない。"""
        s = self.sec(va)
        if s is None or s[4] not in (".text", ".rdata"):
            return None
        vaddr, vsz, praw, rsz, _ = s
        off = praw + (va - self.base - vaddr)
        if va - self.base - vaddr + size > rsz:
            return None
        return int.from_bytes(self.raw[off:off + size], "little")

    def insns(self, fn):
        end = self.ends.get(fn - self.base)
        if end is None:
            raise SystemExit(f"{fn:#x} は .pdata に無い")
        vaddr, vsz, praw, rsz, _ = self.sec(fn)
        off = praw + (fn - self.base - vaddr)
        return {i.address: i for i in self.md.disasm(self.raw[off:off + (self.base + end - fn)], fn)}


def flags_cmp(a, b, w):
    m = MASK[w]
    a &= m
    b &= m
    r = (a - b) & m
    sa, sb, sr = a >> (w - 1) & 1, b >> (w - 1) & 1, r >> (w - 1) & 1
    return {"ZF": int(r == 0), "SF": sr, "CF": int(a < b), "OF": int(sa != sb and sa != sr)}


def flags_res(r, w):
    r &= MASK[w]
    return {"ZF": int(r == 0), "SF": r >> (w - 1) & 1, "CF": 0, "OF": 0}


def jcc_value(name, f):
    if f is None:
        return None
    Z, S, C, O = f["ZF"], f["SF"], f["CF"], f["OF"]
    return {
        "ZF": Z, "!ZF": 1 - Z, "SF": S, "!SF": 1 - S,
        "G": int(Z == 0 and S == O), "GE": int(S == O), "L": int(S != O), "LE": int(Z == 1 or S != O),
        "A": int(C == 0 and Z == 0), "AE": int(C == 0), "B": C, "BE": int(C == 1 or Z == 1),
    }[name]


class State:
    def __init__(self, pc, regs, mem, flags, conds):
        self.pc, self.regs, self.mem, self.flags, self.conds = pc, regs, mem, flags, conds

    def key(self):
        return (self.pc, tuple(sorted(self.regs.items())), tuple(sorted(self.mem.items())),
                None if self.flags is None else tuple(sorted(self.flags.items())))

    def clone(self, pc):
        return State(pc, dict(self.regs), dict(self.mem), None if self.flags is None else dict(self.flags), self.conds)


class Explorer:
    def __init__(self, img, fn, dispatch_from):
        self.img = img
        self.fn = fn
        self.insns = img.insns(fn)
        self.dispatch_from = dispatch_from

    def val(self, st, op, w, ins):
        if op.type == X86_OP_IMM:
            return op.imm & MASK[w]
        if op.type == X86_OP_REG:
            name = ins.reg_name(op.reg)
            c = REG64.get(name)
            v = st.regs.get(c) if c else None
            if v is None:
                return None
            if name in ("ah", "bh", "ch", "dh"):
                return (v >> 8) & 0xFF
            return v & MASK[width_of(name)]
        if op.type == X86_OP_MEM:
            m = op.mem
            if m.base == X86_REG_RIP:
                return self.img.read_ro(ins.address + ins.size + m.disp, w // 8)
            if m.base and ins.reg_name(m.base) == "rbp" and m.index == 0:
                return st.mem.get((m.disp, w))
        return None

    def write_reg(self, st, op, ins, v):
        name = ins.reg_name(op.reg)
        c = REG64.get(name)
        if c is None:
            return
        w = width_of(name)
        if v is None or name in ("ah", "bh", "ch", "dh"):
            st.regs.pop(c, None)
        elif w >= 32:
            st.regs[c] = v & MASK[w]
        elif c in st.regs:
            st.regs[c] = (st.regs[c] & ~MASK[w] & MASK[64]) | (v & MASK[w])
        else:
            st.regs.pop(c, None)

    def write_mem(self, st, op, ins, v, w):
        m = op.mem
        if not (m.base and ins.reg_name(m.base) == "rbp" and m.index == 0):
            return
        st.mem = {k: x for k, x in st.mem.items() if not (k[0] < m.disp + w // 8 and m.disp < k[0] + k[1] // 8)}
        if v is not None:
            st.mem[(m.disp, w)] = v & MASK[w]

    def step(self, st, ins, calls):
        mn, ops, nxt = ins.mnemonic, ins.operands, ins.address + ins.size
        if mn in ("nop", "push", "pop"):
            return [nxt]
        if mn == "ret":
            return []
        if mn == "jmp":
            return [ops[0].imm] if ops[0].type == X86_OP_IMM else None
        if mn == "call":
            t = ops[0].imm if ops[0].type == X86_OP_IMM else None
            if t is not None:
                calls.append((ins.address, t, dict(st.regs), list(st.conds)))
            for c in CALLER_SAVED:
                st.regs.pop(c, None)
            st.flags = None
            return [nxt]
        if mn in JCC:
            f = jcc_value(JCC[mn], st.flags)
            if f is None:
                return [("fork", ops[0].imm, nxt, mn)]
            if ins.address >= self.dispatch_from:
                st.conds = st.conds + [f"{ins.address:#x}:{mn}={'T' if f else 'F'}"]
            return [ops[0].imm] if f else [nxt]
        if mn in SETCC:
            f = jcc_value(JCC[SETCC[mn]], st.flags)
            self.write_reg(st, ops[0], ins, f)
            return [nxt]
        if mn in ("mov", "movzx", "movsxd", "lea"):
            dst, src = ops[0], ops[1]
            if mn == "lea":
                if dst.type == X86_OP_REG:
                    self.write_reg(st, dst, ins, None)
                return [nxt]
            w = width_of(ins.reg_name(dst.reg)) if dst.type == X86_OP_REG else dst.size * 8
            sw = src.size * 8 if src.type == X86_OP_MEM else width_of(ins.reg_name(src.reg)) if src.type == X86_OP_REG else w
            v = self.val(st, src, sw, ins)
            if mn == "movsxd" and v is not None and v >> 31 & 1:
                v = (v | (MASK[64] ^ MASK[32])) & MASK[64]
            if dst.type == X86_OP_REG:
                self.write_reg(st, dst, ins, v)
            else:
                self.write_mem(st, dst, ins, v, w)
            return [nxt]
        if mn in ("cmp", "test", "xor", "sub", "add", "and", "or", "imul", "shl", "shr", "sar", "inc", "dec", "neg", "not"):
            if len(ops) == 1:
                dst = ops[0]
                w = width_of(ins.reg_name(dst.reg)) if dst.type == X86_OP_REG else dst.size * 8
                a = self.val(st, dst, w, ins)
                r = None if a is None else {"inc": a + 1, "dec": a - 1, "neg": -a, "not": ~a}[mn] & MASK[w]
                if dst.type == X86_OP_REG:
                    self.write_reg(st, dst, ins, r)
                st.flags = None if r is None else flags_res(r, w)
                return [nxt]
            dst, src = ops[0], ops[1]
            w = width_of(ins.reg_name(dst.reg)) if dst.type == X86_OP_REG else dst.size * 8
            a = self.val(st, dst, w, ins)
            b = self.val(st, src, w, ins)
            if a is None or b is None:
                r = None
            elif mn in ("cmp", "sub"):
                r = (a - b) & MASK[w]
            elif mn == "test":
                r = a & b & MASK[w]
            else:
                r = {"xor": a ^ b, "add": a + b, "and": a & b, "or": a | b, "imul": a * b,
                     "shl": a << (b & 31), "shr": a >> (b & 31)}.get(mn)
                r = None if r is None else r & MASK[w]
                if mn == "sar":
                    r = None
            if mn in ("cmp", "test"):
                st.flags = None if (a is None or b is None) else (
                    flags_cmp(a, b, w) if mn == "cmp" else flags_res(a & b, w))
                return [nxt]
            if dst.type == X86_OP_REG:
                self.write_reg(st, dst, ins, r)
            else:
                self.write_mem(st, dst, ins, r, w)
            st.flags = None if (r is None or mn == "imul") else (
                flags_cmp(a, b, w) if mn == "sub" else flags_res(r, w))
            return [nxt]
        if ops and ops[0].type == X86_OP_REG:
            self.write_reg(st, ops[0], ins, None)
        st.flags = None
        return [nxt]

    def run(self, op, init_regs, limit=3000000):
        seen, calls, stack, steps = set(), [], [State(self.fn, dict(init_regs), {}, None, [])], 0
        while stack:
            st = stack.pop()
            while True:
                steps += 1
                if steps > limit:
                    return calls, "LIMIT", steps
                k = st.key()
                if k in seen or st.pc not in self.insns:
                    break
                seen.add(k)
                ins = self.insns[st.pc]
                nxts = self.step(st, ins, calls)
                if nxts is None or not nxts:
                    break
                if len(nxts) == 1 and not isinstance(nxts[0], tuple):
                    st.pc = nxts[0]
                    continue
                _, tgt, nx, mn = nxts[0]
                t = st.clone(tgt)
                t.conds = st.conds + [f"{ins.address:#x}:{mn}?T"]
                stack.append(t)
                st.pc = nx
                st.conds = st.conds + [f"{ins.address:#x}:{mn}?F"]
        return calls, "OK", steps


def describe(img, fn):
    ins = img.insns(fn)
    calls = [f"{a:#x}->{i.op_str}" for a, i in sorted(ins.items()) if i.mnemonic == "call"]
    rets = sum(1 for i in ins.values() if i.mnemonic == "ret")
    print(f"[{fn:#x}] size={img.ends[fn - img.base] + img.base - fn:#x} insns={len(ins)} ret={rets}")
    print(f"  calls({len(calls)}): {' '.join(calls)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fn")
    ap.add_argument("ops", nargs="?", default="")
    ap.add_argument("--from", dest="dispatch_from", default="0", help="確定分岐を cond に残す下限 VA (16進)")
    ap.add_argument("--arg", default=None, help="edx (第 2 引数) の既知値 (16進)。省略時は未知")
    ap.add_argument("--describe", nargs="*", default=None, help="関数の大きさと直接の呼出し先 (16進 VA の列)")
    args = ap.parse_args()
    img = Image(os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin"))
    if args.describe is not None:
        for d in args.describe:
            describe(img, int(d, 16))
        if not args.ops:
            return
    fn = int(args.fn, 16)
    ex = Explorer(img, fn, int(args.dispatch_from, 16))
    for op_s in args.ops.split(","):
        op = int(op_s, 0)
        init = {"rcx": op, "r9": 0xF}
        if args.arg is not None:
            init["rdx"] = int(args.arg, 16)
        calls, status, steps = ex.run(op, init)
        sites = {}
        for ca, tgt, regs, conds in calls:
            if (ca, tgt) not in sites or len(conds) - sum("?" in c for c in conds) < len(sites[(ca, tgt)][1]) - sum("?" in c for c in sites[(ca, tgt)][1]):
                sites[(ca, tgt)] = (regs, conds)
        print(f"== op {op:#x} status={status} steps={steps} call_sites={len(sites)}")
        for (ca, tgt), (regs, conds) in sorted(sites.items()):
            rs = ",".join(f"{r}={regs[r]:#x}" for r in ("rcx", "rdx", "r8", "r9") if regs.get(r) is not None)
            det = [c for c in conds if "?" not in c]
            print(f"  {ca:#x} -> {tgt:#x} regs[{rs}] det={det} unknown_forks={len(conds) - len(det)}")


if __name__ == "__main__":
    main()
