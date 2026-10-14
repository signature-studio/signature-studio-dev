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
IA32 = False               # --arch ia32 (PE machine 0x14c): PEInfo が設定する。既定 x64 は出力不変
PTR = 8                    # ポインタ/戻り先幅 (ia32 = 4)
MACHINE_ARCH = {0x8664: 'x64', 0x14c: 'ia32'}
VEXCOV = os.environ.get('OTT_VEXCOV') == '1'   # CAB-135 probe: VEX 命令の実行 address 記録 (ott_vexhit)
# fake TEB/TLS (CAB-135): image 末尾の未使用領域 (.reloc 終端 0x180307794 以降)。
# PE image は MAP_ANONYMOUS(wasm も 0 初期化) なので両側とも 0 が読める = 「TLS 未割当」。
TEB_VA = 0x1803077a0
TLSA_VA = 0x180307840      # 64 qword (ThreadLocalStoragePointer 配列) — 0x180307a40 < image 終端

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


RELOC = os.environ.get('OTT_RELOC') == '1'   # 相対化モード: 画像 VA 定数を (ott_gbase + RVA) で書く (既定 off = 出力不変)
if RELOC and VEXCOV:   # OTT_VEXCOV_HIT の引数は既定 base の shifted VA 固定 (相対化未対応)
    raise SystemExit('[x64c] fail-fast: OTT_RELOC=1 と OTT_VEXCOV=1 は同時に使えない')


def sh(c):
    c &= 0xffffffffffffffff
    return c - SHIFT if IMG <= c < IMG + IMG_SIZE else c


def hx(c):
    return '0x%xULL' % (c & 0xffffffffffffffff)


def gv(c):
    """画像 VA 定数の C 式。既定 = hx(sh(c)) (出力不変)、相対化 = (ott_gbase + RVA)。"""
    c &= 0xffffffffffffffff
    if RELOC and IMG <= c < IMG + IMG_SIZE:
        return '(ott_gbase + %s)' % hx(c - IMG)
    return hx(sh(c))


class Unsup(Exception):
    pass


def iat_slot(ins, op):
    """間接 call/jmp のメモリ operand が指す IAT スロット VA (なければ None)。
    x64 は RIP 相対、ia32 は絶対 disp32 (ImageBase 基準 VA)。"""
    if op.type != X86_OP_MEM:
        return None
    if op.mem.base == X86_REG_RIP:
        return ins.address + ins.size + op.mem.disp
    if IA32 and op.mem.base == 0 and op.mem.index == 0 and op.mem.segment == 0:
        return op.mem.disp & 0xffffffff
    return None


class PEInfo:
    def __init__(self, path, arch=None):
        global IA32, PTR, IMG, SHIFT, IMG_SIZE
        self.data = open(path, 'rb').read()
        pe = pefile.PE(data=self.data)
        mach = pe.FILE_HEADER.Machine
        want = MACHINE_ARCH.get(mach)
        if want is None:
            raise SystemExit('[x64c] fail-fast: PE machine 0x%x は未対応' % mach)
        if arch not in (None, 'auto') and arch != want:
            raise SystemExit('[x64c] fail-fast: --arch %s だが PE machine 0x%x (%s) (D18)' % (arch, mach, want))
        IA32 = want == 'ia32'
        PTR = 4 if IA32 else 8
        if IA32:   # ia32: 絶対アドレス・ImageBase 基準。shift なし (恒等)
            IMG = pe.OPTIONAL_HEADER.ImageBase
            SHIFT = 0
            IMG_SIZE = pe.OPTIONAL_HEADER.SizeOfImage
        self.img = pe.get_memory_mapped_image()
        self.iat = {}                    # slot VA → name
        for ent in pe.DIRECTORY_ENTRY_IMPORT:
            for imp in ent.imports:
                nm = imp.name.decode() if imp.name else 'ord%d' % imp.ordinal
                self.iat[imp.address] = nm
        secs = [s for s in pe.sections if s.Name.startswith(b'.pdata')]
        raw = secs[0].get_data() if secs else b''
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
                        elif op.type == X86_OP_REG or (IA32 and op.type == X86_OP_MEM and op.mem.index != 0):
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
        if ins.operands[0].type == X86_OP_MEM:   # ia32: jmp dword ptr [idx*4+tbl] (tbl は絶対 VA)
            m = ins.operands[0].mem
            if m.scale == 4 and m.index != 0 and m.base == 0 and m.disp:
                tbl = m.disp & 0xffffffff
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
        if IA32:   # ia32 の jump table は絶対 VA (4 B)。tbl は ImageBase 基準の VA
            tbl = tbl - IMG
        for k in range(n + 1):
            if IA32:
                t = struct.unpack_from('<I', self.pe.img, tbl + 4 * k)[0]
            else:
                t = IMG + struct.unpack_from('<i', self.pe.img, tbl + 4 * k)[0]
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
        seg = ''
        if m.segment != 0:
            snm = ins.reg_name(m.segment)
            if snm == 'gs':
                seg = '(ott_gsbase + (uint64_t)'    # Win64: gs = TEB shadow (ott_cpu.c)
            elif snm == 'fs':
                seg = '(ott_fsbase + (uint64_t)'
            elif IA32 and snm in ('es', 'ds', 'cs', 'ss'):   # ia32 user mode: 平坦 (base 0)
                seg = ''
            else:
                raise Unsup('segment ' + snm)
        if m.base == X86_REG_RIP:
            tgt = ins.address + ins.size + m.disp
            if 0x180001000 <= tgt < 0x1801e2000 and ins.mnemonic != 'lea':
                self.textrefs.add(tgt)
            e = gv(tgt)
        else:
            terms = []
            if m.base != 0:
                i, s, h = self.reg(ins, m.base)
                terms.append('R[%d]' % i)
            if m.index != 0:
                i, s, h = self.reg(ins, m.index)
                terms.append('R[%d]*%d' % (i, m.scale) if m.scale != 1 else 'R[%d]' % i)
            disp = m.disp
            if m.base == 0 and m.index == 0:
                e = gv(disp)
            else:
                if disp:
                    terms.append(hx(disp & 0xffffffffffffffff))
                e = '(' + ' + '.join(terms) + ')'
        return seg + e + ')' if seg else e

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
            return gv(v) if sz == 8 else hex(v) + 'U'
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
        ret = gv(ins.address + ins.size)
        if IA32:
            return 'R[RSP] -= 4; ST32(R[RSP], %s); ' % ret + tgt
        return 'R[RSP] -= 8; ST64(R[RSP], %s); ' % ret + tgt

    def emit_call_direct(self, ins, t):
        if t in self.thunks:
            return self.call_stmt(ins, 'imp_%s();' % self.thunks[t])
        if t in self.known:
            return self.call_stmt(ins, 'f_%x();' % t)
        return self.call_stmt(ins, 'ott_unlifted(%s);' % gv(t))

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
                if VEXCOV and strip_prefix(ins.mnemonic).startswith('v'):
                    self.L('OTT_VEXCOV_HIT(%s);' % hx(sh(va)))   # shifted VA (uint32 収容) — JS で RVA に戻す
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
        if m == 'repne scasb':
            return self.repne_scasb(ins)
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
        if m[:2] == 'vf' and m.endswith(('sd', 'ss')) and m[1:-2].rstrip('0123') != m[1:-2]:
            return (self.i_vfma_sd if m.endswith('sd') else self.i_vfma_ss)(ins, ops, m)
        if m.startswith('vcmp') and m.endswith(('sd', 'ss')) and m[4:-2] in self.PRED:
            return (self.i_vcmpsd if m.endswith('sd') else self.i_vcmpss)(ins, ops, m)
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
        if ops[1].type == X86_OP_MEM and ops[1].mem.segment != 0:
            return self.mov_seg(ins, ops)
        self.L(self.wr(ins, ops[0], self.rd(ins, ops[1], ops[0].size)))

    def mov_seg(self, ins, ops):
        """CAB-135: CRT の TLS fallback 経路 (gs:[0x58] ThreadLocalStoragePointer / gs:[0x10] TEB self)。
        guest に実 TEB は無いので定数に張り替える: 0x58 → fake TLS 配列 (image 末尾の未使用領域,
        native/wasm とも 0 埋め = 「TLS 未割当」扱いで CRT の fallback に落ちる)、
        0x10 → __chkstk 系 probe が使うスタック上限参照 (guest rsp 直上を返して probe を
        guest stack 内に閉じる。単一 site 0x1801a065c のみ)。"""
        m = ops[1].mem
        seg = ins.reg_name(m.segment) if m.segment else ''
        if seg == 'gs' and m.base == 0 and m.index == 0 and ops[1].size == 8:
            if m.disp == 0x58:
                return self.L(self.wr(ins, ops[0], gv(TLSA_VA), 8))
            if m.disp == 0x10:
                return self.L(self.wr(ins, ops[0], '(R[RSP] + 0x1000)', 8))
        if IA32 and seg in ('fs', 'es', 'ds', 'cs', 'ss'):   # ia32: ea() と同じ経路 (fs は ott_fsbase、es/ds/cs/ss は平坦)
            return self.L(self.wr(ins, ops[0], self.rd(ins, ops[1], ops[0].size)))
        raise Unsup('segment ' + seg)

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
        if IA32:   # ia32: push r32/imm32/m32 (4 B)。ops[0] は 32bit 値として扱う
            self.L('{ uint32_t v_ = %s; R[RSP] -= 4; ST32(R[RSP], v_); }' % self.rd(ins, ops[0], 4))
            return
        self.L('{ uint64_t v_ = %s; R[RSP] -= 8; ST64(R[RSP], v_); }' % self.rd(ins, ops[0], 8))

    def i_pop(self, ins, ops):
        if IA32:
            self.L('{ uint32_t v_ = LD32(R[RSP]); R[RSP] += 4; %s }' % self.wr(ins, ops[0], 'v_', 4))
            return
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
            if RELOC:   # case 値は RVA、selector は base を引いて比べる
                sw = ' '.join('case %s: goto %s;' % (hx(t - IMG), self.label(t)) for t in sorted(set(self.jtabs[ins.address])))
                sel = '(%s) - ott_gbase' % self.rd(ins, op, PTR)
            else:
                sw = ' '.join('case %s: goto %s;' % (hx(sh(t)), self.label(t)) for t in sorted(set(self.jtabs[ins.address])))
                sel = self.rd(ins, op, PTR)
            return self.L('switch (%s) { %s default: ott_badjump(%s, %s); }' % (sel, sw, hx(ins.address), self.rd(ins, op, PTR)))
        slot = iat_slot(ins, op)
        if slot is not None and slot in self.pe.iat:
            return self.L('imp_%s(); return;' % self.pe.iat[slot])
        # 間接 tail jmp (CFG dispatch 等): target を値として dispatch
        return self.L('{ uint64_t t_ = %s; ott_dispatch(t_); return; }' % self.rd(ins, op, PTR))

    def i_call(self, ins, ops):
        op = ops[0]
        if op.type == X86_OP_IMM:
            return self.L(self.emit_call_direct(ins, op.imm))
        slot = iat_slot(ins, op)
        if slot is not None and slot in self.pe.iat:
            return self.L(self.call_stmt(ins, 'imp_%s();' % self.pe.iat[slot]))
        self.L('{ uint64_t t_ = %s; ' % self.rd(ins, op, PTR) + self.call_stmt(ins, 'ott_dispatch(t_);') + ' }')

    def i_ret(self, ins, ops):
        if IA32 and ops:   # ia32 の ret imm16 (stdcall): 戻り先 + 引数分を捨てる。x64 の出力は不変
            self.L('R[RSP] += %d; return;' % (PTR + ops[0].imm))
            return
        self.L('R[RSP] += %d; return;' % PTR)

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

    def ia32_only(self, m):
        if not IA32:
            raise Unsup(m)

    def ia32_str(self, ins, kind, w):
        """ia32 の非 rep 文字列命令 (1 要素)。DF=0 前提 (rep() と同じ)。ES/DS は平坦 (ea() 参照)。"""
        self.ia32_only(ins.mnemonic)
        if kind == 'movs':
            return self.L('{ uint%d_t v_ = LD%d(R[RSI]); ST%d(R[RDI], v_); R[RSI] += %d; R[RDI] += %d; }' % (w * 8, w * 8, w * 8, w, w))
        self.L('ST%d(R[RDI], R[RAX]); R[RDI] += %d;' % (w * 8, w))

    def i_movsb(self, ins, ops): self.ia32_str(ins, 'movs', 1)
    def i_movsw(self, ins, ops): self.ia32_str(ins, 'movs', 2)
    def i_stosb(self, ins, ops): self.ia32_str(ins, 'stos', 1)
    def i_stosw(self, ins, ops): self.ia32_str(ins, 'stos', 2)
    def i_stosd(self, ins, ops): self.ia32_str(ins, 'stos', 4)

    def repne_scasb(self, ins):
        self.ia32_only('repne scasb')
        self.L('{ while (R[RCX] != 0) { uint8_t a_ = (uint8_t)R[RAX]; uint8_t b_ = LD8(R[RDI]); FL_SUB(8, a_, b_, (uint8_t)(a_ - b_)); R[RDI] += 1; R[RCX] -= 1; if (fZF) break; } }')

    def i_sahf(self, ins, ops):
        self.ia32_only('sahf')   # AF は runtime が持たないため未反映 (x87 比較の後の分岐は CF/ZF/PF で足りる)
        self.L('{ uint8_t ah_ = (uint8_t)(R[RAX] >> 8); fCF = ah_ & 1; fPF = (ah_ >> 2) & 1; fZF = (ah_ >> 6) & 1; fSF = (ah_ >> 7) & 1; }')

    def i_xlatb(self, ins, ops):
        self.ia32_only('xlatb')
        self.L('{ uint64_t a_ = R[RBX] + (R[RAX] & 0xff); R[RAX] = (R[RAX] & ~0xffULL) | LD8(a_); }')

    def i_wait(self, ins, ops):
        self.ia32_only('wait')   # fwait: 未処理 x87 例外の模型を持たないため no-op

    # ---- x87 (ia32 のみ。runtime は tools/ott/rt/ott_x87.h。スタック要素は double = f80→f64 lowering) ----
    X87_BIN = {'fadd': 0, 'fmul': 1, 'fsub': 2, 'fsubr': 3, 'fdiv': 4, 'fdivr': 5}

    def x87_idx(self, ins, op):
        if op.type != X86_OP_REG:
            raise Unsup('x87 operand')
        nm = ins.reg_name(op.reg)
        if nm == 'st':
            return 0
        if nm.startswith('st(') and nm.endswith(')'):
            return int(nm[3:-1])
        raise Unsup('x87 reg ' + nm)

    def x87_mem_val(self, ins, op, m):
        if op.size == 4:
            return 'LDF32(%s)' % self.ea(ins, op)
        if op.size == 8:
            return 'LDF64(%s)' % self.ea(ins, op)
        raise Unsup(m)

    def x87_arith(self, ins, ops, m):
        self.ia32_only(m)
        base = m[:-1] if m.endswith('p') and m[:-1] in self.X87_BIN else m
        if base not in self.X87_BIN:
            raise Unsup(m)
        pop = 1 if base != m else 0
        op = self.X87_BIN[base]
        if len(ops) == 1 and ops[0].type == X86_OP_MEM:   # ST(0) op= m32/m64
            if pop:
                raise Unsup(m)
            return self.L('x87_arith(%d, 0, %s, 0);' % (op, self.x87_mem_val(ins, ops[0], m)))
        if len(ops) == 1:
            i = self.x87_idx(ins, ops[0])
            if pop:   # DE 形: ST(i) op= ST(0) して pop (fsubp st(i) = ST(i) - ST(0))
                return self.L('x87_arith(%d, %d, x87_st(0), 1);' % (op, i))
            return self.L('x87_arith(%d, 0, x87_st(%d), 0);' % (op, i))   # D8 形: ST(0) op= ST(i)
        if len(ops) == 2:   # DC/DE 形: ST(i) op= ST(0) (オペランドは Intel 記法の dst, src)
            di = self.x87_idx(ins, ops[0])
            si = self.x87_idx(ins, ops[1])
            return self.L('x87_arith(%d, %d, x87_st(%d), %d);' % (op, di, si, pop))
        raise Unsup(m)

    def i_fadd(self, ins, ops): self.x87_arith(ins, ops, ins.mnemonic)
    i_faddp = i_fmul = i_fmulp = i_fsub = i_fsubp = i_fsubr = i_fsubrp = i_fdiv = i_fdivp = i_fdivr = i_fdivrp = i_fadd

    def i_fld(self, ins, ops):
        self.ia32_only('fld')
        o = ops[0]
        if o.type == X86_OP_MEM:
            if o.size == 10:
                return self.L('x87_push(x87_f80_to_f64((const uint8_t*)A_(%s)));' % self.ea(ins, o))
            return self.L('x87_push(%s);' % self.x87_mem_val(ins, o, 'fld'))
        self.L('x87_push(x87_st(%d));' % self.x87_idx(ins, o))

    def x87_store(self, ins, ops, m):
        self.ia32_only(m)
        o = ops[0]
        if o.type == X86_OP_MEM:
            if o.size == 4:
                self.L('STF32(%s, x87_st(0));' % self.ea(ins, o))
            elif o.size == 8:
                self.L('STF64(%s, x87_st(0));' % self.ea(ins, o))
            elif o.size == 10:
                self.L('x87_f64_to_f80(x87_st(0), (uint8_t*)A_(%s));' % self.ea(ins, o))
            else:
                raise Unsup(m)
        else:
            self.L('x87_set(%d, x87_st(0));' % self.x87_idx(ins, o))
        if m == 'fstp':
            self.L('x87_pop();')

    def i_fst(self, ins, ops): self.x87_store(ins, ops, 'fst')
    def i_fstp(self, ins, ops): self.x87_store(ins, ops, 'fstp')

    def i_fild(self, ins, ops):
        self.ia32_only('fild')
        o = ops[0]
        if o.type != X86_OP_MEM:
            raise Unsup('fild')
        t = {2: 'int16_t', 4: 'int32_t', 8: 'int64_t'}.get(o.size)
        if t is None:
            raise Unsup('fild')
        self.L('x87_push((double)(%s)LD%d(%s));' % (t, o.size * 8, self.ea(ins, o)))

    def x87_fist(self, ins, ops, m):
        self.ia32_only(m)
        o = ops[0]
        if o.type != X86_OP_MEM:
            raise Unsup(m)
        fn = {2: 'x87_fist16', 4: 'x87_fist32', 8: 'x87_fist64'}.get(o.size)
        if fn is None or (o.size == 8 and m == 'fist'):
            raise Unsup(m)
        self.L('ST%d(%s, %s(x87_st(0)));' % (o.size * 8, self.ea(ins, o), fn))
        if m == 'fistp':
            self.L('x87_pop();')

    def i_fist(self, ins, ops): self.x87_fist(ins, ops, 'fist')
    def i_fistp(self, ins, ops): self.x87_fist(ins, ops, 'fistp')

    def i_fld1(self, ins, ops): self.ia32_only('fld1'); self.L('x87_push(1.0);')
    def i_fldz(self, ins, ops): self.ia32_only('fldz'); self.L('x87_push(0.0);')
    def i_fchs(self, ins, ops): self.ia32_only('fchs'); self.L('x87_set(0, -x87_st(0));')
    def i_fabs(self, ins, ops): self.ia32_only('fabs'); self.L('x87_set(0, fabs(x87_st(0)));')

    def i_fxch(self, ins, ops):
        self.ia32_only('fxch')
        i = self.x87_idx(ins, ops[-1]) if ops else 1   # capstone は fxch st(i) を (st(0), st(i)) の 2 operand で返す
        self.L('{ double t_ = x87_st(0); x87_set(0, x87_st(%d)); x87_set(%d, t_); }' % (i, i))

    def x87_cmp(self, ins, ops, m):
        self.ia32_only(m)
        o = ops[0]
        if o.type == X86_OP_MEM:
            b = self.x87_mem_val(ins, o, m)
        else:
            b = 'x87_st(%d)' % self.x87_idx(ins, o)
        self.L('x87_fcom(x87_st(0), %s);' % b)
        if m == 'fcomp':
            self.L('x87_pop();')

    def i_fcom(self, ins, ops): self.x87_cmp(ins, ops, 'fcom')
    def i_fcomp(self, ins, ops): self.x87_cmp(ins, ops, 'fcomp')

    def i_fcompp(self, ins, ops):
        self.ia32_only('fcompp')
        self.L('x87_fcom(x87_st(0), x87_st(1)); x87_pop(); x87_pop();')

    def i_fnstsw(self, ins, ops):
        self.ia32_only('fnstsw')
        o = ops[0]
        if o.type == X86_OP_REG:
            return self.L('R[RAX] = (R[RAX] & ~0xffffULL) | x87_fsw();')
        if o.type != X86_OP_MEM or o.size != 2:
            raise Unsup('fnstsw')
        self.L('ST16(%s, x87_fsw());' % self.ea(ins, o))

    def i_fnstcw(self, ins, ops):
        self.ia32_only('fnstcw')
        if ops[0].type != X86_OP_MEM or ops[0].size != 2:
            raise Unsup('fnstcw')
        self.L('ST16(%s, ott_fcw);' % self.ea(ins, ops[0]))

    def i_fldcw(self, ins, ops):
        self.ia32_only('fldcw')
        if ops[0].type != X86_OP_MEM or ops[0].size != 2:
            raise Unsup('fldcw')
        self.L('ott_fcw = LD16(%s);' % self.ea(ins, ops[0]))

    def i_movsd(self, ins, ops):
        d, s = ops
        if IA32 and d.type == X86_OP_MEM and s.type == X86_OP_MEM:   # ia32 の非 rep movsd (文字列)
            return self.ia32_str(ins, 'movs', 4)
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

    def i_ldmxcsr(self, ins, ops): self.L('ott_mxcsr = LD32(%s);' % self.ea(ins, ops[0]))
    def i_stmxcsr(self, ins, ops): self.L('ST32(%s, ott_mxcsr);' % self.ea(ins, ops[0]))
    i_vldmxcsr = i_ldmxcsr
    i_vstmxcsr = i_stmxcsr
    def i_leave(self, ins, ops):
        if IA32:
            return self.L('R[RSP] = R[RBP]; R[RBP] = LD32(R[RSP]); R[RSP] += 4;')
        self.L('R[RSP] = R[RBP]; R[RBP] = LD64(R[RSP]); R[RSP] += 8;')
    def i_cld(self, ins, ops): pass
    def i_cpuid(self, ins, ops): self.L('ott_unsup(%s, "cpuid");' % hx(ins.address))

    # ---- VEX / AVX (CAB-135) ----
    # VEX.128 は dest の上位 128bit を 0 化する (XZ)、VEX.256 は X+XH の組。
    # 3 operand 形: d, s1(reg), s2(reg/mem) — s2 を xs() で読む。
    def yd(self, ins, rid):
        nm = ins.reg_name(rid)
        if nm.startswith('ymm'):
            return int(nm[3:])
        raise Unsup('ymm ' + nm)

    def isy(self, ins, op):
        return op.type == X86_OP_REG and ins.reg_name(op.reg).startswith('ymm')

    def ysrc(self, ins, op):
        """ymm source の (lo_expr, hi_expr) — reg は X/XH、mem は 32B を 2 半分に読む"""
        if op.type == X86_OP_REG:
            i = self.yd(ins, op.reg)
            return 'X[%d]' % i, 'XH[%d]' % i
        e = self.ea(ins, op)
        return 'LDX(%s)' % e, 'LDX((%s) + 16)' % e

    def vmov128(self, ins, ops):
        """vmovdqa/vmovdqu/vmovaps/vmovapd/vmovupd/vmovups (VEX 2-op)。xmm dest は上位 0 化"""
        d, s = ops
        if d.type == X86_OP_MEM:
            if self.isy(ins, s):
                return self.L('STY(%d, %s);' % (self.yd(ins, s.reg), self.ea(ins, d)))
            return self.L('STX(%s, X[%d]);' % (self.ea(ins, d), self.xd(ins, s)))
        if self.isy(ins, d):
            di = self.yd(ins, d.reg)
            lo, hi = self.ysrc(ins, s)
            return self.L('{ X128 l_ = %s, h_ = %s; X[%d] = l_; XH[%d] = h_; }' % (lo, hi, di, di))
        di = self.xd(ins, d)
        if s.type == X86_OP_REG:
            return self.L('{ X[%d] = X[%d]; %s }' % (di, self.xd(ins, s), 'XZ(%d);' % di))
        return self.L('{ X[%d] = LDX(%s); %s }' % (di, self.ea(ins, s), 'XZ(%d);' % di))
    i_vmovdqa = i_vmovdqu = i_vmovaps = i_vmovapd = i_vmovupd = i_vmovups = vmov128

    def i_vmovntdq(self, ins, ops):
        d, s = ops
        if self.isy(ins, s):
            return self.L('STY(%d, %s);' % (self.yd(ins, s.reg), self.ea(ins, d)))   # 非一時 store = 単 thread では通常 store と同一
        self.L('STX(%s, X[%d]);' % (self.ea(ins, d), self.xd(ins, s)))

    def i_movntps(self, ins, ops): self.L('STX(%s, X[%d]);' % (self.ea(ins, ops[0]), self.xd(ins, ops[1])))
    i_movntpd = i_movntdq_x = i_movntps

    def i_sfence(self, ins, ops): pass
    def i_vzeroupper(self, ins, ops):
        self.L('{ for (int k_ = 0; k_ < 16; k_++) XH[k_].q[0] = XH[k_].q[1] = 0; }')

    def vscal(self, ins, ops, op, ty):
        """VEX スカラ 3-op 算術 (d = s1 OP s2, 上位 0 化)。ty: f32/f64"""
        di = self.xd(ins, ops[0])
        f = 'f' if ty == 'f32' else 'df'
        T = 'float' if ty == 'f32' else 'double'
        self.L('{ %s a_ = %s; %s b_ = %s; X[%d].%s[0] = %s; %s }' % (
            T, self.xs(ins, ops[1], ty), T, self.xs(ins, ops[2], ty), di, f, op, 'XZ(%d);' % di))
    def i_vaddsd(self, i, o): self.vscal(i, o, 'a_ + b_', 'f64')
    def i_vsubsd(self, i, o): self.vscal(i, o, 'a_ - b_', 'f64')
    def i_vmulsd(self, i, o): self.vscal(i, o, 'a_ * b_', 'f64')
    def i_vdivsd(self, i, o): self.vscal(i, o, 'a_ / b_', 'f64')
    def i_vaddss(self, i, o): self.vscal(i, o, 'a_ + b_', 'f32')
    def i_vsubss(self, i, o): self.vscal(i, o, 'a_ - b_', 'f32')
    def i_vmulss(self, i, o): self.vscal(i, o, 'a_ * b_', 'f32')
    def i_vdivss(self, i, o): self.vscal(i, o, 'a_ / b_', 'f32')
    def i_vmaxsd(self, i, o): self.vscal(i, o, '(a_ > b_) ? a_ : b_', 'f64')
    def i_vminsd(self, i, o): self.vscal(i, o, '(a_ < b_) ? a_ : b_', 'f64')
    def i_vmaxss(self, i, o): self.vscal(i, o, '(a_ > b_) ? a_ : b_', 'f32')
    def i_vminss(self, i, o): self.vscal(i, o, '(a_ < b_) ? a_ : b_', 'f32')

    FMA_BASE = ('fmadd', 'fmsub', 'fnmadd', 'fnmsub')
    FMA_BASE = ('fmadd', 'fmsub', 'fnmadd', 'fnmsub')

    def vfma(self, ins, ops, base, form, ty):
        """vfmadd/fmsub/fnmadd/fnmsub (132/213/231)。d = fma(x, y, z) の 1 回丸め。
        132: d*s2 + s1 / 213: s1*d + s2 / 231: s1*s2 + d (Intel 規約)。"""
        di = self.xd(ins, ops[0])
        f = 'f' if ty == 'f32' else 'df'
        T = 'float' if ty == 'f32' else 'double'
        FM = 'ott_fma_d' if ty == 'f64' else 'ott_fma_s'
        c_old = 'X[%d].%s[0]' % (di, f)
        p1 = self.xs(ins, ops[1], ty)
        p2 = self.xs(ins, ops[2], ty)
        if form == '132': x, y, z = c_old, p2, p1
        elif form == '213': x, y, z = p1, c_old, p2
        else: x, y, z = p1, p2, c_old
        sx = '-(%s)' % x if base in ('fnmadd', 'fnmsub') else x
        sz = '-(%s)' % z if base in ('fmsub', 'fnmsub') else z
        self.L('{ %s r_ = %s(%s, %s, %s); X[%d].%s[0] = r_; %s }' % (T, FM, sx, y, sz, di, f, 'XZ(%d);' % di))
    def i_vfma_sd(self, ins, ops, m):
        base = m[1:-2] if m.startswith('v') else m[:-2]
        for b in self.FMA_BASE:
            if base.startswith(b):
                form = base[len(b):]
                if form in ('132', '213', '231'):
                    return self.vfma(ins, ops, b, form, 'f64')
        raise Unsup(m)
    def i_vfma_ss(self, ins, ops, m):
        base = m[1:-2] if m.startswith('v') else m[:-2]
        for b in self.FMA_BASE:
            if base.startswith(b):
                form = base[len(b):]
                if form in ('132', '213', '231'):
                    return self.vfma(ins, ops, b, form, 'f32')
        raise Unsup(m)

    def vpacked_d(self, ins, ops, op):
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; X128 r_; for (int k_ = 0; k_ < 2; k_++) { double x_ = a_.df[k_], y_ = b_.df[k_]; r_.df[k_] = %s; } X[%d] = r_; %s }' % (
            self.xs(ins, ops[2], 'x128'), self.xd(ins, ops[1]), op, di, 'XZ(%d);' % di))

    def vpacked_f(self, ins, ops, op):
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; X128 r_; for (int k_ = 0; k_ < 4; k_++) { float x_ = a_.f[k_], y_ = b_.f[k_]; r_.f[k_] = %s; } X[%d] = r_; %s }' % (
            self.xs(ins, ops[2], 'x128'), self.xd(ins, ops[1]), op, di, 'XZ(%d);' % di))

    def i_vaddpd(self, i, o): self.vpacked_d(i, o, 'x_ + y_')
    def i_vsubpd(self, i, o): self.vpacked_d(i, o, 'x_ - y_')
    def i_vmulpd(self, i, o): self.vpacked_d(i, o, 'x_ * y_')
    def i_vdivpd(self, i, o): self.vpacked_d(i, o, 'x_ / y_')
    def i_vaddps(self, i, o): self.vpacked_f(i, o, 'x_ + y_')
    def i_vsubps(self, i, o): self.vpacked_f(i, o, 'x_ - y_')
    def i_vmulps(self, i, o): self.vpacked_f(i, o, 'x_ * y_')
    def i_vdivps(self, i, o): self.vpacked_f(i, o, 'x_ / y_')

    def vbitw(self, ins, ops, op):
        """VEX ビット毎 3-op (andpd/andps/or/xor — FP/INT 同義)。op は演算子 or 式テンプレート (%s 含む)"""
        di = self.xd(ins, ops[0])
        e = ('a_.q[k_] %s b_.q[k_]' % op) if '%s' not in op else (op % ('a_.q[k_]', 'b_.q[k_]'))
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; X128 r_; for (int k_ = 0; k_ < 2; k_++) r_.q[k_] = %s; X[%d] = r_; %s }' % (
            self.xs(ins, ops[2], 'x128'), self.xd(ins, ops[1]), e, di, 'XZ(%d);' % di))
    def i_vandpd(self, i, o): self.vbitw(i, o, '&')
    def i_vandps(self, i, o): self.vbitw(i, o, '&')
    def i_vorpd(self, i, o): self.vbitw(i, o, '|')
    def i_vorps(self, i, o): self.vbitw(i, o, '|')
    def i_vxorpd(self, i, o): self.vbitw(i, o, '^')
    def i_vxorps(self, i, o): self.vbitw(i, o, '^')

    def vlanei(self, ins, ops, field, n, op):
        """VEX 整数 lane 演算 3-op (vpaddq/vpsubd 等)"""
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; X128 r_; for (int k_ = 0; k_ < %d; k_++) r_.%s[k_] = a_.%s[k_] %s b_.%s[k_]; X[%d] = r_; %s }' % (
            self.xs(ins, ops[2], 'x128'), self.xd(ins, ops[1]), n, field, field, op, field, di, 'XZ(%d);' % di))
    def i_vandnps(self, i, o): self.vbitw(i, o, '~%s & %s')
    i_vandnpd = i_vandnps
    def i_vpand(self, i, o): self.vbitw(i, o, '&')
    def i_vpor(self, i, o): self.vbitw(i, o, '|')
    def i_vpxor(self, i, o): self.vbitw(i, o, '^')
    def i_vpaddq(self, i, o): self.vlanei(i, o, 'q', 2, '+')
    def i_vpsubq(self, i, o): self.vlanei(i, o, 'q', 2, '-')
    def i_vpaddd(self, i, o): self.vlanei(i, o, 'd', 4, '+')
    def i_vpsubd(self, i, o): self.vlanei(i, o, 'd', 4, '-')
    def i_vpaddw(self, i, o): self.vlanei(i, o, 'w', 8, '+')
    def i_vpsubw(self, i, o): self.vlanei(i, o, 'w', 8, '-')
    def i_vpaddb(self, i, o): self.vlanei(i, o, 'b', 16, '+')
    def i_vpsubb(self, i, o): self.vlanei(i, o, 'b', 16, '-')

    def vpcmpeq(self, ins, ops, field, n, w):
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; X128 r_; for (int k_ = 0; k_ < %d; k_++) r_.%s[k_] = (a_.%s[k_] == b_.%s[k_]) ? %s : 0; X[%d] = r_; %s }' % (
            self.xs(ins, ops[2], 'x128'), self.xd(ins, ops[1]), n, field, field, field, w, di, 'XZ(%d);' % di))
    def i_vpcmpeqb(self, i, o):
        if self.isy(i, o[0]) or (o[-1].type == X86_OP_REG and self.isy(i, o[-1])): return self.vpcmpymm(i, o, 'b', 16, '0xff')
        return self.vpcmpeq(i, o, 'b', 16, '0xff')
    def i_vpcmpeqw(self, i, o):
        if self.isy(i, o[0]) or (o[-1].type == X86_OP_REG and self.isy(i, o[-1])): return self.vpcmpymm(i, o, 'w', 8, '0xffff')
        return self.vpcmpeq(i, o, 'w', 8, '0xffff')
    def i_vpcmpeqd(self, i, o):
        if self.isy(i, o[0]) or (o[-1].type == X86_OP_REG and self.isy(i, o[-1])): return self.vpcmpymm(i, o, 'd', 4, '0xffffffffu')
        return self.vpcmpeq(i, o, 'd', 4, '0xffffffffu')

    def vpcmpymm(self, ins, ops, field, n, w):
        """VEX.256 整数比較 (ymm 32B)"""
        di = self.yd(ins, ops[0].reg) if ops[0].type == X86_OP_REG else None
        if di is None:
            raise Unsup('vpcmpeq ymm mem dest')
        lo, hi = self.ysrc(ins, ops[2])
        self.L('{ X128 b0_ = %s, b1_ = %s, a0_ = X[%d], a1_ = XH[%d], r0_, r1_; '
               'for (int k_ = 0; k_ < %d; k_++) { r0_.%s[k_] = (a0_.%s[k_] == b0_.%s[k_]) ? %s : 0; '
               'r1_.%s[k_] = (a1_.%s[k_] == b1_.%s[k_]) ? %s : 0; } '
               'X[%d] = r0_; XH[%d] = r1_; }' % (
                   lo, hi, di, di, n, field, field, field, w, field, field, field, w, di, di))
    def i_vpcmpeqb_ymm(self, ins, ops): self.vpcmpymm(ins, ops, 'b', 16, '0xff')
    def i_vpcmpeqw_ymm(self, ins, ops): self.vpcmpymm(ins, ops, 'w', 8, '0xffff')
    def i_vpcmpeqd_ymm(self, ins, ops): self.vpcmpymm(ins, ops, 'd', 4, '0xffffffffu')

    def i_vpmovmskb(self, ins, ops):
        if self.isy(ins, ops[1]):
            s = self.yd(ins, ops[1].reg)
            self.L('{ uint32_t m_ = 0; for (int k_ = 0; k_ < 16; k_++) m_ |= ((X[%d].b[k_] >> 7) & 1u) << k_; '
                   'for (int k_ = 0; k_ < 16; k_++) m_ |= ((XH[%d].b[k_] >> 7) & 1u) << (16 + k_); %s }' % (
                       s, s, self.wr(ins, ops[0], 'm_', 4)))
        else:
            s = self.xd(ins, ops[1])
            self.L('{ uint32_t m_ = 0; for (int k_ = 0; k_ < 16; k_++) m_ |= ((X[%d].b[k_] >> 7) & 1u) << k_; %s }' % (
                s, self.wr(ins, ops[0], 'm_', 4)))

    def vshiftimm(self, ins, ops, field, n, kind):
        """VEX lane shift 3-op (vpsllq/vpsrlq/vpsrad 等)。src2 = imm または reg"""
        di = self.xd(ins, ops[0])
        if ops[2].type == X86_OP_IMM:
            c = str(ops[2].imm)
        else:
            c = 'X[%d].q[0]' % self.xd(ins, ops[2]) if ops[2].type == X86_OP_REG else 'LD64(%s)' % self.ea(ins, ops[2])
        W = {'q': 64, 'd': 32, 'w': 16}[field]
        T = {'q': 'uint64_t', 'd': 'uint32_t', 'w': 'uint16_t'}[field]
        ST = {'q': 'int64_t', 'd': 'int32_t', 'w': 'int16_t'}[field]
        if kind == 'l':
            e = '(c_ >= %d) ? 0 : (%s)(a_.%s[k_] << c_)' % (W, T, field)
        elif kind == 'r':
            e = '(c_ >= %d) ? 0 : (%s)(a_.%s[k_] >> c_)' % (W, T, field)
        else:
            e = '(%s)(((%s)a_.%s[k_]) >> (c_ >= %d ? %d : c_))' % (T, ST, field, W, W - 1)
        self.L('{ uint64_t c_ = %s; X128 a_ = X[%d], r_; for (int k_ = 0; k_ < %d; k_++) r_.%s[k_] = %s; X[%d] = r_; %s }' % (
            c, self.xd(ins, ops[1]), n, field, e, di, 'XZ(%d);' % di))
    def i_vpsllq(self, i, o): self.vshiftimm(i, o, 'q', 2, 'l')
    def i_vpsrlq(self, i, o): self.vshiftimm(i, o, 'q', 2, 'r')
    def i_vpslld(self, i, o): self.vshiftimm(i, o, 'd', 4, 'l')
    def i_vpsrld(self, i, o): self.vshiftimm(i, o, 'd', 4, 'r')
    def i_vpsrad(self, i, o): self.vshiftimm(i, o, 'd', 4, 'a')
    def i_vpsllw(self, i, o): self.vshiftimm(i, o, 'w', 8, 'l')
    def i_vpsrlw(self, i, o): self.vshiftimm(i, o, 'w', 8, 'r')
    def i_vpsraw(self, i, o): self.vshiftimm(i, o, 'w', 8, 'a')

    def i_vpsrldq(self, ins, ops):
        di = self.xd(ins, ops[0]); n = ops[2].imm
        self.L('{ X128 a_ = X[%d], r_; memset(&r_, 0, 16); int n_ = %d; if (n_ < 16) memcpy(r_.b, a_.b + n_, 16 - n_); X[%d] = r_; %s }' % (
            self.xd(ins, ops[1]), n, di, 'XZ(%d);' % di))

    def i_vpslldq(self, ins, ops):
        di = self.xd(ins, ops[0]); n = ops[2].imm
        self.L('{ X128 a_ = X[%d], r_; memset(&r_, 0, 16); int n_ = %d; if (n_ < 16) memcpy(r_.b + n_, a_.b, 16 - n_); X[%d] = r_; %s }' % (
            self.xd(ins, ops[1]), n, di, 'XZ(%d);' % di))

    def i_vpshufd(self, ins, ops):
        di = self.xd(ins, ops[0]); imm = ops[2].imm
        self.L('{ X128 s_ = %s; X128 r_; r_.d[0] = s_.d[%d]; r_.d[1] = s_.d[%d]; r_.d[2] = s_.d[%d]; r_.d[3] = s_.d[%d]; X[%d] = r_; %s }' % (
            self.xs(ins, ops[1], 'x128'), imm & 3, (imm >> 2) & 3, (imm >> 4) & 3, (imm >> 6) & 3, di, 'XZ(%d);' % di))

    def i_vshufps(self, ins, ops):
        di = self.xd(ins, ops[0]); imm = ops[3].imm
        self.L('{ X128 a_ = X[%d]; X128 s_ = %s; X128 r_; r_.d[0] = a_.d[%d]; r_.d[1] = a_.d[%d]; r_.d[2] = s_.d[%d]; r_.d[3] = s_.d[%d]; X[%d] = r_; %s }' % (
            self.xd(ins, ops[1]), self.xs(ins, ops[2], 'x128'), imm & 3, (imm >> 2) & 3, (imm >> 4) & 3, (imm >> 6) & 3, di, 'XZ(%d);' % di))

    def i_vshufpd(self, ins, ops):
        di = self.xd(ins, ops[0]); imm = ops[3].imm
        self.L('{ X128 a_ = X[%d]; X128 s_ = %s; X128 r_; r_.q[0] = a_.q[%d]; r_.q[1] = s_.q[%d]; X[%d] = r_; %s }' % (
            self.xd(ins, ops[1]), self.xs(ins, ops[2], 'x128'), imm & 1, (imm >> 1) & 1, di, 'XZ(%d);' % di))

    def i_vunpcklpd(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 a_ = X[%d]; X128 s_ = %s; X128 r_; r_.q[0] = a_.q[0]; r_.q[1] = s_.q[0]; X[%d] = r_; %s }' % (
            self.xd(ins, ops[1]), self.xs(ins, ops[2], 'x128'), di, 'XZ(%d);' % di))

    def i_vunpckhpd(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 a_ = X[%d]; X128 s_ = %s; X128 r_; r_.q[0] = a_.q[1]; r_.q[1] = s_.q[1]; X[%d] = r_; %s }' % (
            self.xd(ins, ops[1]), self.xs(ins, ops[2], 'x128'), di, 'XZ(%d);' % di))

    def i_vpunpckldq(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 a_ = X[%d]; X128 s_ = %s; X128 r_; r_.d[0] = a_.d[0]; r_.d[1] = s_.d[0]; r_.d[2] = a_.d[1]; r_.d[3] = s_.d[1]; X[%d] = r_; %s }' % (
            self.xd(ins, ops[1]), self.xs(ins, ops[2], 'x128'), di, 'XZ(%d);' % di))

    def i_vpunpckhdq(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 a_ = X[%d]; X128 s_ = %s; X128 r_; r_.d[0] = a_.d[2]; r_.d[1] = s_.d[2]; r_.d[2] = a_.d[3]; r_.d[3] = s_.d[3]; X[%d] = r_; %s }' % (
            self.xd(ins, ops[1]), self.xs(ins, ops[2], 'x128'), di, 'XZ(%d);' % di))

    def i_vpmovsxdq(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 s_ = %s; X128 r_; r_.sq[0] = (int64_t)s_.sd[0]; r_.sq[1] = (int64_t)s_.sd[1]; X[%d] = r_; %s }' % (
            self.xs(ins, ops[1], 'x128'), di, 'XZ(%d);' % di))

    def i_vmovsd(self, ins, ops):
        d = ops[0]
        if len(ops) == 2:
            s = ops[1]
            if d.type == X86_OP_MEM:
                return self.L('STF64(%s, X[%d].df[0]);' % (self.ea(ins, d), self.xd(ins, s)))
            di = self.xd(ins, d)
            if s.type == X86_OP_REG:
                return self.L('{ uint64_t v_ = X[%d].q[0]; X[%d].q[0] = v_; X[%d].q[1] = 0; %s }' % (self.xd(ins, s), di, di, 'XZ(%d);' % di))
            return self.L('{ uint64_t v_ = LD64(%s); X[%d].q[0] = v_; X[%d].q[1] = 0; %s }' % (self.ea(ins, s), di, di, 'XZ(%d);' % di))
        di = self.xd(ins, d)   # 3-op: d = { s2 低 64, s1 高 64 }
        s1 = self.xd(ins, ops[1])
        if ops[2].type == X86_OP_REG:
            s2 = 'X[%d].q[0]' % self.xd(ins, ops[2])
        else:
            s2 = 'LD64(%s)' % self.ea(ins, ops[2])
        self.L('{ uint64_t lo_ = %s; X[%d].q[0] = lo_; X[%d].q[1] = X[%d].q[1]; %s }' % (s2, di, di, s1, 'XZ(%d);' % di))

    def i_vmovss(self, ins, ops):
        d = ops[0]
        if len(ops) == 2:
            s = ops[1]
            if d.type == X86_OP_MEM:
                return self.L('STF32(%s, X[%d].f[0]);' % (self.ea(ins, d), self.xd(ins, s)))
            di = self.xd(ins, d)
            if s.type == X86_OP_REG:
                return self.L('{ uint32_t v_ = X[%d].d[0]; X[%d].d[0] = v_; X[%d].d[1] = X[%d].d[2] = X[%d].d[3] = 0; %s }' % (
                    self.xd(ins, s), di, di, di, di, 'XZ(%d);' % di))
            return self.L('{ uint32_t v_ = LD32(%s); X[%d].d[0] = v_; X[%d].d[1] = X[%d].d[2] = X[%d].d[3] = 0; %s }' % (
                self.ea(ins, s), di, di, di, di, 'XZ(%d);' % di))
        di = self.xd(ins, d)
        s1 = self.xd(ins, ops[1])
        if ops[2].type == X86_OP_REG:
            s2 = 'X[%d].d[0]' % self.xd(ins, ops[2])
        else:
            s2 = 'LD32(%s)' % self.ea(ins, ops[2])
        self.L('{ uint32_t lo_ = %s; X[%d].d[0] = lo_; X[%d].d[1] = X[%d].d[1]; X[%d].d[2] = X[%d].d[2]; X[%d].d[3] = X[%d].d[3]; %s }' % (
            s2, di, di, s1, di, s1, di, s1, 'XZ(%d);' % di))

    def i_vmovd(self, ins, ops):
        d, s = ops
        if self.isx(ins, d):
            di = self.xd(ins, d)
            v = self.rd(ins, s, 4)
            return self.L('{ uint32_t v_ = %s; X[%d].d[0] = v_; X[%d].d[1] = X[%d].d[2] = X[%d].d[3] = 0; %s }' % (
                v, di, di, di, di, 'XZ(%d);' % di))
        si = self.xd(ins, s)
        if d.type == X86_OP_REG:
            return self.L(self.wr(ins, d, 'X[%d].d[0]' % si, 4))
        self.L('ST32(%s, X[%d].d[0]);' % (self.ea(ins, d), si))

    def i_vmovq(self, ins, ops):
        d, s = ops
        if self.isx(ins, d):
            di = self.xd(ins, d)
            if self.isx(ins, s):
                return self.L('{ uint64_t v_ = X[%d].q[0]; X[%d].q[0] = v_; X[%d].q[1] = 0; %s }' % (self.xd(ins, s), di, di, 'XZ(%d);' % di))
            if s.type == X86_OP_REG:
                return self.L('{ uint64_t v_ = %s; X[%d].q[0] = v_; X[%d].q[1] = 0; %s }' % (self.rd(ins, s, 8), di, di, 'XZ(%d);' % di))
            return self.L('{ uint64_t v_ = LD64(%s); X[%d].q[0] = v_; X[%d].q[1] = 0; %s }' % (self.ea(ins, s), di, di, 'XZ(%d);' % di))
        si = self.xd(ins, s)
        if d.type == X86_OP_REG:
            return self.L(self.wr(ins, d, 'X[%d].q[0]' % si, 8))
        self.L('ST64(%s, X[%d].q[0]);' % (self.ea(ins, d), si))

    def i_vcomisd(self, ins, ops): self.L('comis_f(X[%d].df[0], %s, 0);' % (self.xd(ins, ops[0]), self.xs(ins, ops[1], 'f64')))
    def i_vucomisd(self, ins, ops): self.L('comis_f(X[%d].df[0], %s, 0);' % (self.xd(ins, ops[0]), self.xs(ins, ops[1], 'f64')))
    def i_vcomiss(self, ins, ops): self.L('comis_f((double)X[%d].f[0], (double)%s, 0);' % (self.xd(ins, ops[0]), self.xs(ins, ops[1], 'f32')))
    def i_vucomiss(self, ins, ops): self.L('comis_f((double)X[%d].f[0], (double)%s, 0);' % (self.xd(ins, ops[0]), self.xs(ins, ops[1], 'f32')))

    def vcmp_pred(self, ins, ops, p, ty):
        """VCMP<pred>SD xmm1, xmm2, xmm3/m64 — src1 (ops[1]) vs src2 (ops[2]) を比較し mask を dest[63:0] へ。
        dest[127:64] = src1 の上位 (実 site は dest≠src1: 1801b4480 vcmplesd xmm2, xmm0, m64)。"""
        di = self.xd(ins, ops[0])
        s1 = self.xd(ins, ops[1])
        if ty == 'sd':
            self.L('{ double b_ = %s; X128 u_ = X[%d]; X[%d] = u_; X[%d].q[0] = cmp_pred_f(%d, u_.df[0], b_) ? ~0ULL : 0; %s }' % (
                self.xs(ins, ops[2], 'f64'), s1, di, di, p, 'XZ(%d);' % di))
        else:
            self.L('{ float b_ = %s; X128 u_ = X[%d]; X[%d] = u_; X[%d].d[0] = cmp_pred_f(%d, (double)u_.f[0], (double)b_) ? 0xffffffffu : 0; %s }' % (
                self.xs(ins, ops[2], 'f32'), s1, di, di, p, 'XZ(%d);' % di))

    def i_vcmpsd(self, ins, ops, m='vcmpsd'):
        base = m[4:-2]
        if base not in self.PRED:
            raise Unsup(m)
        self.vcmp_pred(ins, ops, self.PRED[base], 'sd')

    def i_vcmpss(self, ins, ops, m='vcmpss'):
        base = m[4:-2]
        if base not in self.PRED:
            raise Unsup(m)
        self.vcmp_pred(ins, ops, self.PRED[base], 'ss')

    def i_vcvtsd2ss(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ double b_ = %s; X[%d].f[0] = (float)b_; %s }' % (self.xs(ins, ops[2], 'f64'), di, 'XZ(%d);' % di))

    def i_vcvtss2sd(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ float b_ = %s; X[%d].df[0] = (double)b_; %s }' % (self.xs(ins, ops[2], 'f32'), di, 'XZ(%d);' % di))

    def i_vcvtsi2sd(self, ins, ops):
        di = self.xd(ins, ops[0]); sz = ops[2].size
        self.L('X[%d].df[0] = (double)(int%d_t)%s; %s' % (di, sz * 8, self.rd(ins, ops[2]), 'XZ(%d);' % di))

    def i_vcvtsi2ss(self, ins, ops):
        di = self.xd(ins, ops[0]); sz = ops[2].size
        self.L('X[%d].f[0] = (float)(int%d_t)%s; %s' % (di, sz * 8, self.rd(ins, ops[2]), 'XZ(%d);' % di))

    def i_vcvttsd2si(self, ins, ops):
        sz = ops[0].size
        self.L(self.wr(ins, ops[0], '(uint%d_t)cvtt_d2i%d(%s)' % (sz * 8, sz * 8, self.xs(ins, ops[1], 'f64')), sz))

    def i_vcvttss2si(self, ins, ops):
        sz = ops[0].size
        self.L(self.wr(ins, ops[0], '(uint%d_t)cvtt_d2i%d((double)%s)' % (sz * 8, sz * 8, self.xs(ins, ops[1], 'f32')), sz))

    def i_vcvtsd2si(self, ins, ops):
        sz = ops[0].size
        self.L(self.wr(ins, ops[0], '(uint%d_t)cvt_d2i%d(%s)' % (sz * 8, sz * 8, self.xs(ins, ops[1], 'f64')), sz))

    def i_vcvtss2si(self, ins, ops):
        sz = ops[0].size
        self.L(self.wr(ins, ops[0], '(uint%d_t)cvt_d2i%d((double)%s)' % (sz * 8, sz * 8, self.xs(ins, ops[1], 'f32')), sz))

    def i_vcvtdq2pd(self, ins, ops):
        di = self.xd(ins, ops[0])
        s = self.xs(ins, ops[1], 'q64')
        self.L('{ uint64_t s_ = %s; int32_t a_ = (int32_t)(uint32_t)s_, b_ = (int32_t)(uint32_t)(s_ >> 32); X[%d].df[0] = (double)a_; X[%d].df[1] = (double)b_; %s }' % (
            s, di, di, 'XZ(%d);' % di))

    def i_vcvtps2pd(self, ins, ops):
        di = self.xd(ins, ops[0])
        s = self.xs(ins, ops[1], 'q64')
        self.L('{ uint64_t s_ = %s; float f0_, f1_; memcpy(&f0_, &s_, 4); memcpy(&f1_, ((char*)&s_) + 4, 4); X[%d].df[0] = (double)f0_; X[%d].df[1] = (double)f1_; %s }' % (
            s, di, di, 'XZ(%d);' % di))

    def i_vcvtpd2dq(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 s_ = %s; int32_t a_ = cvt_d2i32(s_.df[0]), b_ = cvt_d2i32(s_.df[1]); X[%d].sd[0] = a_; X[%d].sd[1] = b_; X[%d].q[1] = 0; %s }' % (
            self.xs(ins, ops[1], 'x128'), di, di, di, 'XZ(%d);' % di))

    def i_vcvttpd2dq(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 s_ = %s; int32_t a_ = cvtt_d2i32(s_.df[0]), b_ = cvtt_d2i32(s_.df[1]); X[%d].sd[0] = a_; X[%d].sd[1] = b_; X[%d].q[1] = 0; %s }' % (
            self.xs(ins, ops[1], 'x128'), di, di, di, 'XZ(%d);' % di))

    def i_vcvtdq2ps(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 s_ = %s; for (int k_ = 0; k_ < 4; k_++) X[%d].f[k_] = (float)s_.sd[k_]; %s }' % (
            self.xs(ins, ops[1], 'x128'), di, 'XZ(%d);' % di))

    def i_vroundsd(self, ins, ops):
        di = self.xd(ins, ops[0]); imm = ops[3].imm
        self.L('{ double b_ = %s; X[%d].df[0] = ott_round_d(%d, b_); %s }' % (
            self.xs(ins, ops[2], 'f64'), di, imm, 'XZ(%d);' % di))

    def i_vroundss(self, ins, ops):
        di = self.xd(ins, ops[0]); imm = ops[3].imm
        self.L('{ float b_ = %s; X[%d].f[0] = (float)ott_round_d(%d, (double)b_); %s }' % (
            self.xs(ins, ops[2], 'f32'), di, imm, 'XZ(%d);' % di))

    def i_movhlps(self, ins, ops):
        di, si = self.xd(ins, ops[0]), self.xd(ins, ops[1])
        self.L('{ uint64_t hi_ = X[%d].q[1], lo_ = X[%d].q[0]; X[%d].q[0] = hi_; X[%d].q[1] = lo_; }' % (di, si, di, di))

    def i_movlhps(self, ins, ops):
        di, si = self.xd(ins, ops[0]), self.xd(ins, ops[1])
        self.L('{ uint64_t lo_ = X[%d].q[0]; X[%d].q[1] = lo_; }' % (si, di))

    def i_pshuflw(self, ins, ops):
        di = self.xd(ins, ops[0]); imm = ops[2].imm
        self.L('{ X128 s_ = %s; X128 r_ = X[%d]; r_.w[0] = s_.w[%d]; r_.w[1] = s_.w[%d]; r_.w[2] = s_.w[%d]; r_.w[3] = s_.w[%d]; X[%d] = r_; }' % (
            self.xs(ins, ops[1], 'x128'), di, imm & 3, (imm >> 2) & 3, (imm >> 4) & 3, (imm >> 6) & 3, di))

    def i_pcmpistri(self, ins, ops):
        di = self.xd(ins, ops[0])
        imm = ops[2].imm
        if imm != 0x40:
            raise Unsup('pcmpistri %x' % imm)
        self.L('{ uint32_t ix_ = ott_pcmpistri40(X[%d].b, %s); R[RCX] = (R[RCX] & ~0xffffffffULL) | ix_; }' % (
            di, self.ea(ins, ops[1])))

    def i_pcmpeqw(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; for (int k_ = 0; k_ < 8; k_++) a_.w[k_] = (a_.w[k_] == b_.w[k_]) ? 0xffff : 0; X[%d] = a_; }' % (
            self.xs(ins, ops[1], 'x128'), di, di))

    def i_rcr(self, ins, ops):
        """rcr (rotate through carry right)。CF:a の (W+1)bit 環を右回転。site は count=1 のみ
        (0x1801bc890 の FP 制御演算)。count>1 は loop で等価 (OF は count=1 のみ定義)。"""
        sz = ops[0].size; W = sz * 8; T = 'uint%d_t' % W
        cnt = self.rd(ins, ops[1], 1) if len(ops) > 1 else '1'
        self.L('{ %s a_ = %s; unsigned c_ = (unsigned)(%s) %% %d; uint64_t v_ = ((uint64_t)fCF << %d) | (uint64_t)a_; '
               'while (c_--) { uint64_t b_ = v_ & 1; v_ = (v_ >> 1) | (b_ << %d); } '
               'fCF = (uint8_t)((v_ >> %d) & 1); %s r_ = (%s)v_; fOF = ((r_ >> %d) & 1) ^ fCF; SETZSP(%d, r_); %s }' % (
                   T, self.rd(ins, ops[0], sz), cnt, W + 1, W, W, W, T, T, W - 1, W, self.wr(ins, ops[0], 'r_', sz)))

    def i_cmpxchg(self, ins, ops):
        """cmpxchg (lock は strip_prefix で除去済み = 単 thread と同一意味)。
        cmp dest,acc で flags → 等しければ dest = src、否なら RAX = dest。"""
        sz = ops[0].size; W = sz * 8; T = 'uint%d_t' % W
        amask = '0xffffffffffffffffULL' if sz == 8 else hex(MASK[sz])
        self.L('{ %s d_ = %s; %s a_ = (%s)(R[RAX] & %s); %s s_ = (%s)(%s); FL_SUB(%d, d_, a_, (%s)(d_ - a_)); '
               'if (d_ == a_) { %s } else { R[RAX] = (R[RAX] & ~%sULL) | (uint64_t)d_; } }' % (
                   T, self.rd(ins, ops[0], sz), T, T, amask, T, T, self.rd(ins, ops[1], sz), W, T,
                   self.wr(ins, ops[0], 's_', sz), amask))

    def i_int(self, ins, ops):
        # int 0x29 = __fastfail (CRT 異常終了経路) — guest では fail-fast が同じ意味
        self.L('ott_unsup(%s, "int 0x%x (fail-fast)");' % (hx(ins.address), ops[0].imm if ops else 0))

    def i_in(self, ins, ops):
        # port I/O — guest に存在しない (未実行経路のみ)。0 を返す
        self.L(self.wr(ins, ops[0], '0', ops[0].size))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', required=True)
    ap.add_argument('--entries', required=True, help='json: {"roots":[va..], "calltgt":[rva..]}')
    ap.add_argument('--out', required=True)
    ap.add_argument('--closure', type=int, default=0, help='未 lift の直接 call 先を再帰的に追加 (深さ)')
    ap.add_argument('--override', action='append', default=[], help='VA=CNAME: その関数 body を C 実装 (rt/ott_ovr.c) に置換')
    ap.add_argument('--arch', default='auto', choices=['auto', 'x64', 'ia32'], help='既定 auto = PE machine から決める。不一致は fail-fast (D18)')
    a = ap.parse_args()
    overrides = {int(x.split('=')[0], 16): x.split('=')[1] for x in a.override}
    pe = PEInfo(a.pe, a.arch)
    cfg = json.load(open(a.entries))
    entries = set(IMG + r for r in cfg.get('calltgt', [])) | set(cfg.get('roots', []))
    md = Cs(CS_ARCH_X86, CS_MODE_32 if IA32 else CS_MODE_64); md.detail = True
    thunks = {}

    def thunk_name(va):
        code = pe.bytes_at(va, 8)
        for i in md.disasm(code, va, 1):
            if i.mnemonic == 'jmp' and i.operands[0].type == X86_OP_MEM:
                slot = iat_slot(i, i.operands[0])
                return pe.iat.get(slot) if slot is not None else None
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
            if strip_prefix(ins.mnemonic) in ('call', 'jmp'):
                s = iat_slot(ins, ins.operands[0])
                if s is not None and s in pe.iat:
                    used_imps.add(pe.iat[s])
    used_imps = sorted(used_imps)
    with open(os.path.join(out, 'ott_lifted.c'), 'w') as fh:
        fh.write('#include "ott_cpu.h"\n')
        if IA32:
            fh.write('#include "ott_x87.h"\n')
        if RELOC:
            fh.write('extern uint64_t ott_gbase;\n')
        for nm in used_imps:
            fh.write('void imp_%s(void);\n' % nm)
        for c in sorted(set(overrides.values())):
            fh.write('void %s(void);\n' % c)
        for e in sorted(final):
            fh.write('void f_%x(void);\n' % e)
        for e in sorted(final):
            fh.write(final[e].csrc + '\n')
        fh.write('void ott_dispatch(uint64_t t) {\n  switch (%s) {\n' % ('t - ott_gbase' if RELOC else 't'))
        for e in sorted(final):
            fh.write('  case %s: f_%x(); return;\n' % (hx(e - IMG) if RELOC else hx(sh(e)), e))
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
