#!/usr/bin/env python3
"""lift_pad.py — landing pad 断片の機械語 → LLVM IR lifter (CAB-227).

  python3 lift_pad.py --fragments work/fle_fragments.json --scopes work/fle_scopes.json \
      --verify-out work/pads_verify.ll --lib-out work/pads_lib.ll --meta-out work/pads_meta.json \
      [--exec-kinds dtor_pad] [--icall-target 0x416480]

方針 (チケット要件「正しい IR 片 + メタデータ」):
- 1:1 リフト。レジスタ = SSA 値、メモリ = inttoptr した実アドレスへの load/store、
  基本ブロック化 + 多前駆 block の入口で全 GPR の phi を敷設 (pad 内合流の値を正しく統合)。
- 断片は親関数の「Rip 設定で進入される例外ハンドラ」なので、統一シグネチャ
      i64 @function_<padVA>(i64 %frame, i64 %rax_in, i64 %rcx_in, i64 %r8_in, i64 %r9_in)
  で出す。%frame = 親フレームの rbp 値。live-in (実測: dtor_pad 493 は全てなし) は
  rax/rcx/r8/r9 の入口値として受ける (ネイティブ側トランポリンは非 live-in レジスタを 0 初期化し対称)。
- 間接 call (仮想 dtor `call [rbx-0x20]`) は:
    * lib 形 (統合用)   : HR フック `@__lp_icall(i64 %target, i64 %rcx, %rdx, %r8, %r9)` (declare)
    * verify 形 (検証用): 直接 `@function_<target>` 呼出し (target は case 側で VMT slot に敷設し固定)。
  wasm への落し方 (wasm EH / call_indirect) は CAB-226/228 に委ねる (REPORT.md §6)。
- メタデータ: VA / kind / 属する try 範囲 (scope table の kind-2 + kind-0 entry) / filter 条件 /
  フレーム slot / callee / site を pads_meta.json と .ll 内 `; LP-META:` 行の両方に書く。
"""
import argparse
import collections
import json
import re

UP = {'eax': 'rax', 'ebx': 'rbx', 'ecx': 'rcx', 'edx': 'rdx', 'esi': 'rsi', 'edi': 'rdi', 'ebp': 'rbp', 'esp': 'rsp',
      'r8d': 'r8', 'r9d': 'r9', 'r10d': 'r10', 'r11d': 'r11', 'r12d': 'r12', 'r13d': 'r13', 'r14d': 'r14', 'r15d': 'r15',
      'ax': 'rax', 'bx': 'rbx', 'cx': 'rcx', 'dx': 'rdx', 'si': 'rsi', 'di': 'rdi', 'bp': 'rbp', 'sp': 'rsp',
      'al': 'rax', 'bl': 'rbx', 'cl': 'rcx', 'dl': 'rdx', 'sil': 'rsi', 'dil': 'rdi', 'bpl': 'rbp', 'spl': 'rsp',
      'r8w': 'r8', 'r9w': 'r9', 'r10w': 'r10', 'r11w': 'r11', 'r12w': 'r12', 'r13w': 'r13', 'r14w': 'r14', 'r15w': 'r15',
      'r8b': 'r8', 'r9b': 'r9', 'r10b': 'r10', 'r11b': 'r11', 'r12b': 'r12', 'r13b': 'r13', 'r14b': 'r14', 'r15b': 'r15'}
BITS_MASK = {8: 0xFF, 16: 0xFFFF, 32: 0xFFFFFFFF, 64: None}
BYTES_MASK = {1: 0xFF, 2: 0xFFFF, 4: 0xFFFFFFFF, 8: None}
BYTE_TYPE = {1: 'i8', 2: 'i16', 4: 'i32', 8: 'i64'}
GPRS = ['rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15']
CALL_ACK = ('rcx', 'rdx', 'r8', 'r9')
JCC_MAP = {'je': 'eq', 'jne': 'ne', 'jl': 'lt', 'jle': 'le', 'jg': 'g', 'jge': 'ge',
           'jb': 'b', 'jbe': 'be', 'ja': 'a', 'jae': 'ae', 'js': 'lt', 'jns': 'ge'}
FLAGS = ['eq', 'ne', 'lt', 'le', 'g', 'ge', 'b', 'be', 'a', 'ae']


class LiftError(Exception):
    pass


class Padder:
    def __init__(self):
        self.n = 0

    def tmp(self, hint='t'):
        self.n += 1
        return '%%v%d_%s' % (self.n, hint)

    def raw(self, name):
        self.n += 1
        return '%%v%d_%s' % (self.n, name)


def hexva(v):
    return '0x%x' % v


def mem_content(s):
    """'qword ptr [rbp + 0x50]' → ('rbp + 0x50', size_bytes)"""
    inner = s[s.find('[') + 1:s.rfind(']')] if '[' in s else s
    size = 8
    if 'qword' in s:
        size = 8
    elif 'dword' in s:
        size = 4
    elif 'word' in s and 'qword' not in s:
        size = 2
    elif 'byte' in s:
        size = 1
    return inner.strip(), size


def reg_size(name):
    if name in UP:   # 部分レジスタ
        full = UP[name]
        if name.endswith('b') or name in ('al', 'bl', 'cl', 'dl', 'sil', 'dil', 'bpl', 'spl'):
            return 8
        if name.endswith('w') or name in ('ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'sp'):
            return 16
        return 32
    return 64


class Lifter:
    def __init__(self, frag, mode, icall_target):
        self.frag = frag
        self.mode = mode
        self.icall_target = icall_target
        self.p = Padder()
        self.sites = []
        self.errors = []

    # ---------- 共通ユーティリティ
    def emit(self, body, s):
        body.append('  ' + s)

    def const(self, body, v):
        t = self.p.tmp('c')
        self.emit(body, '%s = or i64 %d, 0' % (t, v & 0xFFFFFFFFFFFFFFFF))
        return t

    def read_reg(self, body, R, name):
        size = reg_size(name)
        r = UP.get(name, name)
        v = R.get(r)
        if v is None:
            raise LiftError('reg %s undefined' % name)
        mask = BITS_MASK[size]
        if mask is None:
            return v
        t = self.p.tmp('m')
        self.emit(body, '%s = and i64 %s, %d' % (t, v, mask))
        return t

    def write_reg(self, body, R, name, val):
        size = reg_size(name)
        r = UP.get(name, name)
        if size == 64:
            R[r] = val
            return
        mask = BITS_MASK[size]
        old = R.get(r)
        t = self.p.tmp('w')
        if old is None:
            self.emit(body, '%s = and i64 %s, %d' % (t, val, mask))
        else:
            keep = self.p.tmp('w')
            self.emit(body, '%s = and i64 %s, %d' % (keep, old, (~mask) & 0xFFFFFFFFFFFFFFFF))
            part = self.p.tmp('w')
            self.emit(body, '%s = and i64 %s, %d' % (part, val, mask))
            self.emit(body, '%s = or i64 %s, %s' % (t, keep, part))
        R[r] = t

    def addr_of(self, body, R, mstr, va, inslen):
        s = mstr.strip()
        if s.startswith('rip'):
            neg = '-' in s.split()[0:2][1] if len(s.split()) > 1 else False
            toks = s.split()
            disp = int(toks[-1], 16)
            if '-' in s:
                disp = -disp
            target = va + inslen + disp
            t = self.p.tmp('a')
            self.emit(body, '%s = or i64 %d, 0' % (t, target))
            if self.sites:
                self.sites[-1]['slot_rip'] = target
            return t
        parts = re.split(r'([+-])', s)
        base = None
        idx = None
        scale = 1
        disp = 0
        sign = 1
        for i, tok in enumerate(parts):
            tok = tok.strip()
            if tok in ('+', '-'):
                sign = 1 if tok == '+' else -1
            elif tok == 'ptr':
                continue
            elif re.match(r'^r[a-z0-9]+$', tok):
                if base is None:
                    base = tok
                else:
                    idx = tok
            elif tok.startswith('0x'):
                disp += sign * int(tok, 16)
            elif tok.isdigit():
                # index*scale の scale
                if idx is not None and parts[i - 1].strip() == '*':
                    scale = int(tok)
                else:
                    disp += sign * int(tok)
            elif tok == '*':
                pass
        bv = R.get(UP.get(base, base)) if base else None
        if bv is None:
            raise LiftError('mem base %r undefined (%s)' % (base, mstr))
        if idx:
            iv = R.get(UP.get(idx, idx))
            t = self.p.tmp('ai')
            self.emit(body, '%s = mul i64 %s, %d' % (t, iv, scale))
            t2 = self.p.tmp('a')
            self.emit(body, '%s = add i64 %s, %s' % (t2, bv, t))
            bv = t2
        if disp:
            t = self.p.tmp('a')
            self.emit(body, '%s = add i64 %s, %d' % (t, bv, disp))
            bv = t
        return bv

    def ptr_of(self, body, addr_v):
        t = self.p.tmp('p')
        self.emit(body, '%s = inttoptr i64 %s to ptr' % (t, addr_v))
        return t

    def load_mem(self, body, addr_v, size):
        ty = BYTE_TYPE[size]
        pv = self.ptr_of(body, addr_v)
        t = self.p.tmp('ld')
        self.emit(body, '%s = load %s, ptr %s, align 1' % (t, ty, pv))
        if size < 8:
            z = self.p.tmp('z')
            self.emit(body, '%s = zext %s %s to i64' % (z, ty, t))
            return z
        return t

    def store_mem(self, body, addr_v, val, size):
        ty = BYTE_TYPE[size]
        pv = self.ptr_of(body, addr_v)
        if size < 8:
            t = self.p.tmp('st')
            self.emit(body, '%s = trunc i64 %s to %s' % (t, val, ty))
            self.emit(body, 'store %s %s, ptr %s, align 1' % (ty, t, pv))
        else:
            self.emit(body, 'store %s %s, ptr %s, align 1' % (ty, val, pv))

    # ---------- ブロック分割
    def split_blocks(self, insns):
        va_lo = insns[0]['va']
        leaders = {va_lo}
        rng = (va_lo, insns[-1]['va'] + len(bytes.fromhex(insns[-1]['bytes'])))
        for i, ins in enumerate(insns):
            mn = ins['mn']
            if mn in JCC_MAP or mn == 'jmp':
                tgt = int(ins['op'].split(',')[0].strip(), 16) if re.match(r'^0x[0-9a-f]+$', ins['op'].split(',')[0].strip()) else None
                if tgt is not None and rng[0] <= tgt < rng[1]:
                    leaders.add(tgt)
                if i + 1 < len(insns):
                    leaders.add(insns[i + 1]['va'])
        blocks = []
        cur = []
        for ins in insns:
            if ins['va'] in leaders and cur:
                blocks.append(cur)
                cur = []
            cur.append(ins)
        if cur:
            blocks.append(cur)
        return blocks

    # ---------- 1 命令 lift
    def lift_insn(self, body, R, ins, block_ctx):
        va = ins['va']
        mn = ins['mn']
        op = ins['op']
        inslen = len(bytes.fromhex(ins['bytes']))
        operands = [t.strip() for t in re.split(r',(?![^[]*\])', op)] if op else []

        if mn in ('nop', 'int3'):
            return []
        if mn in ('mov', 'movabs') and len(operands) == 2:
            dst, src = operands
            if '[' in src:
                inner, size = mem_content(src)
                a = self.addr_of(body, R, inner, va, inslen)
                if src.startswith('xmm') or dst.startswith('xmm'):
                    xv = R.get(src) or R.get(dst)
                    lo = self.p.tmp('xlo')
                    self.emit(body, '%s = bitcast double %s to i64' % (lo, xv))
                    self.store_mem(body, a, lo, 8)
                    a2 = self.p.tmp('a2')
                    self.emit(body, '%s = add i64 %s, 8' % (a2, a))
                    h = self.const(body, 0)
                    self.store_mem(body, a2, h, 8)
                    return []
                v = self.load_mem(body, a, size)
                self.write_reg(body, R, dst, v)
            elif '[' in dst:
                inner, size = mem_content(dst)
                a = self.addr_of(body, R, inner, va, inslen)
                if src.startswith('xmm'):
                    xv = R.get(src)
                    lo = self.p.tmp('xlo')
                    self.emit(body, '%s = bitcast double %s to i64' % (lo, xv))
                    self.store_mem(body, a, lo, 8)
                    a2 = self.p.tmp('a2')
                    self.emit(body, '%s = add i64 %s, 8' % (a2, a))
                    h = self.const(body, 0)
                    self.store_mem(body, a2, h, 8)
                    return []
                if re.match(r'^-?0x[0-9a-f]+$|^[-0-9]+$', src):
                    imm = int(src, 16) if src.startswith(('0x', '-0x')) else int(src)
                    v = self.const(body, imm)
                else:
                    v = self.read_reg(body, R, src)
                self.store_mem(body, a, v, size)
            elif src.startswith('xmm'):
                xv = R.get(src)
                t = self.p.tmp('xb')
                self.emit(body, '%s = bitcast double %s to i64' % (t, xv))
                self.write_reg(body, R, dst, t)
            elif dst.startswith('xmm'):
                if re.match(r'^-?0x[0-9a-f]+$|^[-0-9]+$', src):
                    imm = int(src, 16) if src.startswith(('0x', '-0x')) else int(src)
                    bits = self.const(body, imm)
                else:
                    bits = self.read_reg(body, R, src)
                t = self.p.tmp('xd')
                self.emit(body, '%s = bitcast i64 %s to double' % (t, bits))
                R[dst] = t
            elif re.match(r'^-?0x[0-9a-f]+$|^[-0-9]+$', src):
                imm = int(src, 16) if src.startswith(('0x', '-0x')) else int(src)
                v = self.const(body, imm)
                self.write_reg(body, R, dst, v)
            else:
                v = self.read_reg(body, R, src)
                self.write_reg(body, R, dst, v)
            return []
        if mn == 'lea' and len(operands) == 2:
            dst, src = operands
            inner, _ = mem_content(src)
            a = self.addr_of(body, R, inner, va, inslen)
            self.write_reg(body, R, dst, a)
            return []
        if mn == 'xor' and len(operands) == 2 and operands[0] == operands[1]:
            v = self.const(body, 0)
            self.write_reg(body, R, operands[0], v)
            return []
        if mn in ('add', 'sub', 'and', 'or', 'xor', 'imul') and 2 <= len(operands) <= 3:
            if len(operands) == 3:  # add r, r, i 形 (x86 には無いが保険)
                dst, s0, s1 = operands
            else:
                dst, s0 = operands[0], operands[1]
                s1 = None
            size = reg_size(dst) if '[' not in dst else mem_content(dst)[1] * 8
            v0 = (self.load_mem(body, self.addr_of(body, R, mem_content(dst)[0], va, inslen), size // 8)
                  if '[' in dst else self.read_reg(body, R, dst))
            for s in ([s0, s1] if s1 is not None else [s0]):
                if re.match(r'^-?0x[0-9a-f]+$|^[-0-9]+$', s):
                    imm = int(s, 16) if s.startswith(('0x', '-0x')) else int(s)
                    v1 = self.const(body, imm)
                elif '[' in s:
                    inner, sz2 = mem_content(s)
                    v1 = self.load_mem(body, self.addr_of(body, R, inner, va, inslen), sz2)
                else:
                    v1 = self.read_reg(body, R, s)
                t = self.p.tmp('alu')
                mask = BITS_MASK[size]
                if mn == 'imul':
                    self.emit(body, '%s = mul i64 %s, %s' % (t, v0, v1))
                else:
                    self.emit(body, '%s = %s i64 %s, %s' % (t, mn, v0, v1))
                if mask:
                    t2 = self.p.tmp('alm')
                    self.emit(body, '%s = and i64 %s, %d' % (t2, t, mask))
                    v0 = t2
                else:
                    v0 = t
            if '[' in dst:
                a = self.addr_of(body, R, mem_content(dst)[0], va, inslen)
                self.store_mem(body, a, v0, size // 8)
            else:
                self.write_reg(body, R, dst, v0)
            return []
        if mn in ('shl', 'shr', 'sar') and len(operands) == 2:
            dst, s0 = operands
            size = reg_size(dst)
            v0 = self.read_reg(body, R, dst)
            if re.match(r'^-?0x[0-9a-f]+$|^[-0-9]+$', s0):
                imm = int(s0, 16) if s0.startswith(('0x', '-0x')) else int(s0)
                t = self.p.tmp('sh')
                opn = {'shl': 'shl', 'shr': 'lshr', 'sar': 'ashr'}[mn]
                self.emit(body, '%s = %s i64 %s, %d' % (t, opn, v0, imm))
                mask = BITS_MASK[size]
                if size < 64:
                    t2 = self.p.tmp('shm')
                    self.emit(body, '%s = and i64 %s, %d' % (t2, t, mask))
                    t = t2
                self.write_reg(body, R, dst, t)
                return []
            raise LiftError('shl/shr/sar by reg: %s' % op)
        if mn in ('movzx', 'movsx') and len(operands) == 2:
            dst, src = operands
            if '[' in src:
                inner, size = mem_content(src)
                a = self.addr_of(body, R, inner, va, inslen)
                pv = self.ptr_of(body, a)
                t = self.p.tmp('ld')
                self.emit(body, '%s = load i%d, ptr %s, align 1' % (t, size * 8, pv))
                if mn == 'movzx':
                    z = self.p.tmp('z')
                    self.emit(body, '%s = zext i%d %s to i64' % (z, size * 8, t))
                else:
                    z = self.p.tmp('s')
                    self.emit(body, '%s = sext i%d %s to i64' % (z, size * 8, t))
                self.write_reg(body, R, dst, z)
                return []
            raise LiftError('movzx/movsx reg,reg: %s' % op)
        if mn in ('neg', 'not', 'inc', 'dec') and len(operands) == 1:
            dst = operands[0]
            size = reg_size(dst) if '[' not in dst else mem_content(dst)[1] * 8
            v0 = (self.load_mem(body, self.addr_of(body, R, mem_content(dst)[0], va, inslen), size // 8)
                  if '[' in dst else self.read_reg(body, R, dst))
            t = self.p.tmp('un')
            if mn == 'neg':
                self.emit(body, '%s = sub i64 0, %s' % (t, v0))
            elif mn == 'not':
                self.emit(body, '%s = xor i64 %s, -1' % (t, v0))
            elif mn == 'inc':
                self.emit(body, '%s = add i64 %s, 1' % (t, v0))
            else:
                self.emit(body, '%s = sub i64 %s, 1' % (t, v0))
            mask = BITS_MASK[size]
            if mask:
                t2 = self.p.tmp('unm')
                self.emit(body, '%s = and i64 %s, %d' % (t2, t, mask))
                t = t2
            if '[' in dst:
                a = self.addr_of(body, R, mem_content(dst)[0], va, inslen)
                self.store_mem(body, a, t, size // 8)
            else:
                self.write_reg(body, R, dst, t)
            return []
        if mn in ('cmp', 'test') and len(operands) == 2:
            a0, a1 = operands
            if '[' in a0:
                inner, size = mem_content(a0)
                v0 = self.load_mem(body, self.addr_of(body, R, inner, va, inslen), size)
            else:
                size = reg_size(a0) // 8
                v0 = self.read_reg(body, R, a0)
            if '[' in a1:
                inner1, size1 = mem_content(a1)
                v1 = self.load_mem(body, self.addr_of(body, R, inner1, va, inslen), size1)
            elif re.match(r'^-?0x[0-9a-f]+$|^[-0-9]+$', a1):
                imm = int(a1, 16) if a1.startswith(('0x', '-0x')) else int(a1)
                v1 = self.const(body, imm)
            else:
                v1 = self.read_reg(body, R, a1)
            mask = BYTES_MASK[size]
            t0, t1 = v0, v1
            if mask:
                m0 = self.p.tmp('cm')
                self.emit(body, '%s = and i64 %s, %d' % (m0, v0, mask))
                m1 = self.p.tmp('cm')
                self.emit(body, '%s = and i64 %s, %d' % (m1, v1, mask))
                t0, t1 = m0, m1
            eq = self.p.tmp('cond')
            self.emit(body, '%s = icmp eq i64 %s, %s' % (eq, t0, t1))
            ne = self.p.tmp('cond')
            self.emit(body, '%s = xor i1 %s, 1' % (ne, eq))
            d = self.p.tmp('d')
            self.emit(body, '%s = sub i64 %s, %s' % (d, t0, t1))
            lt = self.p.tmp('lt')
            self.emit(body, '%s = icmp slt i64 %s, 0' % (lt, d))
            le = self.p.tmp('le')
            self.emit(body, '%s = icmp sle i64 %s, 0' % (le, d))
            g = self.p.tmp('g')
            self.emit(body, '%s = xor i1 %s, 1' % (g, le))
            ge = self.p.tmp('ge')
            self.emit(body, '%s = xor i1 %s, 1' % (ge, lt))
            b = self.p.tmp('b')
            self.emit(body, '%s = icmp ult i64 %s, %s' % (b, t0, t1))
            be = self.p.tmp('be')
            self.emit(body, '%s = icmp ule i64 %s, %s' % (be, t0, t1))
            a_ = self.p.tmp('a')
            self.emit(body, '%s = icmp ugt i64 %s, %s' % (a_, t0, t1))
            ae = self.p.tmp('ae')
            self.emit(body, '%s = icmp uge i64 %s, %s' % (ae, t0, t1))
            R['_c'] = {'eq': eq, 'ne': ne, 'lt': lt, 'le': le, 'g': g, 'ge': ge, 'b': b, 'be': be, 'a': a_, 'ae': ae}
            return []
        if mn == 'call':
            a0 = operands[0]
            site = {'va': hexva(va), 'mn': 'call', 'kind': 'direct' if '[' not in a0 else 'indirect', 'bytes': ins['bytes']}
            self.sites.append(site)
            args = [R[r] for r in CALL_ACK]
            if '[' in a0:
                inner, size = mem_content(a0)
                a = self.addr_of(body, R, inner, va, inslen)
                tgt = self.load_mem(body, a, 8)
                site['target_via_memory'] = True
                if self.mode == 'verify' and self.icall_target is not None:
                    callee = '@function_%x' % self.icall_target
                    site['target_fixed_verify'] = hexva(self.icall_target)
                else:
                    rv = self.p.tmp('ret')
                    self.emit(body, '%s = call i64 @__lp_icall(i64 %s, i64 %s, i64 %s, i64 %s, i64 %s)' % (
                        rv, tgt, args[0], args[1], args[2], args[3]))
                    R['rax'] = rv
                    site['hr'] = '__lp_icall(target,rcx,rdx,r8,r9)'
                    return []
            elif re.match(r'^0x[0-9a-f]+$', a0):
                callee = '@function_%s' % a0[2:]
                site['target'] = a0
            else:
                raise LiftError('call form: %s' % a0)
            rv = self.p.tmp('ret')
            self.emit(body, '%s = call i64 %s(i64 %s, i64 %s, i64 %s, i64 %s)' % (
                rv, callee, args[0], args[1], args[2], args[3]))
            R['rax'] = rv
            return []
        if mn == 'jmp':
            a0 = operands[0]
            if '[' in a0:
                inner, size = mem_content(a0)
                a = self.addr_of(body, R, inner, va, inslen)
                tgt = self.load_mem(body, a, 8)
                self.sites.append({'va': hexva(va), 'mn': 'jmp', 'kind': 'indirect', 'bytes': ins['bytes'], 'hr': '__lp_icall'})
                self.emit(body, 'call void @__lp_icall(i64 %s, i64 %s, i64 %s, i64 %s, i64 %s)' % (
                    tgt, R['rcx'], R['rdx'], R['r8'], R['r9']))
                self.emit(body, 'ret i64 %s' % R['rax'])
                return ['term']
            if a0 == 'rax' or (a0 in UP and UP[a0] == 'rax'):
                self.sites.append({'va': hexva(va), 'mn': 'jmp', 'kind': 'reg', 'reg': 'rax', 'bytes': ins['bytes']})
                self.emit(body, 'call void @__lp_icall(i64 %s, i64 %s, i64 %s, i64 %s, i64 %s)' % (
                    R['rax'], R['rcx'], R['rdx'], R['r8'], R['r9']))
                self.emit(body, 'ret i64 %s' % R['rax'])
                return ['term']
            if re.match(r'^0x[0-9a-f]+$', a0):
                t = int(a0, 16)
                if block_ctx['in_range'](t):
                    self.emit(body, 'br label %%%s' % block_ctx['label_of'](t))
                else:
                    self.sites.append({'va': hexva(va), 'mn': 'jmp', 'kind': 'exit', 'target': a0, 'bytes': ins['bytes']})
                    self.emit(body, 'call void @__lp_resume(i64 %d)' % t)
                    self.emit(body, 'ret i64 %s' % R['rax'])
                return ['term']
            raise LiftError('jmp form: %s' % a0)
        if mn in JCC_MAP:
            a0 = operands[0]
            if not re.match(r'^0x[0-9a-f]+$', a0):
                raise LiftError('jcc target form: %s' % a0)
            t = int(a0, 16)
            cond = R['_c'][JCC_MAP[mn]]
            if block_ctx['in_range'](t) and block_ctx['next_va'] is not None:
                self.emit(body, 'br i1 %s, label %%%s, label %%L_%x' % (cond, block_ctx['label_of'](t), block_ctx['next_va']))
            else:
                # 断片外への条件分岐 (MSVC funclet の親 CFG への合流): 両腕を resume フックで終端
                site = {'va': hexva(va), 'mn': mn, 'kind': 'exit_cond', 'target': a0, 'bytes': ins['bytes']}
                self.sites.append(site)
                nxt = block_ctx['next_va']
                self.emit(body, 'br i1 %s, label %%L_out%x_t, label %%L_out%x_f' % (cond, va, va))
                self.emit(body, 'L_out%x_t:' % va)
                self.emit(body, 'call void @__lp_resume(i64 %d)' % t)
                self.emit(body, 'ret i64 %s' % R['rax'])
                self.emit(body, 'L_out%x_f:' % va)
                if nxt is not None:
                    self.emit(body, 'call void @__lp_resume(i64 %d)' % nxt)
                self.emit(body, 'ret i64 %s' % R['rax'])
            return ['term']
        if mn.startswith('cmov') and len(operands) == 2:
            dst, src = operands
            cc = mn[4:]
            k = JCC_MAP.get('j' + cc) or JCC_MAP.get('j' + {'b': 'b', 'be': 'be', 'a': 'a', 'ae': 'ae', 'e': 'eq', 'ne': 'ne', 'l': 'lt', 'le': 'le', 'g': 'g', 'ge': 'ge', 's': 'lt', 'ns': 'ge'}.get(cc, cc))
            cond = (R.get('_c') or {}).get(k)
            if cond is None:
                raise LiftError('cmov without flags: %s' % op)
            if re.match(r'^-?0x[0-9a-f]+$|^[-0-9]+$', src):
                imm = int(src, 16) if src.startswith(('0x', '-0x')) else int(src)
                v1 = self.const(body, imm)
            elif '[' in src:
                inner, size = mem_content(src)
                v1 = self.load_mem(body, self.addr_of(body, R, inner, va, inslen), size)
            else:
                v1 = self.read_reg(body, R, src)
            v0 = self.read_reg(body, R, dst)
            t = self.p.tmp('cmv')
            self.emit(body, '%s = select i1 %s, i64 %s, i64 %s' % (t, cond, v1, v0))
            self.write_reg(body, R, dst, t)
            return []
        if mn in ('movsd', 'movss', 'movaps', 'movups', 'movapd') and len(operands) == 2:
            a0, a1 = operands
            if a0.startswith('xmm') and '[' in a1:
                inner, size = mem_content(a1)
                a = self.addr_of(body, R, inner, va, inslen)
                xv = R.get(a0)
                lo = self.p.tmp('xlo')
                self.emit(body, '%s = bitcast double %s to i64' % (lo, xv))
                pv = self.ptr_of(body, a)
                if size >= 8:
                    self.emit(body, 'store i64 %s, ptr %s, align 1' % (lo, pv))
                else:
                    t = self.p.tmp('st')
                    self.emit(body, '%s = trunc i64 %s to i32' % (t, lo))
                    self.emit(body, 'store i32 %s, ptr %s, align 1' % (t, pv))
                if size >= 8:   # 上位 64bit (16B 形)
                    a2 = self.p.tmp('a2')
                    self.emit(body, '%s = add i64 %s, 8' % (a2, a))
                    h = self.const(body, 0)
                    self.store_mem(body, a2, h, 8)
                return []
            if '[' in a0 and a1.startswith('xmm'):
                inner, size = mem_content(a0)
                a = self.addr_of(body, R, inner, va, inslen)
                pv = self.ptr_of(body, a)
                t = self.p.tmp('ld')
                self.emit(body, '%s = load %s, ptr %s, align 1' % (t, 'i64' if size >= 8 else 'i32', pv))
                if size < 8:
                    z = self.p.tmp('z')
                    self.emit(body, '%s = zext i32 %s to i64' % (z, t))
                    t = z
                x = self.p.tmp('xd')
                self.emit(body, '%s = bitcast i64 %s to double' % (x, t))
                R[a1] = x
                return []
            if a0.startswith('xmm') and a1.startswith('xmm'):
                R[a0] = R.get(a1)
                return []
        if mn in ('xorps', 'pxor', 'xorpd') and len(operands) == 2 and operands[0] == operands[1]:
            t = self.p.tmp('xz')
            self.emit(body, '%s = bitcast i64 0 to double' % t)
            R[operands[0]] = t
            return []
        if mn == 'movsxd' and len(operands) == 2:
            dst, src = operands
            if '[' in src:
                inner, size = mem_content(src)
                a = self.addr_of(body, R, inner, va, inslen)
                pv = self.ptr_of(body, a)
                t = self.p.tmp('ld')
                self.emit(body, '%s = load i%d, ptr %s, align 1' % (t, size * 8, pv))
                z = self.p.tmp('s')
                self.emit(body, '%s = sext i%d %s to i64' % (z, size * 8, t))
                self.write_reg(body, R, dst, z)
                return []
            v = self.read_reg(body, R, src)
            size = reg_size(src)
            z = self.p.tmp('s')
            self.emit(body, '%s = sext i%d %s to i64' % (z, size, v))
            self.write_reg(body, R, dst, z)
            return []
        if mn in ('sete', 'setne', 'setb', 'setbe', 'seta', 'setae', 'setl', 'setle', 'setg', 'setge', 'sets', 'setns') and len(operands) == 1:
            dst = operands[0]
            cc = mn[3:]
            k = JCC_MAP.get('j' + cc)
            cond = (R.get('_c') or {}).get(k)
            if cond is None:
                raise LiftError('setcc without flags: %s' % op)
            z = self.p.tmp('z')
            self.emit(body, '%s = zext i1 %s to i64' % (z, cond))
            self.write_reg(body, R, dst, z)
            return []
        if mn in ('cdq', 'cdqe') and not operands:
            v = self.read_reg(body, R, 'eax' if mn == 'cdq' else 'rax')
            z = self.p.tmp('s')
            self.emit(body, '%s = sext i32 %s to i64' % (z, v))
            if mn == 'cdq':
                # edx:eax = 符号拡張 — edx に上位 32bit
                t = self.p.tmp('hi')
                self.emit(body, '%s = ashr i64 %s, 32' % (t, z))
                self.write_reg(body, R, 'edx', t)
            else:
                self.write_reg(body, R, 'rax', z)
            return []
        if mn == 'ret':
            self.emit(body, 'ret i64 %s' % R['rax'])
            return ['term']
        if mn == 'push':
            src = operands[0]
            a = self.p.tmp('sp')
            self.emit(body, '%s = sub i64 %s, 8' % (a, R['rsp']))
            R['rsp'] = a
            if re.match(r'^-?0x[0-9a-f]+$|^[-0-9]+$', src):
                v = self.const(body, int(src, 16) if src.startswith('0x') else int(src))
            else:
                v = self.read_reg(body, R, src)
            self.store_mem(body, R['rsp'], v, 8)
            return []
        if mn == 'pop':
            v = self.load_mem(body, R['rsp'], 8)
            a = self.p.tmp('sp')
            self.emit(body, '%s = add i64 %s, 8' % (a, R['rsp']))
            R['rsp'] = a
            self.write_reg(body, R, operands[0], v)
            return []
        if mn in ('sub', 'add') and operands[0] in ('rsp', 'esp'):
            imm = int(operands[1], 16) if operands[1].startswith('0x') else int(operands[1])
            t = self.p.tmp('sp')
            self.emit(body, '%s = %s i64 %s, %d' % (t, mn, R['rsp'], imm))
            R['rsp'] = t
            return []
        if mn in ('movapd', 'movups', 'movaps') and len(operands) == 2:
            a0, a1 = operands
            if '[' in a1 and a0.startswith('xmm'):
                inner, _ = mem_content(a1)
                a = self.addr_of(body, R, inner, va, inslen)
                xv = R.get(a0)
                lo = self.p.tmp('xlo')
                self.emit(body, '%s = bitcast double %s to i64' % (lo, xv))
                self.store_mem(body, a, lo, 8)
                a2 = self.p.tmp('a2')
                self.emit(body, '%s = add i64 %s, 8' % (a2, a))
                h = self.const(body, 0)
                self.store_mem(body, a2, h, 8)
                return []
            if '[' in a0 and a1.startswith('xmm'):
                inner, _ = mem_content(a0)
                a = self.addr_of(body, R, inner, va, inslen)
                lo = self.load_mem(body, a, 8)
                t = self.p.tmp('xd')
                self.emit(body, '%s = bitcast i64 %s to double' % (t, lo))
                R[a1] = t
                return []
        raise LiftError('unsupported: %s %s' % (mn, op))

    # ---------- 本体
    def run(self):
        frag = self.frag
        insns = []
        for ins0 in frag['insns']:
            ins = dict(ins0)
            if isinstance(ins.get('va'), str):
                ins['va'] = int(ins['va'], 16)
            insns.append(ins)
        va_lo = insns[0]['va']
        blocks = self.split_blocks(insns)
        rng = (va_lo, insns[-1]['va'] + len(bytes.fromhex(insns[-1]['bytes'])))
        next_map = {}
        for bi, blk in enumerate(blocks):
            next_map[blk[0]['va']] = (blocks[bi + 1][0]['va'] if bi + 1 < len(blocks) else None)

        # 前駆集合
        preds = collections.defaultdict(list)
        out_vals = {}
        for bi, blk in enumerate(blocks):
            bva = blk[0]['va']
            last = blk[-1]
            lastmn = last['mn']
            if lastmn in JCC_MAP:
                tgt = int(last['op'].split(',')[0].strip(), 16)
                nxt = next_map[bva]
                preds[tgt].append(bva)
                if nxt is not None:
                    preds[nxt].append(bva)
            elif lastmn == 'jmp':
                a0 = last['op'].split(',')[0].strip()
                if re.match(r'^0x[0-9a-f]+$', a0) and rng[0] <= int(a0, 16) < rng[1]:
                    preds[int(a0, 16)].append(bva)
                # 外部/間接 jmp は term (後続なし)
            elif lastmn == 'ret':
                pass
            else:
                nxt = next_map[bva]
                if nxt is not None:
                    preds[nxt].append(bva)

        # ラベル名
        label_of = {}
        for b in blocks:
            label_of[b[0]['va']] = 'L_%x' % b[0]['va']

        body = []
        # 入口レジスタ初期化
        R0 = {}
        init = {'rax': '%rax_in', 'rcx': '%rcx_in', 'r8': '%r8_in', 'r9': '%r9_in'}
        for r in GPRS:
            if r in init:
                t = self.p.raw(r + '_in0')
                body.append('  %s = add i64 %s, 0' % (t, init[r]))
            else:
                t = self.p.raw(r + '_z')
                body.append('  %s = or i64 0, 0' % t)
            R0[r] = t
        R0['rbp'] = '%frame'
        t = self.p.raw('rsp0')
        body.append('  %s = or i64 0, 0' % t)
        R0['rsp'] = t
        # flags 疑似レジスタ (block 間で伝播; 入口値は 0 固定 — 静的検証対象の simplification)
        R0['_c'] = {}
        for fl in FLAGS:
            t = self.p.raw('fl_' + fl)
            body.append('  %s = or i1 0, 0' % t)
            R0['_c'][fl] = t

        GPRS_ALL = GPRS + ['rbp', 'rsp']
        out_lines = list(body)
        # init block は entry block (無名) — pad 入口 label へ明示 br (LLVM は暗黙 fallthrough 不許可)
        if blocks:
            out_lines.append('  br label %%%s' % ('L_%x' % blocks[0][0]['va']))
        first = True
        for blk in blocks:
            bva = blk[0]['va']
            prds = preds.get(bva, [])
            if bva != va_lo and not prds:
                # 終端命令の後ろで到達不能な尾部 (nop padding 等) は出力しない
                continue
            if not first:
                out_lines.append('')
            out_lines.append('%s:' % label_of[bva])
            if bva == va_lo:
                R = dict(R0)
            else:
                if any(p not in out_vals for p in prds):
                    raise LiftError('block 0x%x: predecessors not lifted first (backward branch?)' % bva)
                R = {}
                if len(prds) == 1:
                    R = dict(out_vals[prds[0]])
                else:
                    for r in GPRS_ALL:
                        vals = [out_vals[p][r] for p in prds]
                        if len(set(vals)) == 1:
                            R[r] = vals[0]
                        else:
                            ph = self.p.raw('phi_' + r)
                            args = ', '.join('[ %s, %%%s ]' % (v, 'L_%x' % p) for p, v in zip(prds, vals))
                            out_lines.append('  %s = phi i64 %s' % (ph, args))
                            R[r] = ph
                    c = {}
                    for fl in FLAGS:
                        vals = [out_vals[p]['_c'][fl] for p in prds]
                        if len(set(vals)) == 1:
                            c[fl] = vals[0]
                        else:
                            ph = self.p.raw('phifl_' + fl)
                            args = ', '.join('[ %s, %%%s ]' % (v, 'L_%x' % p) for p, v in zip(prds, vals))
                            out_lines.append('  %s = phi i1 %s' % (ph, args))
                            c[fl] = ph
                    R['_c'] = c
            blk_ctx = {
                'in_range': lambda t: rng[0] <= t < rng[1],
                'label_of': lambda t: label_of[t],
                'next_va': next_map[bva],
            }
            terminated = False
            for ins in blk:
                res = self.lift_insn(out_lines, R, ins, blk_ctx)
                if res and res[0] == 'term':
                    terminated = True
                    break
            if not terminated:
                nxt = next_map[bva]
                if nxt is not None:
                    out_lines.append('  br label %%%s' % label_of[nxt])
                else:
                    out_lines.append('  ret i64 %s' % R['rax'])
            out_vals[bva] = {k: (dict(v) if k == '_c' else v) for k, v in R.items()}
            first = False
        name = ('@function_%x' % va_lo) if self.mode == 'verify' else ('@lp_%x' % va_lo)
        header = 'define i64 %s(i64 %%frame, i64 %%rax_in, i64 %%rcx_in, i64 %%r8_in, i64 %%r9_in) {' % name
        meta = '; LP-META: {"va":"%s","kind":"%s","n_insns":%d,"liveins":%s,"sites":%s}' % (
            hexva(va_lo), self.frag['kind'], self.frag['n_insns'],
            json.dumps(self.frag.get('liveins') or []),
            json.dumps(self.sites).replace('"', '\\"'))
        return [meta, header] + out_lines + ['}', ''], self.sites


def lift_fragment(frag, mode, icall_target=None):
    return Lifter(frag, mode, icall_target).run()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fragments', required=True)
    ap.add_argument('--scopes')
    ap.add_argument('--verify-out')
    ap.add_argument('--lib-out')
    ap.add_argument('--meta-out')
    ap.add_argument('--exec-kinds', default='dtor_pad')
    ap.add_argument('--icall-target', default='0x416480')
    ap.add_argument('--label', default='fle')
    a = ap.parse_args()

    fragdoc = json.load(open(a.fragments))
    frags = fragdoc['fragments']
    scopes = json.load(open(a.scopes)) if a.scopes else []
    icall_target = int(a.icall_target, 16)
    exec_kinds = set(a.exec_kinds.split(','))

    by_fn = collections.defaultdict(list)
    for e in scopes:
        by_fn[e['fn_rva']].append(e)
    fn_ranges = sorted({(e['fn_rva'], e['fn_end_rva']) for e in scopes})
    fn_starts = [r for r, _ in fn_ranges]

    def owning_fn(rva):
        import bisect
        i = bisect.bisect_right(fn_starts, rva) - 1
        if i >= 0:
            lo, hi = fn_ranges[i]
            if lo <= rva < hi:
                return lo
        return None

    meta = []
    verify_lines = ['; landing pad verification IR (CAB-227) — %s' % a.label]
    lib_lines = ['; landing pad IR fragments (CAB-227) — %s' % a.label,
                 '; HR フック: @__lp_icall(target, rcx, rdx, r8, r9) = 間接 call の置換先 (CAB-226/228 で接続)',
                 ';              @__lp_resume(va) = 断片外アドレスへの合流 (親関数 CFG への復帰)',
                 'declare i64 @__lp_icall(i64, i64, i64, i64, i64)',
                 'declare void @__lp_resume(i64)', '']
    nok = nfail = 0
    fails = []
    callees = set()
    lib_externs = set()
    def collect_externs(lines):
        for ln in lines:
            m = re.search(r'call i64 @function_([0-9a-f]+)\(', ln)
            if m:
                lib_externs.add(int(m.group(1), 16))
    for f in frags:
        try:
            vlines, sites = lift_fragment(f, 'verify', icall_target=icall_target if f['kind'] in exec_kinds else None)
            llines, _ = lift_fragment(f, 'lib')
            collect_externs(llines)
        except LiftError as e:
            nfail += 1
            fails.append({'va': hexva(f['va_lo']), 'kind': f['kind'], 'error': str(e)})
            continue
        nok += 1
        if f['kind'] in exec_kinds:
            verify_lines.extend(vlines)
            for s in f['sites']:
                if s.get('target'):
                    callees.add(int(s['target'], 16))
            for dc in f['direct_calls']:
                callees.add(dc)
            callees.add(icall_target)
        lib_lines.extend(llines)
        rva = f['va_lo'] - 0x400000
        owning = owning_fn(rva)
        pairs = []
        if owning is not None:
            for e in by_fn.get(owning, []):
                lo, hi = e['begin'], e['end']
                # kind-0 (handler 領域) は断片範囲で一致。kind-2 (try 本体) は landing が
                # 断片先頭の nop 整列分だけ手前になる事があるので ±8 で吸収。
                if lo <= rva < hi or (lo <= e['jump_target'] <= hi and rva - 8 <= e['jump_target'] <= rva):
                    pairs.append({'scope_kind': e['kind'] if e['kind'] < 3 else 'typed_except',
                                  'try_begin': hexva(0x400000 + e['begin']), 'try_end': hexva(0x400000 + e['end']),
                                  'landing': hexva(0x400000 + e['jump_target']),
                                  'filter': ({'class_rva': hexva(d['class_rva']), 'handler': hexva(0x400000 + d['handler_rva'])}
                                             for d in (e.get('descs') or [])) if e.get('descs') else None})
        m = {'va': hexva(f['va_lo']), 'va_hi': hexva(f['va_hi']), 'kind': f['kind'],
             'n_insns': f['n_insns'], 'liveins': f['liveins'],
             'frame_min': f['frame_min'], 'frame_max': f['frame_max'],
             'sites': f['sites'], 'direct_calls': [hexva(x) for x in f['direct_calls']],
             'fn_rva': hexva(owning) if owning is not None else None,
             'scopes': pairs,
             'ir_entry': ('@function_%x' % f['va_lo']) if f['kind'] in exec_kinds else ('@lp_%x' % f['va_lo'])}
        meta.append(m)
    if a.verify_out:
        verify_lines.append('; ---- callee recording stubs (ret 0; native 側は同一効果の entry patch で対称化)')
        for c in sorted(callees):
            verify_lines.append('define i64 @function_%x(i64 %%a, i64 %%b, i64 %%c, i64 %%d) {' % c)
            verify_lines.append('  ret i64 0')
            verify_lines.append('}')
            verify_lines.append('')
        open(a.verify_out, 'w').write('\n'.join(verify_lines) + '\n')
    if a.lib_out:
        # 断片外 callee の declare (断片内で define されるものは除く — 現状 lib 形は断片のみ)
        defined_in_lib = {int(m.group(1), 16) for ln in lib_lines for m in [re.match(r'define i64 @lp_([0-9a-f]+)\(', ln)] if m}
        for c in sorted(lib_externs - defined_in_lib):
            lib_lines.append('declare i64 @function_%x(i64, i64, i64, i64)' % c)
        open(a.lib_out, 'w').write('\n'.join(lib_lines) + '\n')
    if a.meta_out:
        json.dump({'label': a.label, 'icall_target_for_verify': hexva(icall_target),
                   'lift_ok': nok, 'lift_fail': nfail, 'fails': fails, 'pads': meta},
                  open(a.meta_out, 'w'), indent=0)
    print('lift: ok=%d fail=%d (exec-kinds=%s, callee stubs=%d)' % (nok, nfail, ','.join(sorted(exec_kinds)), len(callees)))
    for f in fails[:10]:
        print('  FAIL %s %s: %s' % (f['va'], f['kind'], f['error']))


if __name__ == '__main__':
    main()
