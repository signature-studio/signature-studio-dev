#!/usr/bin/env python3
"""PY-266 (#3890): [reg+0x49e] への書込み命令を block00031 の .text で列挙し、関数単位に分類する。

  FL_WIN64_DIR=<展開先> python3 analysis/py266_0x49e_writers.py [--tsv <出力>]

- 書込み: メモリ先頭オペランドの base レジスタ (index なし・rip 基底なし) で disp == 0x49e、
  かつ capstone の access に WRITE を含むもの。mov/and/or/add/sub/inc/dec/xor/xchg/setcc 等を全部含む。
- lea reg, [reg+0x49e]: 書込みの基になるアドレス計算 (件数のみ)。
- 関数境界: .pdata (RUNTIME_FUNCTION) の範囲。範囲外の命令は関数 (none) として数える。
- 分類: 書込み元 (src) と base レジスタを、同一関数内で後ろ向きに直線で遡り、最後に定義した命令で分類する。
  分岐は越えない (直線の近似)。窓 (直前 TRACE_MAX 命令) を超えたら「窓外」とする。
- 同じ関数内の flag セル 0x15e14a0 への RIP 相対参照の件数も数える。

メモリ: 全命令の capstone オブジェクトを保持しない (約 500 万命令。保持すると OOM する)。
1 パスで、直前 TRACE_MAX 命令の軽量レコードだけを ring buffer に持つ。
"""
import bisect
import collections
import os
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
DISP = 0x49E
FLAG_CELL = 0x15E14A0
TRACE_MAX = 300
ARG_REGS = {"rcx", "rdx", "r8", "r9"}
AC_WRITE = 2
X86 = capstone.x86
REG_RIP = X86.X86_REG_RIP


def load_funcs(pe, raw):
    pdata = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".pdata")
    base = pe.OPTIONAL_HEADER.ImageBase
    pd = raw[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
    funcs = []
    for k in range(0, len(pd) - 11, 12):
        b, e, _ = struct.unpack_from("<III", pd, k)
        if b == 0 and e == 0:
            continue
        funcs.append((base + b, base + e))
    funcs.sort()
    return funcs, [f[0] for f in funcs]


def func_of(addr, funcs, starts):
    k = bisect.bisect_right(starts, addr) - 1
    if k >= 0 and funcs[k][0] <= addr < funcs[k][1]:
        return funcs[k][0]
    return None


def iter_insns():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    n = min(text.Misc_VirtualSize, text.SizeOfRawData)
    va0 = base + text.VirtualAddress
    data = raw[text.PointerToRawData:text.PointerToRawData + n]
    funcs, starts = load_funcs(pe, raw)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    off = 0
    while off < n:
        ins = next(md.disasm(data[off:off + 16], va0 + off), None)
        if ins is None:
            off += 1
            continue
        yield ins
        off += ins.size
    del raw, data


class Rec:
    """直前命令の軽量レコード。trace に必要な最小限だけ持つ。"""
    __slots__ = ("addr", "mnem", "opstr", "wr", "ops", "reg_name")

    def __init__(self, ins):
        self.addr = ins.address
        self.mnem = ins.mnemonic
        self.opstr = ins.op_str
        _, wr = ins.regs_access()
        self.wr = frozenset(wr)
        self.ops = []
        for op in ins.operands:
            if op.type == X86.X86_OP_REG:
                self.ops.append(("reg", op.reg, ins.reg_name(op.reg)))
            elif op.type == X86.X86_OP_IMM:
                self.ops.append(("imm", op.imm & 0xFFFFFFFFFFFFFFFF, None))
            elif op.type == X86.X86_OP_MEM:
                self.ops.append(("mem", op.mem.base, ins.reg_name(op.mem.base) if op.mem.base else ""))
            else:
                self.ops.append(("other", 0, None))


def describe_def(r, reg_name, fstart, ring_has_start):
    """r は reg を書いた直前の命令。その分類を返す。"""
    if r.mnem == "call":
        return f"call 戻り値 ({hex(r.addr)} call {r.opstr})"
    if r.mnem in ("mov", "movabs", "movzx", "movsx", "movsxd", "lea") and r.ops:
        dst = r.ops[0]
        if dst[0] == "reg" and len(r.ops) >= 2:
            src = r.ops[1]
            if src[0] == "imm":
                return f"定数 {hex(src[1])} ({hex(r.addr)})"
            if src[0] == "mem":
                return f"読込み {r.mnem} {r.opstr} ({hex(r.addr)})"
            if src[0] == "reg" and r.mnem == "mov":
                return f"レジスタ複写 {r.opstr} ({hex(r.addr)})"
    if r.mnem == "xor" and len(r.ops) == 2 and r.ops[0][0] == "reg" and r.ops[1][0] == "reg" and r.ops[0][1] == r.ops[1][1]:
        return f"定数 0 ({hex(r.addr)})"
    return f"演算 {r.mnem} {r.opstr} ({hex(r.addr)})"


def trace(ring, reg, reg_name, fstart):
    """ring (古い順・直前命令) を後ろ向きに遡り、reg を最後に書いた命令の分類を返す。
    関数入口 (fstart) より前は見ない。入口まで定義が無ければ入口値として返す。"""
    if fstart is None:
        return "関数外"
    for r in reversed(ring):
        if r.addr < fstart:
            break
        if reg in r.wr:
            return describe_def(r, reg_name, fstart, True)
    if len(ring) and ring[0].addr > fstart:
        return f"窓外 ({reg_name}・関数内で {TRACE_MAX} 命令より前)"
    if reg_name in ARG_REGS:
        return f"入口値候補 ({reg_name})"
    return f"関数入口まで定義なし ({reg_name})"


def main():
    tsv = None
    if "--tsv" in sys.argv:
        tsv = sys.argv[sys.argv.index("--tsv") + 1]
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    funcs, starts = load_funcs(pe, raw)
    del raw

    ring = collections.deque(maxlen=TRACE_MAX)
    rows = []
    lea_rows = []
    wide_rows = []
    flag_refs = collections.Counter()
    n_ins = 0
    for ins in iter_insns():
        n_ins += 1
        rec = Rec(ins)
        f = func_of(ins.address, funcs, starts)
        fstart = f
        # フラグセル参照 (RIP 相対)
        for op in ins.operands:
            if op.type == X86.X86_OP_MEM and op.mem.base == REG_RIP:
                if ins.address + ins.size + op.mem.disp == FLAG_CELL:
                    flag_refs[f] += 1
            if op.type == X86.X86_OP_MEM and op.mem.base != REG_RIP and op.mem.base != 0 \
                    and op.mem.index == 0 and op.mem.disp != DISP and op.access & AC_WRITE \
                    and op.mem.disp <= DISP < op.mem.disp + op.size:
                if len(ins.operands) >= 2 and ins.operands[1].type == X86.X86_OP_IMM:
                    wsrc = f"定数 {hex(ins.operands[1].imm & 0xFFFFFFFFFFFFFFFF)}"
                elif len(ins.operands) >= 2 and ins.operands[1].type == X86.X86_OP_REG:
                    wsrc = trace(ring, ins.operands[1].reg, ins.reg_name(ins.operands[1].reg), f)
                else:
                    wsrc = f"{ins.mnemonic} {ins.op_str}"
                wide_rows.append((ins.address, f, f"{ins.mnemonic} {ins.op_str}", ins.reg_name(op.mem.base), op.mem.disp, op.size, wsrc))
            if op.type == X86.X86_OP_MEM and op.mem.base != REG_RIP and op.mem.base != 0 \
                    and op.mem.index == 0 and op.mem.disp == DISP:
                if ins.mnemonic == "lea":
                    lea_rows.append((ins.address, f"{ins.mnemonic} {ins.op_str}"))
                elif op.access & AC_WRITE:
                    base_name = ins.reg_name(op.mem.base)
                    if len(ins.operands) >= 2 and ins.operands[1].type == X86.X86_OP_IMM:
                        src = f"定数 {hex(ins.operands[1].imm & 0xFFFFFFFFFFFFFFFF)}"
                    elif len(ins.operands) >= 2 and ins.operands[1].type == X86.X86_OP_REG:
                        src = trace(ring, ins.operands[1].reg, ins.reg_name(ins.operands[1].reg), fstart)
                    elif len(ins.operands) == 1:
                        src = f"単項 {ins.mnemonic}"
                    else:
                        src = f"{ins.mnemonic} {ins.op_str}"
                    bdesc = trace(ring, op.mem.base, base_name, fstart)
                    rows.append((ins.address, f, f"{ins.mnemonic} {ins.op_str}", src, bdesc, flag_refs))
        ring.append(rec)

    fn_flag = dict(flag_refs)
    by_func = collections.OrderedDict()
    for r in rows:
        by_func.setdefault(r[1], []).append(r)

    print(f"block00031 .text: insns={n_ins} funcs(.pdata)={len(funcs)}")
    print(f"writes to [reg+0x49e]: {len(rows)} (in {len(by_func)} functions)")
    print(f"lea [reg+0x49e] (address taken): {len(lea_rows)}")
    print(f"RIP refs to flag cell {hex(FLAG_CELL)}: {sum(fn_flag.values())} in {len(fn_flag)} functions")
    print("--- per function ---")
    for f, rs in sorted(by_func.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
        fs = hex(f) if f is not None else "(none)"
        print(f"fn {fs} writes={len(rs)} flag_refs={fn_flag.get(f, 0)}")
        for a, _, ins_s, src, base, _ in rs:
            print(f"  {hex(a)}  {ins_s}  | src: {src} | base: {base}")
    print("--- lea ---")
    for a, s in lea_rows:
        print(f"  {hex(a)}  {s}")
    fw = collections.OrderedDict()
    for a, f, s, base, disp, size, wsrc in wide_rows:
        fw.setdefault(f, []).append((a, s, base, disp, size, wsrc))
    print(f"--- wider writes covering byte 0x49e (not exact): {len(wide_rows)} in {len(fw)} functions ---")
    for f, rs in fw.items():
        print(f"fn {hex(f) if f is not None else '(none)'} n={len(rs)}")
        for a, s, base, disp, size, wsrc in rs:
            print(f"  {hex(a)}  {s}  | base: {base} disp {hex(disp)} width {size} | src: {wsrc}")
    if tsv:
        with open(tsv, "w") as fh:
            fh.write("insn\tfunc\tinstruction\tsrc\tbase\tflag_refs_in_func\n")
            for a, f, ins_s, src, base, _ in rows:
                fh.write(f"{hex(a)}\t{hex(f) if f is not None else '-'}\t{ins_s}\t{src}\t{base}\t{fn_flag.get(f, 0)}\n")


if __name__ == "__main__":
    main()
