#!/usr/bin/env python3
"""x64c.py — x86-64 (MS ABI) 機械語 → C の命令 1:1 lifter (capstone)。RetDec 非依存。

RetDec lift で判明した欠陥 (間接 call 脱落 / 引数 reg 脱落 / 小 global 範囲外 / CRT 数学を libm へ置換) を避け,
OTT の DSP クロージャを「機械語に忠実」に C 化するための最小実装。
  - CPU 状態は global (R[16], X[16], flags)。関数 = `void f_<va>(void)` (引数は R/X に在る)。
  - call = return address push → f_xxx() ; ret = rsp+=8; return ; 間接 call/jmp 表は switch 化。
  - image VA (0x180000000+) は 0x30000000+ へ shift (data は ott_data_install で同アドレス)。
  - 未対応命令/未 lift callee は実行時 fail-fast (ott_unsup / ott_unlifted)。
usage: x64c.py --pe DLL --entries entries.json --out out_dir
"""
import sys, json, struct, argparse, bisect, collections, os
import pefile
import capstone
from capstone import *
from capstone.x86 import *

IMG = 0x180000000
SHIFT = 0x150000000        # 0x180000000 → 0x30000000
IMG_SIZE = 0x308000

GPR_NAMES = {}
for i, n in enumerate(['rax', 'rcx', 'rdx', 'rbx', 'rsp', 'rbp', 'rsi', 'rdi']):
    GPR_NAMES[n] = (i, 8, 0); GPR_NAMES['e' + n[1:]] = (i, 4, 0); GPR_NAMES[n[1:]] = (i, 2, 0)
for i, n in enumerate(['al', 'cl', 'dl', 'bl']):
    GPR_NAMES[n] = (i, 1, 0)
for i, n in enumerate(['spl', 'bpl', 'sil', 'dil']):
    GPR_NAMES[n] = (4 + i, 1, 0)
for i, n in enumerate(['ah', 'ch', 'dh', 'bh']):
    GPR_NAMES[n] = (i, 1, 1)
for k in range(8, 16):
    GPR_NAMES['r%d' % k] = (k, 8, 0); GPR_NAMES['r%dd' % k] = (k, 4, 0); GPR_NAMES['r%dw' % k] = (k, 2, 0); GPR_NAMES['r%db' % k] = (k, 1, 0)

MASK = {1: 0xff, 2: 0xffff, 4: 0xffffffff, 8: 0xffffffffffffffff}


def strip_prefix(m):
    """MPX (bnd) / lock prefix を落とした base mnemonic。bnd は MPX 非搭載実行で no-op prefix、
    lock は単 thread では直列化 no-op (xadd/inc の意味は不変)。入口拡張 (CAB-137) で
    CRT の MPX 付き文字列 path・refcount path が closure に入ったために追加。"""
    if m.startswith('bnd '):
        return m[4:]
    if m.startswith('lock '):
        return m[5:]
    return m
CCMAP = {'e': 'E', 'z': 'E', 'ne': 'NE', 'nz': 'NE', 'b': 'B', 'c': 'B', 'nae': 'B', 'ae': 'AE', 'nb': 'AE', 'nc': 'AE',
         'be': 'BE', 'na': 'BE', 'a': 'A', 'nbe': 'A', 's': 'S', 'ns': 'NS', 'p': 'P', 'pe': 'P', 'np': 'NP', 'po': 'NP',
         'o': 'O', 'no': 'NO', 'l': 'L', 'nge': 'L', 'ge': 'GE', 'nl': 'GE', 'le': 'LE', 'ng': 'LE', 'g': 'G', 'nle': 'G'}


def sh(c):
    c &= 0xffffffffffffffff
    return c - SHIFT if IMG <= c < IMG + IMG_SIZE else c


def hx(c):
    return '0x%xULL' % (c & 0xffffffffffffffff)


class Unsup(Exception):
    pass


class PEInfo:
    def __init__(self, path):
        self.data = open(path, 'rb').read()
        pe = pefile.PE(data=self.data)
        self.img = pe.get_memory_mapped_image()
        self.iat = {}                    # slot VA → name
        for ent in pe.DIRECTORY_ENTRY_IMPORT:
            for imp in ent.imports:
                nm = imp.name.decode() if imp.name else 'ord%d' % imp.ordinal
                self.iat[imp.address] = nm
        sec = [s for s in pe.sections if s.Name.startswith(b'.pdata')][0]
        raw = sec.get_data()
        self.pdata = []
        for i in range(0, len(raw) // 12 * 12, 12):
            b, e, u = struct.unpack_from('<III', raw, i)
            if b == 0 and e == 0:
                break
            self.pdata.append((IMG + b, IMG + e, u))
        self.pstarts = [p[0] for p in self.pdata]

    def bytes_at(self, va, n):
        o = va - IMG
        return self.img[o:o + n]


class FnLift:
    """1 関数 (entry からの再帰降下) を C に変換"""

    def __init__(self, pe, entry, known_entries, md, thunks):
        self.pe = pe; self.entry = entry; self.known = known_entries; self.md = md; self.thunks = thunks
        self.insns = {}            # va → insn
        self.targets = set()       # label が必要な va
        self.calls = set()         # 直接 call 先 VA
        self.unsup = collections.Counter()
        self.out = []
        self.jtabs = {}            # jmp va → [target va]
        self.tail = set()
        self.textrefs = set()
        self.jt_ranges = []

    # ---- 降下 ----
    def decode_at(self, va):
        code = self.pe.bytes_at(va, 16)
        for i in self.md.disasm(code, va, 1):
            return i
        return None

    def descend(self):
        work = [self.entry]
        seen = set()
        while work:
            va = work.pop()
            while True:
                if va in seen or va in self.insns:
                    break
                ins = self.decode_at(va)
                if ins is None:
                    break
                self.insns[va] = ins
                seen.add(va)
                m = strip_prefix(ins.mnemonic)
                nxt = va + ins.size
                if m.startswith('j'):
                    if m == 'jmp':
                        op = ins.operands[0]
                        if op.type == X86_OP_IMM:
                            t = op.imm
                            if t != self.entry and t in self.known:
                                self.tail.add(va)       # 他関数への tail call
                            else:
                                self.targets.add(t); work.append(t)
                        elif op.type == X86_OP_REG:
                            tg = self.jump_table(va, ins)
                            if tg:
                                self.jtabs[va] = tg
                                for t in tg:
                                    self.targets.add(t); work.append(t)
                        break
                    else:
                        t = ins.operands[0].imm
                        self.targets.add(t); work.append(t)
                        va = nxt; continue
                if m == 'ret' or m == 'ud2' or m == 'int3' or m == 'hlt':
                    break
                if m == 'call':
                    op = ins.operands[0]
                    if op.type == X86_OP_IMM:
                        self.calls.add(op.imm)
                va = nxt

    def jump_table(self, va, ins):
        """MSVC 形式 jump table: ... mov eY,[rX+rIdx*4+tbl]; add rY,rX; jmp rY (tbl = image RVA)"""
        cand = sorted([x for x in self.insns if x < va], reverse=True)[:24]
        tbl = None; n = None
        for x in cand:
            i = self.insns[x]
            if i.mnemonic == 'mov' and len(i.operands) == 2 and i.operands[1].type == X86_OP_MEM:
                m = i.operands[1].mem
                if m.scale == 4 and m.index != 0 and tbl is None and m.disp:
                    tbl = m.disp & 0xffffffff
            if i.mnemonic == 'cmp' and len(i.operands) == 2 and i.operands[1].type == X86_OP_IMM and n is None:
                n = i.operands[1].imm
        if tbl is None:
            return None
        ent = []
        if n is None or n < 0 or n > 512:
            n = 64
        for k in range(n + 1):
            off = struct.unpack_from('<i', self.pe.img, tbl + 4 * k)[0]
            t = IMG + off
            if not (self.entry - 0x4000 <= t < self.entry + 0x20000):
                break
            ent.append(t)
        self.jt_ranges.append((IMG + tbl, 4 * (len(ent) + 1)))
        return ent

    # ---- 値/アドレス式 ----
    def reg(self, ins, rid):
        nm = ins.reg_name(rid)
        if nm in GPR_NAMES:
            return GPR_NAMES[nm]
        raise Unsup('reg ' + nm)

    def xreg(self, ins, rid):
        nm = ins.reg_name(rid)
        if nm.startswith('xmm'):
            return int(nm[3:])
        raise Unsup('xreg ' + nm)

    def ea(self, ins, op):
        m = op.mem
        if m.segment != 0:
            raise Unsup('segment')
        if m.base == X86_REG_RIP:
            tgt = ins.address + ins.size + m.disp
            if 0x180001000 <= tgt < 0x1801e2000 and ins.mnemonic != 'lea':
                self.textrefs.add(tgt)
            return hx(sh(tgt))
        terms = []
        if m.base != 0:
            i, s, h = self.reg(ins, m.base)
            terms.append('R[%d]' % i)
        if m.index != 0:
            i, s, h = self.reg(ins, m.index)
            terms.append('R[%d]*%d' % (i, m.scale) if m.scale != 1 else 'R[%d]' % i)
        disp = m.disp
        if m.base == 0 and m.index == 0:
            return hx(sh(disp & 0xffffffffffffffff if disp < 0 else disp))
        if disp:
            terms.append(hx(disp & 0xffffffffffffffff))
        return '(' + ' + '.join(terms) + ')'

    def rd(self, ins, op, size=None):
        """unsigned 値式 (size バイトに mask 済み)"""
        sz = size or op.size
        if op.type == X86_OP_REG:
            i, s, h = self.reg(ins, op.reg)
            if h:
                return '((R[%d] >> 8) & 0xff)' % i
            if s == 8:
                return 'R[%d]' % i if sz == 8 else '(R[%d] & %s)' % (i, hex(MASK[sz]))
            return '(R[%d] & %s)' % (i, hex(MASK[min(s, sz)]))
        if op.type == X86_OP_IMM:
            v = op.imm & MASK[8]
            if sz < 8:
                v &= MASK[sz]
            return hx(sh(v)) if sz == 8 else hex(v) + 'U'
        if op.type == X86_OP_MEM:
            return 'LD%d(%s)' % (sz * 8, self.ea(ins, op))
        raise Unsup('rd')

    def wr(self, ins, op, val, size=None):
        sz = size or op.size
        if op.type == X86_OP_REG:
            i, s, h = self.reg(ins, op.reg)
            if h:
                return 'R[%d] = (R[%d] & ~0xff00ULL) | (((uint64_t)(%s) & 0xff) << 8);' % (i, i, val)
            if s == 8:
                return 'R[%d] = (uint64_t)(%s);' % (i, val)
            if s == 4:
                return 'R[%d] = (uint32_t)(%s);' % (i, val)
            return 'R[%d] = (R[%d] & ~%sULL) | ((uint64_t)(%s) & %s);' % (i, i, hex(MASK[s]), val, hex(MASK[s]))
        if op.type == X86_OP_MEM:
            return 'ST%d(%s, %s);' % (sz * 8, self.ea(ins, op), val)
        raise Unsup('wr')

    def sgn(self, expr, sz):
        return '((int%d_t)(%s))' % (sz * 8, expr)

    # ---- xmm helpers ----
    def xs(self, ins, op, kind):
        """kind: f32/f64/d32/q64/x128 → 値式"""
        if op.type == X86_OP_REG:
            i = self.xreg(ins, op.reg)
            return {'f32': 'X[%d].f[0]', 'f64': 'X[%d].df[0]', 'd32': 'X[%d].d[0]', 'q64': 'X[%d].q[0]', 'x128': 'X[%d]'}[kind] % i
        e = self.ea(ins, op)
        return {'f32': 'LDF32(%s)', 'f64': 'LDF64(%s)', 'd32': 'LD32(%s)', 'q64': 'LD64(%s)', 'x128': 'LDX(%s)'}[kind] % e

    def xd(self, ins, op):
        return self.xreg(ins, op.reg)

    # ---- 出力 ----
    def L(self, s):
        self.out.append('  ' + s)

    def label(self, va):
        return 'L_%x' % va

    def call_stmt(self, ins, tgt):
        ret = sh(ins.address + ins.size)
        return 'R[RSP] -= 8; ST64(R[RSP], %s); ' % hx(ret) + tgt

    def emit_call_direct(self, ins, t):
        if t in self.thunks:
            return self.call_stmt(ins, 'imp_%s();' % self.thunks[t])
        if t in self.known:
            return self.call_stmt(ins, 'f_%x();' % t)
        return self.call_stmt(ins, 'ott_unlifted(%s);' % hx(sh(t)))

    def lift(self):
        self.descend()
        # MSVC の「image base 相対 data 参照」idiom: lea rX, [rip→IMG] 後に [rX + idx + disp(.text 内
        # table)] で 2 段 jump table (getParamLabel の byte permutation 表など) を張る。data_gen は
        # .text を敷設しないので、disp が .text RVA に見える memory operand に窓を張っておく
        # (data-in-code の追送分。余分な窓は正しい image byte の追送でしかないため無害)。
        if any(ins.mnemonic == 'lea' and ins.operands[1].mem.base == X86_REG_RIP
               and ins.address + ins.size + ins.operands[1].mem.disp == IMG for ins in self.insns.values()):
            for ins in self.insns.values():
                for op in ins.operands:
                    if op.type == X86_OP_MEM and op.mem.base != X86_REG_RIP:
                        d = op.mem.disp & 0xffffffff
                        if 0x1000 <= d < 0x1e2000:
                            self.textrefs.add(IMG + d)
        order = sorted(self.insns)
        self.out.append('void f_%x(void) {' % self.entry)
        for va in order:
            ins = self.insns[va]
            if va in self.targets or va == self.entry:
                self.out.append(self.label(va) + ':;')
            try:
                self.one(ins)
            except Unsup as e:
                mm = strip_prefix(ins.mnemonic)
                self.unsup[mm + ':' + str(e)] += 1
                self.L('ott_unsup(%s, "%s %s");' % (hx(ins.address), mm, ins.op_str.replace('"', "'")))
        self.out.append('  ott_badjump(%s, 0);' % hx(order[-1] if order else 0))
        self.out.append('}')
        return '\n'.join(self.out)

    # ---- 命令 ----
    def one(self, ins):
        m = strip_prefix(ins.mnemonic)
        ops = ins.operands
        va = ins.address
        L = self.L
        L('/* %x: %s %s */' % (va, m, ins.op_str.replace('*/', '* /')))
        if m.startswith('rep '):
            return self.rep(ins)
        h = getattr(self, 'i_' + m, None)
        if h is not None:
            return h(ins, ops)
        if m.startswith('cmov'):
            return self.cmov(ins, ops, m[4:])
        if m.startswith('set'):
            return self.setcc(ins, ops, m[3:])
        if m.startswith('j') and m != 'jmp':
            cc = CCMAP.get(m[1:])
            if cc is None:
                raise Unsup(m)
            t = ops[0].imm
            if t != self.entry and t in self.known and t not in self.targets:
                L('if (CC_%s) { %s return; }' % (cc, 'f_%x();' % t))      # 条件付き tail call (稀)
                return
            return L('if (CC_%s) goto %s;' % (cc, self.label(t)))
        if m.startswith('cmp') and m.endswith(('ss', 'sd')) and m not in ('cmpss', 'cmpsd'):
            return self.cmpfp(ins, ops, m)
        raise Unsup(m)

    # nop
    def i_nop(self, ins, ops): pass
    i_int3 = i_nop
    i_endbr64 = i_nop
    i_fnop = i_nop
    i_pause = i_nop
    i_prefetcht0 = i_nop
    i_prefetchnta = i_nop

    def i_ud2(self, ins, ops): self.L('ott_unsup(%s, "ud2");' % hx(ins.address))

    def i_mov(self, ins, ops):
        self.L(self.wr(ins, ops[0], self.rd(ins, ops[1], ops[0].size)))

    def i_movabs(self, ins, ops): self.i_mov(ins, ops)

    def i_movzx(self, ins, ops):
        self.L(self.wr(ins, ops[0], self.rd(ins, ops[1]), ops[0].size))

    def i_movsx(self, ins, ops):
        s = ops[1].size
        self.L(self.wr(ins, ops[0], '(uint64_t)(int64_t)' + self.sgn(self.rd(ins, ops[1]), s), ops[0].size))

    i_movsxd = i_movsx

    def i_lea(self, ins, ops):
        self.L(self.wr(ins, ops[0], self.ea(ins, ops[1]), ops[0].size))

    def i_push(self, ins, ops):
        self.L('{ uint64_t v_ = %s; R[RSP] -= 8; ST64(R[RSP], v_); }' % self.rd(ins, ops[0], 8))

    def i_pop(self, ins, ops):
        self.L('{ uint64_t v_ = LD64(R[RSP]); R[RSP] += 8; %s }' % self.wr(ins, ops[0], 'v_', 8))

    def i_xchg(self, ins, ops):
        sz = ops[0].size
        self.L('{ uint64_t a_ = %s, b_ = %s; %s %s }' % (self.rd(ins, ops[0], sz), self.rd(ins, ops[1], sz),
                                                         self.wr(ins, ops[0], 'b_', sz), self.wr(ins, ops[1], 'a_', sz)))

    def arith(self, ins, ops, kind):
        sz = ops[0].size; W = sz * 8
        T = 'uint%d_t' % W
        a = self.rd(ins, ops[0], sz)
        b = self.rd(ins, ops[1], sz)
        if len(ops) > 1 and ops[1].type == X86_OP_IMM and sz == 8:
            b = hx(ops[1].imm & MASK[8])
        s = '{ %s a_ = (%s)(%s); %s b_ = (%s)(%s); ' % (T, T, a, T, T, b)
        if kind == 'add':
            s += '%s r_ = a_ + b_; FL_ADD(%d, a_, b_, r_); %s }' % (T, W, self.wr(ins, ops[0], 'r_', sz))
        elif kind == 'adc':
            s += '%s c_ = fCF; %s r_ = a_ + b_ + c_; FL_ADC(%d, a_, b_, r_, c_); %s }' % (T, T, W, self.wr(ins, ops[0], 'r_', sz))
        elif kind == 'sub':
            s += '%s r_ = a_ - b_; FL_SUB(%d, a_, b_, r_); %s }' % (T, W, self.wr(ins, ops[0], 'r_', sz))
        elif kind == 'sbb':
            s += '%s c_ = fCF; %s r_ = a_ - b_ - c_; FL_SBB(%d, a_, b_, r_, c_); %s }' % (T, T, W, self.wr(ins, ops[0], 'r_', sz))
        elif kind == 'cmp':
            s += '%s r_ = a_ - b_; FL_SUB(%d, a_, b_, r_); }' % (T, W)
        elif kind in ('and', 'or', 'xor'):
            op = {'and': '&', 'or': '|', 'xor': '^'}[kind]
            s += '%s r_ = a_ %s b_; FL_LOGIC(%d, r_); %s }' % (T, op, W, self.wr(ins, ops[0], 'r_', sz))
        elif kind == 'test':
            s += '%s r_ = a_ & b_; FL_LOGIC(%d, r_); }' % (T, W)
        self.L(s)

    def i_add(self, i, o): self.arith(i, o, 'add')
    def i_adc(self, i, o): self.arith(i, o, 'adc')
    def i_sub(self, i, o): self.arith(i, o, 'sub')
    def i_sbb(self, i, o): self.arith(i, o, 'sbb')
    def i_cmp(self, i, o): self.arith(i, o, 'cmp')
    def i_and(self, i, o): self.arith(i, o, 'and')
    def i_or(self, i, o): self.arith(i, o, 'or')
    def i_xor(self, i, o): self.arith(i, o, 'xor')
    def i_test(self, i, o): self.arith(i, o, 'test')

    def i_inc(self, ins, ops):
        sz = ops[0].size; W = sz * 8; T = 'uint%d_t' % W
        self.L('{ %s a_ = %s; %s r_ = a_ + 1; fOF = (r_ == ((%s)1 << %d)); SETZSP(%d, r_); %s }' % (T, self.rd(ins, ops[0]), T, T, W - 1, W, self.wr(ins, ops[0], 'r_', sz)))

    def i_dec(self, ins, ops):
        sz = ops[0].size; W = sz * 8; T = 'uint%d_t' % W
        self.L('{ %s a_ = %s; %s r_ = a_ - 1; fOF = (a_ == ((%s)1 << %d)); SETZSP(%d, r_); %s }' % (T, self.rd(ins, ops[0]), T, T, W - 1, W, self.wr(ins, ops[0], 'r_', sz)))

    def i_neg(self, ins, ops):
        sz = ops[0].size; W = sz * 8; T = 'uint%d_t' % W
        self.L('{ %s a_ = %s; %s r_ = 0 - a_; fCF = (a_ != 0); fOF = (a_ == ((%s)1 << %d)); SETZSP(%d, r_); %s }' % (T, self.rd(ins, ops[0]), T, T, W - 1, W, self.wr(ins, ops[0], 'r_', sz)))

    def i_not(self, ins, ops):
        sz = ops[0].size
        self.L(self.wr(ins, ops[0], '~(%s)' % self.rd(ins, ops[0]), sz))

    def shift(self, ins, ops, kind):
        sz = ops[0].size; W = sz * 8; T = 'uint%d_t' % W; ST = 'int%d_t' % W
        cnt = self.rd(ins, ops[1], 1) if len(ops) > 1 else '1'
        cm = 63 if sz == 8 else 31
        pre = '{ %s a_ = %s; unsigned c_ = (unsigned)(%s) & %d; if (c_) { ' % (T, self.rd(ins, ops[0]), cnt, cm)
        if kind == 'shl':
            body = '%s r_ = (c_ >= %d) ? 0 : (%s)(a_ << c_); fCF = (c_ <= %d) ? ((a_ >> (%d - c_)) & 1) : 0; fOF = ((r_ >> %d) & 1) ^ fCF; SETZSP(%d, r_); %s' % (T, W, T, W, W, W - 1, W, self.wr(ins, ops[0], 'r_', sz))
        elif kind == 'shr':
            body = '%s r_ = (c_ >= %d) ? 0 : (a_ >> c_); fCF = (a_ >> (c_ - 1)) & 1; fOF = (a_ >> %d) & 1; SETZSP(%d, r_); %s' % (T, W, W - 1, W, self.wr(ins, ops[0], 'r_', sz))
        elif kind == 'sar':
            body = '%s r_ = (%s)((%s)a_ >> (c_ >= %d ? %d : c_)); fCF = ((%s)a_ >> (c_ - 1 >= %d ? %d : c_ - 1)) & 1; fOF = 0; SETZSP(%d, r_); %s' % (T, T, ST, W, W - 1, ST, W, W - 1, W, self.wr(ins, ops[0], 'r_', sz))
        elif kind == 'rol':
            body = 'unsigned k_ = c_ %% %d; %s r_ = k_ ? (%s)((a_ << k_) | (a_ >> (%d - k_))) : a_; fCF = r_ & 1; %s' % (W, T, T, W, self.wr(ins, ops[0], 'r_', sz))
        elif kind == 'ror':
            body = 'unsigned k_ = c_ %% %d; %s r_ = k_ ? (%s)((a_ >> k_) | (a_ << (%d - k_))) : a_; fCF = (r_ >> %d) & 1; %s' % (W, T, T, W, W - 1, self.wr(ins, ops[0], 'r_', sz))
        self.L(pre + body + ' } }')

    def i_shl(self, i, o): self.shift(i, o, 'shl')
    i_sal = i_shl
    def i_shr(self, i, o): self.shift(i, o, 'shr')
    def i_sar(self, i, o): self.shift(i, o, 'sar')
    def i_rol(self, i, o): self.shift(i, o, 'rol')
    def i_ror(self, i, o): self.shift(i, o, 'ror')

    def i_imul(self, ins, ops):
        if len(ops) == 1:
            sz = ops[0].size
            if sz == 8:
                self.L('{ __int128 p_ = (__int128)(int64_t)R[RAX] * (int64_t)%s; R[RAX] = (uint64_t)p_; R[RDX] = (uint64_t)(p_ >> 64); fCF = fOF = (p_ != (__int128)(int64_t)R[RAX]); }' % self.rd(ins, ops[0]))
            else:
                self.L('{ int64_t p_ = (int64_t)(int32_t)R[RAX] * (int32_t)%s; R[RAX] = (uint32_t)p_; R[RDX] = (uint32_t)((uint64_t)p_ >> 32); fCF = fOF = (p_ != (int64_t)(int32_t)p_); }' % self.rd(ins, ops[0]))
            return
        dst = ops[0]; sz = dst.size; W = sz * 8
        a_op, b_op = (ops[1], ops[2]) if len(ops) == 3 else (ops[0], ops[1])
        a = self.rd(ins, a_op, sz); b = self.rd(ins, b_op, sz)
        if b_op.type == X86_OP_IMM:
            b = '(int%d_t)%d' % (W, (b_op.imm if b_op.imm < 2 ** 63 else b_op.imm - 2 ** 64))
        if sz == 8:
            self.L('{ __int128 p_ = (__int128)(int64_t)(%s) * (int64_t)(%s); uint64_t r_ = (uint64_t)p_; fCF = fOF = (p_ != (__int128)(int64_t)r_); SETZSP(64, r_); %s }' % (a, b, self.wr(ins, dst, 'r_', sz)))
        else:
            self.L('{ int64_t p_ = (int64_t)(int%d_t)(%s) * (int64_t)(int%d_t)(%s); uint%d_t r_ = (uint%d_t)p_; fCF = fOF = (p_ != (int64_t)(int%d_t)r_); SETZSP(%d, r_); %s }' % (W, a, W, b, W, W, W, W, self.wr(ins, dst, 'r_', sz)))

    def i_mul(self, ins, ops):
        sz = ops[0].size
        if sz == 8:
            self.L('{ unsigned __int128 p_ = (unsigned __int128)R[RAX] * %s; R[RAX] = (uint64_t)p_; R[RDX] = (uint64_t)(p_ >> 64); fCF = fOF = (R[RDX] != 0); }' % self.rd(ins, ops[0]))
        elif sz == 4:
            self.L('{ uint64_t p_ = (uint64_t)(uint32_t)R[RAX] * (uint32_t)%s; R[RAX] = (uint32_t)p_; R[RDX] = (uint32_t)(p_ >> 32); fCF = fOF = (R[RDX] != 0); }' % self.rd(ins, ops[0]))
        else:
            raise Unsup('mul%d' % sz)

    def i_div(self, ins, ops):
        sz = ops[0].size
        if sz == 8:
            self.L('{ uint64_t d_ = %s; if (!d_) ott_unsup(%s, "div by zero"); unsigned __int128 n_ = ((unsigned __int128)R[RDX] << 64) | R[RAX]; R[RAX] = (uint64_t)(n_ / d_); R[RDX] = (uint64_t)(n_ %% d_); }' % (self.rd(ins, ops[0]), hx(ins.address)))
        elif sz == 4:
            self.L('{ uint32_t d_ = %s; if (!d_) ott_unsup(%s, "div by zero"); uint64_t n_ = ((uint64_t)(uint32_t)R[RDX] << 32) | (uint32_t)R[RAX]; R[RAX] = (uint32_t)(n_ / d_); R[RDX] = (uint32_t)(n_ %% d_); }' % (self.rd(ins, ops[0]), hx(ins.address)))
        else:
            raise Unsup('div%d' % sz)

    def i_idiv(self, ins, ops):
        sz = ops[0].size
        if sz == 8:
            self.L('{ int64_t d_ = (int64_t)%s; if (!d_) ott_unsup(%s, "idiv by zero"); __int128 n_ = ((__int128)(int64_t)R[RDX] << 64) | R[RAX]; R[RAX] = (uint64_t)(int64_t)(n_ / d_); R[RDX] = (uint64_t)(int64_t)(n_ %% d_); }' % (self.rd(ins, ops[0]), hx(ins.address)))
        elif sz == 4:
            self.L('{ int32_t d_ = (int32_t)%s; if (!d_) ott_unsup(%s, "idiv by zero"); int64_t n_ = ((int64_t)(int32_t)R[RDX] << 32) | (uint32_t)R[RAX]; R[RAX] = (uint32_t)(int32_t)(n_ / d_); R[RDX] = (uint32_t)(int32_t)(n_ %% d_); }' % (self.rd(ins, ops[0]), hx(ins.address)))
        else:
            raise Unsup('idiv%d' % sz)

    def i_xadd(self, ins, ops):
        """xadd: dest = dest + src, src = 旧 dest (単 thread = lock 付きと同一意味)。flags は ADD 基準"""
        sz = ops[0].size; W = sz * 8; T = 'uint%d_t' % W
        a = self.rd(ins, ops[0], sz); b = self.rd(ins, ops[1], sz)
        self.L('{ %s o_ = %s; %s b_ = (%s)(%s); %s r_ = o_ + b_; FL_ADD(%d, o_, b_, r_); %s %s }' % (
            T, a, T, T, b, T, W, self.wr(ins, ops[0], 'r_', sz), self.wr(ins, ops[1], 'o_', sz)))

    def i_cdq(self, ins, ops): self.L('R[RDX] = (uint32_t)((int32_t)R[RAX] >> 31);')
    def i_cqo(self, ins, ops): self.L('R[RDX] = (uint64_t)((int64_t)R[RAX] >> 63);')
    def i_cdqe(self, ins, ops): self.L('R[RAX] = (uint64_t)(int64_t)(int32_t)R[RAX];')
    def i_cwde(self, ins, ops): self.L('R[RAX] = (uint32_t)(int32_t)(int16_t)R[RAX];')

    def bitop(self, ins, ops, kind):
        sz = ops[0].size; W = sz * 8; T = 'uint%d_t' % W
        if ops[0].type == X86_OP_MEM and ops[1].type != X86_OP_IMM:
            raise Unsup('bt mem,reg')
        idx = '(%s) %% %d' % (self.rd(ins, ops[1], sz), W) if ops[1].type != X86_OP_IMM else '%d' % (ops[1].imm % W)
        s = '{ %s a_ = %s; unsigned b_ = %s; fCF = (a_ >> b_) & 1; ' % (T, self.rd(ins, ops[0]), idx)
        if kind == 'btr': s += self.wr(ins, ops[0], 'a_ & ~((%s)1 << b_)' % T, sz)
        elif kind == 'bts': s += self.wr(ins, ops[0], 'a_ | ((%s)1 << b_)' % T, sz)
        elif kind == 'btc': s += self.wr(ins, ops[0], 'a_ ^ ((%s)1 << b_)' % T, sz)
        self.L(s + ' }')

    def i_bt(self, i, o): self.bitop(i, o, 'bt')
    def i_btr(self, i, o): self.bitop(i, o, 'btr')
    def i_bts(self, i, o): self.bitop(i, o, 'bts')
    def i_btc(self, i, o): self.bitop(i, o, 'btc')

    def i_bsr(self, ins, ops):
        sz = ops[0].size
        self.L('{ uint64_t s_ = %s; if (!s_) { fZF = 1; } else { fZF = 0; %s } }' % (self.rd(ins, ops[1]), self.wr(ins, ops[0], '63 - __builtin_clzll(s_)', sz)))

    def i_bsf(self, ins, ops):
        sz = ops[0].size
        self.L('{ uint64_t s_ = %s; if (!s_) { fZF = 1; } else { fZF = 0; %s } }' % (self.rd(ins, ops[1]), self.wr(ins, ops[0], '__builtin_ctzll(s_)', sz)))

    def i_bswap(self, ins, ops):
        sz = ops[0].size
        self.L(self.wr(ins, ops[0], '__builtin_bswap%d(%s)' % (sz * 8, self.rd(ins, ops[0])), sz))

    def cmov(self, ins, ops, cc):
        c = CCMAP.get(cc)
        if c is None: raise Unsup('cmov' + cc)
        sz = ops[0].size
        if sz == 4:
            ri = self.reg(ins, ops[0].reg)[0]
            self.L('{ uint32_t v_ = %s; if (CC_%s) R[%d] = v_; else R[%d] = (uint32_t)R[%d]; }' % (self.rd(ins, ops[1], 4), c, ri, ri, ri))
        else:
            self.L('{ uint64_t v_ = %s; if (CC_%s) { %s } }' % (self.rd(ins, ops[1], sz), c, self.wr(ins, ops[0], 'v_', sz)))

    def setcc(self, ins, ops, cc):
        c = CCMAP.get(cc)
        if c is None: raise Unsup('set' + cc)
        self.L(self.wr(ins, ops[0], '(CC_%s) ? 1 : 0' % c, 1))

    # ---- 制御 ----
    def i_jmp(self, ins, ops):
        op = ops[0]
        if op.type == X86_OP_IMM:
            t = op.imm
            if ins.address in self.tail:
                if t in self.thunks:
                    return self.L('imp_%s(); return;' % self.thunks[t])
                return self.L('f_%x(); return;' % t)
            return self.L('goto %s;' % self.label(t))
        if ins.address in self.jtabs:
            sw = ' '.join('case %s: goto %s;' % (hx(sh(t)), self.label(t)) for t in sorted(set(self.jtabs[ins.address])))
            return self.L('switch (%s) { %s default: ott_badjump(%s, %s); }' % (self.rd(ins, op, 8), sw, hx(ins.address), self.rd(ins, op, 8)))
        if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
            slot = ins.address + ins.size + op.mem.disp
            if slot in self.pe.iat:
                return self.L('imp_%s(); return;' % self.pe.iat[slot])
        # 間接 tail jmp (CFG dispatch 等): target を値として dispatch
        return self.L('{ uint64_t t_ = %s; ott_dispatch(t_); return; }' % self.rd(ins, op, 8))

    def i_call(self, ins, ops):
        op = ops[0]
        if op.type == X86_OP_IMM:
            return self.L(self.emit_call_direct(ins, op.imm))
        if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
            slot = ins.address + ins.size + op.mem.disp
            if slot in self.pe.iat:
                return self.L(self.call_stmt(ins, 'imp_%s();' % self.pe.iat[slot]))
        self.L('{ uint64_t t_ = %s; ' % self.rd(ins, op, 8) + self.call_stmt(ins, 'ott_dispatch(t_);') + ' }')

    def i_ret(self, ins, ops):
        self.L('R[RSP] += 8; return;')

    # ---- rep string ----
    def rep(self, ins):
        m = ins.mnemonic[4:]
        if m.startswith('movs'):
            w = {'b': 1, 'w': 2, 'd': 4, 'q': 8}[m[-1]]
            self.L('{ uint64_t n_ = R[RCX]; memmove((void*)A_(R[RDI]), (void*)A_(R[RSI]), n_ * %d); R[RDI] += n_ * %d; R[RSI] += n_ * %d; R[RCX] = 0; }' % (w, w, w))
        elif m.startswith('stos'):
            w = {'b': 1, 'w': 2, 'd': 4, 'q': 8}[m[-1]]
            v = {1: 'R[RAX] & 0xff', 2: 'R[RAX] & 0xffff', 4: 'R[RAX] & 0xffffffff', 8: 'R[RAX]'}[w]
            self.L('{ uint64_t n_ = R[RCX]; uint64_t v_ = %s; for (uint64_t k_ = 0; k_ < n_; k_++) ST%d(R[RDI] + k_ * %d, v_); R[RDI] += n_ * %d; R[RCX] = 0; }' % (v, w * 8, w, w))
        else:
            raise Unsup(ins.mnemonic)

    # ---- SSE ----
    def i_movss(self, ins, ops):
        d, s = ops
        if d.type == X86_OP_MEM:
            return self.L('STF32(%s, X[%d].f[0]);' % (self.ea(ins, d), self.xd(ins, s)))
        di = self.xd(ins, d)
        if s.type == X86_OP_REG:
            return self.L('X[%d].d[0] = X[%d].d[0];' % (di, self.xd(ins, s)))
        self.L('{ uint32_t v_ = LD32(%s); X[%d].d[0] = v_; X[%d].d[1] = X[%d].d[2] = X[%d].d[3] = 0; }' % (self.ea(ins, s), di, di, di, di))

    def i_movsd(self, ins, ops):
        d, s = ops
        if d.type == X86_OP_MEM:
            return self.L('STF64(%s, X[%d].df[0]);' % (self.ea(ins, d), self.xd(ins, s)))
        di = self.xd(ins, d)
        if s.type == X86_OP_REG:
            return self.L('X[%d].q[0] = X[%d].q[0];' % (di, self.xd(ins, s)))
        self.L('{ uint64_t v_ = LD64(%s); X[%d].q[0] = v_; X[%d].q[1] = 0; }' % (self.ea(ins, s), di, di))

    def mov128(self, ins, ops):
        d, s = ops
        if d.type == X86_OP_MEM:
            return self.L('STX(%s, X[%d]);' % (self.ea(ins, d), self.xd(ins, s)))
        di = self.xd(ins, d)
        if s.type == X86_OP_REG:
            return self.L('X[%d] = X[%d];' % (di, self.xd(ins, s)))
        self.L('X[%d] = LDX(%s);' % (di, self.ea(ins, s)))
    i_movaps = i_movapd = i_movdqa = i_movups = i_movupd = i_movdqu = mov128

    def i_movlpd(self, ins, ops):
        d, s = ops
        if d.type == X86_OP_MEM: return self.L('ST64(%s, X[%d].q[0]);' % (self.ea(ins, d), self.xd(ins, s)))
        self.L('X[%d].q[0] = LD64(%s);' % (self.xd(ins, d), self.ea(ins, s)))
    i_movlps = i_movlpd

    def i_movhpd(self, ins, ops):
        d, s = ops
        if d.type == X86_OP_MEM: return self.L('ST64(%s, X[%d].q[1]);' % (self.ea(ins, d), self.xd(ins, s)))
        self.L('X[%d].q[1] = LD64(%s);' % (self.xd(ins, d), self.ea(ins, s)))
    i_movhps = i_movhpd

    def isx(self, ins, op):
        return op.type == X86_OP_REG and ins.reg_name(op.reg).startswith('xmm')

    def i_movq(self, ins, ops):
        d, s = ops
        if self.isx(ins, d):
            di = self.xd(ins, d)
            if self.isx(ins, s):
                return self.L('{ uint64_t v_ = X[%d].q[0]; X[%d].q[0] = v_; X[%d].q[1] = 0; }' % (self.xd(ins, s), di, di))
            if s.type == X86_OP_REG:
                return self.L('{ uint64_t v_ = %s; X[%d].q[0] = v_; X[%d].q[1] = 0; }' % (self.rd(ins, s, 8), di, di))
            return self.L('{ uint64_t v_ = LD64(%s); X[%d].q[0] = v_; X[%d].q[1] = 0; }' % (self.ea(ins, s), di, di))
        si = self.xd(ins, s)
        if d.type == X86_OP_REG:
            return self.L(self.wr(ins, d, 'X[%d].q[0]' % si, 8))
        self.L('ST64(%s, X[%d].q[0]);' % (self.ea(ins, d), si))

    def i_movd(self, ins, ops):
        d, s = ops
        if self.isx(ins, d):
            di = self.xd(ins, d)
            v = self.rd(ins, s, 4)
            return self.L('{ uint32_t v_ = %s; X[%d].d[0] = v_; X[%d].d[1] = X[%d].d[2] = X[%d].d[3] = 0; }' % (v, di, di, di, di))
        si = self.xd(ins, s)
        if d.type == X86_OP_REG:
            return self.L(self.wr(ins, d, 'X[%d].d[0]' % si, 4))
        self.L('ST32(%s, X[%d].d[0]);' % (self.ea(ins, d), si))

    def scal(self, ins, ops, op, ty):
        di = self.xd(ins, ops[0])
        f = 'f' if ty == 'f32' else 'df'
        src = self.xs(ins, ops[1], ty)
        T = 'float' if ty == 'f32' else 'double'
        self.L('{ %s b_ = %s; %s a_ = X[%d].%s[0]; X[%d].%s[0] = %s; }' % (T, src, T, di, f, di, f, op))

    def i_addss(self, i, o): self.scal(i, o, 'a_ + b_', 'f32')
    def i_subss(self, i, o): self.scal(i, o, 'a_ - b_', 'f32')
    def i_mulss(self, i, o): self.scal(i, o, 'a_ * b_', 'f32')
    def i_divss(self, i, o): self.scal(i, o, 'a_ / b_', 'f32')
    def i_addsd(self, i, o): self.scal(i, o, 'a_ + b_', 'f64')
    def i_subsd(self, i, o): self.scal(i, o, 'a_ - b_', 'f64')
    def i_mulsd(self, i, o): self.scal(i, o, 'a_ * b_', 'f64')
    def i_divsd(self, i, o): self.scal(i, o, 'a_ / b_', 'f64')
    def i_maxss(self, i, o): self.scal(i, o, '(a_ > b_) ? a_ : b_', 'f32')
    def i_minss(self, i, o): self.scal(i, o, '(a_ < b_) ? a_ : b_', 'f32')
    def i_maxsd(self, i, o): self.scal(i, o, '(a_ > b_) ? a_ : b_', 'f64')
    def i_minsd(self, i, o): self.scal(i, o, '(a_ < b_) ? a_ : b_', 'f64')
    def i_sqrtss(self, i, o): self.scal(i, o, 'sqrtf(b_)', 'f32')
    def i_sqrtsd(self, i, o): self.scal(i, o, 'sqrt(b_)', 'f64')

    def packed_d(self, ins, ops, op):
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; X128 r_; for (int k_ = 0; k_ < 2; k_++) { double x_ = a_.df[k_], y_ = b_.df[k_]; r_.df[k_] = %s; } X[%d] = r_; }' % (self.xs(ins, ops[1], 'x128'), di, op, di))

    def packed_f(self, ins, ops, op):
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; X128 r_; for (int k_ = 0; k_ < 4; k_++) { float x_ = a_.f[k_], y_ = b_.f[k_]; r_.f[k_] = %s; } X[%d] = r_; }' % (self.xs(ins, ops[1], 'x128'), di, op, di))

    def i_addpd(self, i, o): self.packed_d(i, o, 'x_ + y_')
    def i_subpd(self, i, o): self.packed_d(i, o, 'x_ - y_')
    def i_mulpd(self, i, o): self.packed_d(i, o, 'x_ * y_')
    def i_divpd(self, i, o): self.packed_d(i, o, 'x_ / y_')
    def i_addps(self, i, o): self.packed_f(i, o, 'x_ + y_')
    def i_subps(self, i, o): self.packed_f(i, o, 'x_ - y_')
    def i_mulps(self, i, o): self.packed_f(i, o, 'x_ * y_')
    def i_divps(self, i, o): self.packed_f(i, o, 'x_ / y_')
    def i_maxpd(self, i, o): self.packed_d(i, o, '(x_ > y_) ? x_ : y_')
    def i_minpd(self, i, o): self.packed_d(i, o, '(x_ < y_) ? x_ : y_')
    def i_maxps(self, i, o): self.packed_f(i, o, '(x_ > y_) ? x_ : y_')
    def i_minps(self, i, o): self.packed_f(i, o, '(x_ < y_) ? x_ : y_')

    def i_sqrtpd(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X[%d].df[0] = sqrt(b_.df[0]); X[%d].df[1] = sqrt(b_.df[1]); }' % (self.xs(ins, ops[1], 'x128'), di, di))

    def i_sqrtps(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; for (int k_ = 0; k_ < 4; k_++) X[%d].f[k_] = sqrtf(b_.f[k_]); }' % (self.xs(ins, ops[1], 'x128'), di))

    def bitw(self, ins, ops, op):
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; for (int k_ = 0; k_ < 2; k_++) a_.q[k_] = %s; X[%d] = a_; }' % (self.xs(ins, ops[1], 'x128'), di, op, di))

    def i_andps(self, i, o): self.bitw(i, o, 'a_.q[k_] & b_.q[k_]')
    i_andpd = i_pand = i_andps
    def i_orps(self, i, o): self.bitw(i, o, 'a_.q[k_] | b_.q[k_]')
    i_orpd = i_por = i_orps
    def i_xorps(self, i, o): self.bitw(i, o, 'a_.q[k_] ^ b_.q[k_]')
    i_xorpd = i_pxor = i_xorps
    def i_andnps(self, i, o): self.bitw(i, o, '~a_.q[k_] & b_.q[k_]')
    i_andnpd = i_pandn = i_andnps

    def lane(self, ins, ops, field, n, op):
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; for (int k_ = 0; k_ < %d; k_++) a_.%s[k_] = %s; X[%d] = a_; }' % (self.xs(ins, ops[1], 'x128'), di, n, field, op, di))

    def i_paddq(self, i, o): self.lane(i, o, 'q', 2, 'a_.q[k_] + b_.q[k_]')
    def i_psubq(self, i, o): self.lane(i, o, 'q', 2, 'a_.q[k_] - b_.q[k_]')
    def i_paddd(self, i, o): self.lane(i, o, 'd', 4, 'a_.d[k_] + b_.d[k_]')
    def i_psubd(self, i, o): self.lane(i, o, 'd', 4, 'a_.d[k_] - b_.d[k_]')
    def i_paddw(self, i, o): self.lane(i, o, 'w', 8, 'a_.w[k_] + b_.w[k_]')
    def i_paddb(self, i, o): self.lane(i, o, 'b', 16, 'a_.b[k_] + b_.b[k_]')
    def i_pcmpeqd(self, i, o): self.lane(i, o, 'd', 4, '(a_.d[k_] == b_.d[k_]) ? 0xffffffffu : 0')
    def i_pcmpeqb(self, i, o): self.lane(i, o, 'b', 16, '(a_.b[k_] == b_.b[k_]) ? 0xff : 0')
    def i_pcmpgtd(self, i, o): self.lane(i, o, 'd', 4, '(a_.sd[k_] > b_.sd[k_]) ? 0xffffffffu : 0')

    def shiftimm(self, ins, ops, field, n, kind):
        di = self.xd(ins, ops[0])
        if ops[1].type == X86_OP_IMM:
            c = str(ops[1].imm)
        else:
            c = 'X[%d].q[0]' % self.xd(ins, ops[1]) if ops[1].type == X86_OP_REG else 'LD64(%s)' % self.ea(ins, ops[1])
        W = {'q': 64, 'd': 32, 'w': 16}[field]
        T = {'q': 'uint64_t', 'd': 'uint32_t', 'w': 'uint16_t'}[field]
        ST = {'q': 'int64_t', 'd': 'int32_t', 'w': 'int16_t'}[field]
        if kind == 'l':
            e = '(c_ >= %d) ? 0 : (%s)(a_.%s[k_] << c_)' % (W, T, field)
        elif kind == 'r':
            e = '(c_ >= %d) ? 0 : (%s)(a_.%s[k_] >> c_)' % (W, T, field)
        else:
            e = '(%s)(((%s)a_.%s[k_]) >> (c_ >= %d ? %d : c_))' % (T, ST, field, W, W - 1)
        self.L('{ uint64_t c_ = %s; X128 a_ = X[%d]; for (int k_ = 0; k_ < %d; k_++) a_.%s[k_] = %s; X[%d] = a_; }' % (c, di, n, field, e, di))

    def i_psllq(self, i, o): self.shiftimm(i, o, 'q', 2, 'l')
    def i_psrlq(self, i, o): self.shiftimm(i, o, 'q', 2, 'r')
    def i_pslld(self, i, o): self.shiftimm(i, o, 'd', 4, 'l')
    def i_psrld(self, i, o): self.shiftimm(i, o, 'd', 4, 'r')
    def i_psrad(self, i, o): self.shiftimm(i, o, 'd', 4, 'a')
    def i_psllw(self, i, o): self.shiftimm(i, o, 'w', 8, 'l')
    def i_psrlw(self, i, o): self.shiftimm(i, o, 'w', 8, 'r')
    def i_psraw(self, i, o): self.shiftimm(i, o, 'w', 8, 'a')

    def i_pslldq(self, ins, ops):
        di = self.xd(ins, ops[0]); n = ops[1].imm
        self.L('{ X128 a_ = X[%d], r_; memset(&r_, 0, 16); int n_ = %d; if (n_ < 16) memcpy(r_.b + n_, a_.b, 16 - n_); X[%d] = r_; }' % (di, n, di))

    def i_psrldq(self, ins, ops):
        di = self.xd(ins, ops[0]); n = ops[1].imm
        self.L('{ X128 a_ = X[%d], r_; memset(&r_, 0, 16); int n_ = %d; if (n_ < 16) memcpy(r_.b, a_.b + n_, 16 - n_); X[%d] = r_; }' % (di, n, di))

    def i_pshufd(self, ins, ops):
        di = self.xd(ins, ops[0]); imm = ops[2].imm
        self.L('{ X128 s_ = %s; X128 r_; r_.d[0] = s_.d[%d]; r_.d[1] = s_.d[%d]; r_.d[2] = s_.d[%d]; r_.d[3] = s_.d[%d]; X[%d] = r_; }' % (
            self.xs(ins, ops[1], 'x128'), imm & 3, (imm >> 2) & 3, (imm >> 4) & 3, (imm >> 6) & 3, di))

    def i_shufps(self, ins, ops):
        di = self.xd(ins, ops[0]); imm = ops[2].imm
        self.L('{ X128 a_ = X[%d]; X128 s_ = %s; X128 r_; r_.d[0] = a_.d[%d]; r_.d[1] = a_.d[%d]; r_.d[2] = s_.d[%d]; r_.d[3] = s_.d[%d]; X[%d] = r_; }' % (
            di, self.xs(ins, ops[1], 'x128'), imm & 3, (imm >> 2) & 3, (imm >> 4) & 3, (imm >> 6) & 3, di))

    def i_shufpd(self, ins, ops):
        di = self.xd(ins, ops[0]); imm = ops[2].imm
        self.L('{ X128 a_ = X[%d]; X128 s_ = %s; X128 r_; r_.q[0] = a_.q[%d]; r_.q[1] = s_.q[%d]; X[%d] = r_; }' % (
            di, self.xs(ins, ops[1], 'x128'), imm & 1, (imm >> 1) & 1, di))

    def unpack(self, ins, ops, field, n, hi):
        di = self.xd(ins, ops[0])
        base = n // 2 if hi else 0
        self.L('{ X128 a_ = X[%d]; X128 s_ = %s; X128 r_; for (int k_ = 0; k_ < %d; k_++) { r_.%s[2*k_] = a_.%s[%d + k_]; r_.%s[2*k_+1] = s_.%s[%d + k_]; } X[%d] = r_; }' % (
            di, self.xs(ins, ops[1], 'x128'), n // 2, field, field, base, field, field, base, di))

    def i_punpcklbw(self, i, o): self.unpack(i, o, 'b', 16, False)
    def i_punpckhbw(self, i, o): self.unpack(i, o, 'b', 16, True)
    def i_punpcklwd(self, i, o): self.unpack(i, o, 'w', 8, False)
    def i_punpckhwd(self, i, o): self.unpack(i, o, 'w', 8, True)
    def i_punpckldq(self, i, o): self.unpack(i, o, 'd', 4, False)
    def i_punpckhdq(self, i, o): self.unpack(i, o, 'd', 4, True)
    def i_punpcklqdq(self, i, o): self.unpack(i, o, 'q', 2, False)
    def i_punpckhqdq(self, i, o): self.unpack(i, o, 'q', 2, True)
    def i_unpcklps(self, i, o): self.unpack(i, o, 'd', 4, False)
    def i_unpckhps(self, i, o): self.unpack(i, o, 'd', 4, True)
    def i_unpcklpd(self, i, o): self.unpack(i, o, 'q', 2, False)
    def i_unpckhpd(self, i, o): self.unpack(i, o, 'q', 2, True)

    # 変換
    def i_cvtss2sd(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('X[%d].df[0] = (double)%s;' % (di, self.xs(ins, ops[1], 'f32')))

    def i_cvtsd2ss(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('X[%d].f[0] = (float)%s;' % (di, self.xs(ins, ops[1], 'f64')))

    def i_cvtps2pd(self, ins, ops):
        di = self.xd(ins, ops[0])
        s = self.xs(ins, ops[1], 'q64')
        self.L('{ uint64_t s_ = %s; float f0_, f1_; memcpy(&f0_, &s_, 4); memcpy(&f1_, ((char*)&s_) + 4, 4); X[%d].df[0] = (double)f0_; X[%d].df[1] = (double)f1_; }' % (s, di, di))

    def i_cvtpd2ps(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 s_ = %s; float a_ = (float)s_.df[0], b_ = (float)s_.df[1]; X[%d].f[0] = a_; X[%d].f[1] = b_; X[%d].q[1] = 0; }' % (self.xs(ins, ops[1], 'x128'), di, di, di))

    def i_cvtdq2pd(self, ins, ops):
        di = self.xd(ins, ops[0])
        s = self.xs(ins, ops[1], 'q64')
        self.L('{ uint64_t s_ = %s; int32_t a_ = (int32_t)(uint32_t)s_, b_ = (int32_t)(uint32_t)(s_ >> 32); X[%d].df[0] = (double)a_; X[%d].df[1] = (double)b_; }' % (s, di, di))

    def i_cvtdq2ps(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 s_ = %s; for (int k_ = 0; k_ < 4; k_++) X[%d].f[k_] = (float)s_.sd[k_]; }' % (self.xs(ins, ops[1], 'x128'), di))

    def i_cvttpd2dq(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 s_ = %s; int32_t a_ = cvtt_d2i32(s_.df[0]), b_ = cvtt_d2i32(s_.df[1]); X[%d].sd[0] = a_; X[%d].sd[1] = b_; X[%d].q[1] = 0; }' % (self.xs(ins, ops[1], 'x128'), di, di, di))

    def i_cvtpd2dq(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 s_ = %s; int32_t a_ = cvt_d2i32(s_.df[0]), b_ = cvt_d2i32(s_.df[1]); X[%d].sd[0] = a_; X[%d].sd[1] = b_; X[%d].q[1] = 0; }' % (self.xs(ins, ops[1], 'x128'), di, di, di))

    def i_cvttps2dq(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 s_ = %s; for (int k_ = 0; k_ < 4; k_++) X[%d].sd[k_] = cvtt_d2i32((double)s_.f[k_]); }' % (self.xs(ins, ops[1], 'x128'), di))

    def i_cvtsi2sd(self, ins, ops):
        di = self.xd(ins, ops[0]); sz = ops[1].size
        self.L('X[%d].df[0] = (double)(int%d_t)%s;' % (di, sz * 8, self.rd(ins, ops[1])))

    def i_cvtsi2ss(self, ins, ops):
        di = self.xd(ins, ops[0]); sz = ops[1].size
        self.L('X[%d].f[0] = (float)(int%d_t)%s;' % (di, sz * 8, self.rd(ins, ops[1])))

    def i_cvttsd2si(self, ins, ops):
        sz = ops[0].size
        self.L(self.wr(ins, ops[0], '(uint%d_t)cvtt_d2i%d(%s)' % (sz * 8, sz * 8, self.xs(ins, ops[1], 'f64')), sz))

    def i_cvttss2si(self, ins, ops):
        sz = ops[0].size
        self.L(self.wr(ins, ops[0], '(uint%d_t)cvtt_d2i%d((double)%s)' % (sz * 8, sz * 8, self.xs(ins, ops[1], 'f32')), sz))

    def i_cvtsd2si(self, ins, ops):
        sz = ops[0].size
        self.L(self.wr(ins, ops[0], '(uint%d_t)cvt_d2i%d(%s)' % (sz * 8, sz * 8, self.xs(ins, ops[1], 'f64')), sz))

    def i_cvtss2si(self, ins, ops):
        sz = ops[0].size
        self.L(self.wr(ins, ops[0], '(uint%d_t)cvt_d2i%d((double)%s)' % (sz * 8, sz * 8, self.xs(ins, ops[1], 'f32')), sz))

    def i_comiss(self, ins, ops): self.L('comis_f((double)X[%d].f[0], (double)%s, 0);' % (self.xd(ins, ops[0]), self.xs(ins, ops[1], 'f32')))
    i_ucomiss = i_comiss
    def i_comisd(self, ins, ops): self.L('comis_f(X[%d].df[0], %s, 0);' % (self.xd(ins, ops[0]), self.xs(ins, ops[1], 'f64')))
    i_ucomisd = i_comisd

    PRED = {'eq': 0, 'lt': 1, 'le': 2, 'unord': 3, 'neq': 4, 'nlt': 5, 'nle': 6, 'ord': 7}

    def cmpfp(self, ins, ops, m):
        base = m[3:-2]
        ty = m[-2:]
        if base not in self.PRED:
            raise Unsup(m)
        self.cmpfp_pred(ins, ops, self.PRED[base], ty)

    def cmpfp_pred(self, ins, ops, p, ty):
        di = self.xd(ins, ops[0])
        if ty == 'sd':
            self.L('{ double b_ = %s; X[%d].q[0] = cmp_pred_f(%d, X[%d].df[0], b_) ? ~0ULL : 0; }' % (self.xs(ins, ops[1], 'f64'), di, p, di))
        else:
            self.L('{ float b_ = %s; X[%d].d[0] = cmp_pred_f(%d, (double)X[%d].f[0], (double)b_) ? 0xffffffffu : 0; }' % (self.xs(ins, ops[1], 'f32'), di, p, di))

    def i_cmpsd(self, ins, ops):
        if len(ops) == 3: return self.cmpfp_pred(ins, ops[:2], ops[2].imm, 'sd')
        raise Unsup('cmpsd string')

    def i_cmpss(self, ins, ops):
        if len(ops) == 3: return self.cmpfp_pred(ins, ops[:2], ops[2].imm, 'ss')
        raise Unsup('cmpss')

    def i_movmskpd(self, ins, ops):
        s = self.xd(ins, ops[1])
        self.L(self.wr(ins, ops[0], '((X[%d].q[0] >> 63) & 1) | (((X[%d].q[1] >> 63) & 1) << 1)' % (s, s), 4))

    def i_movmskps(self, ins, ops):
        s = self.xd(ins, ops[1])
        self.L(self.wr(ins, ops[0], '(X[%d].d[0] >> 31) | ((X[%d].d[1] >> 31) << 1) | ((X[%d].d[2] >> 31) << 2) | ((X[%d].d[3] >> 31) << 3)' % (s, s, s, s), 4))

    def i_pmovmskb(self, ins, ops):
        s = self.xd(ins, ops[1])
        self.L('{ uint32_t m_ = 0; for (int k_ = 0; k_ < 16; k_++) m_ |= ((X[%d].b[k_] >> 7) & 1u) << k_; %s }' % (s, self.wr(ins, ops[0], 'm_', 4)))

    def i_pextrw(self, ins, ops):
        self.L(self.wr(ins, ops[0], 'X[%d].w[%d]' % (self.xd(ins, ops[1]), ops[2].imm & 7), 4))

    def i_ldmxcsr(self, ins, ops): self.L('ott_unsup(%s, "ldmxcsr");' % hx(ins.address))
    def i_stmxcsr(self, ins, ops): self.L('ST32(%s, 0x1f80);' % self.ea(ins, ops[0]))
    def i_leave(self, ins, ops): self.L('R[RSP] = R[RBP]; R[RBP] = LD64(R[RSP]); R[RSP] += 8;')
    def i_cld(self, ins, ops): pass
    def i_cpuid(self, ins, ops): self.L('ott_unsup(%s, "cpuid");' % hx(ins.address))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', required=True)
    ap.add_argument('--entries', required=True, help='json: {"roots":[va..], "calltgt":[rva..]}')
    ap.add_argument('--out', required=True)
    ap.add_argument('--closure', type=int, default=0, help='未 lift の直接 call 先を再帰的に追加 (深さ)')
    ap.add_argument('--override', action='append', default=[], help='VA=CNAME: その関数 body を C 実装 (rt/ott_ovr.c) に置換')
    a = ap.parse_args()
    overrides = {int(x.split('=')[0], 16): x.split('=')[1] for x in a.override}
    pe = PEInfo(a.pe)
    cfg = json.load(open(a.entries))
    entries = set(IMG + r for r in cfg.get('calltgt', [])) | set(cfg.get('roots', []))
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    thunks = {}

    def thunk_name(va):
        code = pe.bytes_at(va, 8)
        for i in md.disasm(code, va, 1):
            if i.mnemonic == 'jmp' and i.operands[0].type == X86_OP_MEM and i.operands[0].mem.base == X86_REG_RIP:
                slot = va + i.size + i.operands[0].mem.disp
                return pe.iat.get(slot)
        return None

    for e in list(entries):
        nm = thunk_name(e)
        if nm:
            thunks[e] = nm; entries.discard(e)
    done = {}
    queue = sorted(entries)
    known = set(entries)
    depth = 0
    while True:
        newc = set()
        for e in queue:
            if e in done: continue
            f = FnLift(pe, e, known, md, thunks)
            done[e] = f
            f.csrc = ('void f_%x(void) { %s(); }' % (e, overrides[e])) if e in overrides else f.lift()
            for t in f.calls:
                if t not in known and t not in thunks:
                    nm = thunk_name(t)
                    if nm:
                        thunks[t] = nm
                    else:
                        newc.add(t)
        if depth >= a.closure or not newc:
            break
        depth += 1
        known |= newc
        queue = sorted(newc)
    final = {}
    for e in sorted(done):
        f = FnLift(pe, e, known, md, thunks)
        f.csrc = ('void f_%x(void) { %s(); }' % (e, overrides[e])) if e in overrides else f.lift()
        final[e] = f
    unsup = collections.Counter()
    unl = collections.Counter()
    for e, f in final.items():
        unsup.update(f.unsup)
        for t in f.calls:
            if t not in known and t not in thunks:
                unl[t] += 1
    out = a.out
    os.makedirs(out, exist_ok=True)
    used_imps = set(thunks.values())
    for f in final.values():
        for ins in f.insns.values():
            if strip_prefix(ins.mnemonic) in ('call', 'jmp') and ins.operands[0].type == X86_OP_MEM and ins.operands[0].mem.base == X86_REG_RIP:
                s = ins.address + ins.size + ins.operands[0].mem.disp
                if s in pe.iat:
                    used_imps.add(pe.iat[s])
    used_imps = sorted(used_imps)
    with open(os.path.join(out, 'ott_lifted.c'), 'w') as fh:
        fh.write('#include "ott_cpu.h"\n')
        for nm in used_imps:
            fh.write('void imp_%s(void);\n' % nm)
        for c in sorted(set(overrides.values())):
            fh.write('void %s(void);\n' % c)
        for e in sorted(final):
            fh.write('void f_%x(void);\n' % e)
        for e in sorted(final):
            fh.write(final[e].csrc + '\n')
        fh.write('void ott_dispatch(uint64_t t) {\n  switch (t) {\n')
        for e in sorted(final):
            fh.write('  case %s: f_%x(); return;\n' % (hx(sh(e)), e))
        fh.write('  default: ott_unlifted(t);\n  }\n}\n')
        for nm in used_imps:
            fh.write('__attribute__((weak)) void imp_%s(void) { extern void ott_missing_import(const char*); ott_missing_import("%s"); }\n' % (nm, nm))
    meta = {'functions': sorted('%x' % e for e in final), 'unsup': dict(unsup), 'unlifted_callees': {'%x' % k: v for k, v in unl.items()},
            'overrides': {'%x' % k: v for k, v in overrides.items()}, 'imports_used': used_imps, 'ninsn': sum(len(f.insns) for f in final.values()),
            'textrefs': sorted({t for f in final.values() for t in f.textrefs}),
            'jt_ranges': sorted({r for f in final.values() for r in f.jt_ranges})}
    json.dump(meta, open(os.path.join(out, 'lift_meta.json'), 'w'), indent=1)
    print('[x64c] functions %d, insns %d, unsup %s, unlifted callees %d, imports %d' % (
        len(final), meta['ninsn'], dict(unsup) or '{}', len(unl), len(used_imps)))


if __name__ == '__main__':
    main()
