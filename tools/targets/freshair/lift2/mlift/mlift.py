"""mlift.py — 機械語駆動 x86-64 → LLVM IR リフタ (整数 + SSE/AVX スカラ/一部パック)。

RetDec の SSE スカラ lift が分岐/引数/戻り値/cmov を大量に取りこぼす (lift2/REPORT.md §3) ため、
RetDec の `__asm_*` 不透明 helper を介さず、capstone で復号した機械語 1 命令ずつを直接 LLVM IR 化する。
- レジスタ: 関数ローカル alloca (mem2reg/SROA で SSA 化)。GPR=i64, XMM=<4 x i32>, flags=CF/ZF/SF/OF/PF の i1。
- スタック: 関数ごとの alloca フレーム (rsp は実アドレス)。call は LLVM call (return address push は省略)。
- 呼出規約: MS x64。全関数を一様シグネチャ (rcx,rdx,r8,r9,xmm0-3)->{rax,xmm0} で出力し LLVM の DAE に
  未使用引数/戻り値を削らせる (xmm 引数落ちが原理的に起きない)。
- イメージ data (.rdata/.data/.bss) は参照 VA 周辺ページを fa_img_* グローバルに実データ化。`lea` は blob アドレスを返す。
- 間接 call は fa_icall (VA→関数 switch、未知は host shim)。IAT call は win_<dll>_<name> 外部関数。
usage: mlift.py CORE OUT.ll --root VA[:sig] ... [--stub VA] [--map VA=symbol] [--icall VA] [--report out.json]
"""
import sys, re, json, struct, argparse, collections
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_REG, CS_OP_IMM, CS_OP_MEM
from capstone.x86 import X86_REG_RIP, X86_REG_INVALID, X86_REG_GS
from pe_image import Image

# ---------------------------------------------------------------- レジスタ表
G64 = ['rax', 'rcx', 'rdx', 'rbx', 'rsp', 'rbp', 'rsi', 'rdi'] + ['r%d' % i for i in range(8, 16)]
REGINFO = {}
for i, n in enumerate(G64):
    REGINFO[n] = (n, 64, 0)
    if i < 8:
        b = n[1:]
        REGINFO['e' + b] = (n, 32, 0)
        REGINFO[b if b in ('ax', 'cx', 'dx', 'bx', 'sp', 'bp', 'si', 'di') else b] = (n, 16, 0)
    else:
        REGINFO[n + 'd'] = (n, 32, 0); REGINFO[n + 'w'] = (n, 16, 0); REGINFO[n + 'b'] = (n, 8, 0)
for n8, f in [('al', 'rax'), ('cl', 'rcx'), ('dl', 'rdx'), ('bl', 'rbx'), ('spl', 'rsp'), ('bpl', 'rbp'), ('sil', 'rsi'), ('dil', 'rdi')]:
    REGINFO[n8] = (f, 8, 0)
for n8, f in [('ah', 'rax'), ('ch', 'rcx'), ('dh', 'rdx'), ('bh', 'rbx')]:
    REGINFO[n8] = (f, 8, 8)
ARG_G = ['rcx', 'rdx', 'r8', 'r9']

JCC = {  # 条件 -> (式 builder 名)
    'o': 'OF', 'no': '!OF', 'b': 'CF', 'c': 'CF', 'nae': 'CF', 'ae': '!CF', 'nb': '!CF', 'nc': '!CF',
    'e': 'ZF', 'z': 'ZF', 'ne': '!ZF', 'nz': '!ZF', 'be': 'CF|ZF', 'na': 'CF|ZF', 'a': '!CF&!ZF', 'nbe': '!CF&!ZF',
    's': 'SF', 'ns': '!SF', 'p': 'PF', 'pe': 'PF', 'np': '!PF', 'po': '!PF',
    'l': 'SF!=OF', 'nge': 'SF!=OF', 'ge': 'SF==OF', 'nl': 'SF==OF', 'le': 'ZF|SF!=OF', 'ng': 'ZF|SF!=OF',
    'g': '!ZF&SF==OF', 'nle': '!ZF&SF==OF',
}


class Unsupported(Exception):
    pass


STACK_BYTES = 8 << 20   # 共有マシンスタック (@fa_stack)。FA-2c: 制御層 closure は深い入れ子 + 大フレーム (0x5cb0) で 1MB では不足する実測のため 8MB (host stack と同値)


def mask(bits):
    return (1 << bits) - 1


def imm_s(v, bits):
    v &= mask(bits)
    return v - (1 << bits) if v >> (bits - 1) else v


class FnLifter:
    def __init__(self, M, begin, end):
        self.M = M; self.img = M.img
        self.begin, self.end = begin, end
        self.lines = []; self.n = 0
        self.ins = {}            # va -> capstone insn
        self.order = []
        self.unsupported = []    # (va, mnemonic)
        self.calls = set()       # 直接 call 先
        self.mn_hist = collections.Counter()

    # ------------------------------------------------ 基本
    def e(self, s): self.lines.append('  ' + s)
    def t(self): self.n += 1; return '%%t%d' % self.n
    def lbl(self, va): return 'bb_%x' % va

    def tmp_lbl(self):
        self.n += 1
        return 'bb_tmp%d' % self.n

    def emit_trace(self, va):
        """--trace 指定範囲: 命令実行前の全 GPR/XMM を @fa_trace に Append (デバッグ用。行 = 33 x i64)。"""
        if not self.M.trace_vas or va not in self.M.trace_vas:
            return
        tn = self.t(); self.e('%s = load i64, ptr @fa_trace_n' % tn)
        base = self.t(); self.e('%s = mul i64 %s, 81' % (base, tn))
        vals = [str(va)]
        vals += ['%%ptr_%s' % r for r in G64]
        for k in range(16):
            xv = self.t(); self.e('%s = load <4 x i32>, ptr %%X_%d' % (xv, k))
            for lane in range(4):
                lv = self.t(); self.e('%s = extractelement <4 x i32> %s, i32 %d' % (lv, xv, lane))
                z = self.t(); self.e('%s = zext i32 %s to i64' % (z, lv))
                vals.append(z)
        for r in G64:
            g = self.g_get64(r)
            vals[1 + G64.index(r)] = g
        for k, v in enumerate(vals):
            p = self.t(); self.e('%s = add i64 %s, %d' % (p, base, k))
            q = self.t(); self.e('%s = getelementptr i64, ptr @fa_trace, i64 %s' % (q, p))
            self.e('store i64 %s, ptr %s' % (v, q))
        t1 = self.t(); self.e('%s = add i64 %s, 1' % (t1, tn))
        self.e('store i64 %s, ptr @fa_trace_n' % t1)


    def decode(self):
        md = self.M.md
        code = self.img.read(self.begin, self.end - self.begin)
        for i in md.disasm(code, self.begin):
            self.ins[i.address] = i; self.order.append(i.address)
        if not self.order:
            raise Unsupported('empty')
        last = self.ins[self.order[-1]]
        if last.address + last.size != self.end:
            # データ混在/復号不能: 残りは未復号扱いで先頭側のみ
            pass

    def leaders(self):
        L = {self.begin}
        for va in self.order:
            i = self.ins[va]; m = i.mnemonic
            nxt = va + i.size
            if m == 'jmp' or m.startswith('j') or m in ('ret', 'int3', 'ud2'):
                if i.operands and i.operands[0].type == CS_OP_IMM:
                    tgt = i.operands[0].imm
                    if self.begin <= tgt < self.end:
                        L.add(tgt)
                if nxt < self.end:
                    L.add(nxt)
        # MSVC jump table の case 先 (表を image から読んで leader に加える)
        for va in self.order:
            i = self.ins[va]
            if i.mnemonic == 'jmp' and i.operands and i.operands[0].type == CS_OP_REG:
                L |= self.jump_table_targets(va)
        return sorted(L)

    def jump_table_targets(self, jva):
        pos = self.order.index(jva); tbl = None; cnt = None
        for k in range(pos - 1, max(pos - 16, -1), -1):
            pi = self.ins[self.order[k]]
            if pi.mnemonic == 'mov' and len(pi.operands) == 2 and pi.operands[1].type == CS_OP_MEM and pi.operands[1].mem.scale == 4 \
                    and pi.operands[1].mem.disp > 0x1000 and tbl is None:
                tbl = pi.operands[1].mem.disp
            if pi.mnemonic == 'cmp' and len(pi.operands) == 2 and pi.operands[1].type == CS_OP_IMM and cnt is None:
                cnt = pi.operands[1].imm + 1
        out = set()
        if tbl is None or cnt is None or not (1 <= cnt <= 512):
            return out
        data = self.img.read(self.img.base + tbl, 4 * cnt)
        for e in range(cnt):
            t = self.img.base + struct.unpack_from('<I', data, 4 * e)[0]
            if self.begin <= t < self.end:
                out.add(t)
        return out

    # ------------------------------------------------ レジスタ I/O
    def g_get64(self, full):
        t = self.t(); self.e('%s = load i64, ptr %%R_%s' % (t, full)); return t

    def g_set64(self, full, v): self.e('store i64 %s, ptr %%R_%s' % (v, full))

    def rd_reg(self, name):
        full, bits, sh = REGINFO[name]
        v = self.g_get64(full)
        if sh:
            t = self.t(); self.e('%s = lshr i64 %s, %d' % (t, v, sh)); v = t
        if bits == 64: return v
        t = self.t(); self.e('%s = trunc i64 %s to i%d' % (t, v, bits)); return t

    def wr_reg(self, name, val):
        full, bits, sh = REGINFO[name]
        if bits == 64:
            self.g_set64(full, val)
        elif bits == 32:
            t = self.t(); self.e('%s = zext i32 %s to i64' % (t, val)); self.g_set64(full, t)
        else:
            old = self.g_get64(full)
            z = self.t(); self.e('%s = zext i%d %s to i64' % (z, bits, val))
            if sh:
                z2 = self.t(); self.e('%s = shl i64 %s, %d' % (z2, z, sh)); z = z2
            m = ~(mask(bits) << sh) & mask(64)
            a = self.t(); self.e('%s = and i64 %s, %d' % (a, old, imm_s(m, 64)))
            o = self.t(); self.e('%s = or i64 %s, %s' % (o, a, z))
            self.g_set64(full, o)

    def xi(self, n): return n  # xmm index

    def x_get(self, n):
        t = self.t(); self.e('%s = load <4 x i32>, ptr %%X_%d' % (t, n)); return t

    def x_set(self, n, v): self.e('store <4 x i32> %s, ptr %%X_%d' % (v, n))

    # ymm の上位 128bit (Y_n)。VEX.128 の xmm 書込と vzeroupper でゼロ化する。関数入口ではゼロ (呼出側の上位は不明)。
    def y_get(self, n):
        t = self.t(); self.e('%s = load <4 x i32>, ptr %%Y_%d' % (t, n)); return t

    def y_set(self, n, v): self.e('store <4 x i32> %s, ptr %%Y_%d' % (v, n))

    # ---- ベクタ変換ヘルパ
    def v_to(self, v, ty):
        t = self.t(); self.e('%s = bitcast <4 x i32> %s to %s' % (t, v, ty)); return t

    def v_from(self, v, ty):
        t = self.t(); self.e('%s = bitcast %s %s to <4 x i32>' % (t, ty, v)); return t

    def v_f32(self, v):
        e = self.t(); self.e('%s = extractelement <4 x i32> %s, i32 0' % (e, v))
        f = self.t(); self.e('%s = bitcast i32 %s to float' % (f, e)); return f

    def v_f64(self, v):
        d2 = self.v_to(v, '<2 x double>')
        e = self.t(); self.e('%s = extractelement <2 x double> %s, i32 0' % (e, d2)); return e

    def v_with_f32(self, v, f):
        i = self.t(); self.e('%s = bitcast float %s to i32' % (i, f))
        r = self.t(); self.e('%s = insertelement <4 x i32> %s, i32 %s, i32 0' % (r, v, i)); return r

    def v_with_f64(self, v, d):
        l = self.v_to(v, '<2 x double>')
        r = self.t(); self.e('%s = insertelement <2 x double> %s, double %s, i32 0' % (r, l, d))
        return self.v_from(r, '<2 x double>')

    def v_zero_f32(self, f):
        i = self.t(); self.e('%s = bitcast float %s to i32' % (i, f))
        r = self.t(); self.e('%s = insertelement <4 x i32> zeroinitializer, i32 %s, i32 0' % (r, i)); return r

    def v_zero_f64(self, d):
        r = self.t(); self.e('%s = insertelement <2 x double> zeroinitializer, double %s, i32 0' % (r, d))
        return self.v_from(r, '<2 x double>')

    def v_i64(self, v, lane=0):
        q = self.v_to(v, '<2 x i64>')
        e = self.t(); self.e('%s = extractelement <2 x i64> %s, i32 %d' % (e, q, lane)); return e

    def v_with_i64(self, v, x, lane=0):
        q = self.v_to(v, '<2 x i64>')
        r = self.t(); self.e('%s = insertelement <2 x i64> %s, i64 %s, i32 %d' % (r, q, x, lane))
        return self.v_from(r, '<2 x i64>')

    def v_zero_i64(self, x):
        r = self.t(); self.e('%s = insertelement <2 x i64> zeroinitializer, i64 %s, i32 0' % (r, x))
        return self.v_from(r, '<2 x i64>')

    # ------------------------------------------------ メモリ/アドレス
    def img_ptr(self, va):
        return self.M.img_ptr_expr(va)

    def reg_val64(self, regid):
        name = self.cur.reg_name(regid)
        full, bits, sh = REGINFO[name]
        if bits != 64:
            # 32 ビットレジスタのアドレシング (0x67 address-size prefix 等)。64 bit スロットは
            # 32 bit 書込で必ずゼロ拡張されるため、そのまま親レジスタの値を読めば同一意味。
            return self.g_get64(full)
        return self.g_get64(full)

    def mem_addr(self, op):
        """メモリ operand → (ptr 式)。rip 相対でイメージ内 data は blob 定数ポインタ。"""
        m = op.mem
        if m.segment == X86_REG_GS:
            # TEB 読み (例: __chkstk の gs:[0x10] = StackBase)。wasm では @fa_teb セルにエミュレーション
            # (fa_teb_init が @fa_stack 先頭 = StackBase 相当を設定)。native は実 TEB を直接読むので影響なし。
            if m.base != X86_REG_INVALID or m.index != X86_REG_INVALID:
                raise Unsupported('gs base/index')
            if m.disp % 8 or not (0 <= m.disp < 128):
                raise Unsupported('gs disp %x' % m.disp)
            return 'getelementptr (i64, ptr @fa_teb, i64 %d)' % (m.disp // 8)
        if m.segment != 0:
            raise Unsupported('segment')
        if m.base == X86_REG_RIP:
            va = self.cur.address + self.cur.size + m.disp
            if self.img.in_image(va) and not self.img.is_text(va):
                self.M.need_data(va)
                return self.img_ptr(va)
            a = self.t(); self.e('%s = add i64 0, %d' % (a, imm_s(va, 64)))
        else:
            parts = []
            if m.base != X86_REG_INVALID:
                parts.append(self.reg_val64(m.base))
            if m.index != X86_REG_INVALID:
                ix = self.reg_val64(m.index)
                if m.scale != 1:
                    t = self.t(); self.e('%s = mul i64 %s, %d' % (t, ix, m.scale)); ix = t
                parts.append(ix)
            if m.disp or not parts:
                parts.append(str(imm_s(m.disp, 64)))
            self.note_base_rel(m)
            a = parts[0]
            if len(parts) == 1 and a.lstrip('-').isdigit():
                t = self.t(); self.e('%s = add i64 0, %s' % (t, a)); a = t
            for p in parts[1:]:
                t = self.t(); self.e('%s = add i64 %s, %s' % (t, a, p)); a = t
        p = self.t(); self.e('%s = inttoptr i64 %s to ptr' % (p, a)); return p

    def note_base_rel(self, m):
        # MSVC の「イメージベースを保持したレジスタ + RVA 即値」パターン ([r14+r15*8+0x13071a0] 等)
        if m.base != X86_REG_INVALID and m.base != X86_REG_RIP and 0x100000 <= m.disp < self.img.size_of_image \
                and not self.img.is_text(self.img.base + m.disp):
            self.M.need_data(self.img.base + m.disp)

    def lea_val(self, op):
        m = op.mem
        if m.segment != 0:
            raise Unsupported('segment')
        if m.base == X86_REG_RIP:
            va = self.cur.address + self.cur.size + m.disp
            if self.img.in_image(va) and not self.img.is_text(va):
                self.M.need_data(va)
                return 'ptrtoint (ptr %s to i64)' % self.img_ptr(va)
            return str(imm_s(va, 64))
        parts = []
        if m.base != X86_REG_INVALID:
            parts.append(self.reg_val64(m.base))
        if m.index != X86_REG_INVALID:
            ix = self.reg_val64(m.index)
            if m.scale != 1:
                t = self.t(); self.e('%s = mul i64 %s, %d' % (t, ix, m.scale)); ix = t
            parts.append(ix)
        if m.disp or not parts:
            parts.append(str(imm_s(m.disp, 64)))
        self.note_base_rel(m)
        a = parts[0]
        if len(parts) == 1:
            t = self.t(); self.e('%s = add i64 0, %s' % (t, a)); return t
        for p in parts[1:]:
            t = self.t(); self.e('%s = add i64 %s, %s' % (t, a, p)); a = t
        return a

    def ld(self, ptr, bits):
        t = self.t(); self.e('%s = load i%d, ptr %s, align 1' % (t, bits, ptr)); return t

    def st(self, ptr, val, bits): self.e('store i%d %s, ptr %s, align 1' % (bits, val, ptr))

    # ------------------------------------------------ operand 読み書き (整数)
    def rd(self, op, bits=None):
        bits = bits or op.size * 8
        if op.type == CS_OP_REG:
            return self.rd_reg(self.cur.reg_name(op.reg))
        if op.type == CS_OP_IMM:
            return str(imm_s(op.imm, bits))
        if op.type == CS_OP_MEM:
            return self.ld(self.mem_addr(op), bits)
        raise Unsupported('operand')

    def wr(self, op, val, bits=None):
        bits = bits or op.size * 8
        if op.type == CS_OP_REG:
            self.wr_reg(self.cur.reg_name(op.reg), val)
        elif op.type == CS_OP_MEM:
            self.st(self.mem_addr(op), val, bits)
        else:
            raise Unsupported('wr operand')

    # ------------------------------------------------ フラグ
    FL = ('CF', 'ZF', 'SF', 'OF', 'PF')

    def fset(self, name, v): self.e('store i1 %s, ptr %%F_%s' % (v, name))

    def fget(self, name):
        t = self.t(); self.e('%s = load i1, ptr %%F_%s' % (t, name)); return t

    def set_zsp(self, res, bits):
        z = self.t(); self.e('%s = icmp eq i%d %s, 0' % (z, bits, res)); self.fset('ZF', z)
        s = self.t(); self.e('%s = icmp slt i%d %s, 0' % (s, bits, res)); self.fset('SF', s)
        self.set_pf(res, bits)

    def set_pf(self, res, bits):
        lo = res
        if bits != 8:
            lo = self.t(); self.e('%s = trunc i%d %s to i8' % (lo, bits, res))
        pc = self.t(); self.e('%s = call i8 @llvm.ctpop.i8(i8 %s)' % (pc, lo))
        b = self.t(); self.e('%s = and i8 %s, 1' % (b, pc))
        p = self.t(); self.e('%s = icmp eq i8 %s, 0' % (p, b)); self.fset('PF', p)

    def cond(self, cc):
        """x86 条件名 → i1"""
        expr = JCC[cc]
        def F(n): return self.fget(n)
        def NOT(v):
            t = self.t(); self.e('%s = xor i1 %s, true' % (t, v)); return t
        def OP(o, a, b):
            t = self.t(); self.e('%s = %s i1 %s, %s' % (t, o, a, b)); return t
        if expr in ('OF', 'CF', 'ZF', 'SF', 'PF'): return F(expr)
        if expr.startswith('!') and expr[1:] in self.FL: return NOT(F(expr[1:]))
        if expr == 'CF|ZF': return OP('or', F('CF'), F('ZF'))
        if expr == '!CF&!ZF': return OP('and', NOT(F('CF')), NOT(F('ZF')))
        if expr == 'SF!=OF': return OP('xor', F('SF'), F('OF'))
        if expr == 'SF==OF': return NOT(OP('xor', F('SF'), F('OF')))
        if expr == 'ZF|SF!=OF': return OP('or', F('ZF'), OP('xor', F('SF'), F('OF')))
        if expr == '!ZF&SF==OF': return OP('and', NOT(F('ZF')), NOT(OP('xor', F('SF'), F('OF'))))
        raise Unsupported('cond ' + cc)

    # ------------------------------------------------ ALU
    def alu(self, kind, a, b, bits, cin=None, setflags=True):
        t = self.t()
        if kind in ('add', 'adc'):
            if kind == 'adc':
                c = self.t(); self.e('%s = zext i1 %s to i%d' % (c, cin, bits))
                s1 = self.t(); self.e('%s = add i%d %s, %s' % (s1, bits, a, b))
                self.e('%s = add i%d %s, %s' % (t, bits, s1, c))
            else:
                self.e('%s = add i%d %s, %s' % (t, bits, a, b))
            if setflags:
                cf = self.t(); self.e('%s = icmp ult i%d %s, %s' % (cf, bits, t, a))
                if kind == 'adc':
                    eq = self.t(); self.e('%s = icmp eq i%d %s, %s' % (eq, bits, t, a))
                    c2 = self.t(); self.e('%s = and i1 %s, %s' % (c2, eq, cin))
                    cf2 = self.t(); self.e('%s = or i1 %s, %s' % (cf2, cf, c2)); cf = cf2
                self.fset('CF', cf)
                x1 = self.t(); self.e('%s = xor i%d %s, %s' % (x1, bits, a, t))
                x2 = self.t(); self.e('%s = xor i%d %s, %s' % (x2, bits, b, t))
                x3 = self.t(); self.e('%s = and i%d %s, %s' % (x3, bits, x1, x2))
                of = self.t(); self.e('%s = icmp slt i%d %s, 0' % (of, bits, x3)); self.fset('OF', of)
        elif kind in ('sub', 'cmp', 'sbb'):
            if kind == 'sbb':
                c = self.t(); self.e('%s = zext i1 %s to i%d' % (c, cin, bits))
                s1 = self.t(); self.e('%s = sub i%d %s, %s' % (s1, bits, a, b))
                self.e('%s = sub i%d %s, %s' % (t, bits, s1, c))
            else:
                self.e('%s = sub i%d %s, %s' % (t, bits, a, b))
            if setflags:
                cf = self.t(); self.e('%s = icmp ult i%d %s, %s' % (cf, bits, a, b))
                if kind == 'sbb':
                    eq = self.t(); self.e('%s = icmp eq i%d %s, %s' % (eq, bits, a, b))
                    c2 = self.t(); self.e('%s = and i1 %s, %s' % (c2, eq, cin))
                    cf2 = self.t(); self.e('%s = or i1 %s, %s' % (cf2, cf, c2)); cf = cf2
                self.fset('CF', cf)
                x1 = self.t(); self.e('%s = xor i%d %s, %s' % (x1, bits, a, b))
                x2 = self.t(); self.e('%s = xor i%d %s, %s' % (x2, bits, a, t))
                x3 = self.t(); self.e('%s = and i%d %s, %s' % (x3, bits, x1, x2))
                of = self.t(); self.e('%s = icmp slt i%d %s, 0' % (of, bits, x3)); self.fset('OF', of)
        elif kind in ('and', 'or', 'xor', 'test'):
            op = {'and': 'and', 'test': 'and', 'or': 'or', 'xor': 'xor'}[kind]
            self.e('%s = %s i%d %s, %s' % (t, op, bits, a, b))
            if setflags:
                self.fset('CF', 'false'); self.fset('OF', 'false')
        else:
            raise Unsupported('alu ' + kind)
        if setflags:
            self.set_zsp(t, bits)
        return t

    def shift(self, kind, a, cnt, bits, cnt_imm):
        """shl/shr/sar/rol/ror。cnt は i8 値 or 即値 str。"""
        cm = 63 if bits == 64 else 31
        if bits < 32 and kind in ('shl', 'shr', 'sar'):
            # 8/16bit 非回転シフト: 32bit に拡張して実行 (LLVM では幅以上のシフト量が poison のため) し trunc
            ext = 'sext' if kind == 'sar' else 'zext'
            w = self.t(); self.e('%s = %s i%d %s to i32' % (w, ext, bits, a))
            r32 = self.shift(kind, w, cnt, 32, cnt_imm)
            if r32 is w: return a
            t = self.t(); self.e('%s = trunc i32 %s to i%d' % (t, r32, bits))
            self.set_zsp(t, bits)
            return t
        if bits < 32 and kind in ('rol', 'ror'):
            if cnt_imm is not None:
                cnt_imm = cnt_imm % bits
                if cnt_imm == 0: return a
            else:
                c8 = self.t(); self.e('%s = urem i8 %s, %d' % (c8, cnt, bits)); cnt = c8; cm = 255
        if cnt_imm is not None:
            c = cnt_imm & cm
            if c == 0:
                return a
            cv = str(c)
            cz = c
        else:
            ct = self.t(); self.e('%s = and i8 %s, %d' % (ct, cnt, cm)); cv = ct; cz = None
        # 幅合わせ
        def wide(x):
            if x.lstrip('-').isdigit(): return x
            if bits == 8: return x
            t = self.t(); self.e('%s = zext i8 %s to i%d' % (t, x, bits)); return t
        cw = wide(cv)
        t = self.t()
        if kind == 'shl': self.e('%s = shl i%d %s, %s' % (t, bits, a, cw))
        elif kind == 'shr': self.e('%s = lshr i%d %s, %s' % (t, bits, a, cw))
        elif kind == 'sar': self.e('%s = ashr i%d %s, %s' % (t, bits, a, cw))
        elif kind == 'rol': self.e('%s = call i%d @llvm.fshl.i%d(i%d %s, i%d %s, i%d %s)' % (t, bits, bits, bits, a, bits, a, bits, cw))
        elif kind == 'ror': self.e('%s = call i%d @llvm.fshr.i%d(i%d %s, i%d %s, i%d %s)' % (t, bits, bits, bits, a, bits, a, bits, cw))
        else: raise Unsupported(kind)
        # フラグ
        if kind in ('shl', 'shr', 'sar'):
            # CF = 最後に押し出されたビット
            if kind == 'shl':
                sh = self.t()
                if cz is not None: self.e('%s = sub i%d %d, %s' % (sh, bits, bits, cw)) if False else None
                bw = self.t(); self.e('%s = sub i%d %d, %s' % (bw, bits, bits, cw))
                x = self.t(); self.e('%s = lshr i%d %s, %s' % (x, bits, a, bw))
            else:
                one = self.t(); self.e('%s = sub i%d %s, 1' % (one, bits, cw))
                x = self.t()
                self.e('%s = %s i%d %s, %s' % (x, 'lshr' if kind == 'shr' else 'ashr', bits, a, one))
            cfn = self.t(); self.e('%s = trunc i%d %s to i1' % (cfn, bits, x))
            msb = self.t(); self.e('%s = icmp slt i%d %s, 0' % (msb, bits, t))
            if kind == 'shl':
                ofn = self.t(); self.e('%s = xor i1 %s, %s' % (ofn, msb, cfn))
            elif kind == 'shr':
                ofn = self.t(); self.e('%s = icmp slt i%d %s, 0' % (ofn, bits, a))
            else:
                ofn = 'false'
            zf = self.t(); self.e('%s = icmp eq i%d %s, 0' % (zf, bits, t))
            pf_lo = t
            if cz is not None:
                self.fset('CF', cfn); self.fset('OF', ofn); self.set_zsp(t, bits)
            else:
                nz = self.t(); self.e('%s = icmp ne i%d %s, 0' % (nz, bits, cw))
                for nm, new in (('CF', cfn), ('OF', ofn)):
                    old = self.fget(nm); sel = self.t(); self.e('%s = select i1 %s, i1 %s, i1 %s' % (sel, nz, new, old)); self.fset(nm, sel)
                oz = self.fget('ZF'); s1 = self.t(); self.e('%s = select i1 %s, i1 %s, i1 %s' % (s1, nz, zf, oz)); self.fset('ZF', s1)
                osf = self.fget('SF'); s2 = self.t(); self.e('%s = select i1 %s, i1 %s, i1 %s' % (s2, nz, msb, osf)); self.fset('SF', s2)
        else:  # rol/ror: CF のみ
            if kind == 'rol':
                cfn = self.t(); self.e('%s = trunc i%d %s to i1' % (cfn, bits, t))
            else:
                msb = self.t(); self.e('%s = icmp slt i%d %s, 0' % (msb, bits, t)); cfn = msb
            if cz is None:
                nz = self.t(); self.e('%s = icmp ne i%d %s, 0' % (nz, bits, cw))
                old = self.fget('CF'); sel = self.t(); self.e('%s = select i1 %s, i1 %s, i1 %s' % (sel, nz, cfn, old)); cfn = sel
            self.fset('CF', cfn)
        return t

    # ------------------------------------------------ 呼出
    def regs_args(self):
        a = []
        for r in ARG_G:
            a.append('i64 ' + self.g_get64(r))
        for k in range(4):
            a.append('<4 x i32> ' + ('zeroinitializer' if 'xmm_args_drop' in self.M.inject else self.x_get(k)))
        a.append('i64 ' + self.g_get64('rsp'))   # callee の初期 rsp (実機の retaddr push 相当を callee 側 -8 で再現)
        a.append('i64 ' + self.g_get64('rax'))   # callee の初期 rax (実機: void 呼出でも caller の rax は温存される)
        return ', '.join(a)

    def after_call(self, res):
        r = self.t(); self.e('%s = extractvalue {i64, <4 x i32>, <4 x i32>} %s, 0' % (r, res)); self.g_set64('rax', r)
        x = self.t(); self.e('%s = extractvalue {i64, <4 x i32>, <4 x i32>} %s, 1' % (x, res))
        if 'xmm_ret_drop' not in self.M.inject:
            self.x_set(0, x)
        y = self.t(); self.e('%s = extractvalue {i64, <4 x i32>, <4 x i32>} %s, 2' % (y, res))
        if 'xmm_ret_drop' not in self.M.inject and not self.M.no_xmm1_ret:
            self.x_set(1, y)   # 構造体戻り (2 x double) の第 2 レジスタ / 実機の xmm1 残留を再現

    def emit_call(self, i, tail=False):
        op = i.operands[0]
        res = self.t()
        if op.type == CS_OP_IMM:
            tgt = op.imm
            if tgt in self.M.maps:
                sym = self.M.maps[tgt]; self.M.mapped_used.add(sym)
                r = self.t()
                self.e('%s = call i64 @%s(i64 %s, i64 %s, i64 %s, i64 %s)' % (r, sym, *[self.g_get64(x) for x in ARG_G]))
                self.g_set64('rax', r)
                return
            sym = self.M.call_target(tgt, self)
            self.e('%s = call {i64, <4 x i32>, <4 x i32>} %s(%s)' % (res, sym, self.regs_args()))
        elif op.type == CS_OP_MEM and op.mem.base == X86_REG_RIP and \
                (i.address + i.size + op.mem.disp) in self.img.iat:
            va = i.address + i.size + op.mem.disp
            dll, nm = self.img.iat[va]
            self.M.imports.add((dll, nm)); self.M.iat_slots[va] = '%s!%s' % (dll, nm)
            r = self.t()
            self.e('%s = call i64 @win_%s_%s(i64 %s, i64 %s, i64 %s, i64 %s)' % (
                r, dll, re.sub(r'\W', '_', nm), *[self.g_get64(x) for x in ARG_G]))
            self.g_set64('rax', r)
            return
        else:
            # 間接 call
            if op.type == CS_OP_REG:
                tgt = self.rd_reg(i.reg_name(op.reg))
            else:
                tgt = self.ld(self.mem_addr(op), 64)
            self.M.icall_used = True
            if 'icall_drop' in self.M.inject:
                return
            if getattr(self.M, 'icall_site_dbg', False):
                self.e('call void @fa_icall_site(i64 %d)' % i.address)
            self.e('%s = call {i64, <4 x i32>, <4 x i32>} @fa_icall(i64 %s, %s)' % (res, tgt, self.regs_args()))
        self.after_call(res)

    def emit_ret(self):
        r = self.g_get64('rax'); x0 = self.x_get(0); x1 = self.x_get(1)
        a = self.t(); self.e('%s = insertvalue {i64, <4 x i32>, <4 x i32>} undef, i64 %s, 0' % (a, r))
        b = self.t(); self.e('%s = insertvalue {i64, <4 x i32>, <4 x i32>} %s, <4 x i32> %s, 1' % (b, a, x0))
        c = self.t(); self.e('%s = insertvalue {i64, <4 x i32>, <4 x i32>} %s, <4 x i32> %s, 2' % (c, b, x1))
        self.e('ret {i64, <4 x i32>, <4 x i32>} %s' % c)

    # ------------------------------------------------ 本体
    def lift(self):
        from mlift_ops import emit_insn
        self.decode()
        L = self.leaders(); self.leaders_cache = L
        body = []
        for bi, lv in enumerate(L):
            nxt_leader = L[bi + 1] if bi + 1 < len(L) else None
            self.lines.append('%s:' % self.lbl(lv))
            va = lv
            terminated = False
            while va in self.ins and (nxt_leader is None or va < nxt_leader):
                i = self.ins[va]; self.cur = i
                self.mn_hist[i.mnemonic] += 1
                self.lines.append('  ; %x: %s %s' % (va, i.mnemonic, i.op_str))
                self.emit_trace(va)
                if self.M.cov:
                    idx = self.M.cov_idx.setdefault(va, len(self.M.cov_idx))
                    self.e('store i8 1, ptr getelementptr (i8, ptr @fa_cov, i64 %d)' % idx)
                try:
                    term = emit_insn(self, i)
                except Unsupported as ex:
                    self.unsupported.append((va, i.mnemonic + ' ' + i.op_str + ' :: ' + str(ex)))
                    self.e('call void @llvm.trap()'); self.e('unreachable')
                    terminated = True
                    break
                va += i.size
                if term:
                    terminated = True
                    break
            if not terminated:
                if va in self.ins or va == self.end:
                    if va == self.end or va not in self.ins:
                        self.e('call void @llvm.trap()'); self.e('unreachable')
                    else:
                        self.e('br label %%%s' % self.lbl(va))
                else:
                    self.e('call void @llvm.trap()'); self.e('unreachable')
        self.lines.append('%s:' % self.lbl(self.end))
        self.e('call void @llvm.trap()'); self.e('unreachable')
        # 関数ヘッダ
        hdr = []
        name = '@f_%x' % self.begin
        link = '' if self.begin in self.M.exported else 'internal '
        hdr.append('define %s{i64, <4 x i32>, <4 x i32>} %s(i64 %%a_rcx, i64 %%a_rdx, i64 %%a_r8, i64 %%a_r9, '
                   '<4 x i32> %%a_x0, <4 x i32> %%a_x1, <4 x i32> %%a_x2, <4 x i32> %%a_x3, i64 %%a_sp, i64 %%a_rax) {' % (link, name))
        hdr.append('entry:')
        for r in G64:
            hdr.append('  %%R_%s = alloca i64' % r)
        for k in range(16):
            hdr.append('  %%X_%d = alloca <4 x i32>' % k)
            hdr.append('  %%Y_%d = alloca <4 x i32>' % k)
        for f in self.FL:
            hdr.append('  %%F_%s = alloca i1' % f)
        for r in G64:
            if r in ARG_G:
                hdr.append('  store i64 %%a_%s, ptr %%R_%s' % (r, r))
            elif r == 'rsp':
                # 実機: call が retaddr を push して callee 入口 rsp = caller rsp - 8。
                # rsp は共有スタック @fa_stack 上の連続アドレス (caller のスタック引数 [rsp+0x20..] が callee から見える)
                hdr.append('  %sp_e = sub i64 %a_sp, 8')
                hdr.append('  store i64 %sp_e, ptr %R_rsp')
            elif r == 'rax':
                # 実機: callee が触れない volatile rax は caller の値のまま (e.g. __security_check_cookie 越しに戻り値が生存)
                hdr.append('  store i64 %a_rax, ptr %R_rax')
            else:
                hdr.append('  store i64 0, ptr %%R_%s' % r)
        for k in range(16):
            hdr.append('  store <4 x i32> %s, ptr %%X_%d' % ('%%a_x%d' % k if k < 4 else 'zeroinitializer', k))
            hdr.append('  store <4 x i32> zeroinitializer, ptr %%Y_%d' % k)
        for f in self.FL:
            hdr.append('  store i1 false, ptr %%F_%s' % f)
        hdr.append('  br label %%%s' % self.lbl(self.begin))
        return '\n'.join(hdr + self.lines + ['}'])


class Module:
    def __init__(self, img, a):
        self.img = img
        self.md = Cs(CS_ARCH_X86, CS_MODE_64); self.md.detail = True
        self.exported = set(); self.stubs = set(a.stub); self.maps = {}
        self.icall_targets = set(); self.icall_used = False
        self.imports = set(); self.data_vas = set()
        self.lifted = {}; self.failed = {}; self.pending = []; self.seen = set()
        self.inject = set(a.inject); self.cov = a.cov; self.cov_idx = {}; self.ext_decl = {}; self.text_tables = {}; self.jump_tables = []; self.iat_slots = {}; self.mapped_used = set(); self.extents = {}; self.indirect_jmp = []
        self.no_xmm1_ret = bool(a.no_xmm1_ret)
        self.icall_site_dbg = bool(a.icall_site_dbg)
        self.trace_vas = set()
        for tr in (a.trace or []):
            lo, _, hi = tr.partition(':')
            lo = int(lo, 16); hi = int(hi, 16) if hi else lo
            self.trace_vas |= set(range(lo, hi + 1))
        self.pad = a.data_pad
        self.pokes = []
        for pk in a.poke:
            va, sz, val = pk.split(':')
            self.pokes.append((int(va, 16), int(sz), int(val, 16)))
        for m in a.map:
            va, sym = m.split('=')
            self.maps[int(va, 16)] = sym
        for v in a.icall:
            self.icall_targets.add(int(v, 16))

    def frame_size(self, fl):
        mx = 0
        for va in fl.order:
            i = fl.ins[va]
            if i.mnemonic == 'sub' and i.operands[0].type == CS_OP_REG and i.reg_name(i.operands[0].reg) == 'rsp' \
                    and i.operands[1].type == CS_OP_IMM:
                mx = max(mx, i.operands[1].imm)
        return (mx + 0x200 + 15) & ~15

    def need_data(self, va): self.data_vas.add(va)

    def need_intrinsic(self, *a): pass

    def text_table(self, va, cnt):
        key = (va, cnt)
        if key not in self.text_tables:
            self.text_tables[key] = '@jt_%x' % va
        return self.text_tables[key]

    def img_ptr_expr(self, va):
        return 'getelementptr (i8, ptr @fa_img_%d, i64 %d)' % (0, 0) if False else '@@IMG_%x@@' % va

    def call_target(self, tgt, fl):
        ext = self.img.func_extent(tgt, self.md) if self.img.is_text(tgt) else None
        if not ext:
            raise Unsupported('call to non-function/mid-function %x' % tgt)
        self.extents[tgt] = ext
        fl.calls.add(tgt)
        if tgt not in self.seen:
            self.seen.add(tgt); self.pending.append(tgt)
        return '@f_%x' % tgt

    def run(self, roots):
        for r in roots:
            self.extents[r] = self.img.func_extent(r, self.md)
            self.seen.add(r); self.pending.append(r)
        # --icall 指定 VA も lift 対象に seed する (FA-2c: vtable 間接 call 先の実関数を fa_icall switch に接続)
        for t in sorted(self.icall_targets):
            if t in self.seen:
                continue
            ext = self.img.func_extent(t, self.md) if self.img.is_text(t) else None
            if not ext:
                continue
            self.extents[t] = ext
            self.seen.add(t); self.pending.append(t)
        while self.pending:
            va = self.pending.pop()
            if va in self.stubs:
                continue
            b, e = self.extents.get(va) or self.img.func_of(va)
            fl = FnLifter(self, b, e)
            try:
                txt = fl.lift()
                self.lifted[va] = (txt, fl)
                if fl.unsupported:
                    self.failed[va] = fl.unsupported
            except Unsupported as ex:
                self.failed[va] = [(va, str(ex))]
            except Exception as ex:      # 予期せぬ形状 (非対応オペランド等) = 未 lift 関数として記録し
                self.failed[va] = [(va, 'EXC %s: %s' % (type(ex).__name__, ex))]
        return self

    def build(self, roots_spec):
        out = []
        out.append('target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128-f128:64-n32:64-S128-ni:1:10:20"')
        out.append('target triple = "wasm32-unknown-emscripten"')
        out.append('')
        out.append(PRELUDE)
        body = []
        for va in sorted(self.lifted):
            body.append(self.lifted[va][0])
        # stubs / 未 lift の callee
        called = set()
        for va, (txt, fl) in self.lifted.items():
            called |= fl.calls
        stubs = []
        for va in sorted(called):
            if va not in self.lifted:
                stubs.append('define internal {i64, <4 x i32>, <4 x i32>} @f_%x(i64 %%a, i64 %%b, i64 %%c, i64 %%d, <4 x i32> %%e, <4 x i32> %%f, <4 x i32> %%g, <4 x i32> %%h, i64 %%i, i64 %%j) noinline {\n'
                             '  call void @fa_stub_trap(i64 %d)\n  unreachable\n}' % (va, va))
        for sym in sorted(self.mapped_used):
            body.append('declare i64 @%s(i64, i64, i64, i64)' % sym)
        for dll, nm in sorted(self.imports):
            body.append('declare i64 @win_%s_%s(i64, i64, i64, i64)' % (dll, re.sub(r'\W', '_', nm)))
        body += stubs
        for (tva, cnt), sym in self.text_tables.items():
            vals = struct.unpack('<%dI' % cnt, self.img.read(tva, 4 * cnt))
            body.append('%s = internal constant [%d x i32] [%s]' % (sym, cnt, ', '.join('i32 %d' % v for v in vals)))
        body.append('@fa_stack = global [%d x i8] zeroinitializer, align 16' % STACK_BYTES)
        # TEB エミュレーション (gs:[0x10] = StackLimit = 0)。__chkstk は r10(Stack 目標) >= StackLimit で probe を
        # skip するため 0 を返せば probe 無効 (@fa_stack 1MB に収容前提)。fa_teb_init は各 wrapper 冒頭で呼ぶ。
        body.append('@fa_teb = global [16 x i64] zeroinitializer, align 16')
        body.append('define internal void @fa_teb_init() {\n'
                    '  ret void\n}')
        if self.trace_vas:
            body.append('@fa_trace = global [8100000 x i64] zeroinitializer, align 16')  # 100K rows x 81
            body.append('@fa_trace_n = global i64 0')
            body.append('define i64 @fa_trace_ptr() {\n  %p = ptrtoint ptr @fa_trace to i64\n  ret i64 %p\n}')
            body.append('define i64 @fa_trace_count() {\n  %p = load i64, ptr @fa_trace_n\n  ret i64 %p\n}')
        body.append(self.icall_fn())
        if self.cov:
            body.append('@fa_cov = global [%d x i8] zeroinitializer' % (len(self.cov_idx) + 8))
            body.append('define i64 @fa_cov_ptr() {\n  %p = ptrtoint ptr @fa_cov to i64\n  ret i64 %p\n}')
        body.append(self.wrappers(roots_spec))
        txt = '\n'.join(out + body)
        return self.patch_data(txt)

    def icall_fn(self):
        args = ('i64 %t, i64 %c, i64 %d, i64 %e, i64 %f, <4 x i32> %x0, <4 x i32> %x1, <4 x i32> %x2, <4 x i32> %x3, '
                'i64 %sp, i64 %rax0')
        L = ['define internal {i64, <4 x i32>, <4 x i32>} @fa_icall(%s) {' % args, 'entry:']
        # 間接呼出の解決対象 = **lift 済み全関数** (icall_targets はその部分集合)。実機の vtable/関数ポインタ
        # 経由は既知関数に必ず着地するため、未知 (host token / 未 lift) だけが host フォールバックに入る。
        targets = sorted(self.lifted)
        L.append('  switch i64 %t, label %host [')
        for t in targets:
            L.append('    i64 %d, label %%c_%x' % (t, t))
        L.append('  ]')
        for t in targets:
            L.append('c_%x:' % t)
            if self.img.is_text(t) and self.img.read(t, 2) == b'\xff\xe0':
                # 実機の CFG ディスパッチ stub (jmp rax): 間接呼出の実先着は rax → rax0 で再ディスパッチ
                L.append('  %%rd_%x = call {i64, <4 x i32>, <4 x i32>} @fa_icall(i64 %%rax0, i64 %%c, i64 %%d, i64 %%e, i64 %%f, '
                         '<4 x i32> %%x0, <4 x i32> %%x1, <4 x i32> %%x2, <4 x i32> %%x3, i64 %%sp, i64 %%rax0)' % t)
                L.append('  ret {i64, <4 x i32>, <4 x i32>} %%rd_%x' % t)
                continue
            L.append('  %%r_%x = call {i64, <4 x i32>, <4 x i32>} @f_%x(i64 %%c, i64 %%d, i64 %%e, i64 %%f, <4 x i32> %%x0, <4 x i32> %%x1, <4 x i32> %%x2, <4 x i32> %%x3, i64 %%sp, i64 %%rax0)' % (t, t))
            L.append('  ret {i64, <4 x i32>, <4 x i32>} %%r_%x' % t)
        L.append('host:')
        L.append('  %x0i = bitcast <4 x i32> %x0 to i128')
        L.append('  %x1i = bitcast <4 x i32> %x1 to i128')
        L.append('  %rax = call i64 @fa_host_icall(i64 %t, i64 %c, i64 %d, i64 %e, i64 %f, i128 %x0i, i128 %x1i)')
        L.append('  %xr = call i128 @fa_host_icall_xmm0()')
        L.append('  %xv = bitcast i128 %xr to <4 x i32>')
        L.append('  %s0 = insertvalue {i64, <4 x i32>, <4 x i32>} undef, i64 %rax, 0')
        L.append('  %s1 = insertvalue {i64, <4 x i32>, <4 x i32>} %s0, <4 x i32> %xv, 1')
        L.append('  %s2 = insertvalue {i64, <4 x i32>, <4 x i32>} %s1, <4 x i32> zeroinitializer, 2')
        L.append('  ret {i64, <4 x i32>, <4 x i32>} %s2')
        L.append('}')
        L.append('declare i64 @fa_host_icall(i64, i64, i64, i64, i64, i128, i128)')
        L.append('declare void @fa_icall_site(i64)')
        L.append('declare i128 @fa_host_icall_xmm0()')
        L.append('declare void @fa_stub_trap(i64)')
        return '\n'.join(L)

    def wrappers(self, roots_spec):
        """root ごとの JS/C 呼出可能 wrapper: fa_root_<va>(args...) 。sig は 'ret(arg,arg)'; 型 i64/i32/f32/f64。
        5 番目以降の引数は MS x64 のスタック引数として [rsp+0x20+8k] (8 byte slot) に store してから call する。"""
        L = []
        for va, sig in roots_spec:
            m = re.match(r'(\w+)\((.*)\)', sig)
            ret = m.group(1); args = [x for x in m.group(2).split(',') if x]
            ty = {'i64': 'i64', 'i32': 'i32', 'f32': 'float', 'f64': 'double', 'void': 'void'}
            ps = ', '.join('%s %%p%d' % (ty[a], k) for k, a in enumerate(args))
            L.append('define %s @fa_root_%x(%s) {' % (ty[ret], va, ps))
            L.append('  call void @fa_teb_init()')
            gv = {r: '0' for r in ARG_G}; xv = {k: 'zeroinitializer' for k in range(4)}
            pre = []
            for k, a in enumerate(args):
                if k < 4:
                    if a in ('i64', 'i32'):
                        r = ARG_G[k]
                        if a == 'i32':
                            pre.append('  %%z%d = zext i32 %%p%d to i64' % (k, k)); gv[r] = '%%z%d' % k
                        else:
                            gv[r] = '%%p%d' % k
                    else:
                        if a == 'f32':
                            pre.append('  %%b%d = bitcast float %%p%d to i32' % (k, k))
                            pre.append('  %%v%d = insertelement <4 x i32> zeroinitializer, i32 %%b%d, i32 0' % (k, k))
                        else:
                            pre.append('  %%b%d = bitcast double %%p%d to i64' % (k, k))
                            pre.append('  %%q%d = insertelement <2 x i64> zeroinitializer, i64 %%b%d, i32 0' % (k, k))
                            pre.append('  %%v%d = bitcast <2 x i64> %%q%d to <4 x i32>' % (k, k))
                        xv[k] = '%%v%d' % k
                else:
                    slot = k - 4
                    pre.append('  %%sp%d = add i64 %%top, %d' % (slot, 0x20 + 8 * slot))
                    pre.append('  %%sq%d = inttoptr i64 %%sp%d to ptr' % (slot, slot))
                    if a == 'i64':
                        pre.append('  store i64 %%p%d, ptr %%sq%d' % (k, slot))
                    elif a == 'i32':
                        pre.append('  %%sv%d = zext i32 %%p%d to i64' % (slot, k))
                        pre.append('  store i64 %%sv%d, ptr %%sq%d' % (slot, slot))
                    elif a == 'f64':
                        pre.append('  %%sv%d = bitcast double %%p%d to i64' % (slot, k))
                        pre.append('  store i64 %%sv%d, ptr %%sq%d' % (slot, slot))
                    else:  # f32 — MS x64 は float stack arg を 4 byte store (slot 上位 4B は未定義。callee は 4byte 読みが前提)
                        pre.append('  %%sv%d = bitcast float %%p%d to i32' % (slot, k))
                        pre.append('  store i32 %%sv%d, ptr %%sq%d' % (slot, slot))
            L.append('  %stk = ptrtoint ptr @fa_stack to i64')
            L.append('  %%top = add i64 %%stk, %d' % (STACK_BYTES - 0x100))   # root のスタック引数/shadow 分のへッドルーム
            L += pre
            L.append('  %%r = call {i64, <4 x i32>, <4 x i32>} @f_%x(i64 %s, i64 %s, i64 %s, i64 %s, <4 x i32> %s, <4 x i32> %s, <4 x i32> %s, <4 x i32> %s, i64 %%top, i64 0)' % (
                va, gv['rcx'], gv['rdx'], gv['r8'], gv['r9'], xv[0], xv[1], xv[2], xv[3]))
            if ret == 'void':
                L.append('  ret void')
            elif ret in ('i64', 'i32'):
                L.append('  %a = extractvalue {i64, <4 x i32>, <4 x i32>} %r, 0')
                if ret == 'i32':
                    L.append('  %a32 = trunc i64 %a to i32'); L.append('  ret i32 %a32')
                else:
                    L.append('  ret i64 %a')
            elif ret == 'f32':
                L.append('  %x = extractvalue {i64, <4 x i32>, <4 x i32>} %r, 1')
                L.append('  %e = extractelement <4 x i32> %x, i32 0')
                L.append('  %f = bitcast i32 %e to float'); L.append('  ret float %f')
            elif ret == 'f64':
                L.append('  %x = extractvalue {i64, <4 x i32>, <4 x i32>} %r, 1')
                L.append('  %q = bitcast <4 x i32> %x to <2 x i64>')
                L.append('  %e = extractelement <2 x i64> %q, i32 0')
                L.append('  %f = bitcast i64 %e to double'); L.append('  ret double %f')
            L.append('}')
        return '\n'.join(L)

    # ------------------------------------------------ data blob
    def patch_data(self, txt):
        vas = sorted(self.data_vas)
        pages = set()
        for va in vas:
            lo = (va - self.pad) & ~0xFFF
            hi = ((va + self.pad) + 0xFFF) & ~0xFFF
            p = lo
            while p < hi:
                if self.img.in_image(p) and not self.img.is_text(p):
                    pages.add(p)
                p += 0x1000
        first_sec = min(x[1] for x in self.img.sections)
        body_pages = sorted(p for p in pages if p >= first_sec)
        chunks = [[body_pages[0], body_pages[-1] + 0x1000]] if body_pages else []
        decl = []
        for k, (lo, hi) in enumerate(chunks):
            data = bytearray(self.img.read(lo, hi - lo))
            for pva, psz, pval in self.pokes:
                if lo <= pva and pva + psz <= hi:
                    data[pva - lo:pva - lo + psz] = pval.to_bytes(psz, 'little')
            data = bytes(data)
            esc = ''.join('\\%02X' % b for b in data)
            decl.append('@fa_img_%d = global [%d x i8] c"%s", align 4096' % (k, hi - lo, esc))
        self.chunks = chunks

        def sub(m):
            va = int(m.group(1), 16)      # 単一連続 blob: VA は blob 先頭からの線形オフセット (範囲外 = ヘッダ頁等は負オフセット, wasm32 では mod 2^32 で整合)
            return 'getelementptr (i8, ptr @fa_img_0, i64 %d)' % (va - chunks[0][0])
        txt = re.sub(r'@@IMG_([0-9a-f]+)@@', sub, txt)
        # fa_va2ptr (harness 用)
        L = ['define i64 @fa_va2ptr(i64 %va) {', 'entry:']
        for k, (lo, hi) in enumerate(chunks):
            L.append('  %%c%d = icmp uge i64 %%va, %d' % (k, lo))
            L.append('  %%d%d = icmp ult i64 %%va, %d' % (k, hi))
            L.append('  %%i%d = and i1 %%c%d, %%d%d' % (k, k, k))
            L.append('  br i1 %%i%d, label %%h%d, label %%n%d' % (k, k, k))
            L.append('h%d:' % k)
            L.append('  %%o%d = sub i64 %%va, %d' % (k, lo))
            L.append('  %%p%d = ptrtoint ptr @fa_img_%d to i64' % (k, k))
            L.append('  %%r%d = add i64 %%p%d, %%o%d' % (k, k, k))
            L.append('  ret i64 %%r%d' % k)
            L.append('n%d:' % k)
        L.append('  ret i64 0')
        L.append('}')
        return txt + '\n' + '\n'.join(decl) + '\n' + '\n'.join(L) + '\n'


PRELUDE = r'''
declare i8 @llvm.ctpop.i8(i8)
declare i32 @llvm.fshl.i32(i32, i32, i32)
declare i64 @llvm.fshl.i64(i64, i64, i64)
declare i32 @llvm.fshr.i32(i32, i32, i32)
declare i64 @llvm.fshr.i64(i64, i64, i64)
declare i16 @llvm.fshl.i16(i16, i16, i16)
declare i16 @llvm.fshr.i16(i16, i16, i16)
declare i8 @llvm.fshl.i8(i8, i8, i8)
declare i8 @llvm.fshr.i8(i8, i8, i8)
declare void @llvm.trap()
declare float @llvm.rint.f32(float)
declare double @llvm.rint.f64(double)
declare float @llvm.fma.f32(float, float, float)
declare double @llvm.fma.f64(double, double, double)
declare double @llvm.sqrt.f64(double)
declare float @llvm.sqrt.f32(float)
declare float @llvm.fabs.f32(float)
declare {i8, i1} @llvm.smul.with.overflow.i8(i8, i8)
declare {i16, i1} @llvm.smul.with.overflow.i16(i16, i16)
declare {i32, i1} @llvm.smul.with.overflow.i32(i32, i32)
declare {i64, i1} @llvm.smul.with.overflow.i64(i64, i64)
declare i32 @llvm.ctlz.i32(i32, i1)
declare i64 @llvm.ctlz.i64(i64, i1)
declare i32 @llvm.cttz.i32(i32, i1)
declare i64 @llvm.cttz.i64(i64, i1)
declare i32 @llvm.bswap.i32(i32)
declare i64 @llvm.bswap.i64(i64)
declare <4 x float> @llvm.sqrt.v4f32(<4 x float>)
declare <2 x double> @llvm.sqrt.v2f64(<2 x double>)
@fa_mxcsr = global i32 8064
define internal i32 @fa_cvt32(float %x, i1 %trunc) alwaysinline {
  %r = call float @llvm.rint.f32(float %x)
  %v = select i1 %trunc, float %x, float %r
  %lo = fcmp oge float %v, -2147483648.0
  %hi = fcmp olt float %v, 2147483648.0
  %ok = and i1 %lo, %hi
  %s = fptosi float %v to i32
  %o = select i1 %ok, i32 %s, i32 -2147483648
  ret i32 %o
}
define internal i32 @fa_cvt32d(double %x, i1 %trunc) alwaysinline {
  %r = call double @llvm.rint.f64(double %x)
  %v = select i1 %trunc, double %x, double %r
  %lo = fcmp oge double %v, -2147483648.0
  %hi = fcmp olt double %v, 2147483648.0
  %ok = and i1 %lo, %hi
  %s = fptosi double %v to i32
  %o = select i1 %ok, i32 %s, i32 -2147483648
  ret i32 %o
}
define internal i64 @fa_cvt64(float %x, i1 %trunc) alwaysinline {
  %r = call float @llvm.rint.f32(float %x)
  %v = select i1 %trunc, float %x, float %r
  %lo = fcmp oge float %v, -9223372036854775808.0
  %hi = fcmp olt float %v, 9223372036854775808.0
  %ok = and i1 %lo, %hi
  %s = fptosi float %v to i64
  %o = select i1 %ok, i64 %s, i64 -9223372036854775808
  ret i64 %o
}
define internal i64 @fa_cvt64d(double %x, i1 %trunc) alwaysinline {
  %r = call double @llvm.rint.f64(double %x)
  %v = select i1 %trunc, double %x, double %r
  %lo = fcmp oge double %v, -9223372036854775808.0
  %hi = fcmp olt double %v, 9223372036854775808.0
  %ok = and i1 %lo, %hi
  %s = fptosi double %v to i64
  %o = select i1 %ok, i64 %s, i64 -9223372036854775808
  ret i64 %o
}
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pe'); ap.add_argument('out')
    ap.add_argument('--root', action='append', default=[], help='VA[:sig] 例 0x180775220:void(i64,i64)')
    ap.add_argument('--stub', action='append', default=[], type=lambda x: int(x, 16))
    ap.add_argument('--map', action='append', default=[], help='VA=symbol (外部 C 関数へ置換)')
    ap.add_argument('--icall', action='append', default=[], help='間接 call 先として登録する VA')
    ap.add_argument('--icall-site-dbg', action='store_true', help='各間接 call 前に fa_icall_site(VA) を出す (デバッグ用)')
    ap.add_argument('--poke', action='append', default=[], help='VA:size:value(hex)  データ blob への初期値上書き (CRT 初期化済み状態の再現)')
    ap.add_argument('--inject', action='append', default=[], choices=['comis_noflags', 'xmm_args_drop', 'xmm_ret_drop', 'icall_drop', 'cmov_drop'],
                    help='RetDec 欠陥類型の故障注入 (ablation 用): lift の意味論をその類型だけ欠落させる')
    ap.add_argument('--cov', action='store_true', help='命令単位カバレッジ bitmap (@fa_cov, fa_cov_ptr()) を埋込')
    ap.add_argument('--no-xmm1-ret', action='store_true', help='xmm1 戻り伝搬を無効化 (実験用)')
    ap.add_argument('--trace', action='append', default=[], help='VA:VA (範囲) の命令前レジスタトレースを @fa_trace に埋込 (デバッグ用)')
    ap.add_argument('--data-pad', type=lambda x: int(x, 0), default=0x1000)
    ap.add_argument('--report')
    a = ap.parse_args()
    img = Image(a.pe)
    M = Module(img, a)
    roots = []; spec = []
    for r in a.root:
        va, _, sig = r.partition(':')
        va = int(va, 16); roots.append(va); M.exported.add(va)
        spec.append((va, sig or 'void(i64,i64)'))
    M.run(roots)
    txt = M.build(spec)
    open(a.out, 'w').write(txt)
    rep = {
        'lifted': len(M.lifted), 'failed': {('%x' % k): v for k, v in M.failed.items()},
        'bytes': sum(fl.end - fl.begin for _, (t, fl) in M.lifted.items()),
        'insns': sum(len(fl.order) for _, (t, fl) in M.lifted.items()),
        'imports': sorted('%s!%s' % x for x in M.imports),
        'mnemonics': dict(sum((fl.mn_hist for _, (t, fl) in M.lifted.items()), collections.Counter())),
        'data_chunks': [(hex(lo), hex(hi)) for lo, hi in M.chunks],
        'iat_slots': {hex(k): v for k, v in sorted(M.iat_slots.items())},
        'indirect_jmp_as_tailcall': [hex(x) for x in M.indirect_jmp],
        'jump_tables': [hex(x) for x in M.jump_tables],
        'funcs': {('%x' % k): {'size': fl.end - fl.begin, 'insns': len(fl.order), 'calls': sorted('%x' % c for c in fl.calls)} for k, (t, fl) in sorted(M.lifted.items())},
    }
    if a.cov:
        rep['cov_map'] = {('%x' % k): v for k, v in M.cov_idx.items()}
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1)
    print('mlift: lifted %d funcs / %d B / %d insns, failed(funcs with unsupported) %d, imports %d, data chunks %d' % (
        rep['lifted'], rep['bytes'], rep['insns'], len(M.failed), len(M.imports), len(M.chunks)))
    for k, v in M.failed.items():
        for va, why in v[:3]:
            print('  FAIL f_%x @%x: %s' % (k, va, why))


if __name__ == '__main__':
    import mlift
    mlift.main()
