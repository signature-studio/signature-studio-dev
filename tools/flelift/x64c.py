#!/usr/bin/env python3
"""x64c.py (flelift fork) — x86-64 (MS ABI) 機械語 → C の命令 1:1 lifter (capstone)。RetDec 非依存。

tools/ott/lift/x64c.py (f4e0514+e58b418, OTT 実績: matrix 89/89 bit-exact) を FLEngine_x64.dll
(Delphi, ImageBase 0x400000) 向けに vendored fork して汎用化したもの (CAB-226)。tools/ott 本体は不変。

ott 原版からの差分 (FLEngine 実測 1,105 未対応 site = 0.32% の解消):
  - IMG/SHIFT/IMG_SIZE を CLI パラメタ化 (--img/--shift/--img-size, 既定 = FLEngine)
  - string 命令: 非 rep の movs*/stos*/lods* (movsq 632 / stosq 122 / stosd 5 / movsd 文字列形 29) + DF 対応
  - lock 系: xadd / cmpxchg / xchg / cmpxchg16b (単一スレッド前提の非 atomic 実装, flag 意味は保持)
  - bt/bts/btr/btc の mem,reg 形 (ビット文字列: byte = ea + (idx>>3))
  - MMX (mm0-7 → X[0..7] low 64bit alias) と 3DNow! (pi2fw/pi2fd)
  - SSE2 整数: packuswb/packssdw/packsswb/pmulhuw/pmulhw/pmullw/pmaddwd/pminsw/pmaxsw/pminub/pmaxub/
    paddusb/paddusw/psubusb/psubusw/paddsw/psubsw/pavgb/pavgw/psadbw/pshuflw/pshufhw/pshufw/cvtps2dq/
    movhlps/movlhps/pextrw/pinsrw/pextrd/pinsrd/pextrq/pinsrq/pcmpeqw
  - AVX (ymm): vmovups/vmovupd/vmovaps/vmovapd/vmovdqa/vmovdqu/vmovntps/vmovntpd (256bit) + vzeroupper
    (Y[16] = X[16] の上位 128bit)
  - x87 制御: fldcw/fnstcw/fstcw/fnstsw/fstsw/fnclex/fninit/emms (x87_cw/x87_sw モデル)
  - segment (gs/fs): TEB モデル (SEG_GS/SEG_FS base + TLS)。Windows x64 の TEB = gs
  - lea の riz (index 無効 SIB) 対応 / jecxz-jrcxz-loop 系 / xgetbv (XCR0 固定モデル) / rdtsc / cpuid モデル
  - sfence/lfence/mfence/prefetch を nop 化, ret imm16, stc/clc/cmc/sahf/lahf
  - Delphi 形 jump table: `lea rB,[rip+d]` / `mov rB,imm` + `jmp [rB+idx*scale+disp]` (8B 絶対 VA 表,
    index は前後両方向へ解決) と MSVC 形 (4B RVA 表 + add) の両方
  - lift 時の Python 例外 (AttributeError 等) を unsup に記録して継続 (CRASH-XXX として計上)
  - VEX.128 (xmm) を legacy SSE handler へ落とす (vex_leg: 3-op は d=s1 コピー後に legacy (d,s2)、上位 YL を 0 化)、
    VEX FMA (vfmadd/fmsub/fnmadd/fnmsub × 132/213/231 × sd/ss)、vinsertf128・vmovntdq (ymm)、rcr、int (fail-fast)、
    movsldup/movshdup/cmpXXps (KH-38 #3065。before 160 closure の unsup 285 site → 0。差分テスト tests/x64c_vex_diff.py)
  - dispatch に IAT pseudo-VA 経路を追加: data 側で IAT slot に IMP_VA_BASE+idx を敷設し,
    `mov rax,[iat]; call rax` 形の間接呼出を imp 呼出に解決

usage: x64c.py --pe DLL --entries entries.json --out out_dir [--closure N] [--override VA=CNAME]
               [--img 0x400000] [--shift 0] [--img-size 0x18c0000] [--impbase 0x1D80000]
"""
import sys, json, struct, argparse, bisect, collections, os, shutil, contextlib
import pefile
import capstone
from capstone import *
from capstone.x86 import *

# 既定は FLEngine_x64.dll (ImageBase 0x400000, SizeOfImage 0x18c0000)。--img 等で差し替え可。
IMG = 0x400000
SHIFT = 0                  # 0x400000+RVA → そのまま (恒等写像)
IMG_SIZE = 0x18c0000

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
CCMAP = {'e': 'E', 'z': 'E', 'ne': 'NE', 'nz': 'NE', 'b': 'B', 'c': 'B', 'nae': 'B', 'ae': 'AE', 'nb': 'AE', 'nc': 'AE',
         'be': 'BE', 'na': 'BE', 'a': 'A', 'nbe': 'A', 's': 'S', 'ns': 'NS', 'p': 'P', 'pe': 'P', 'np': 'NP', 'po': 'NP',
         'o': 'O', 'no': 'NO', 'l': 'L', 'nge': 'L', 'ge': 'GE', 'nl': 'GE', 'le': 'LE', 'ng': 'LE', 'g': 'G', 'nle': 'G'}

STRW = {'movsb': 1, 'movsw': 2, 'movsd': 4, 'movsq': 8, 'stosb': 1, 'stosw': 2, 'stosd': 4, 'stosq': 8,
        'lodsb': 1, 'lodsw': 2, 'lodsd': 4, 'lodsq': 8, 'scasb': 1, 'scasw': 2, 'scasd': 4, 'scasq': 8}


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
        # 遅延読み込み (delay import): jmp [遅延IAT] 形 thunk も通常 import と同一扱いにする
        # (slot に pseudo-VA を敷設 → thunk 経由の呼出が imp 直行。__delayLoadHelper2 は不要化)
        for ent in getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', []):
            for imp in ent.imports:
                nm = imp.name.decode() if imp.name else 'ord%d' % imp.ordinal
                self.iat[imp.address] = nm
        self.pdata = []
        for s in pe.sections:
            if s.Name.startswith(b'.pdata'):
                raw = s.get_data()
                for i in range(0, len(raw) // 12 * 12, 12):
                    b, e, u = struct.unpack_from('<III', raw, i)
                    if b == 0 and e == 0:
                        break
                    self.pdata.append((IMG + b, IMG + e, u))
                break
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
        self.unsup_va = []
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
                m = ins.mnemonic
                nxt = va + ins.size
                if m == 'jmp':
                    op = ins.operands[0]
                    if op.type == X86_OP_IMM:
                        t = op.imm
                        if t != self.entry and t in self.known:
                            self.tail.add(va)       # 他関数への tail call
                        else:
                            self.targets.add(t); work.append(t)
                    elif op.type == X86_OP_REG:
                        tg = self.jump_table_msvc(va, ins)
                        if tg is None:
                            tg = self.jump_table_abs(va, ins)
                        if tg:
                            self.jtabs[va] = tg
                            for t in tg:
                                self.targets.add(t); work.append(t)
                    elif op.type == X86_OP_MEM:
                        tg = self.jump_table_abs(va, ins)
                        if tg:
                            self.jtabs[va] = tg
                            for t in tg:
                                self.targets.add(t); work.append(t)
                    break
                if m.startswith('j') or m in ('loop', 'loope', 'loopne'):
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

    def jump_table_msvc(self, va, ins):
        """MSVC 形式: ... mov eY,[rX+rIdx*4+tbl]; add rY,rX; jmp rY (tbl = image RVA, 4B 相対)"""
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
        if not ent:
            return None
        self.jt_ranges.append((IMG + tbl, 4 * (len(ent) + 1)))
        return ent

    def jump_table_abs(self, va, ins):
        """絶対形 (Delphi): jmp [rB + rIdx*scale + disp] — rB は直前の `lea rB,[rip+d]` / `mov rB,imm` で解決。
        scale 8 = 8B 絶対 VA 表, scale 4 = 4B RVA 表。index は負方向にも届き得るため前後両方向に解決する。"""
        op = ins.operands[0]
        if op.type != X86_OP_MEM:
            return None
        m = op.mem
        if m.scale not in (4, 8) or m.index == 0 or m.index == X86_REG_RIZ:
            return None
        base_val = None
        disp = m.disp
        if m.base == X86_REG_RIP:
            base_val = va + ins.size + m.disp
            disp = 0
        else:
            try:
                bname = ins.reg_name(m.base)
            except Exception:
                return None
            cand = sorted([x for x in self.insns if x < va], reverse=True)[:24]
            for x in cand:
                i = self.insns[x]
                if i.mnemonic == 'lea' and len(i.operands) == 2 and i.operands[0].type == X86_OP_REG \
                        and ins.reg_name(i.operands[0].reg) == bname:
                    mm = i.operands[1].mem
                    if mm.base == X86_REG_RIP and mm.index == 0:
                        base_val = i.address + i.size + mm.disp
                        break
                    if mm.base == 0 and mm.index == 0:
                        base_val = mm.disp & 0xffffffffffffffff
                        break
                if i.mnemonic in ('mov', 'movabs') and len(i.operands) == 2 and i.operands[0].type == X86_OP_REG \
                        and ins.reg_name(i.operands[0].reg) == bname and i.operands[1].type == X86_OP_IMM:
                    base_val = i.operands[1].imm & 0xffffffffffffffff
                    break
        if base_val is None:
            return None
        try:
            iname = ins.reg_name(m.index)
        except Exception:
            return None
        n = None
        for x in sorted([x for x in self.insns if x < va], reverse=True)[:24]:
            i = self.insns[x]
            if i.mnemonic == 'cmp' and len(i.operands) == 2 and i.operands[0].type == X86_OP_REG \
                    and i.operands[1].type == X86_OP_IMM and i.reg_name(i.operands[0].reg) == iname:
                n = i.operands[1].imm
                break
        if n is None or n < 0 or n > 1024:
            n = 64

        def rd_ent(addr):
            o = addr - IMG
            if o < 0 or o + m.scale > len(self.pe.img):
                return None
            if m.scale == 8:
                return struct.unpack_from('<Q', self.pe.img, o)[0]
            return IMG + struct.unpack_from('<I', self.pe.img, o)[0]

        def ok(t):
            return self.entry - 0x4000 <= t < self.entry + 0x20000

        center = base_val + disp
        fwd, bwd = [], []
        k = 0
        while k <= n:
            t = rd_ent(center + m.scale * k)
            if t is None or not ok(t):
                break
            fwd.append(t); k += 1
        k = -1
        while k >= -n:
            t = rd_ent(center + m.scale * k)
            if t is None or not ok(t):
                break
            bwd.append(t); k -= 1
        ent = list(reversed(bwd)) + fwd
        if len(ent) < 2:
            return None
        lo = center + m.scale * (-len(bwd))
        hi = center + m.scale * len(fwd)
        self.jt_ranges.append((lo, hi - lo))
        return ent

    # ---- 値/アドレス式 ----
    def reg(self, ins, rid):
        nm = ins.reg_name(rid)
        if nm in GPR_NAMES:
            return GPR_NAMES[nm]
        raise Unsup('reg ' + str(nm))

    def xreg(self, ins, rid):
        nm = ins.reg_name(rid)
        if nm and nm.startswith('xmm'):
            return int(nm[3:])
        if nm and nm.startswith('ymm'):
            return int(nm[3:])
        raise Unsup('xreg ' + str(nm))

    def mmidx(self, ins, op):
        nm = ins.reg_name(op.reg)
        if nm and nm.startswith('mm'):
            return int(nm[2:])
        raise Unsup('mmidx ' + str(nm))

    def isymm(self, ins, rid):
        nm = ins.reg_name(rid)
        return bool(nm) and nm.startswith('ymm')

    def ismm(self, ins, op):
        return op.type == X86_OP_REG and (ins.reg_name(op.reg) or '').startswith('mm')

    def ea(self, ins, op):
        m = op.mem
        seg = None
        if m.segment != 0:
            sn = ins.reg_name(m.segment)
            if sn == 'gs':
                seg = 'SEG_GS'
            elif sn == 'fs':
                seg = 'SEG_FS'
            else:
                raise Unsup('segment ' + str(sn))
        if m.base == X86_REG_RIP:
            tgt = ins.address + ins.size + m.disp
            # .text 内 data (jump table 等) 参照を記録 (data install の敷設窓に使う)
            if IMG + 0x1000 <= tgt < IMG + 0xfa4000 and ins.mnemonic != 'lea':
                self.textrefs.add(tgt)
            e = hx(sh(tgt))
            return '%s + %s' % (seg, e) if seg else e
        terms = []
        if m.base != 0:
            i, s, h = self.reg(ins, m.base)
            terms.append('R[%d]' % i)
        if m.index != 0 and m.index != X86_REG_RIZ and m.index != X86_REG_RSP:
            i, s, h = self.reg(ins, m.index)
            terms.append('R[%d]*%d' % (i, m.scale) if m.scale != 1 else 'R[%d]' % i)
        disp = m.disp
        if m.base == 0 and (m.index == 0 or m.index == X86_REG_RIZ):
            e = hx(sh(disp & 0xffffffffffffffff if disp < 0 else disp))
            return '%s + %s' % (seg, e) if seg else e
        if disp:
            terms.append(hx(disp & 0xffffffffffffffff))
        e = '(' + ' + '.join(terms) + ')'
        return '%s + %s' % (seg, e) if seg else e

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

    def wr_rax(self, sz, val):
        return {1: 'R[RAX] = (R[RAX] & ~0xffULL) | ((uint64_t)(%s) & 0xff);',
                2: 'R[RAX] = (R[RAX] & ~0xffffULL) | ((uint64_t)(%s) & 0xffff);',
                4: 'R[RAX] = (uint32_t)(%s);',
                8: 'R[RAX] = (uint64_t)(%s);'}[sz] % val

    def sgn(self, expr, sz):
        return '((int%d_t)(%s))' % (sz * 8, expr)

    # ---- xmm/ymm helpers ----
    def xs(self, ins, op, kind):
        """kind: f32/f64/d32/q64/x128/x256 → 値式"""
        if op.type == X86_OP_REG:
            i = self.xreg(ins, op.reg)
            if self.isymm(ins, op.reg):
                if kind == 'x128':
                    return 'YL[%d]' % i
                if kind == 'x256':
                    return 'X[%d], YL[%d]' % (i, i)
            return {'f32': 'X[%d].f[0]', 'f64': 'X[%d].df[0]', 'd32': 'X[%d].d[0]', 'q64': 'X[%d].q[0]', 'x128': 'X[%d]'}[kind] % i
        e = self.ea(ins, op)
        return {'f32': 'LDF32(%s)', 'f64': 'LDF64(%s)', 'd32': 'LD32(%s)', 'q64': 'LD64(%s)', 'x128': 'LDX(%s)', 'x256': 'LDY2(%s)'}[kind] % e

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
        order = sorted(self.insns)
        self.out.append('void f_%x(void) {' % self.entry)
        # 関数内の後方分岐が entry より前 (別 .pdata 断片 / 前置コード) を到達先にする場合,
        # C の先頭文がそちらになってしまうので entry へ飛ばす (flelift 修正。OTT では未発火)
        if order and order[0] != self.entry:
            self.L('goto %s;' % self.label(self.entry))
        for va in order:
            ins = self.insns[va]
            if va in self.targets or va == self.entry:
                self.out.append(self.label(va) + ':;')
            nu = len(self.unsup)
            try:
                self.one(ins)
            except (Unsup, AttributeError, IndexError, KeyError, TypeError, ValueError) as e:
                key = ins.mnemonic + ':' + (str(e) if isinstance(e, Unsup) else 'CRASH-' + type(e).__name__)
                self.unsup[key] += 1
                self.unsup_va.append(va)
                self.L('ott_unsup(%s, "%s %s");' % (hx(ins.address), ins.mnemonic, ins.op_str.replace('"', "'")))
        self.out.append('  ott_badjump(%s, 0);' % hx(order[-1] if order else 0))
        self.out.append('}')
        return '\n'.join(self.out)

    # ---- 命令 ----
    def one(self, ins):
        m = ins.mnemonic
        ops = ins.operands
        va = ins.address
        L = self.L
        L('/* %x: %s %s */' % (va, m, ins.op_str.replace('*/', '* /')))
        if m.startswith('rep ') or m.startswith('repne '):
            return self.rep(ins)
        if m.startswith('lock '):
            return self.locked(ins, m[5:])
        if not m.startswith(('j', 'set', 'cmov', 'cmp')) and any(self.ismm(ins, o) for o in ops):
            try:
                return self.mmx_dispatch(m, ins, ops)
            except Unsup:
                pass
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
        if m.startswith('vf') and m[-2:] in ('sd', 'ss') and len(ops) == 3:
            return self.vfma_dispatch(ins, ops, m)
        if m.startswith('v'):
            return self.vex_leg(ins, ops, m)
        raise Unsup(m)

    def locked(self, ins, m2):
        """lock prefix — 単一スレッド前提で非 atomic 実装 (意味は同一)"""
        ops = ins.operands
        if m2 in ('xadd', 'xchg', 'cmpxchg', 'cmpxchg16b'):
            return getattr(self, 'i_' + m2)(ins, ops)
        if m2 in ('add', 'sub', 'or', 'and', 'xor', 'inc', 'dec', 'bts', 'btr', 'btc', 'adc', 'sbb', 'not', 'neg'):
            h = getattr(self, 'i_' + m2, None)
            if h:
                return h(ins, ops)
        raise Unsup('lock ' + m2)

    # nop
    def i_nop(self, ins, ops): pass
    i_int3 = i_nop
    i_endbr64 = i_nop
    i_fnop = i_nop
    i_pause = i_nop
    i_prefetcht0 = i_nop
    i_prefetcht1 = i_nop
    i_prefetcht2 = i_nop
    i_prefetchnta = i_nop
    i_prefetchw = i_nop
    i_sfence = i_nop
    i_lfence = i_nop
    i_mfence = i_nop

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

    def i_xadd(self, ins, ops):
        """xadd dst, src: tmp=dst; dst+=src; src=tmp (flags = add)"""
        sz = ops[0].size; W = sz * 8; T = 'uint%d_t' % W
        self.L('{ %s a_ = %s; %s b_ = %s; %s r_ = a_ + b_; FL_ADD(%d, a_, b_, r_); %s %s }' % (
            T, self.rd(ins, ops[0], sz), T, self.rd(ins, ops[1], sz), T, W,
            self.wr(ins, ops[0], 'r_', sz), self.wr(ins, ops[1], 'a_', sz)))

    def i_cmpxchg(self, ins, ops):
        """cmpxchg dst, src: cmp AL/AX/EAX/RAX と dst (flags=cmp) → 等しければ dst=src, 否 rax=dst"""
        sz = ops[0].size; W = sz * 8; T = 'uint%d_t' % W
        areg = {1: '(R[RAX] & 0xff)', 2: '(R[RAX] & 0xffff)', 4: '(R[RAX] & 0xffffffff)', 8: 'R[RAX]'}[sz]
        self.L('{ %s c_ = (%s)(%s); %s d_ = (%s)(%s); %s r_ = c_ - d_; FL_SUB(%d, c_, d_, r_); '
               'if (fZF) { %s } else { %s } }' % (
                   T, T, areg, T, T, self.rd(ins, ops[0], sz), T, W,
                   self.wr(ins, ops[0], self.rd(ins, ops[1], sz), sz),
                   self.wr_rax(sz, 'd_')))

    def i_cmpxchg16b(self, ins, ops):
        """cmpxchg16b m128: cmp RDX:RAX と m128 (flags) → 等: m128=RCX:RBX (ZF=1) / 否: RDX:RAX=m128"""
        a = self.ea(ins, ops[0])
        self.L('{ uint64_t lo_ = LD64(%s), hi_ = LD64((%s) + 8); '
               'if (R[RAX] == lo_ && R[RDX] == hi_) { fZF = 1; fCF = 0; fPF = PAR8(0); ST64(%s, R[RCX]); ST64((%s) + 8, R[RBX]); } '
               'else { uint64_t dlo_ = lo_ - R[RAX]; int borrow_ = (lo_ < R[RAX]); uint64_t dhi_ = hi_ - R[RDX] - (uint64_t)borrow_; '
               'fZF = 0; fCF = ((hi_ < R[RDX]) || (hi_ == R[RDX] && borrow_)) ? 1 : 0; fPF = PAR8((uint8_t)dlo_); fOF = 0; fSF = 0; '
               'R[RAX] = lo_; R[RDX] = hi_; } }' % (a, a, a, a))

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

    def i_shld(self, ins, ops):
        sz = ops[0].size; W = sz * 8; T = 'uint%d_t' % W
        cnt = self.rd(ins, ops[2], 1) if len(ops) > 2 else '1'
        cm = 63 if sz == 8 else 31
        then = self.wr(ins, ops[0], '((%s)((a_ << c_) | (b_ >> (%d - c_))))' % (T, W), sz)
        els = self.wr(ins, ops[0], '((%s)(b_ << (c_ - %d)))' % (T, W), sz)
        self.L('{ %s a_ = %s; %s b_ = %s; unsigned c_ = (unsigned)(%s) & %d; if (c_) { if (c_ <= %d) { %s } else { %s } } }' % (
            T, self.rd(ins, ops[0]), T, self.rd(ins, ops[1]), cnt, cm, W, then, els))

    def i_shrd(self, ins, ops):
        sz = ops[0].size; W = sz * 8; T = 'uint%d_t' % W
        cnt = self.rd(ins, ops[2], 1) if len(ops) > 2 else '1'
        cm = 63 if sz == 8 else 31
        then = self.wr(ins, ops[0], '((%s)((a_ >> c_) | (b_ << (%d - c_))))' % (T, W), sz)
        els = self.wr(ins, ops[0], '((%s)(b_ >> (c_ - %d)))' % (T, W), sz)
        self.L('{ %s a_ = %s; %s b_ = %s; unsigned c_ = (unsigned)(%s) & %d; if (c_) { if (c_ <= %d) { %s } else { %s } } }' % (
            T, self.rd(ins, ops[0]), T, self.rd(ins, ops[1]), cnt, cm, W, then, els))

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

    def i_cdq(self, ins, ops): self.L('R[RDX] = (uint32_t)((int32_t)R[RAX] >> 31);')
    def i_cqo(self, ins, ops): self.L('R[RDX] = (uint64_t)((int64_t)R[RAX] >> 63);')
    def i_cdqe(self, ins, ops): self.L('R[RAX] = (uint64_t)(int64_t)(int32_t)R[RAX];')
    def i_cwde(self, ins, ops): self.L('R[RAX] = (uint32_t)(int32_t)(int16_t)R[RAX];')
    def i_cbw(self, ins, ops): self.L('R[RAX] = (R[RAX] & ~0xffffULL) | (uint64_t)(uint16_t)(int16_t)(int8_t)R[RAX];')

    def bitop(self, ins, ops, kind):
        sz = ops[0].size; W = sz * 8; T = 'uint%d_t' % W
        if ops[0].type == X86_OP_MEM and ops[1].type == X86_OP_REG:
            # mem,reg 形: ビット文字列 — アクセス byte = ea + (idx>>3), bit = idx&7
            addr = self.ea(ins, ops[0])
            idx = self.rd(ins, ops[1], ops[1].size)
            s = '{ uint64_t a_ = (%s) + ((uint64_t)(%s) >> 3); unsigned b_ = (unsigned)(%s) & 7; fCF = (LD8(a_) >> b_) & 1; ' % (addr, idx, idx)
            if kind == 'bts': s += 'ST8(a_, LD8(a_) | (uint8_t)(1u << b_)); '
            elif kind == 'btr': s += 'ST8(a_, LD8(a_) & (uint8_t)~(1u << b_)); '
            elif kind == 'btc': s += 'ST8(a_, LD8(a_) ^ (uint8_t)(1u << b_)); '
            return self.L(s + ' }')
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
        # 間接 tail jmp (CFG dispatch / longjmp 形 / IAT 経由等): target を値として dispatch
        return self.L('{ uint64_t t_ = %s; ott_dispatch(t_); return; }' % self.rd(ins, op, 8))

    def i_jecxz(self, ins, ops):
        self.L('if ((R[RCX] & 0xffffffffULL) == 0) goto %s;' % self.label(ops[0].imm))

    def i_jrcxz(self, ins, ops):
        self.L('if (R[RCX] == 0) goto %s;' % self.label(ops[0].imm))

    def i_loop(self, ins, ops):
        self.L('{ R[RCX]--; if (R[RCX]) goto %s; }' % self.label(ops[0].imm))

    def i_loope(self, ins, ops):
        self.L('{ R[RCX]--; if (R[RCX] && CC_E) goto %s; }' % self.label(ops[0].imm))

    def i_loopne(self, ins, ops):
        self.L('{ R[RCX]--; if (R[RCX] && !CC_E) goto %s; }' % self.label(ops[0].imm))

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
        imm = ops[0].imm if ops else 0
        if imm:
            self.L('R[RSP] += 8 + %d; return;' % imm)
        else:
            self.L('R[RSP] += 8; return;')

    i_retn = i_ret

    # ---- flag / direction ----
    def i_cld(self, ins, ops): self.L('fDF = 0;')
    def i_std(self, ins, ops): self.L('fDF = 1;')
    def i_stc(self, ins, ops): self.L('fCF = 1;')
    def i_clc(self, ins, ops): self.L('fCF = 0;')
    def i_cmc(self, ins, ops): self.L('fCF = !fCF;')
    def i_sahf(self, ins, ops):
        self.L('{ uint8_t ah_ = (uint8_t)((R[RAX] >> 8) & 0xff); fCF = (ah_ >> 0) & 1; fPF = (ah_ >> 2) & 1; fZF = (ah_ >> 6) & 1; fSF = (ah_ >> 7) & 1; fAF = (ah_ >> 4) & 1; }')
    def i_lahf(self, ins, ops):
        self.L('R[RAX] = (R[RAX] & ~0xff00ULL) | ((uint64_t)(((fSF & 1) << 7) | ((fZF & 1) << 6) | ((fAF & 1) << 4) | ((fPF & 1) << 2) | 0x02 | (fCF & 1)) << 8);')

    # ---- rep / string ----
    def str_step(self, w):
        return 'R[RSI] += (fDF ? -(uint64_t)%d : (uint64_t)%d); R[RDI] += (fDF ? -(uint64_t)%d : (uint64_t)%d);' % (w, w, w, w)

    def str_mov(self, ins, w):
        ld = {1: 'LD8', 2: 'LD16', 4: 'LD32', 8: 'LD64'}[w]
        st = {1: 'ST8', 2: 'ST16', 4: 'ST32', 8: 'ST64'}[w]
        self.L('{ %s(R[RDI], %s(R[RSI])); %s }' % (st, ld, self.str_step(w)))

    def str_stos(self, ins, w):
        v = {1: 'R[RAX] & 0xff', 2: 'R[RAX] & 0xffff', 4: 'R[RAX] & 0xffffffff', 8: 'R[RAX]'}[w]
        st = {1: 'ST8', 2: 'ST16', 4: 'ST32', 8: 'ST64'}[w]
        self.L('{ %s(R[RDI], %s); R[RDI] += (fDF ? -(uint64_t)%d : (uint64_t)%d); }' % (st, v, w, w))

    def str_lods(self, ins, w):
        ld = {1: 'LD8', 2: 'LD16', 4: 'LD32', 8: 'LD64'}[w]
        val = {1: '(R[RAX] & ~0xffULL) | (uint64_t)%s(R[RSI])' % ld,
               2: '(R[RAX] & ~0xffffULL) | (uint64_t)%s(R[RSI])' % ld,
               4: '(uint32_t)%s(R[RSI])' % ld, 8: '%s(R[RSI])' % ld}[w]
        self.L('{ R[RAX] = %s; R[RSI] += (fDF ? -(uint64_t)%d : (uint64_t)%d); }' % (val, w, w))

    def rep(self, ins):
        base = ins.mnemonic.split(' ', 1)[1] if ' ' in ins.mnemonic else ins.mnemonic
        w = STRW.get(base)
        if w is None:
            raise Unsup(ins.mnemonic)
        if base.startswith('movs'):
            self.L('{ uint64_t n_ = R[RCX]; uint64_t s0_ = R[RSI], d0_ = R[RDI]; '
                   'if (fDF) { R[RSI] = s0_ - n_ * %d; R[RDI] = d0_ - n_ * %d; memmove((void*)A_(d0_ - n_ * %d), (void*)A_(s0_ - n_ * %d), n_ * %d); R[RSI] = s0_ - n_ * %d; R[RDI] = d0_ - n_ * %d; } '
                   'else { memmove((void*)A_(d0_), (void*)A_(s0_), n_ * %d); R[RSI] = s0_ + n_ * %d; R[RDI] = d0_ + n_ * %d; } R[RCX] = 0; }'
                   % (w, w, w, w, w, w, w, w, w, w))
        elif base.startswith('stos'):
            v = {1: 'R[RAX] & 0xff', 2: 'R[RAX] & 0xffff', 4: 'R[RAX] & 0xffffffff', 8: 'R[RAX]'}[w]
            self.L('{ uint64_t n_ = R[RCX]; uint64_t d0_ = R[RDI]; '
                   'if (fDF) { R[RDI] = d0_ - n_ * %d; for (uint64_t k_ = 0; k_ < n_; k_++) ST%d(d0_ - n_ * %d + k_ * %d, %s); R[RDI] = d0_ - n_ * %d; } '
                   'else { for (uint64_t k_ = 0; k_ < n_; k_++) ST%d(d0_ + k_ * %d, %s); R[RDI] = d0_ + n_ * %d; } R[RCX] = 0; }'
                   % (w, w * 8, w, w, v, w, w * 8, w, v, w))
        else:
            raise Unsup(ins.mnemonic)

    def i_movsb(self, ins, ops): self.str_mov(ins, 1)
    def i_movsw(self, ins, ops): self.str_mov(ins, 2)
    def i_movsq(self, ins, ops): self.str_mov(ins, 8)
    def i_stosb(self, ins, ops): self.str_stos(ins, 1)
    def i_stosw(self, ins, ops): self.str_stos(ins, 2)
    def i_stosd(self, ins, ops): self.str_stos(ins, 4)
    def i_stosq(self, ins, ops): self.str_stos(ins, 8)
    def i_lodsb(self, ins, ops): self.str_lods(ins, 1)
    def i_lodsw(self, ins, ops): self.str_lods(ins, 2)
    def i_lodsd(self, ins, ops): self.str_lods(ins, 4)
    def i_lodsq(self, ins, ops): self.str_lods(ins, 8)

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
        if d.type == X86_OP_MEM and s.type == X86_OP_MEM:
            return self.str_mov(ins, 4)     # 文字列形 movsd (dword)
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

    # AVX (ymm / xmm の両形)
    def vmov(self, ins, ops):
        d, s = ops
        y = self.isymm(ins, ops[0].reg) if ops[0].type == X86_OP_REG else self.isymm(ins, ops[1].reg)
        if d.type == X86_OP_MEM:
            if y:
                return self.L('STY(%s, X[%d], YL[%d]);' % (self.ea(ins, d), self.xd(ins, s), self.xd(ins, s)))
            return self.L('STX(%s, X[%d]);' % (self.ea(ins, d), self.xd(ins, s)))
        di = self.xd(ins, d)
        if s.type == X86_OP_REG:
            if y:
                return self.L('X[%d] = X[%d]; YL[%d] = YL[%d];' % (di, self.xd(ins, s), di, self.xd(ins, s)))
            return self.L('X[%d] = X[%d];' % (di, self.xd(ins, s)))
        if y:
            return self.L('LDYSPLIT(%s, &X[%d], &YL[%d]);' % (self.ea(ins, s), di, di))
        self.L('X[%d] = LDX(%s);' % (di, self.ea(ins, s)))
    i_vmovups = vmov
    i_vmovupd = vmov
    i_vmovaps = vmov
    i_vmovapd = vmov
    i_vmovdqa = vmov
    i_vmovdqu = vmov

    def i_vmovntps(self, ins, ops):
        d, s = ops
        y = self.isymm(ins, ops[1].reg)
        if y:
            return self.L('STY(%s, X[%d], YL[%d]);' % (self.ea(ins, d), self.xd(ins, s), self.xd(ins, s)))
        self.L('STX(%s, X[%d]);' % (self.ea(ins, d), self.xd(ins, s)))
    i_vmovntpd = i_vmovntps

    def i_vzeroupper(self, ins, ops):
        self.L('for (int k_ = 0; k_ < 16; k_++) memset(&YL[k_], 0, 16);')

    i_vmovntdq = i_movntdq = i_movntps = i_vmovntps

    def i_vinsertf128(self, ins, ops):
        d, s1, s2, im = ops
        di = self.xd(ins, d); a = self.xd(ins, s1); k = im.imm & 1
        src = self.xs(ins, s2, 'x128')
        if k:
            self.L('{ X128 lo_ = X[%d]; X128 t_ = %s; X[%d] = lo_; YL[%d] = t_; }' % (a, src, di, di))
        else:
            self.L('{ X128 t_ = %s; X128 hi_ = YL[%d]; X[%d] = t_; YL[%d] = hi_; }' % (src, a, di, di))

    # VEX.128 → legacy SSE handler (値 = (legacy 名, 可換か))。3-op (d, s1, s2|imm) は d=s1 を
    # コピーして legacy (d, s2) を適用する。VEX2 は 2-op (+imm)。VEXF は flags のみ更新 (上位は触らない)。
    VEX3 = {'vaddsd': ('addsd', True), 'vsubsd': ('subsd', False), 'vmulsd': ('mulsd', True), 'vdivsd': ('divsd', False),
            'vaddss': ('addss', True), 'vsubss': ('subss', False), 'vmulss': ('mulss', True), 'vdivss': ('divss', False),
            'vaddpd': ('addpd', True), 'vmulpd': ('mulpd', True),
            'vpxor': ('pxor', True), 'vpand': ('pand', True), 'vpor': ('por', True),
            'vxorpd': ('xorpd', True), 'vorpd': ('orpd', True), 'vandpd': ('andpd', True), 'vorps': ('orps', True),
            'vpaddq': ('paddq', True), 'vpaddd': ('paddd', True), 'vpsubq': ('psubq', False), 'vpsubd': ('psubd', False),
            'vunpcklpd': ('unpcklpd', False), 'vpunpckldq': ('punpckldq', False),
            'vpsrlq': ('psrlq', False), 'vpsllq': ('psllq', False), 'vpsrad': ('psrad', False),
            'vmovsd': ('movsd', False), 'vmovss': ('movss', False),
            'vcvtsd2ss': ('cvtsd2ss', False), 'vcvtsi2ss': ('cvtsi2ss', False)}
    VEX2 = {'vmovd': 'movd', 'vmovq': 'movq', 'vcvtdq2pd': 'cvtdq2pd', 'vcvtps2pd': 'cvtps2pd',
            'vcvtpd2dq': 'cvtpd2dq', 'vcvtss2si': 'cvtss2si', 'vpshufd': 'pshufd'}
    VEXF = {'vucomisd': 'ucomisd', 'vucomiss': 'ucomiss', 'vcomisd': 'comisd', 'vstmxcsr': 'stmxcsr', 'vldmxcsr': 'ldmxcsr'}

    def vex_leg(self, ins, ops, m):
        if any(o.type == X86_OP_REG and self.isymm(ins, o.reg) for o in ops):
            raise Unsup('ymm ' + m)
        if m in self.VEX3:
            leg, comm = self.VEX3[m]
            if len(ops) == 3:
                return self.vex3(ins, ops, leg, comm)
            return self.vex2(ins, ops, leg, True)
        if m in self.VEX2:
            return self.vex2(ins, ops, self.VEX2[m], True)
        if m in self.VEXF:
            return self.vex2(ins, ops, self.VEXF[m], False)
        raise Unsup(m)

    def vex2(self, ins, ops, leg, zero):
        getattr(self, 'i_' + leg)(ins, list(ops))
        if zero and self.isx(ins, ops[0]):
            self.L('memset(&YL[%d], 0, 16);' % self.xd(ins, ops[0]))

    def vex3(self, ins, ops, leg, comm):
        d, s1, s2 = ops[0], ops[1], ops[2]
        if not self.isx(ins, s1):
            raise Unsup('vex s1 ' + ins.mnemonic)
        di = self.xd(ins, d)
        if self.isx(ins, s2) and self.xd(ins, s2) == di and self.xd(ins, s1) != di:
            if not comm:
                raise Unsup('vex d==s2 ' + ins.mnemonic)
            getattr(self, 'i_' + leg)(ins, [d, s1])
            if leg[-2:] in ('sd', 'ss'):
                w = 8 if leg[-2:] == 'sd' else 4
                self.L('memcpy((uint8_t*)&X[%d] + %d, (uint8_t*)&X[%d] + %d, %d);' % (di, w, self.xd(ins, s1), w, 16 - w))
            self.L('memset(&YL[%d], 0, 16);' % di)
            return
        if self.xd(ins, s1) != di:
            self.L('X[%d] = X[%d];' % (di, self.xd(ins, s1)))
        getattr(self, 'i_' + leg)(ins, [d, s2])
        self.L('memset(&YL[%d], 0, 16);' % di)

    FMA_BASE = ('fmadd', 'fmsub', 'fnmadd', 'fnmsub')

    def vfma_dispatch(self, ins, ops, m):
        if any(o.type == X86_OP_REG and self.isymm(ins, o.reg) for o in ops) or not self.isx(ins, ops[1]):
            raise Unsup('ymm ' + m)
        base = m[1:-2]
        for b in self.FMA_BASE:
            if base.startswith(b) and base[len(b):] in ('132', '213', '231'):
                return self.vfma(ins, ops, b, base[len(b):], 'f32' if m.endswith('ss') else 'f64')
        raise Unsup(m)

    def vfma(self, ins, ops, base, form, ty):
        """vfmadd/fmsub/fnmadd/fnmsub (132/213/231)。d = fma(x, y, z) の 1 回丸め (OTT の ott_fma_d/s と同式)。
        132: d*s2 + s1 / 213: s1*d + s2 / 231: s1*s2 + d (Intel 規約)。"""
        di = self.xd(ins, ops[0])
        f = 'f' if ty == 'f32' else 'df'
        T = 'float' if ty == 'f32' else 'double'
        FM = 'ott_fma_s' if ty == 'f32' else 'ott_fma_d'
        c_old = 'X[%d].%s[0]' % (di, f)
        p1 = self.xs(ins, ops[1], ty)
        p2 = self.xs(ins, ops[2], ty)
        if form == '132': x, y, z = c_old, p2, p1
        elif form == '213': x, y, z = p1, c_old, p2
        else: x, y, z = p1, p2, c_old
        sx = '-(%s)' % x if base in ('fnmadd', 'fnmsub') else x
        sz = '-(%s)' % z if base in ('fmsub', 'fnmsub') else z
        self.L('{ %s r_ = %s(%s, %s, %s); X[%d].%s[0] = r_; memset(&YL[%d], 0, 16); }' % (T, FM, sx, y, sz, di, f, di))

    def dup_lanes(self, ins, ops, a, b):
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X[%d].d[0] = X[%d].d[1] = b_.d[%d]; X[%d].d[2] = X[%d].d[3] = b_.d[%d]; }' % (
            self.xs(ins, ops[1], 'x128'), di, di, a, di, di, b))

    def i_movsldup(self, ins, ops): self.dup_lanes(ins, ops, 0, 2)
    def i_movshdup(self, ins, ops): self.dup_lanes(ins, ops, 1, 3)

    def cmpps_pred(self, ins, ops, p):
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; for (int k_ = 0; k_ < 4; k_++) X[%d].d[k_] = cmp_pred_f(%d, X[%d].f[k_], b_.f[k_]) ? 0xffffffffU : 0U; }' % (
            self.xs(ins, ops[1], 'x128'), di, p, di))

    def i_cmpeqps(self, ins, ops): self.cmpps_pred(ins, ops, 0)
    def i_cmpltps(self, ins, ops): self.cmpps_pred(ins, ops, 1)
    def i_cmpleps(self, ins, ops): self.cmpps_pred(ins, ops, 2)
    def i_cmpunordps(self, ins, ops): self.cmpps_pred(ins, ops, 3)
    def i_cmpneqps(self, ins, ops): self.cmpps_pred(ins, ops, 4)
    def i_cmpnltps(self, ins, ops): self.cmpps_pred(ins, ops, 5)
    def i_cmpnleps(self, ins, ops): self.cmpps_pred(ins, ops, 6)
    def i_cmpordps(self, ins, ops): self.cmpps_pred(ins, ops, 7)

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

    def i_movhlps(self, ins, ops):
        di, si = self.xd(ins, ops[0]), self.xd(ins, ops[1])
        self.L('X[%d].q[0] = X[%d].q[1];' % (di, si))

    def i_movelhps(self, ins, ops):
        di, si = self.xd(ins, ops[0]), self.xd(ins, ops[1])
        self.L('X[%d].q[1] = X[%d].q[0];' % (di, si))
    i_movlhps = i_movelhps

    def isx(self, ins, op):
        if op.type != X86_OP_REG:
            return False
        nm = ins.reg_name(op.reg)
        return bool(nm) and nm.startswith('xmm')

    def i_movq(self, ins, ops):
        d, s = ops
        if self.ismm(ins, d) or self.ismm(ins, s):
            # mm 関連 (movq mm,mm/mem/gpr | movq gpr/mem,mm | movq xmm,mm)
            dn = ins.reg_name(d.reg) if d.type == X86_OP_REG else None
            if dn and dn.startswith('mm'):
                di = int(dn[2:])
                if self.isx(ins, s):
                    return self.L('M[%d] = X[%d].q[0];' % (di, self.xd(ins, s)))
                if self.ismm(ins, s):
                    return self.L('M[%d] = M[%d];' % (di, self.mmidx(ins, s)))
                if s.type == X86_OP_REG:
                    return self.L('M[%d] = %s;' % (di, self.rd(ins, s, 8)))
                return self.L('M[%d] = LD64(%s);' % (di, self.ea(ins, s)))
            if self.ismm(ins, s):
                if self.isx(ins, d):
                    return self.L('{ uint64_t v_ = M[%d]; X[%d].q[0] = v_; X[%d].q[1] = 0; }' % (self.mmidx(ins, s), self.xd(ins, d), self.xd(ins, d)))
                if d.type == X86_OP_REG:
                    return self.L(self.wr(ins, d, 'M[%d]' % self.mmidx(ins, s), 8))
                return self.L('ST64(%s, M[%d]);' % (self.ea(ins, d), self.mmidx(ins, s)))
        if self.isx(ins, d):
            di = self.xd(ins, d)
            if self.ismm(ins, s):
                return self.L('{ uint64_t v_ = M[%d]; X[%d].q[0] = v_; X[%d].q[1] = 0; }' % (self.mmidx(ins, s), di, di))
            if self.isx(ins, s):
                return self.L('{ uint64_t v_ = X[%d].q[0]; X[%d].q[0] = v_; X[%d].q[1] = 0; }' % (self.xd(ins, s), di, di))
            if s.type == X86_OP_REG:
                return self.L('{ uint64_t v_ = %s; X[%d].q[0] = v_; X[%d].q[1] = 0; }' % (self.rd(ins, s, 8), di, di))
            return self.L('{ uint64_t v_ = LD64(%s); X[%d].q[0] = v_; X[%d].q[1] = 0; }' % (self.ea(ins, s), di, di))
        if d.type == X86_OP_REG:
            dn = ins.reg_name(d.reg)
            if dn.startswith('mm'):
                di = int(dn[2:])
                if self.isx(ins, s):
                    return self.L('M[%d] = X[%d].q[0];' % (di, self.xd(ins, s)))
                if self.ismm(ins, s):
                    return self.L('M[%d] = M[%d];' % (di, self.mmidx(ins, s)))
                if s.type == X86_OP_REG:
                    return self.L('M[%d] = %s;' % (di, self.rd(ins, s, 8)))
                return self.L('M[%d] = LD64(%s);' % (di, self.ea(ins, s)))
            # gpr64 dest (movq r9, xmm0 形)
            if self.isx(ins, s):
                return self.L(self.wr(ins, d, 'X[%d].q[0]' % self.xd(ins, s), 8))
            if self.ismm(ins, s):
                return self.L(self.wr(ins, d, 'M[%d]' % self.mmidx(ins, s), 8))
            if s.type == X86_OP_REG:
                return self.L(self.wr(ins, d, self.rd(ins, s, 8), 8))
            return self.L(self.wr(ins, d, 'LD64(%s)' % self.ea(ins, s), 8))
        # mem dest
        if self.isx(ins, s):
            return self.L('ST64(%s, X[%d].q[0]);' % (self.ea(ins, d), self.xd(ins, s)))
        if self.ismm(ins, s):
            return self.L('ST64(%s, M[%d]);' % (self.ea(ins, d), self.mmidx(ins, s)))
        if s.type == X86_OP_REG:
            return self.L('ST64(%s, %s);' % (self.ea(ins, d), self.rd(ins, s, 8)))
        raise Unsup('movq mem,mem')

    def i_movd(self, ins, ops):
        d, s = ops
        if self.ismm(ins, d):
            di = self.mmidx(ins, d)
            if self.isx(ins, s):
                return self.L('M[%d] = (uint32_t)X[%d].d[0];' % (di, self.xd(ins, s)))
            if self.ismm(ins, s):
                return self.L('M[%d] = (M[%d] & 0xffffffff00000000ULL) | (M[%d] & 0xffffffffULL);' % (di, di, self.mmidx(ins, s)))
            return self.L('M[%d] = %s;' % (di, self.rd(ins, s, 4)))
        if self.ismm(ins, s):
            return self.L(self.wr(ins, d, '(uint32_t)M[%d]' % self.mmidx(ins, s), 4))
        if self.isx(ins, d):
            di = self.xd(ins, d)
            v = self.rd(ins, s, 4)
            return self.L('{ uint32_t v_ = %s; X[%d].d[0] = v_; X[%d].d[1] = X[%d].d[2] = X[%d].d[3] = 0; }' % (v, di, di, di, di))
        # gpr dest (movd eax, mm0 / movd eax, xmm0)
        if self.isx(ins, s):
            return self.L(self.wr(ins, d, 'X[%d].d[0]' % self.xd(ins, s), 4))
        raise Unsup('movd')

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
        if self.ismm(ins, ops[0]):
            di = self.mmidx(ins, ops[0])
            # MMX: half lane 数, 独立レジスタ M[di] (実機で XMM 非alias を実測)
            n2 = n // 2
            if self.ismm(ins, ops[1]):
                bexpr = 'M[%d]' % self.mmidx(ins, ops[1])
            elif self.isx(ins, ops[1]):
                bexpr = 'X[%d].q[0]' % self.xd(ins, ops[1])
            elif ops[1].type == X86_OP_REG:
                raise Unsup('mm reg')
            else:
                bexpr = 'LD64(%s)' % self.ea(ins, ops[1])
            self.L('{ MM64 b_; b_.q = %s; MM64 a_; a_.q = M[%d]; for (int k_ = 0; k_ < %d; k_++) a_.%s[k_] = %s; M[%d] = a_.q; }'
                   % (bexpr, di, n2, field, op, di))
            return
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; for (int k_ = 0; k_ < %d; k_++) a_.%s[k_] = %s; X[%d] = a_; }' % (self.xs(ins, ops[1], 'x128'), di, n, field, op, di))

    def i_paddq(self, i, o): self.lane(i, o, 'q', 2, 'a_.q[k_] + b_.q[k_]')
    def i_psubq(self, i, o): self.lane(i, o, 'q', 2, 'a_.q[k_] - b_.q[k_]')
    def i_paddd(self, i, o): self.lane(i, o, 'd', 4, 'a_.d[k_] + b_.d[k_]')
    def i_psubd(self, i, o): self.lane(i, o, 'd', 4, 'a_.d[k_] - b_.d[k_]')
    def i_paddw(self, i, o): self.lane(i, o, 'w', 8, 'a_.w[k_] + b_.w[k_]')
    def i_psubw(self, i, o): self.lane(i, o, 'w', 8, 'a_.w[k_] - b_.w[k_]')
    def i_paddb(self, i, o): self.lane(i, o, 'b', 16, 'a_.b[k_] + b_.b[k_]')
    def i_psubb(self, i, o): self.lane(i, o, 'b', 16, 'a_.b[k_] - b_.b[k_]')
    def i_pcmpeqd(self, i, o): self.lane(i, o, 'd', 4, '(a_.d[k_] == b_.d[k_]) ? 0xffffffffu : 0')
    def i_pcmpeqw(self, i, o): self.lane(i, o, 'w', 8, '(a_.w[k_] == b_.w[k_]) ? 0xffff : 0')
    def i_pcmpeqb(self, i, o): self.lane(i, o, 'b', 16, '(a_.b[k_] == b_.b[k_]) ? 0xff : 0')
    def i_pcmpgtd(self, i, o): self.lane(i, o, 'd', 4, '(a_.sd[k_] > b_.sd[k_]) ? 0xffffffffu : 0')

    def mm_lane(self, ins, ops, n, expr):
        """mm dst,src — expr は {a}/{b} プレースホルダ付き。独立レジスタ M[] で動く"""
        di = self.mmidx(ins, ops[0])
        if self.ismm(ins, ops[1]):
            bexpr = 'M[%d]' % self.mmidx(ins, ops[1])
        elif self.isx(ins, ops[1]):
            bexpr = 'X[%d].q[0]' % self.xd(ins, ops[1])
        elif ops[1].type == X86_OP_REG:
            raise Unsup('mm reg')
        else:
            bexpr = 'LD64(%s)' % self.ea(ins, ops[1])
        f, nl = {'q': ('q', 1), 'd': ('d', 2), 'w': ('w', 4), 'b': ('b', 8)}[n]
        if f == 'q':
            self.L('{ MM64 b_; b_.q = %s; MM64 a_; a_.q = M[%d]; MM64 r_; r_.q = %s; M[%d] = r_.q; }'
                   % (bexpr, di, expr.replace('{a}', 'a_.q').replace('{b}', 'b_.q'), di))
            return
        self.L('{ MM64 b_; b_.q = %s; MM64 a_; a_.q = M[%d]; MM64 r_ = a_; for (int k_ = 0; k_ < %d; k_++) r_.%s[k_] = %s; M[%d] = r_.q; }'
               % (bexpr, di, nl, f, expr.replace('{a}', 'a_.%s[k_]' % f).replace('{b}', 'b_.%s[k_]' % f), di))

    def i_mm_paddw(self, i, o): self.mm_lane(i, o, 'w', '(uint16_t)({a} + {b})')
    def i_mm_paddb(self, i, o): self.mm_lane(i, o, 'b', '(uint8_t)({a} + {b})')
    def i_mm_paddd(self, i, o): self.mm_lane(i, o, 'd', '(uint32_t)({a} + {b})')
    def i_mm_psubd(self, i, o): self.mm_lane(i, o, 'd', '(uint32_t)({a} - {b})')
    def i_mm_psubw(self, i, o): self.mm_lane(i, o, 'w', '(uint16_t)({a} - {b})')
    def i_mm_psubsw(self, i, o): self.mm_lane(i, o, 'w', 'sat_i16({a} - {b})')
    def i_mm_psubusb(self, i, o): self.mm_lane(i, o, 'b', 'sat_u8({a} - {b})')
    def i_mm_paddsw(self, i, o): self.mm_lane(i, o, 'w', 'sat_i16({a} + {b})')
    def i_mm_paddusb(self, i, o): self.mm_lane(i, o, 'b', 'sat_u8({a} + {b})')
    def i_mm_pxor(self, i, o): self.mm_lane(i, o, 'q', '{a} ^ {b}')
    def i_mm_pand(self, i, o): self.mm_lane(i, o, 'q', '{a} & {b}')
    def i_mm_por(self, i, o): self.mm_lane(i, o, 'q', '{a} | {b}')
    def i_mm_psubq(self, i, o): self.mm_lane(i, o, 'q', '{a} - {b}')

    def i_mm_psllw(self, ins, ops):
        di = self.mmidx(ins, ops[0])
        c = ops[1].imm if ops[1].type == X86_OP_IMM else 'LD64(%s) & 0xffff' % self.ea(ins, ops[1])
        self.L('{ uint64_t c_ = (%s) & 15; MM64 a_; a_.q = M[%d]; for (int k_ = 0; k_ < 4; k_++) a_.w[k_] = (uint16_t)(a_.w[k_] << c_); M[%d] = a_.q; }' % (c, di, di))

    def i_mm_psrlw(self, ins, ops):
        di = self.mmidx(ins, ops[0])
        c = ops[1].imm if ops[1].type == X86_OP_IMM else 'LD64(%s) & 0xffff' % self.ea(ins, ops[1])
        self.L('{ uint64_t c_ = (%s) & 15; MM64 a_; a_.q = M[%d]; for (int k_ = 0; k_ < 4; k_++) a_.w[k_] = (uint16_t)(a_.w[k_] >> c_); M[%d] = a_.q; }' % (c, di, di))

    def i_mm_psraw(self, ins, ops):
        di = self.mmidx(ins, ops[0])
        c = ops[1].imm if ops[1].type == X86_OP_IMM else 'LD64(%s) & 0xffff' % self.ea(ins, ops[1])
        self.L('{ uint64_t c_ = (%s) & 15; MM64 a_; a_.q = M[%d]; for (int k_ = 0; k_ < 4; k_++) a_.sw[k_] = (int16_t)(a_.sw[k_] >> c_); M[%d] = a_.q; }' % (c, di, di))

    def i_mm_pshufw(self, ins, ops):
        di = self.mmidx(ins, ops[0]); imm = ops[2].imm
        self.L('{ MM64 s_; s_.q = %s; MM64 r_; for (int k_ = 0; k_ < 4; k_++) r_.w[k_] = s_.w[(%d >> (2 * k_)) & 3]; M[%d] = r_.q; }'
               % (self.xs(ins, ops[1], 'q64') if self.isx(ins, ops[1]) else ('M[%d]' % self.mmidx(ins, ops[1]) if self.ismm(ins, ops[1]) else 'LD64(%s)' % self.ea(ins, ops[1])), imm, di))

    def i_mm_pi2fw(self, ins, ops):
        di = self.mmidx(ins, ops[0])
        src = self.xs(ins, ops[1], 'q64') if self.isx(ins, ops[1]) else ('M[%d]' % self.mmidx(ins, ops[1]) if self.ismm(ins, ops[1]) else 'LD64(%s)' % self.ea(ins, ops[1]))
        self.L('{ MM64 s_; s_.q = %s; MM64 r_; for (int k_ = 0; k_ < 2; k_++) r_.f[k_] = (float)s_.sw[2 * k_]; M[%d] = r_.q; }' % (src, di))

    def i_mm_pi2fd(self, ins, ops):
        di = self.mmidx(ins, ops[0])
        src = self.xs(ins, ops[1], 'q64') if self.isx(ins, ops[1]) else ('M[%d]' % self.mmidx(ins, ops[1]) if self.ismm(ins, ops[1]) else 'LD64(%s)' % self.ea(ins, ops[1]))
        self.L('{ MM64 s_; s_.q = %s; MM64 r_; for (int k_ = 0; k_ < 2; k_++) r_.f[k_] = (float)s_.sd[k_]; M[%d] = r_.q; }' % (src, di))

    def mmx_dispatch(self, m, ins, ops):
        tbl = {
            'paddw': self.i_mm_paddw, 'paddb': self.i_mm_paddb, 'paddd': self.i_mm_paddd,
            'psubd': self.i_mm_psubd, 'psubw': self.i_mm_psubw, 'psubsw': self.i_mm_psubsw,
            'psubusb': self.i_mm_psubusb, 'paddsw': self.i_mm_paddsw, 'paddusb': self.i_mm_paddusb,
            'pxor': self.i_mm_pxor, 'pand': self.i_mm_pand, 'por': self.i_mm_por, 'psubq': self.i_mm_psubq,
            'psllw': self.i_mm_psllw, 'psrlw': self.i_mm_psrlw, 'psraw': self.i_mm_psraw,
            'pshufw': self.i_mm_pshufw, 'pi2fw': self.i_mm_pi2fw, 'pi2fd': self.i_mm_pi2fd,
            'paddq': self.i_paddq, 'psubq': self.i_psubq, 'pcmpeqd': self.i_pcmpeqd,
        }
        fn = tbl.get(m)
        if fn:
            return fn(ins, ops)
        # pack*/pmul*/pmin*/pmax*/punpck*/movd/movq/emms は mm 形でも共通実装が mm 対応済
        h = getattr(self, 'i_' + m, None)
        if h is not None:
            return h(ins, ops)
        raise Unsup('mm ' + m)

    # SSE2 整数 pack / mul / minmax / sat

    def mm_src_q(self, ins, op):
        """mm 命令の第 2 オペランドを u64 式として評価 (M[] / X[].q[0] / memory)"""
        if self.ismm(ins, op):
            return 'M[%d]' % self.mmidx(ins, op)
        if self.isx(ins, op):
            return 'X[%d].q[0]' % self.xd(ins, op)
        if op.type == X86_OP_REG:
            raise Unsup('mm src reg')
        return 'LD64(%s)' % self.ea(ins, op)

    def i_packuswb(self, ins, ops):
        if self.ismm(ins, ops[0]):
            di = self.mmidx(ins, ops[0])
            return self.L('{ MM64 a_; a_.q = M[%d]; MM64 b_; b_.q = %s; MM64 r_; for (int k_ = 0; k_ < 4; k_++) { int v_ = a_.sw[k_]; r_.b[k_] = v_ < 0 ? 0 : (v_ > 255 ? 255 : v_); } '
                          'for (int k_ = 0; k_ < 4; k_++) { int v_ = b_.sw[k_]; r_.b[4 + k_] = v_ < 0 ? 0 : (v_ > 255 ? 255 : v_); } M[%d] = r_.q; }' % (di, self.mm_src_q(ins, ops[1]), di))
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; X128 r_; for (int k_ = 0; k_ < 8; k_++) { int v_ = a_.sw[k_]; r_.b[k_] = v_ < 0 ? 0 : (v_ > 255 ? 255 : v_); } '
               'for (int k_ = 0; k_ < 8; k_++) { int v_ = b_.sw[k_]; r_.b[8 + k_] = v_ < 0 ? 0 : (v_ > 255 ? 255 : v_); } X[%d] = r_; }' % (self.xs(ins, ops[1], 'x128'), di, di))

    def i_packssdw(self, ins, ops):
        di = self.xd(ins, ops[0])
        if self.ismm(ins, ops[0]):
            return self.L('{ MM64 a_; a_.q = M[%d]; MM64 b_; b_.q = %s; MM64 r_; for (int k_ = 0; k_ < 2; k_++) { int v_ = a_.sd[k_]; r_.w[k_] = v_ < -32768 ? -32768 : (v_ > 32767 ? 32767 : (int16_t)v_); } '
                          'for (int k_ = 0; k_ < 2; k_++) { int v_ = b_.sd[k_]; r_.w[2 + k_] = v_ < -32768 ? -32768 : (v_ > 32767 ? 32767 : (int16_t)v_); } M[%d] = r_.q; }' % (di, self.mm_src_q(ins, ops[1]), di))
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; X128 r_; for (int k_ = 0; k_ < 4; k_++) { int v_ = a_.sd[k_]; r_.sw[k_] = v_ < -32768 ? -32768 : (v_ > 32767 ? 32767 : (int16_t)v_); } '
               'for (int k_ = 0; k_ < 4; k_++) { int v_ = b_.sd[k_]; r_.sw[4 + k_] = v_ < -32768 ? -32768 : (v_ > 32767 ? 32767 : (int16_t)v_); } X[%d] = r_; }' % (self.xs(ins, ops[1], 'x128'), di, di))

    def i_packsswb(self, ins, ops):
        di = self.xd(ins, ops[0])
        if self.ismm(ins, ops[0]):
            return self.L('{ MM64 a_; a_.q = M[%d]; MM64 b_; b_.q = %s; MM64 r_; for (int k_ = 0; k_ < 4; k_++) { int v_ = a_.sw[k_]; r_.sb[k_] = v_ < -128 ? -128 : (v_ > 127 ? 127 : (int8_t)v_); } '
                          'for (int k_ = 0; k_ < 4; k_++) { int v_ = b_.sw[k_]; r_.sb[4 + k_] = v_ < -128 ? -128 : (v_ > 127 ? 127 : (int8_t)v_); } M[%d] = r_.q; }' % (di, self.mm_src_q(ins, ops[1]), di))
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; X128 r_; for (int k_ = 0; k_ < 8; k_++) { int v_ = a_.sw[k_]; r_.sb[k_] = v_ < -128 ? -128 : (v_ > 127 ? 127 : (int8_t)v_); } '
               'for (int k_ = 0; k_ < 8; k_++) { int v_ = b_.sw[k_]; r_.sb[8 + k_] = v_ < -128 ? -128 : (v_ > 127 ? 127 : (int8_t)v_); } X[%d] = r_; }' % (self.xs(ins, ops[1], 'x128'), di, di))

    def i_pmulhuw(self, i, o): self.lane(i, o, 'w', 8, '(uint16_t)(((uint32_t)a_.w[k_] * (uint32_t)b_.w[k_]) >> 16)')
    def i_pmulhw(self, i, o): self.lane(i, o, 'w', 8, '(uint16_t)(((int32_t)a_.sw[k_] * (int32_t)b_.sw[k_]) >> 16)')
    def i_pmullw(self, i, o): self.lane(i, o, 'w', 8, '(uint16_t)(a_.w[k_] * b_.w[k_])')
    def i_pmaddwd(self, i, o): self.lane(i, o, 'd', 4, '(int32_t)a_.sw[2*k_] * b_.sw[2*k_] + (int32_t)a_.sw[2*k_+1] * b_.sw[2*k_+1]')
    def i_pminsw(self, i, o): self.lane(i, o, 'w', 8, '(a_.sw[k_] < b_.sw[k_]) ? a_.sw[k_] : b_.sw[k_]')
    def i_pmaxsw(self, i, o): self.lane(i, o, 'w', 8, '(a_.sw[k_] > b_.sw[k_]) ? a_.sw[k_] : b_.sw[k_]')
    def i_pminub(self, i, o): self.lane(i, o, 'b', 16, '(a_.b[k_] < b_.b[k_]) ? a_.b[k_] : b_.b[k_]')
    def i_pmaxub(self, i, o): self.lane(i, o, 'b', 16, '(a_.b[k_] > b_.b[k_]) ? a_.b[k_] : b_.b[k_]')
    def i_paddusb(self, i, o): self.lane(i, o, 'b', 16, 'sat_u8((int)a_.b[k_] + b_.b[k_])')
    def i_paddusw(self, i, o): self.lane(i, o, 'w', 8, 'sat_u16((uint32_t)a_.w[k_] + b_.w[k_])')
    def i_psubusb(self, i, o): self.lane(i, o, 'b', 16, 'sat_u8((int)a_.b[k_] - b_.b[k_])')
    def i_psubusw(self, i, o): self.lane(i, o, 'w', 8, 'sat_u16((uint32_t)a_.w[k_] - b_.w[k_])')
    def i_paddsw(self, i, o): self.lane(i, o, 'w', 8, 'sat_i16((int32_t)a_.sw[k_] + b_.sw[k_])')
    def i_psubsw(self, i, o): self.lane(i, o, 'w', 8, 'sat_i16((int32_t)a_.sw[k_] - b_.sw[k_])')
    def i_pavgb(self, i, o): self.lane(i, o, 'b', 16, '(uint8_t)(((uint32_t)a_.b[k_] + b_.b[k_] + 1) >> 1)')
    def i_pavgw(self, i, o): self.lane(i, o, 'w', 8, '(uint16_t)(((uint32_t)a_.w[k_] + b_.w[k_] + 1) >> 1)')

    def i_psadbw(self, ins, ops):
        if self.ismm(ins, ops[0]):
            di = self.mmidx(ins, ops[0])
            return self.L('{ MM64 a_; a_.q = M[%d]; MM64 b_; b_.q = %s; unsigned s_ = 0; for (int k_ = 0; k_ < 8; k_++) s_ += abs(a_.b[k_] - b_.b[k_]); M[%d] = s_; }'
                          % (di, self.mm_src_q(ins, ops[1]), di))
        di = self.xd(ins, ops[0])
        self.L('{ X128 b_ = %s; X128 a_ = X[%d]; X128 r_; memset(&r_, 0, 16); for (int h_ = 0; h_ < 2; h_++) { unsigned s_ = 0; for (int k_ = 0; k_ < 8; k_++) s_ += abs(a_.b[8*h_+k_] - b_.b[8*h_+k_]); r_.q[h_] = s_; } X[%d] = r_; }' % (self.xs(ins, ops[1], 'x128'), di, di))

    def i_pshuflw(self, ins, ops):
        di = self.xd(ins, ops[0]); imm = ops[2].imm
        self.L('{ X128 s_ = %s; X128 r_ = s_; for (int k_ = 0; k_ < 4; k_++) r_.w[k_] = s_.w[(%d >> (2 * k_)) & 3]; X[%d] = r_; }'
               % (self.xs(ins, ops[1], 'x128'), imm, di))

    def i_pshufhw(self, ins, ops):
        di = self.xd(ins, ops[0]); imm = ops[2].imm
        self.L('{ X128 s_ = %s; X128 r_ = s_; for (int k_ = 0; k_ < 4; k_++) r_.w[4 + k_] = s_.w[4 + ((%d >> (2 * k_)) & 3)]; X[%d] = r_; }'
               % (self.xs(ins, ops[1], 'x128'), imm, di))

    def i_cvtps2dq(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 s_ = %s; for (int k_ = 0; k_ < 4; k_++) X[%d].sd[k_] = cvt_d2i32((double)s_.f[k_]); }' % (self.xs(ins, ops[1], 'x128'), di))

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
        base = n // 2 if hi else 0
        if self.ismm(ins, ops[0]):
            di = self.mmidx(ins, ops[0])
            n2 = n // 2
            return self.L('{ MM64 b_; b_.q = %s; MM64 a_; a_.q = M[%d]; MM64 r_; for (int k_ = 0; k_ < %d; k_++) { r_.%s[2*k_] = a_.%s[%d + k_]; r_.%s[2*k_+1] = b_.%s[%d + k_]; } M[%d] = r_.q; }'
                          % (self.mm_src_q(ins, ops[1]), di, n2 // 2, field, field, base, field, field, base, di))
        di = self.xd(ins, ops[0])
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

    def i_pinsrw(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 a_ = X[%d]; a_.w[%d] = (uint16_t)%s; X[%d] = a_; }' % (di, ops[2].imm & 7, self.rd(ins, ops[1], 2), di))

    def i_pextrd(self, ins, ops):
        self.L(self.wr(ins, ops[0], 'X[%d].d[%d]' % (self.xd(ins, ops[1]), ops[2].imm & 3), 4))

    def i_pinsrd(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 a_ = X[%d]; a_.d[%d] = (uint32_t)%s; X[%d] = a_; }' % (di, ops[2].imm & 3, self.rd(ins, ops[1], 4), di))

    def i_pextrq(self, ins, ops):
        self.L(self.wr(ins, ops[0], 'X[%d].q[%d]' % (self.xd(ins, ops[1]), ops[2].imm & 1), 8))

    def i_pinsrq(self, ins, ops):
        di = self.xd(ins, ops[0])
        self.L('{ X128 a_ = X[%d]; a_.q[%d] = (uint64_t)%s; X[%d] = a_; }' % (di, ops[2].imm & 1, self.rd(ins, ops[1], 8), di))

    def i_ldmxcsr(self, ins, ops): self.L('mxcsr = LD32(%s);' % self.ea(ins, ops[0]))
    def i_stmxcsr(self, ins, ops): self.L('ST32(%s, mxcsr);' % self.ea(ins, ops[0]))
    def i_leave(self, ins, ops): self.L('R[RSP] = R[RBP]; R[RBP] = LD64(R[RSP]); R[RSP] += 8;')
    def i_cpuid(self, ins, ops): self.L('cpuid_model();')
    def i_rdtsc(self, ins, ops): self.L('rdtsc_model();')
    def i_xgetbv(self, ins, ops): self.L('R[RAX] = XCR0 & 0xffffffffULL; R[RDX] = XCR0 >> 32;')

    # ---- x87 制御 (FLEngine の lift 集合に x87 演算は無く制御のみ) ----
    def i_fldcw(self, ins, ops): self.L('x87_cw = LD16(%s);' % self.ea(ins, ops[0]))
    def i_fnstcw(self, ins, ops): self.L('ST16(%s, x87_cw);' % self.ea(ins, ops[0]))
    i_fstcw = i_fnstcw
    def i_fnstsw(self, ins, ops):
        op = ops[0]
        if op.type == X86_OP_REG:
            self.L(self.wr(ins, op, 'x87_sw', 2))
        else:
            self.L('ST16(%s, x87_sw);' % self.ea(ins, op))
    i_fstsw = i_fnstsw
    def i_fnclex(self, ins, ops): self.L('x87_sw = 0;')
    def i_fninit(self, ins, ops): self.L('x87_cw = 0x037f; x87_sw = 0;')
    def i_emms(self, ins, ops): pass

    def i_rcr(self, ins, ops):
        """rcr: CF を含む (W+1)bit 環を右回転。count は &0x1F (64bit は &0x3F)、8/16bit は続けて MOD 9/17。
        マスク後の count が 0 なら flags は不変、それ以外は CF と OF (= MSB ^ MSB-1) だけ更新 (実機 rcr 4000 件と一致: tests/rcr_native_check.py)。
        32bit の書き込みは count 0 でも上位をゼロ拡張する (実機。同ファイルの照合で 64bit レジスタ全体を比較)。"""
        sz = ops[0].size; W = sz * 8; T = 'uint%d_t' % W
        cnt = self.rd(ins, ops[1], 1) if len(ops) > 1 else '1'
        cm = 63 if sz == 8 else 31
        n = '(c_ %% %d)' % (W + 1) if sz < 4 else 'c_'
        self.L('{ %s a_ = %s; %s r_ = a_; unsigned c_ = (unsigned)(%s) & %d; '
               'if (c_) { unsigned __int128 v_ = ((unsigned __int128)fCF << %d) | a_; unsigned n_ = %s; '
               'while (n_--) v_ = (v_ >> 1) | ((v_ & 1) << %d); '
               'fCF = (uint8_t)((v_ >> %d) & 1); r_ = (%s)v_; fOF = ((r_ >> %d) ^ (r_ >> %d)) & 1; } %s }' % (
                   T, self.rd(ins, ops[0], sz), T, cnt, cm, W, n, W, W, T, W - 1, W - 2, self.wr(ins, ops[0], 'r_', sz)))

    def i_int(self, ins, ops):
        # int 0x29 = __fastfail (CRT 異常終了経路) — guest では fail-fast が同じ意味 (OTT と同じ扱い)
        self.L('ott_unsup(%s, "int 0x%x (fail-fast)");' % (hx(ins.address), ops[0].imm if ops else 0))


def main():
    global IMG, SHIFT, IMG_SIZE
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', required=True)
    ap.add_argument('--entries', required=True, help='json: {"roots":[va..], "calltgt":[rva..]}')
    ap.add_argument('--out', required=True)
    ap.add_argument('--closure', type=int, default=0, help='未 lift の直接 call 先を再帰的に追加 (深さ)')
    ap.add_argument('--override', action='append', default=[], help='VA=CNAME: その関数 body を C 実装に置換')
    ap.add_argument('--img', type=lambda x: int(x, 0), default=0x400000)
    ap.add_argument('--shift', type=lambda x: int(x, 0), default=0)
    ap.add_argument('--img-size', type=lambda x: int(x, 0), default=0x18c0000)
    ap.add_argument('--impbase', type=lambda x: int(x, 0), default=0x1D80000, help='IAT slot に敷設する pseudo-VA 基準 (dispatch が imp 呼出に解決)')
    ap.add_argument('--shards', type=int, default=1, help='N>1 で fle_lifted.c を fle_lifted_s<k>.c (k<N) の N 本に分ける (関数は i%%N、ott_dispatch・weak imp・imp_tab は shard 0 のみ。1 は従来の単一ファイル)')
    a = ap.parse_args()
    IMG = a.img; SHIFT = a.shift; IMG_SIZE = a.img_size
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
    # メモリ: FnLift (capstone insn 込み) は関数ごとに捨てる。closure 探索は呼出先の収集だけ、
    # 最終パスは関数ごとに C 本体を一時ファイルへ流し、統計だけ残す (出力は旧版と同一)。
    done = set()
    queue = sorted(entries)
    known = set(entries)
    depth = 0
    while True:
        newc = set()
        for e in queue:
            if e in done: continue
            f = FnLift(pe, e, known, md, thunks)
            done.add(e)
            if e not in overrides:
                f.descend()
            for t in f.calls:
                if t not in known and t not in thunks:
                    nm = thunk_name(t)
                    if nm:
                        thunks[t] = nm
                    else:
                        newc.add(t)
            del f
        if depth >= a.closure or not newc:
            break
        depth += 1
        known |= newc
        queue = sorted(newc)
    out = a.out
    os.makedirs(out, exist_ok=True)
    nsh = max(1, a.shards)
    body_paths = [os.path.join(out, 'fle_lifted.body%d.tmp' % k) for k in range(nsh)]
    unsup = collections.Counter()
    unl = collections.Counter()
    unsup_sites = []
    used_imps = set(thunks.values())
    ninsn = 0
    textrefs = set()
    jt_ranges = set()
    with contextlib.ExitStack() as stack:
        bfs = [stack.enter_context(open(p, 'w')) for p in body_paths]
        for i, e in enumerate(sorted(done)):
            bf = bfs[i % nsh]
            f = FnLift(pe, e, known, md, thunks)
            bf.write(('void f_%x(void) { %s(); }' % (e, overrides[e])) if e in overrides else f.lift())
            bf.write('\n')
            unsup.update(f.unsup)
            unsup_sites += ['%x' % va for va in f.unsup_va]
            for t in f.calls:
                if t not in known and t not in thunks:
                    unl[t] += 1
            for ins in f.insns.values():
                if ins.mnemonic in ('call', 'jmp') and ins.operands and ins.operands[0].type == X86_OP_MEM and ins.operands[0].mem.base == X86_REG_RIP:
                    s = ins.address + ins.size + ins.operands[0].mem.disp
                    if s in pe.iat:
                        used_imps.add(pe.iat[s])
            ninsn += len(f.insns)
            textrefs |= f.textrefs
            jt_ranges |= set(f.jt_ranges)
            del f
    used_imps = sorted(used_imps)
    slots = sorted(pe.iat)                       # IAT slot VA (DLL 宣言順でなく VA 順で固定)
    imp_names = [pe.iat[s] for s in slots]
    names = ['fle_lifted.c'] if nsh == 1 else ['fle_lifted_s%d.c' % k for k in range(nsh)]
    for k, name in enumerate(names):
        with open(os.path.join(out, name), 'w') as fh:
            fh.write('#include "fle_cpu.h"\n')
            for nm in used_imps:
                fh.write('void imp_%s(void);\n' % nm)
            for c in sorted(set(overrides.values())):
                fh.write('void %s(void);\n' % c)
            for e in sorted(done):
                fh.write('void f_%x(void);\n' % e)
            with open(body_paths[k]) as bf:
                shutil.copyfileobj(bf, fh)
            os.remove(body_paths[k])
            if k: continue
            # 間接 dispatch: lifted 関数表 + IAT pseudo-VA 経路
            # (FLE-2: 冒頭に optional probe hook — boot 側で計数/トレースする。未設定なら何もしない)
            fh.write('void ott_dispatch(uint64_t t) {\n')
            fh.write('  if (fle_dispatch_probe) fle_dispatch_probe(t);\n  switch (t) {\n')
            for e in sorted(done):
                fh.write('  case %s: f_%x(); return;\n' % (hx(sh(e)), e))
            for tv2 in sorted(thunks):
                fh.write('  case %s: imp_%s(); return;\n' % (hx(sh(tv2)), thunks[tv2]))
            fh.write('  default: break;\n  }\n')
            if slots:
                fh.write('  if (t >= IMP_VA_BASE && t < IMP_VA_BASE + %du) { imp_by_index((int)(t - IMP_VA_BASE)); return; }\n' % len(slots))
            fh.write('  ott_unlifted(t);\n}\n')
            for nm in used_imps:
                fh.write('__attribute__((weak)) void imp_%s(void) { extern void ott_missing_import(const char*); ott_missing_import("%s"); }\n' % (nm, nm))
            # imp_by_index: IAT slot 順 (slot VA 昇順) の関数表
            fh.write('static void imp_unimpl(void) { ott_missing_import("(unresolved import)"); }\n')
            fh.write('static void (*const imp_tab[])(void) = {\n')
            fh.write(',\n'.join('  imp_%s' % nm if nm in used_imps else '  imp_unimpl' for nm in imp_names))
            fh.write('\n};\nvoid imp_by_index(int k) { if (k < 0 || k >= %d) { ott_missing_import("(oob import)"); return; } imp_tab[k](); }\n' % len(slots))
    # IAT slot → pseudo-VA index map (data 側の敷設に使う)
    iat_names = {}
    for idx, s in enumerate(slots):
        iat_names['%x' % s] = {'name': pe.iat[s], 'index': idx}
    meta = {'functions': sorted('%x' % e for e in done), 'unsup': dict(unsup), 'unsup_sites': unsup_sites,
            'unlifted_callees': {'%x' % k: v for k, v in unl.items()},
            'overrides': {'%x' % k: v for k, v in overrides.items()}, 'imports_used': used_imps,
            'iat_map': iat_names, 'impbase': a.impbase,
            'ninsn': ninsn,
            'textrefs': sorted(textrefs),
            'jt_ranges': sorted(jt_ranges)}
    json.dump(meta, open(os.path.join(out, 'lift_meta.json'), 'w'), indent=1)
    print('[flelift.x64c] functions %d, insns %d, unsup %s, unlifted callees %d, imports %d' % (
        len(done), meta['ninsn'], dict(unsup) or '{}', len(unl), len(used_imps)))


if __name__ == '__main__':
    main()
