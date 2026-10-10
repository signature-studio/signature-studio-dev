"""mc.py — 機械語 (x86-64) 解析: capstone による関数 disasm / CFG / 到達定義 / 活性。

RetDec IR の `!insn.addr` と突き合わせるための基盤。IR 側と独立に機械語だけで
  - 命令の読書レジスタ集合 (canon 名: rax.. r15 / xmm0..15 / flags)
  - メモリ operand (base/index/scale/disp/size/access/rip_target)
  - 直接分岐先 / 条件コード
  - CFG (基本ブロック), 到達定義 (reaching defs), 関数入口の live-in 集合
を計算する。
"""
import capstone
from capstone import x86_const as X

_GPR_FAMILIES = {
    "rax": "rax eax ax al ah", "rbx": "rbx ebx bx bl bh", "rcx": "rcx ecx cx cl ch",
    "rdx": "rdx edx dx dl dh", "rsi": "rsi esi si sil", "rdi": "rdi edi di dil",
    "rbp": "rbp ebp bp bpl", "rsp": "rsp esp sp spl",
}
for _n in range(8, 16):
    _GPR_FAMILIES["r%d" % _n] = "r%d r%dd r%dw r%db" % (_n, _n, _n, _n)
CANON = {}
for _c, _names in _GPR_FAMILIES.items():
    for _n in _names.split():
        CANON[_n] = _c
for _i in range(32):
    for _p in ("xmm", "ymm", "zmm"):
        CANON["%s%d" % (_p, _i)] = "xmm%d" % _i
CANON["eflags"] = "flags"
CANON["rflags"] = "flags"

GPR_ARGS = ["rcx", "rdx", "r8", "r9"]          # MS x64 ABI
XMM_ARGS = ["xmm0", "xmm1", "xmm2", "xmm3"]
VOLATILE = set(["rax", "rcx", "rdx", "r8", "r9", "r10", "r11"] + ["xmm%d" % i for i in range(6)] + ["flags"])
CALLEE_SAVED_XMM = set("xmm%d" % i for i in range(6, 16))

COND_JCC = {"jo", "jno", "jb", "jnae", "jc", "jae", "jnb", "jnc", "je", "jz", "jne", "jnz", "jbe", "jna",
            "ja", "jnbe", "js", "jns", "jp", "jpe", "jnp", "jpo", "jl", "jnge", "jge", "jnl", "jle", "jng",
            "jg", "jnle", "jecxz", "jrcxz"}

_ZERO_IDIOMS = {"xor", "pxor", "xorps", "xorpd", "vxorps", "vxorpd", "vpxor", "sub", "psubb", "psubw", "psubd",
                "psubq", "pcmpeqb", "pcmpeqw", "pcmpeqd", "vpcmpeqd", "andnps", "pandn"}

_md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
_md.detail = True


class Insn:
    __slots__ = ("va", "size", "mnem", "op_str", "bytes", "reads", "writes", "mem", "is_call", "is_ret",
                 "is_jmp", "is_jcc", "target", "cc", "indirect", "ops", "_ci")

    def __repr__(self):
        return "%x: %s %s" % (self.va, self.mnem, self.op_str)

    @property
    def next(self):
        return self.va + self.size


def _canon_reg(ci, rid):
    n = ci.reg_name(rid)
    return CANON.get(n, n) if n else None


def decode_one(code, va):
    for ci in _md.disasm(code, va, 1):
        return _wrap(ci)
    return None


def _wrap(ci):
    it = Insn()
    it._ci = ci
    it.va, it.size, it.mnem, it.op_str, it.bytes = ci.address, ci.size, ci.mnemonic, ci.op_str, bytes(ci.bytes)
    rd, wr = ci.regs_access()
    reads = set(filter(None, (_canon_reg(ci, r) for r in rd)))
    writes = set(filter(None, (_canon_reg(ci, r) for r in wr)))
    it.mem = None
    it.ops = ci.operands
    m = ci.mnemonic
    if m.startswith("nop") or m.startswith("prefetch") or m == "int3":
        reads = set()
    for op in ci.operands:
        if op.type == X.X86_OP_MEM and not (m.startswith("nop") or m.startswith("prefetch")):
            base = _canon_reg(ci, op.mem.base) if op.mem.base else None
            idx = _canon_reg(ci, op.mem.index) if op.mem.index else None
            rip_t = None
            if op.mem.base == X.X86_REG_RIP:
                rip_t = ci.address + ci.size + op.mem.disp
                base = "rip"
            it.mem = dict(base=base, index=idx, scale=op.mem.scale, disp=op.mem.disp, size=op.size,
                          rip=rip_t, lea=(m == "lea"), seg=op.mem.segment,
                          read=bool(op.access & 1) and m != "lea", write=bool(op.access & 2))
    # ゼロ化イディオム (xorps x,x 等) は読取なし
    if m in _ZERO_IDIOMS and len(ci.operands) >= 2 and ci.operands[0].type == X.X86_OP_REG \
            and ci.operands[1].type == X.X86_OP_REG and ci.operands[0].reg == ci.operands[1].reg:
        reads = set()
    if m in ("vxorps", "vxorpd", "vpxor") and len(ci.operands) == 3 and all(o.type == X.X86_OP_REG for o in ci.operands) \
            and ci.operands[1].reg == ci.operands[2].reg:
        reads = set()
    reads.discard("rip")
    writes.discard("rip")
    it.reads, it.writes = reads, writes
    it.is_call = X.X86_GRP_CALL in ci.groups
    it.is_ret = X.X86_GRP_RET in ci.groups
    it.is_jmp = m == "jmp"
    it.is_jcc = m in COND_JCC
    it.cc = m[1:] if it.is_jcc else None
    it.target = None
    it.indirect = False
    if (it.is_jmp or it.is_jcc or it.is_call) and ci.operands:
        o = ci.operands[0]
        if o.type == X.X86_OP_IMM:
            it.target = o.imm
        else:
            it.indirect = True
    if it.is_call:
        it.writes |= VOLATILE
        it.writes.add("rax")
    return it


class MFunc:
    """1 関数の機械語。linear sweep (関数境界は pdata または明示範囲)。"""

    def __init__(self, img, start, end):
        self.img, self.start, self.end = img, start, end
        code = img.read(start, end - start)
        self.insns = {}
        self.order = []
        va = start
        for ci in _md.disasm(code, start):
            it = _wrap(ci)
            self.insns[it.va] = it
            self.order.append(it.va)
        self._cfg = None
        self._rd = None

    def __getitem__(self, va):
        return self.insns[va]

    def __contains__(self, va):
        return va in self.insns

    # ---- CFG --------------------------------------------------------------
    def cfg(self):
        if self._cfg:
            return self._cfg
        leaders = {self.start}
        for va in self.order:
            it = self.insns[va]
            if (it.is_jmp or it.is_jcc) and it.target is not None and self.start <= it.target < self.end:
                leaders.add(it.target)
            if (it.is_jmp or it.is_jcc or it.is_ret) and it.next < self.end:
                leaders.add(it.next)
            if it.mnem in ("int3", "ud2") and it.next < self.end:
                leaders.add(it.next)
        leaders = sorted(l for l in leaders if l in self.insns)
        blocks = {}
        for i, l in enumerate(leaders):
            nxt = leaders[i + 1] if i + 1 < len(leaders) else self.end
            vas = [v for v in self.order if l <= v < nxt]
            blocks[l] = dict(start=l, vas=vas, succ=[], pred=[])
        for l, b in blocks.items():
            last = self.insns[b["vas"][-1]]
            succ = []
            if last.is_ret or last.mnem in ("int3", "ud2"):
                pass
            elif last.is_jmp:
                if last.target is not None and last.target in blocks:
                    succ.append(last.target)
            elif last.is_jcc:
                if last.target in blocks:
                    succ.append(last.target)
                if last.next in blocks:
                    succ.append(last.next)
            else:
                if last.next in blocks:
                    succ.append(last.next)
            b["succ"] = succ
        for l, b in blocks.items():
            for s in b["succ"]:
                blocks[s]["pred"].append(l)
        self._cfg = blocks
        return blocks

    def block_of(self, va):
        best = None
        for l, b in self.cfg().items():
            if l <= va and (best is None or l > best):
                best = l
        return best

    # ---- 到達定義 ---------------------------------------------------------
    ENTRY = 0

    def reaching_defs(self):
        """{block_start: {reg: frozenset(def_addr)}} (ブロック入口)。関数入口の def は 0 (ENTRY)。"""
        if self._rd is not None:
            return self._rd
        blocks = self.cfg()
        gen = {}
        for l, b in blocks.items():
            g = {}
            for va in b["vas"]:
                for r in self.insns[va].writes:
                    g[r] = va
            gen[l] = g
        regs = set()
        for it in self.insns.values():
            regs |= it.reads | it.writes
        IN = {l: {} for l in blocks}
        OUT = {l: {} for l in blocks}
        IN[self.start] = {r: frozenset([self.ENTRY]) for r in regs}
        work = list(blocks)
        while work:
            l = work.pop(0)
            b = blocks[l]
            if l == self.start:
                cur = {r: frozenset(s) for r, s in IN[l].items()}
            else:
                cur = {}
                for p in b["pred"]:
                    for r, s in OUT[p].items():
                        cur[r] = cur.get(r, frozenset()) | s
            IN[l] = cur
            out = dict(cur)
            for r, va in gen[l].items():
                out[r] = frozenset([va])
            if out != OUT[l]:
                OUT[l] = out
                for s in b["succ"]:
                    if s not in work:
                        work.append(s)
        self._rd = IN
        return IN

    def defs_before(self, va, reg):
        """命令 va の直前時点での reg の到達定義アドレス集合 (ENTRY=0)。"""
        blk = self.block_of(va)
        cur = set(self.reaching_defs()[blk].get(reg, frozenset()))
        for v in self.cfg()[blk]["vas"]:
            if v == va:
                break
            if reg in self.insns[v].writes:
                cur = {v}
        return cur

    # ---- 入口 live-in -----------------------------------------------------
    def live_in(self):
        """関数入口での live-in レジスタ集合 (読まれる前に書かれない)。"""
        blocks = self.cfg()
        use, defn = {}, {}
        for l, b in blocks.items():
            u, d = set(), set()
            for va in b["vas"]:
                it = self.insns[va]
                u |= (it.reads - d)
                d |= it.writes
            use[l], defn[l] = u, d
        LIVE_IN = {l: set() for l in blocks}
        changed = True
        while changed:
            changed = False
            for l, b in blocks.items():
                out = set()
                for s in b["succ"]:
                    out |= LIVE_IN[s]
                new = use[l] | (out - defn[l])
                if new != LIVE_IN[l]:
                    LIVE_IN[l] = new
                    changed = True
        return LIVE_IN[self.start]

    def comis_sites(self):
        return [va for va in self.order if self.insns[va].mnem.lstrip("v") in ("comisd", "comiss", "ucomisd", "ucomiss")]

    def loads(self):
        """メモリ read を持つ命令: [(va, mem, mnem)]"""
        return [(va, self.insns[va].mem, self.insns[va].mnem) for va in self.order
                if self.insns[va].mem and self.insns[va].mem["read"]]


def tail_ranges(img, start):
    """pdata 範囲 (begin, end)。無ければ ret までの linear 推定。"""
    r = img.func_at(start)
    if r:
        return r
    return None
