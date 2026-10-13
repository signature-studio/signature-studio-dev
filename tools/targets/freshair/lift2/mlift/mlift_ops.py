"""mlift_ops.py — mlift の命令セマンティクス (整数 / SSE / AVX スカラ + 一部パック)。"""
import re
from capstone import CS_OP_REG, CS_OP_IMM, CS_OP_MEM
from capstone.x86 import X86_REG_RIP
from mlift import Unsupported, REGINFO, imm_s, mask, JCC


def xidx(fl, op):
    nm = fl.cur.reg_name(op.reg)
    m = re.match(r'xmm(\d+)$', nm)
    if not m:
        raise Unsupported('non-xmm reg ' + nm)
    return int(m.group(1))


def is_x(fl, op):
    return op.type == CS_OP_REG and fl.cur.reg_name(op.reg).startswith(('xmm', 'ymm'))


def vec_src(fl, op):
    if op.type == CS_OP_REG:
        return fl.x_get(xidx(fl, op))
    p = fl.mem_addr(op); t = fl.t(); fl.e('%s = load <4 x i32>, ptr %s, align 1' % (t, p)); return t


def f32_src(fl, op):
    if op.type == CS_OP_REG:
        return fl.v_f32(fl.x_get(xidx(fl, op)))
    p = fl.mem_addr(op); t = fl.t(); fl.e('%s = load float, ptr %s, align 1' % (t, p)); return t


def f64_src(fl, op):
    if op.type == CS_OP_REG:
        return fl.v_f64(fl.x_get(xidx(fl, op)))
    p = fl.mem_addr(op); t = fl.t(); fl.e('%s = load double, ptr %s, align 1' % (t, p)); return t


def i32_src(fl, op):
    if op.type == CS_OP_REG:
        nm = fl.cur.reg_name(op.reg)
        if nm.startswith('xmm'):
            v = fl.x_get(xidx(fl, op)); t = fl.t(); fl.e('%s = extractelement <4 x i32> %s, i32 0' % (t, v)); return t
        return fl.rd_reg(nm)
    return fl.ld(fl.mem_addr(op), 32)


def x3(fl, i):
    """(d, s1vec, s2op): VEX 3-op または legacy 2-op (s1=d)"""
    ops = i.operands
    if len(ops) == 3 and not (ops[2].type == CS_OP_IMM):
        return xidx(fl, ops[0]), fl.x_get(xidx(fl, ops[1])), ops[2]
    return xidx(fl, ops[0]), fl.x_get(xidx(fl, ops[0])), ops[1]


def fbin(fl, op, a, b, ty):
    t = fl.t()
    if op in ('add', 'sub', 'mul', 'div'):
        fl.e('%s = f%s %s %s, %s' % (t, op, ty, a, b))
    elif op in ('max', 'min'):
        c = fl.t(); fl.e('%s = fcmp %s %s %s, %s' % (c, 'ogt' if op == 'max' else 'olt', ty, a, b))
        fl.e('%s = select i1 %s, %s %s, %s %s' % (t, c, ty, a, ty, b))
    else:
        raise Unsupported(op)
    return t


def vcmp_flags(fl, a, b, ty):
    un = fl.t(); fl.e('%s = fcmp uno %s %s, %s' % (un, ty, a, b))
    lt = fl.t(); fl.e('%s = fcmp olt %s %s, %s' % (lt, ty, a, b))
    eq = fl.t(); fl.e('%s = fcmp oeq %s %s, %s' % (eq, ty, a, b))
    cf = fl.t(); fl.e('%s = or i1 %s, %s' % (cf, un, lt))
    zf = fl.t(); fl.e('%s = or i1 %s, %s' % (zf, un, eq))
    fl.fset('CF', cf); fl.fset('ZF', zf); fl.fset('PF', un); fl.fset('OF', 'false'); fl.fset('SF', 'false')


def packed_binop(fl, kind, a, b, ty):
    """a,b: <4 x i32> -> <4 x i32>。ty: <4 x float> / <2 x double> / <4 x i32> / <2 x i64>..."""
    A = fl.v_to(a, ty) if ty != '<4 x i32>' else a
    B = fl.v_to(b, ty) if ty != '<4 x i32>' else b
    t = fl.t()
    if kind in ('add', 'sub', 'mul', 'div') and 'float' in ty or kind in ('add', 'sub', 'mul', 'div') and 'double' in ty:
        fl.e('%s = f%s %s %s, %s' % (t, kind, ty, A, B))
    elif kind in ('add', 'sub'):
        fl.e('%s = %s %s %s, %s' % (t, kind, ty, A, B))
    elif kind in ('max', 'min'):
        c = fl.t(); fl.e('%s = fcmp %s %s %s, %s' % (c, 'ogt' if kind == 'max' else 'olt', ty, A, B))
        n = ty.split(' ')[0]
        fl.e('%s = select %s %s, %s %s, %s %s' % (t, n.replace('<', '<') + ' x i1>', c, ty, A, ty, B)) if False else \
            fl.e('%s = select <%s x i1> %s, %s %s, %s %s' % (t, ty[1], c, ty, A, ty, B))
    else:
        raise Unsupported('packed ' + kind)
    return fl.v_from(t, ty) if ty != '<4 x i32>' else t


def emit_insn(fl, i, ):
    m = i.mnemonic
    if m.startswith('lock '):
        m = m[5:]
    if m.startswith('rep'):
        inner = m.split(' ', 1)[1] if ' ' in m else ''
        if inner in ('stosb', 'stosw', 'stosd', 'stosq'):
            return h_rep_str(fl, i, 'stos', inner)
        if inner in ('movsb', 'movsw', 'movsd', 'movsq'):
            return h_rep_str(fl, i, 'movs', inner)
        raise Unsupported('rep prefix ' + m)
    ops = i.operands
    O = ops
    h = HANDLERS.get(m)
    if h is not None:
        return h(fl, i, m, O)
    # 条件分岐 / cmov / setcc
    if m[0] == 'j' and m[1:] in JCC:
        return h_jcc(fl, i, m, O)
    if m.startswith('cmov') and m[4:] in JCC:
        return h_cmov(fl, i, m, O)
    if m.startswith('set') and m[3:] in JCC:
        c = fl.cond(m[3:]); z = fl.t(); fl.e('%s = zext i1 %s to i8' % (z, c)); fl.wr(O[0], z, 8); return False
    # VEX / SSE
    r = emit_sse(fl, i, m, O)
    if r is None:
        raise Unsupported('mnemonic ' + m)
    return r


# ------------------------------------------------------------ 制御
def h_nop(fl, i, m, O): return False


def h_rep_str(fl, i, op, kind):
    """rep stos{b,w,d,q} / rep movs{b,w,d,q}: while(rcx){ 1 要素 [rdi]=al/ax/eax/rax (movs は [rdi]=[rsi]); rdi+=n; (rsi+=n); rcx-- }
    (DF=0 前提, cld/std は未対応)。要素逐次処理なので rdi/rsi の重なりも命令仕様どおり。

    rcx はループ頭で **毎回ロード** する (ループ持ち回し変数)。初期値を一度だけ読んで
    `rcx0-1` を毎回書くと rcx0>1 のとき終了条件が成立せず無限ループになり OOB する
    (FA-2c で実測: __chkstk 内の rep stosb → wasm memory access out of bounds)。"""
    bits = {'b': 8, 'w': 16, 'd': 32, 'q': 64}[kind[-1]]
    nb = bits // 8
    vreg = {8: 'al', 16: 'ax', 32: 'eax', 64: 'rax'}[bits]
    loop = fl.tmp_lbl(); done = fl.tmp_lbl()
    r0 = fl.t(); fl.e('%s = load i64, ptr %%R_rcx' % r0)
    z0 = fl.t(); fl.e('%s = icmp eq i64 %s, 0' % (z0, r0))
    fl.e('br i1 %s, label %%%s, label %%%s' % (z0, done, loop))
    fl.lines.append('%s:' % loop)
    if op == 'movs':
        src = fl.g_get64('rsi')
        sp = fl.t(); fl.e('%s = inttoptr i64 %s to ptr' % (sp, src))
        val = fl.ld(sp, bits)
        s2 = fl.t(); fl.e('%s = add i64 %s, %d' % (s2, src, nb)); fl.g_set64('rsi', s2)
    else:
        val = fl.rd_reg(vreg)
    dst = fl.g_get64('rdi')
    p = fl.t(); fl.e('%s = inttoptr i64 %s to ptr' % (p, dst))
    fl.st(p, val, bits)
    d2 = fl.t(); fl.e('%s = add i64 %s, %d' % (d2, dst, nb))
    fl.g_set64('rdi', d2)
    rc = fl.t(); fl.e('%s = load i64, ptr %%R_rcx' % rc)   # 現在値 (ループ持ち回し)
    c2 = fl.t(); fl.e('%s = sub i64 %s, 1' % (c2, rc))
    fl.g_set64('rcx', c2)
    z2 = fl.t(); fl.e('%s = icmp eq i64 %s, 0' % (z2, c2))
    fl.e('br i1 %s, label %%%s, label %%%s' % (z2, done, loop))
    fl.lines.append('%s:' % done)
    return False


def h_trap(fl, i, m, O):
    fl.e('call void @llvm.trap()'); fl.e('unreachable'); return True


def h_ret(fl, i, m, O):
    fl.emit_ret(); return True


def h_call(fl, i, m, O):
    fl.emit_call(i); return False


def h_jmp(fl, i, m, O):
    op = O[0]
    if op.type == CS_OP_IMM:
        tgt = op.imm
        if fl.begin <= tgt < fl.end:
            fl.e('br label %%%s' % fl.lbl(tgt)); return True
        fl.emit_call(i); fl.emit_ret(); return True      # tail call
    if op.type == CS_OP_MEM and op.mem.base == X86_REG_RIP and (i.address + i.size + op.mem.disp) in fl.img.iat:
        fl.emit_call(i); fl.emit_ret(); return True      # IAT thunk (jmp [iat])
    # MSVC jump table: `mov r32,[B+idx*4+TBL]; add R,B; jmp R` (B = イメージベース) → 関数内全 leader への switch に展開
    if op.type == CS_OP_REG:
        R = fl.cur.reg_name(op.reg)
        pos = fl.order.index(i.address)
        Bn = None
        for k in range(pos - 1, max(pos - 8, -1), -1):
            pi = fl.ins[fl.order[k]]
            if pi.mnemonic == 'add' and pi.operands[0].type == CS_OP_REG and pi.operands[1].type == CS_OP_REG \
                    and pi.reg_name(pi.operands[0].reg) == R:
                Bn = pi.reg_name(pi.operands[1].reg); break
        if Bn is not None:
            fl.M.jump_tables.append(i.address)
            rv = fl.rd_reg(R); bv = fl.rd_reg(Bn)
            rva = fl.t(); fl.e('%s = sub i64 %s, %s' % (rva, rv, bv))
            va = fl.t(); fl.e('%s = add i64 %s, %d' % (va, rva, fl.img.base))
            cases = ' '.join('i64 %d, label %%%s' % (lv, fl.lbl(lv)) for lv in fl.leaders_cache if lv != fl.begin)
            fl.e('switch i64 %s, label %%jt_trap_%x [ %s ]' % (va, i.address, cases))
            fl.lines.append('jt_trap_%x:' % i.address)
            fl.e('call void @llvm.trap()'); fl.e('unreachable')
            return True
    # 非 IAT の間接 jmp: 関数ポインタ経由 tail call とみなす
    fl.M.indirect_jmp.append(i.address)
    fl.emit_call(i); fl.emit_ret(); return True


def h_jcc(fl, i, m, O):
    c = fl.cond(m[1:])
    tgt = O[0].imm
    nxt = i.address + i.size
    if not (fl.begin <= tgt < fl.end):       # 条件付き tail call
        tl = 'tc_%x' % i.address
        fl.e('br i1 %s, label %%%s, label %%%s' % (c, tl, fl.lbl(nxt)))
        fl.lines.append('%s:' % tl)
        fl.emit_call(i); fl.emit_ret()
        return True
    fl.e('br i1 %s, label %%%s, label %%%s' % (c, fl.lbl(tgt), fl.lbl(nxt)))
    return True


def h_cmov(fl, i, m, O):
    if 'cmov_drop' in fl.M.inject:
        return False
    bits = O[0].size * 8
    c = fl.cond(m[4:])
    a = fl.rd(O[0], bits); b = fl.rd(O[1], bits)
    t = fl.t(); fl.e('%s = select i1 %s, i%d %s, i%d %s' % (t, c, bits, b, bits, a))
    fl.wr(O[0], t, bits); return False


# ------------------------------------------------------------ 移動
def text_table_operand(fl, op):
    """mov r32,[B+idx*4+disp] で img.base+disp が .text 内 (jump table が .text に埋込まれた形) か判定"""
    if op.type != CS_OP_MEM: return False
    m = op.mem
    return m.base != 0 and m.base != X86_REG_RIP and m.index != 0 and m.scale == 4 and m.disp >= 0x100000 \
        and fl.img.is_text(fl.img.base + m.disp)


def h_mov(fl, i, m, O):
    bits = O[0].size * 8
    if bits == 32 and text_table_operand(fl, O[1]):
        # .text 内 jump table: blob に text は入れないので, 表を IR 定数配列化して idx で引く (idx は +4 倍された添字)
        mm = O[1].mem; tva = fl.img.base + mm.disp
        cnt = 64
        pos = fl.order.index(i.address)
        for k in range(pos - 1, max(pos - 16, -1), -1):
            pi = fl.ins[fl.order[k]]
            if pi.mnemonic == 'cmp' and len(pi.operands) == 2 and pi.operands[1].type == CS_OP_IMM:
                cnt = pi.operands[1].imm + 1; break
        sym = fl.M.text_table(tva, cnt)
        idx = fl.reg_val64(mm.index)
        p = fl.t(); fl.e('%s = getelementptr [%d x i32], ptr %s, i64 0, i64 %s' % (p, cnt, sym, idx))
        v = fl.ld(p, 32); fl.wr(O[0], v, 32); return False
    v0 = None
    v = fl.rd(O[1], bits)
    fl.wr(O[0], v, bits); return False


def h_movzx(fl, i, m, O):
    sb = O[1].size * 8; db = O[0].size * 8
    v = fl.rd(O[1], sb)
    t = fl.t(); fl.e('%s = zext i%d %s to i%d' % (t, sb, v, db)); fl.wr(O[0], t, db); return False


def h_movsx(fl, i, m, O):
    sb = O[1].size * 8; db = O[0].size * 8
    v = fl.rd(O[1], sb)
    t = fl.t(); fl.e('%s = sext i%d %s to i%d' % (t, sb, v, db)); fl.wr(O[0], t, db); return False


def h_lea(fl, i, m, O):
    v = fl.lea_val(O[1]); bits = O[0].size * 8
    if bits != 64:
        t = fl.t(); fl.e('%s = trunc i64 %s to i%d' % (t, v, bits)); v = t
    fl.wr(O[0], v, bits); return False


def h_push(fl, i, m, O):
    v = fl.rd(O[0], 64)
    sp = fl.g_get64('rsp'); n = fl.t(); fl.e('%s = sub i64 %s, 8' % (n, sp)); fl.g_set64('rsp', n)
    p = fl.t(); fl.e('%s = inttoptr i64 %s to ptr' % (p, n)); fl.st(p, v, 64); return False


def h_pop(fl, i, m, O):
    sp = fl.g_get64('rsp'); p = fl.t(); fl.e('%s = inttoptr i64 %s to ptr' % (p, sp))
    v = fl.ld(p, 64); n = fl.t(); fl.e('%s = add i64 %s, 8' % (n, sp)); fl.g_set64('rsp', n)
    fl.wr(O[0], v, 64); return False


def h_xchg(fl, i, m, O):
    bits = O[0].size * 8
    a = fl.rd(O[0], bits); b = fl.rd(O[1], bits)
    fl.wr(O[0], b, bits); fl.wr(O[1], a, bits); return False


def h_cdqe(fl, i, m, O):
    v = fl.rd_reg('eax'); t = fl.t(); fl.e('%s = sext i32 %s to i64' % (t, v)); fl.g_set64('rax', t); return False


def h_cdq(fl, i, m, O):
    v = fl.rd_reg('eax'); t = fl.t(); fl.e('%s = ashr i32 %s, 31' % (t, v)); fl.wr_reg('edx', t); return False


def h_cqo(fl, i, m, O):
    v = fl.g_get64('rax'); t = fl.t(); fl.e('%s = ashr i64 %s, 63' % (t, v)); fl.g_set64('rdx', t); return False


# ------------------------------------------------------------ ALU
def h_alu(fl, i, m, O):
    bits = O[0].size * 8
    a = fl.rd(O[0], bits); b = fl.rd(O[1], bits)
    cin = fl.fget('CF') if m in ('adc', 'sbb') else None
    if m == 'xor' and O[0].type == CS_OP_REG and O[1].type == CS_OP_REG and O[0].reg == O[1].reg:
        r = fl.alu('xor', a, b, bits)
    else:
        r = fl.alu(m, a, b, bits, cin)
    if m not in ('cmp', 'test'):
        fl.wr(O[0], r, bits)
    return False


def h_incdec(fl, i, m, O):
    bits = O[0].size * 8
    a = fl.rd(O[0], bits)
    cf = fl.fget('CF')
    r = fl.alu('add' if m == 'inc' else 'sub', a, '1', bits)
    fl.fset('CF', cf)     # inc/dec は CF 不変
    fl.wr(O[0], r, bits); return False


def h_neg(fl, i, m, O):
    bits = O[0].size * 8
    a = fl.rd(O[0], bits)
    r = fl.alu('sub', '0', a, bits)
    nz = fl.t(); fl.e('%s = icmp ne i%d %s, 0' % (nz, bits, a)); fl.fset('CF', nz)
    fl.wr(O[0], r, bits); return False


def h_not(fl, i, m, O):
    bits = O[0].size * 8
    a = fl.rd(O[0], bits); t = fl.t(); fl.e('%s = xor i%d %s, -1' % (t, bits, a)); fl.wr(O[0], t, bits); return False


def h_shift(fl, i, m, O):
    bits = O[0].size * 8
    a = fl.rd(O[0], bits)
    if len(O) == 1:
        cnt, imm = None, 1
    elif O[1].type == CS_OP_IMM:
        cnt, imm = None, O[1].imm & 0xff
    else:
        cnt, imm = fl.rd_reg('cl'), None
    r = fl.shift(m, a, cnt, bits, imm)
    fl.wr(O[0], r, bits); return False


def h_rcr(fl, i, m, O):
    bits = O[0].size * 8
    if not (len(O) == 2 and O[1].type == CS_OP_IMM and O[1].imm == 1):
        raise Unsupported('rcr count != 1')
    a = fl.rd(O[0], bits); cf = fl.fget('CF')
    newcf = fl.t(); fl.e('%s = trunc i%d %s to i1' % (newcf, bits, a))
    s = fl.t(); fl.e('%s = lshr i%d %s, 1' % (s, bits, a))
    c = fl.t(); fl.e('%s = zext i1 %s to i%d' % (c, cf, bits))
    sh = fl.t(); fl.e('%s = shl i%d %s, %d' % (sh, bits, c, bits - 1))
    r = fl.t(); fl.e('%s = or i%d %s, %s' % (r, bits, s, sh))
    msb_old = fl.t(); fl.e('%s = icmp slt i%d %s, 0' % (msb_old, bits, a))
    of = fl.t(); fl.e('%s = xor i1 %s, %s' % (of, cf, msb_old))
    fl.fset('CF', newcf); fl.fset('OF', of)
    fl.wr(O[0], r, bits); return False


def h_imul(fl, i, m, O):
    if len(O) == 1:
        return h_mul(fl, i, 'imul', O)
    bits = O[0].size * 8
    if len(O) == 2:
        a = fl.rd(O[0], bits); b = fl.rd(O[1], bits)
    else:
        a = fl.rd(O[1], bits); b = fl.rd(O[2], bits)
    t = fl.t(); fl.e('%s = call {i%d, i1} @llvm.smul.with.overflow.i%d(i%d %s, i%d %s)' % (t, bits, bits, bits, a, bits, b))
    r = fl.t(); fl.e('%s = extractvalue {i%d, i1} %s, 0' % (r, bits, t))
    o = fl.t(); fl.e('%s = extractvalue {i%d, i1} %s, 1' % (o, bits, t))
    fl.fset('CF', o); fl.fset('OF', o); fl.set_zsp(r, bits)
    fl.M.need_intrinsic('llvm.smul.with.overflow.i%d' % bits)
    fl.wr(O[0], r, bits); return False


def h_mul(fl, i, m, O):
    bits = O[0].size * 8
    sign = (m == 'imul')
    a = fl.rd_reg({64: 'rax', 32: 'eax', 16: 'ax', 8: 'al'}[bits]); b = fl.rd(O[0], bits)
    ext = 'sext' if sign else 'zext'
    wa = fl.t(); fl.e('%s = %s i%d %s to i%d' % (wa, ext, bits, a, bits * 2))
    wb = fl.t(); fl.e('%s = %s i%d %s to i%d' % (wb, ext, bits, b, bits * 2))
    p = fl.t(); fl.e('%s = mul i%d %s, %s' % (p, bits * 2, wa, wb))
    lo = fl.t(); fl.e('%s = trunc i%d %s to i%d' % (lo, bits * 2, p, bits))
    sh = fl.t(); fl.e('%s = lshr i%d %s, %d' % (sh, bits * 2, p, bits))
    hi = fl.t(); fl.e('%s = trunc i%d %s to i%d' % (hi, bits * 2, sh, bits))
    if bits == 8:
        raise Unsupported('mul8')
    fl.wr_reg({64: 'rax', 32: 'eax', 16: 'ax'}[bits], lo)
    fl.wr_reg({64: 'rdx', 32: 'edx', 16: 'dx'}[bits], hi)
    if sign:
        s = fl.t(); fl.e('%s = ashr i%d %s, %d' % (s, bits, lo, bits - 1))
        c = fl.t(); fl.e('%s = icmp ne i%d %s, %s' % (c, bits, hi, s))
    else:
        c = fl.t(); fl.e('%s = icmp ne i%d %s, 0' % (c, bits, hi))
    fl.fset('CF', c); fl.fset('OF', c); return False


def h_div(fl, i, m, O):
    bits = O[0].size * 8
    sign = (m == 'idiv')
    if bits == 8:
        raise Unsupported('div8')
    ra, rd_ = {64: ('rax', 'rdx'), 32: ('eax', 'edx'), 16: ('ax', 'dx')}[bits]
    lo = fl.rd_reg(ra); hi = fl.rd_reg(rd_); d = fl.rd(O[0], bits)
    ext = 'sext' if sign else 'zext'
    W = bits * 2
    zl = fl.t(); fl.e('%s = zext i%d %s to i%d' % (zl, bits, lo, W))
    zh = fl.t(); fl.e('%s = zext i%d %s to i%d' % (zh, bits, hi, W))
    sh = fl.t(); fl.e('%s = shl i%d %s, %d' % (sh, W, zh, bits))
    n = fl.t(); fl.e('%s = or i%d %s, %s' % (n, W, sh, zl))
    dd = fl.t(); fl.e('%s = %s i%d %s to i%d' % (dd, ext, bits, d, W))
    q = fl.t(); fl.e('%s = %s i%d %s, %s' % (q, 'sdiv' if sign else 'udiv', W, n, dd))
    r = fl.t(); fl.e('%s = %s i%d %s, %s' % (r, 'srem' if sign else 'urem', W, n, dd))
    qt = fl.t(); fl.e('%s = trunc i%d %s to i%d' % (qt, W, q, bits))
    rt = fl.t(); fl.e('%s = trunc i%d %s to i%d' % (rt, W, r, bits))
    fl.wr_reg(ra, qt); fl.wr_reg(rd_, rt); return False


def h_bt(fl, i, m, O):
    bits = O[0].size * 8
    if O[0].type == CS_OP_MEM and O[1].type != CS_OP_IMM:
        raise Unsupported('bt mem,reg')
    a = fl.rd(O[0], bits)
    if O[1].type == CS_OP_IMM:
        k = str(O[1].imm & (bits - 1))
    else:
        kk = fl.rd(O[1], bits)
        k = fl.t(); fl.e('%s = and i%d %s, %d' % (k, bits, kk, bits - 1))
    sh = fl.t(); fl.e('%s = lshr i%d %s, %s' % (sh, bits, a, k))
    cf = fl.t(); fl.e('%s = trunc i%d %s to i1' % (cf, bits, sh)); fl.fset('CF', cf)
    if m != 'bt':
        one = fl.t(); fl.e('%s = shl i%d 1, %s' % (one, bits, k))
        if m == 'bts':
            r = fl.t(); fl.e('%s = or i%d %s, %s' % (r, bits, a, one))
        elif m == 'btr':
            nm = fl.t(); fl.e('%s = xor i%d %s, -1' % (nm, bits, one))
            r = fl.t(); fl.e('%s = and i%d %s, %s' % (r, bits, a, nm))
        else:
            r = fl.t(); fl.e('%s = xor i%d %s, %s' % (r, bits, a, one))
        fl.wr(O[0], r, bits)
    return False


def h_bsr(fl, i, m, O):
    bits = O[0].size * 8
    s = fl.rd(O[1], bits); old = fl.rd(O[0], bits)
    z = fl.t(); fl.e('%s = icmp eq i%d %s, 0' % (z, bits, s)); fl.fset('ZF', z)
    if m == 'bsr':
        l = fl.t(); fl.e('%s = call i%d @llvm.ctlz.i%d(i%d %s, i1 false)' % (l, bits, bits, bits, s))
        r = fl.t(); fl.e('%s = sub i%d %d, %s' % (r, bits, bits - 1, l))
        fl.M.need_intrinsic('llvm.ctlz.i%d' % bits)
    else:
        r = fl.t(); fl.e('%s = call i%d @llvm.cttz.i%d(i%d %s, i1 false)' % (r, bits, bits, bits, s))
        fl.M.need_intrinsic('llvm.cttz.i%d' % bits)
    sel = fl.t(); fl.e('%s = select i1 %s, i%d %s, i%d %s' % (sel, z, bits, old, bits, r))
    fl.wr(O[0], sel, bits); return False


def h_xadd(fl, i, m, O):
    bits = O[0].size * 8
    a = fl.rd(O[0], bits); b = fl.rd(O[1], bits)
    r = fl.alu('add', a, b, bits)
    fl.wr(O[1], a, bits); fl.wr(O[0], r, bits); return False


def h_cmpxchg(fl, i, m, O):
    bits = O[0].size * 8
    ra = {64: 'rax', 32: 'eax', 16: 'ax', 8: 'al'}[bits]
    acc = fl.rd_reg(ra); dst = fl.rd(O[0], bits); src = fl.rd(O[1], bits)
    fl.alu('cmp', acc, dst, bits)
    eq = fl.fget('ZF')
    nd = fl.t(); fl.e('%s = select i1 %s, i%d %s, i%d %s' % (nd, eq, bits, src, bits, dst))
    na = fl.t(); fl.e('%s = select i1 %s, i%d %s, i%d %s' % (na, eq, bits, acc, bits, dst))
    fl.wr(O[0], nd, bits); fl.wr_reg(ra, na); return False


def h_bswap(fl, i, m, O):
    bits = O[0].size * 8
    a = fl.rd(O[0], bits); t = fl.t(); fl.e('%s = call i%d @llvm.bswap.i%d(i%d %s)' % (t, bits, bits, bits, a))
    fl.M.need_intrinsic('llvm.bswap.i%d' % bits)
    fl.wr(O[0], t, bits); return False


HANDLERS = {
    'nop': h_nop, 'pause': h_nop, 'lfence': h_nop, 'sfence': h_nop, 'mfence': h_nop, 'vzeroupper': h_nop, 'endbr64': h_nop,
    'prefetcht0': h_nop, 'prefetchnta': h_nop, 'prefetcht1': h_nop, 'prefetcht2': h_nop, 'prefetchw': h_nop,
    'int3': h_trap, 'ud2': h_trap, 'int': h_trap, 'hlt': h_trap,
    'ret': h_ret, 'call': h_call, 'jmp': h_jmp,
    'mov': h_mov, 'movabs': h_mov, 'movzx': h_movzx, 'movsx': h_movsx, 'movsxd': h_movsx, 'lea': h_lea,
    'push': h_push, 'pop': h_pop, 'xchg': h_xchg, 'cdqe': h_cdqe, 'cdq': h_cdq, 'cqo': h_cqo,
    'add': h_alu, 'sub': h_alu, 'adc': h_alu, 'sbb': h_alu, 'and': h_alu, 'or': h_alu, 'xor': h_alu, 'cmp': h_alu, 'test': h_alu,
    'inc': h_incdec, 'dec': h_incdec, 'neg': h_neg, 'not': h_not,
    'shl': h_shift, 'shr': h_shift, 'sar': h_shift, 'rol': h_shift, 'ror': h_shift, 'sal': h_shift, 'rcr': h_rcr,
    'imul': h_imul, 'mul': h_mul, 'div': h_div, 'idiv': h_div,
    'bt': h_bt, 'bts': h_bt, 'btr': h_bt, 'btc': h_bt, 'bsr': h_bsr, 'bsf': h_bsr,
    'xadd': h_xadd, 'cmpxchg': h_cmpxchg, 'bswap': h_bswap,
}


# ------------------------------------------------------------ SSE / AVX
SCALAR_OPS = {'add', 'sub', 'mul', 'div', 'max', 'min'}


def emit_sse(fl, i, m, O):
    vex = m.startswith('v') and m not in ('vzeroupper',)
    b = m[1:] if vex else m
    # ---- FMA
    mf = re.match(r'vf(n?)(madd|msub)(132|213|231)(s[sd])$', m)
    if mf:
        neg, kind, order, sz = mf.groups()
        ty = 'float' if sz == 'ss' else 'double'
        d = xidx(fl, O[0]); dv = fl.x_get(d)
        get = f32_src if ty == 'float' else f64_src
        val = (lambda v: fl.v_f32(v)) if ty == 'float' else (lambda v: fl.v_f64(v))
        A = val(dv); B = val(fl.x_get(xidx(fl, O[1]))) if O[1].type == CS_OP_REG else get(fl, O[1]); C = get(fl, O[2]) if O[2].type == CS_OP_MEM else val(fl.x_get(xidx(fl, O[2])))
        # Intel 順: op0=d(A), op1=B, op2=C
        if order == '213':   x, y, z = B, A, C
        elif order == '132': x, y, z = A, C, B
        else:                x, y, z = B, C, A
        if neg:
            nx = fl.t(); fl.e('%s = fneg %s %s' % (nx, ty, x)); x = nx
        if kind == 'msub':
            nz = fl.t(); fl.e('%s = fneg %s %s' % (nz, ty, z)); z = nz
        r = fl.t(); fl.e('%s = call %s @llvm.fma.%s(%s %s, %s %s, %s %s)' % (r, ty, 'f32' if ty == 'float' else 'f64', ty, x, ty, y, ty, z))
        out = fl.v_with_f32(dv, r) if ty == 'float' else fl.v_with_f64(dv, r)
        fl.x_set(d, out); return False

    # ---- 128bit 移動
    if b in ('movaps', 'movapd', 'movdqa', 'movdqu', 'movups', 'movupd', 'movntps', 'movntdq', 'movntpd', 'lddqu'):
        if O[0].type == CS_OP_REG:
            fl.x_set(xidx(fl, O[0]), vec_src(fl, O[1]))
        else:
            v = fl.x_get(xidx(fl, O[1])); p = fl.mem_addr(O[0])
            fl.e('store <4 x i32> %s, ptr %s, align 1' % (v, p))
        return False
    if b == 'movss':
        if O[0].type == CS_OP_MEM:
            f = fl.v_f32(fl.x_get(xidx(fl, O[1]))); p = fl.mem_addr(O[0])
            fl.e('store float %s, ptr %s, align 1' % (f, p)); return False
        d = xidx(fl, O[0])
        if O[-1].type == CS_OP_MEM:
            fl.x_set(d, fl.v_zero_f32(f32_src(fl, O[-1])))
        else:
            base = fl.x_get(xidx(fl, O[1])) if len(O) == 3 else fl.x_get(d)
            fl.x_set(d, fl.v_with_f32(base, fl.v_f32(fl.x_get(xidx(fl, O[-1]))))); return False
        return False
    if b == 'movsd':
        if O[0].type == CS_OP_MEM:
            f = fl.v_f64(fl.x_get(xidx(fl, O[1]))); p = fl.mem_addr(O[0])
            fl.e('store double %s, ptr %s, align 1' % (f, p)); return False
        d = xidx(fl, O[0])
        if O[-1].type == CS_OP_MEM:
            fl.x_set(d, fl.v_zero_f64(f64_src(fl, O[-1])))
        else:
            base = fl.x_get(xidx(fl, O[1])) if len(O) == 3 else fl.x_get(d)
            fl.x_set(d, fl.v_with_f64(base, fl.v_f64(fl.x_get(xidx(fl, O[-1]))))); return False
        return False
    if b == 'movd':
        if is_x(fl, O[0]):
            v = i32_src(fl, O[1]); t = fl.t()
            fl.e('%s = insertelement <4 x i32> zeroinitializer, i32 %s, i32 0' % (t, v)); fl.x_set(xidx(fl, O[0]), t)
        else:
            v = i32_src(fl, O[1]); fl.wr(O[0], v, 32)
        return False
    if b == 'movq':
        if is_x(fl, O[0]):
            if O[1].type == CS_OP_REG and fl.cur.reg_name(O[1].reg).startswith('xmm'):
                v = fl.v_i64(fl.x_get(xidx(fl, O[1])))
            else:
                v = fl.rd(O[1], 64)
            fl.x_set(xidx(fl, O[0]), fl.v_zero_i64(v))
        else:
            v = fl.v_i64(fl.x_get(xidx(fl, O[1]))); fl.wr(O[0], v, 64)
        return False
    if b in ('movlps', 'movlpd', 'movhps', 'movhpd'):
        lane = 0 if b.startswith('movl') else 1
        if O[0].type == CS_OP_MEM:
            v = fl.v_i64(fl.x_get(xidx(fl, O[1])), lane); fl.st(fl.mem_addr(O[0]), v, 64)
        else:
            d = xidx(fl, O[0]); src = O[-1]
            x = fl.ld(fl.mem_addr(src), 64)
            base = fl.x_get(xidx(fl, O[1])) if len(O) == 3 else fl.x_get(d)
            fl.x_set(d, fl.v_with_i64(base, x, lane))
        return False
    if b in ('movlhps', 'movhlps'):
        d = xidx(fl, O[0]); s = fl.x_get(xidx(fl, O[-1]))
        base = fl.x_get(xidx(fl, O[1])) if len(O) == 3 else fl.x_get(d)
        if b == 'movlhps':
            x = fl.v_i64(s, 0); fl.x_set(d, fl.v_with_i64(base, x, 1))
        else:
            x = fl.v_i64(s, 1); fl.x_set(d, fl.v_with_i64(base, x, 0))
        return False

    # ---- スカラ算術
    ms = re.match(r'(add|sub|mul|div|max|min)(s[sd])$', b)
    if ms:
        op, sz = ms.groups(); ty = 'float' if sz == 'ss' else 'double'
        d, s1, s2 = x3(fl, i)
        a = fl.v_f32(s1) if ty == 'float' else fl.v_f64(s1)
        c = f32_src(fl, s2) if ty == 'float' else f64_src(fl, s2)
        r = fbin(fl, op, a, c, ty)
        fl.x_set(d, fl.v_with_f32(s1, r) if ty == 'float' else fl.v_with_f64(s1, r)); return False
    if b in ('sqrtss', 'sqrtsd'):
        ty = 'float' if b == 'sqrtss' else 'double'
        d, s1, s2 = x3(fl, i)
        c = f32_src(fl, s2) if ty == 'float' else f64_src(fl, s2)
        r = fl.t(); fl.e('%s = call %s @llvm.sqrt.%s(%s %s)' % (r, ty, 'f32' if ty == 'float' else 'f64', ty, c))
        fl.x_set(d, fl.v_with_f32(s1, r) if ty == 'float' else fl.v_with_f64(s1, r)); return False
    # ---- パック算術
    mp = re.match(r'(add|sub|mul|div|max|min)(p[sd])$', b)
    if mp:
        op, sz = mp.groups(); ty = '<4 x float>' if sz == 'ps' else '<2 x double>'
        d, s1, s2 = x3(fl, i)
        fl.x_set(d, packed_binop(fl, op, s1, vec_src(fl, s2), ty)); return False
    if b in ('sqrtps', 'sqrtpd'):
        ty = '<4 x float>' if b == 'sqrtps' else '<2 x double>'
        src = fl.v_to(vec_src(fl, O[-1]), ty); t = fl.t()
        fl.e('%s = call %s @llvm.sqrt.%s(%s %s)' % (t, ty, 'v4f32' if 'float' in ty else 'v2f64', ty, src))
        fl.M.need_intrinsic('llvm.sqrt.%s' % ('v4f32' if 'float' in ty else 'v2f64'), ty)
        fl.x_set(xidx(fl, O[0]), fl.v_from(t, ty)); return False
    # ---- 論理
    if b in ('andps', 'andpd', 'orps', 'orpd', 'xorps', 'xorpd', 'pand', 'por', 'pxor', 'andnps', 'andnpd', 'pandn'):
        d, s1, s2 = x3(fl, i)
        v2 = vec_src(fl, s2)
        op = 'and' if b.startswith(('and', 'pand')) and 'n' not in b[3:5] else None
        if b in ('andnps', 'andnpd', 'pandn'):
            n = fl.t(); fl.e('%s = xor <4 x i32> %s, <i32 -1, i32 -1, i32 -1, i32 -1>' % (n, s1))
            t = fl.t(); fl.e('%s = and <4 x i32> %s, %s' % (t, n, v2))
        else:
            o = 'and' if b in ('andps', 'andpd', 'pand') else ('or' if b in ('orps', 'orpd', 'por') else 'xor')
            t = fl.t(); fl.e('%s = %s <4 x i32> %s, %s' % (t, o, s1, v2))
        fl.x_set(d, t); return False
    # ---- 整数パック算術
    mi = re.match(r'p(add|sub)([bwdq])$', b)
    if mi:
        op, w = mi.groups(); ty = {'b': '<16 x i8>', 'w': '<8 x i16>', 'd': '<4 x i32>', 'q': '<2 x i64>'}[w]
        d, s1, s2 = x3(fl, i)
        A = fl.v_to(s1, ty) if w != 'd' else s1; B = fl.v_to(vec_src(fl, s2), ty) if w != 'd' else vec_src(fl, s2)
        t = fl.t(); fl.e('%s = %s %s %s, %s' % (t, op, ty, A, B))
        fl.x_set(d, fl.v_from(t, ty) if w != 'd' else t); return False
    mq = re.match(r'p(sll|srl|sra)([wdq])$', b)
    if mq:
        op, w = mq.groups(); ty = {'w': '<8 x i16>', 'd': '<4 x i32>', 'q': '<2 x i64>'}[w]
        n = {'w': 8, 'd': 4, 'q': 2}[w]; bits = {'w': 16, 'd': 32, 'q': 64}[w]
        ops = O
        if len(O) == 3: d = xidx(fl, O[0]); src = fl.x_get(xidx(fl, O[1])); cnt = O[2]
        else: d = xidx(fl, O[0]); src = fl.x_get(d); cnt = O[1]
        A = fl.v_to(src, ty) if w != 'd' else src
        if cnt.type == CS_OP_IMM:
            c = cnt.imm & 0xff
            if c >= bits:
                if op == 'sra': c = bits - 1
                else:
                    z = fl.t(); fl.e('%s = xor %s %s, %s' % (z, ty, A, A)); fl.x_set(d, fl.v_from(z, ty) if w != 'd' else z); return False
            cs = str(c)
        else:
            cv = fl.v_i64(vec_src(fl, cnt), 0)
            ge = fl.t(); fl.e('%s = icmp uge i64 %s, %d' % (ge, cv, bits))
            cs0 = fl.t(); fl.e('%s = select i1 %s, i64 %d, i64 %s' % (cs0, ge, bits - 1 if op == 'sra' else 0, cv))
            cs = fl.t(); fl.e('%s = trunc i64 %s to i%d' % (cs, cs0, bits))
            if op != 'sra':
                # >= bits は 0 になるよう後で select
                pass
        sp = fl.t()
        if cnt.type == CS_OP_IMM:
            splat = '<%s>' % ', '.join(['i%d %s' % (bits, cs)] * n)
        else:
            ins = fl.t(); fl.e('%s = insertelement %s undef, i%d %s, i32 0' % (ins, ty, bits, cs))
            splat = fl.t(); fl.e('%s = shufflevector %s %s, %s undef, <%d x i32> zeroinitializer' % (splat, ty, ins, ty, n))
        opn = {'sll': 'shl', 'srl': 'lshr', 'sra': 'ashr'}[op]
        r = fl.t(); fl.e('%s = %s %s %s, %s' % (r, opn, ty, A, splat))
        if cnt.type != CS_OP_IMM and op != 'sra':
            cvv = fl.v_i64(vec_src(fl, cnt), 0)
            ge = fl.t(); fl.e('%s = icmp uge i64 %s, %d' % (ge, cvv, bits))
            zero = 'zeroinitializer'
            r2 = fl.t(); fl.e('%s = select i1 %s, %s %s, %s %s' % (r2, ge, ty, zero, ty, r)); r = r2
        fl.x_set(d, fl.v_from(r, ty) if w != 'd' else r); return False
    if b in ('psrldq', 'pslldq'):
        d = xidx(fl, O[0]); src = fl.x_get(xidx(fl, O[1] if len(O) == 3 else O[0]))
        n = O[-1].imm & 0xff
        A = fl.v_to(src, '<16 x i8>')
        if n > 15: n = 16
        idx = []
        for k in range(16):
            j = k + n if b == 'psrldq' else k - n
            idx.append(j if 0 <= j < 16 else 16)
        mask_ = ', '.join('i32 %d' % x for x in idx)
        r = fl.t(); fl.e('%s = shufflevector <16 x i8> %s, <16 x i8> zeroinitializer, <16 x i32> <%s>' % (r, A, mask_))
        fl.x_set(d, fl.v_from(r, '<16 x i8>')); return False
    if b == 'pshufd':
        d = xidx(fl, O[0]); src = vec_src(fl, O[1]); imm = O[2].imm & 0xff
        idx = ', '.join('i32 %d' % ((imm >> (2 * k)) & 3) for k in range(4))
        r = fl.t(); fl.e('%s = shufflevector <4 x i32> %s, <4 x i32> undef, <4 x i32> <%s>' % (r, src, idx))
        fl.x_set(d, r); return False
    mc = re.match(r'pcmpeq([bd])$', b)
    if mc:
        w = mc.group(1); ty, n = {'b': ('<16 x i8>', 16), 'd': ('<4 x i32>', 4)}[w]
        d, s1, s2 = x3(fl, i)
        A = fl.v_to(s1, ty); B = fl.v_to(vec_src(fl, s2), ty)
        c = fl.t(); fl.e('%s = icmp eq %s %s, %s' % (c, ty, A, B))
        s = fl.t(); fl.e('%s = sext <%d x i1> %s to %s' % (s, n, c, ty))
        fl.x_set(d, fl.v_from(s, ty)); return False
    if b in ('punpckldq', 'unpcklps'):
        d, s1, s2 = x3(fl, i)
        r = fl.t(); fl.e('%s = shufflevector <4 x i32> %s, <4 x i32> %s, <4 x i32> <i32 0, i32 4, i32 1, i32 5>' % (r, s1, vec_src(fl, s2)))
        fl.x_set(d, r); return False
    if b in ('punpckhdq', 'unpckhps'):
        d, s1, s2 = x3(fl, i)
        r = fl.t(); fl.e('%s = shufflevector <4 x i32> %s, <4 x i32> %s, <4 x i32> <i32 2, i32 6, i32 3, i32 7>' % (r, s1, vec_src(fl, s2)))
        fl.x_set(d, r); return False
    if b in ('punpcklqdq', 'unpcklpd'):
        d, s1, s2 = x3(fl, i)
        r = fl.t(); fl.e('%s = shufflevector <4 x i32> %s, <4 x i32> %s, <4 x i32> <i32 0, i32 1, i32 4, i32 5>' % (r, s1, vec_src(fl, s2)))
        fl.x_set(d, r); return False
    if b in ('punpckhqdq', 'unpckhpd'):
        d, s1, s2 = x3(fl, i)
        r = fl.t(); fl.e('%s = shufflevector <4 x i32> %s, <4 x i32> %s, <4 x i32> <i32 2, i32 3, i32 6, i32 7>' % (r, s1, vec_src(fl, s2)))
        fl.x_set(d, r); return False
    if b == 'punpcklbw':
        d, s1, s2 = x3(fl, i)
        A = fl.v_to(s1, '<16 x i8>'); B = fl.v_to(vec_src(fl, s2), '<16 x i8>')
        idx = []
        for k in range(8): idx += [k, 16 + k]
        r = fl.t(); fl.e('%s = shufflevector <16 x i8> %s, <16 x i8> %s, <16 x i32> <%s>' % (r, A, B, ', '.join('i32 %d' % x for x in idx)))
        fl.x_set(d, fl.v_from(r, '<16 x i8>')); return False
    if b in ('shufps', 'shufpd'):
        d, s1, s2 = x3(fl, i) if len(O) == 3 and not vex else (xidx(fl, O[0]), fl.x_get(xidx(fl, O[1] if vex else O[0])), O[-2] if vex else O[1])
        imm = O[-1].imm & 0xff
        B = vec_src(fl, s2)
        if b == 'shufps':
            idx = [imm & 3, (imm >> 2) & 3, 4 + ((imm >> 4) & 3), 4 + ((imm >> 6) & 3)]
        else:
            lo = imm & 1; hi = (imm >> 1) & 1
            idx = [2 * lo, 2 * lo + 1, 4 + 2 * hi, 4 + 2 * hi + 1]
        r = fl.t(); fl.e('%s = shufflevector <4 x i32> %s, <4 x i32> %s, <4 x i32> <%s>' % (r, s1, B, ', '.join('i32 %d' % x for x in idx)))
        fl.x_set(d, r); return False

    # ---- 比較 (cmpXXps/pd/ss/sd, cmpps imm)
    PRED = {'eq': 0, 'lt': 1, 'le': 2, 'unord': 3, 'neq': 4, 'nlt': 5, 'nle': 6, 'ord': 7}
    FPR = {0: 'oeq', 1: 'olt', 2: 'ole', 3: 'uno', 4: 'une', 5: 'uge', 6: 'ugt', 7: 'ord'}
    mc = re.match(r'cmp(eq|lt|le|unord|neq|nlt|nle|ord)?(p[sd]|s[sd])$', b)
    if mc:
        pn, sz = mc.groups()
        pred = PRED[pn] if pn else O[-1].imm & 7
        if sz[0] == 'p':
            ty = '<4 x float>' if sz == 'ps' else '<2 x double>'; it = '<4 x i32>' if sz == 'ps' else '<2 x i64>'
            d, s1, s2 = x3(fl, i) if (len(O) == 3 and pn) or (len(O) == 4) or not pn else (xidx(fl, O[0]), fl.x_get(xidx(fl, O[0])), O[1])
            A = fl.v_to(s1, ty); B = fl.v_to(vec_src(fl, s2), ty)
            c = fl.t(); fl.e('%s = fcmp %s %s %s, %s' % (c, FPR[pred], ty, A, B))
            n = 4 if sz == 'ps' else 2
            r = fl.t(); fl.e('%s = sext <%d x i1> %s to %s' % (r, n, c, it))
            fl.x_set(d, fl.v_from(r, it) if sz != 'ps' else r)
        else:
            ty = 'float' if sz == 'ss' else 'double'; bits = 32 if sz == 'ss' else 64
            d = xidx(fl, O[0]); s1 = fl.x_get(xidx(fl, O[1])) if (len(O) == 4 or (pn and len(O) == 3)) and vex else fl.x_get(d)
            s2 = O[-1] if not pn else O[-1]
            if not pn: s2 = O[-2]
            A = fl.v_f32(s1) if ty == 'float' else fl.v_f64(s1)
            Bv = f32_src(fl, s2) if ty == 'float' else f64_src(fl, s2)
            c = fl.t(); fl.e('%s = fcmp %s %s %s, %s' % (c, FPR[pred], ty, A, Bv))
            z = fl.t(); fl.e('%s = sext i1 %s to i%d' % (z, c, bits))
            if ty == 'float':
                zz = fl.t(); fl.e('%s = insertelement <4 x i32> %s, i32 %s, i32 0' % (zz, s1, z)); fl.x_set(d, zz)
            else:
                q = fl.v_to(s1, '<2 x i64>'); zz = fl.t(); fl.e('%s = insertelement <2 x i64> %s, i64 %s, i32 0' % (zz, q, z)); fl.x_set(d, fl.v_from(zz, '<2 x i64>'))
        return False
    if b == 'blendvpd' or b == 'blendvps':
        d = xidx(fl, O[0]); ty = '<2 x double>' if b == 'blendvpd' else '<4 x float>'; it = '<2 x i64>' if b == 'blendvpd' else '<4 x i32>'
        n = 2 if b == 'blendvpd' else 4; bits = 64 if n == 2 else 32
        D = fl.x_get(d); S_ = vec_src(fl, O[1]); M_ = fl.x_get(0)
        Mi = fl.v_to(M_, it) if n == 2 else M_
        neg = fl.t(); fl.e('%s = icmp slt %s %s, zeroinitializer' % (neg, it, Mi))
        Di = fl.v_to(D, it) if n == 2 else D; Si = fl.v_to(S_, it) if n == 2 else S_
        r = fl.t(); fl.e('%s = select <%d x i1> %s, %s %s, %s %s' % (r, n, neg, it, Si, it, Di))
        fl.x_set(d, fl.v_from(r, it) if n == 2 else r); return False
    if b == 'pmuludq':
        d, s1, s2 = x3(fl, i)
        A = fl.v_to(s1, '<2 x i64>'); B = fl.v_to(vec_src(fl, s2), '<2 x i64>')
        am = fl.t(); fl.e('%s = and <2 x i64> %s, <i64 4294967295, i64 4294967295>' % (am, A))
        bm = fl.t(); fl.e('%s = and <2 x i64> %s, <i64 4294967295, i64 4294967295>' % (bm, B))
        r = fl.t(); fl.e('%s = mul <2 x i64> %s, %s' % (r, am, bm)); fl.x_set(d, fl.v_from(r, '<2 x i64>')); return False
    if b == 'pcmpeqw':
        d, s1, s2 = x3(fl, i)
        A = fl.v_to(s1, '<8 x i16>'); B = fl.v_to(vec_src(fl, s2), '<8 x i16>')
        c = fl.t(); fl.e('%s = icmp eq <8 x i16> %s, %s' % (c, A, B))
        r = fl.t(); fl.e('%s = sext <8 x i1> %s to <8 x i16>' % (r, c)); fl.x_set(d, fl.v_from(r, '<8 x i16>')); return False
    if b == 'pshuflw':
        d = xidx(fl, O[0]); src = fl.v_to(vec_src(fl, O[1]), '<8 x i16>'); imm = O[2].imm & 0xff
        idx = [(imm >> (2 * k)) & 3 for k in range(4)] + [4, 5, 6, 7]
        r = fl.t(); fl.e('%s = shufflevector <8 x i16> %s, <8 x i16> undef, <8 x i32> <%s>' % (r, src, ', '.join('i32 %d' % x for x in idx)))
        fl.x_set(d, fl.v_from(r, '<8 x i16>')); return False
    if b == 'pextrw':
        v = fl.v_to(fl.x_get(xidx(fl, O[1])), '<8 x i16>'); e = fl.t(); fl.e('%s = extractelement <8 x i16> %s, i32 %d' % (e, v, O[2].imm & 7))
        z = fl.t(); fl.e('%s = zext i16 %s to i32' % (z, e)); fl.wr(O[0], z, 32) if O[0].size == 4 else fl.wr(O[0], z, 32); return False
    if b == 'pinsrw':
        d = xidx(fl, O[0]); v = fl.v_to(fl.x_get(d), '<8 x i16>'); src = fl.rd(O[1], 32) if O[1].type != CS_OP_MEM else fl.ld(fl.mem_addr(O[1]), 16)
        s16 = fl.t(); fl.e('%s = trunc i32 %s to i16' % (s16, src)) if O[1].type != CS_OP_MEM else None
        val = s16 if O[1].type != CS_OP_MEM else src
        r = fl.t(); fl.e('%s = insertelement <8 x i16> %s, i16 %s, i32 %d' % (r, v, val, O[2].imm & 7)); fl.x_set(d, fl.v_from(r, '<8 x i16>')); return False
    if b == 'pmovmskb':
        v = fl.v_to(fl.x_get(xidx(fl, O[1])), '<16 x i8>')
        neg = fl.t(); fl.e('%s = icmp slt <16 x i8> %s, zeroinitializer' % (neg, v))
        m_ = fl.t(); fl.e('%s = bitcast <16 x i1> %s to i16' % (m_, neg))
        z = fl.t(); fl.e('%s = zext i16 %s to i32' % (z, m_)); fl.wr(O[0], z, 32); return False
    if b in ('movmskpd', 'movmskps'):
        n = 2 if b == 'movmskpd' else 4; bits = 64 if n == 2 else 32
        v = fl.v_to(fl.x_get(xidx(fl, O[1])), '<2 x i64>' if n == 2 else '<4 x i32>')
        neg = fl.t(); fl.e('%s = icmp slt <%d x i%d> %s, zeroinitializer' % (neg, n, bits, v))
        m_ = fl.t(); fl.e('%s = bitcast <%d x i1> %s to i%d' % (m_, n, neg, n))
        z = fl.t(); fl.e('%s = zext i%d %s to i32' % (z, n, m_)); fl.wr(O[0], z, 32); return False
    # ---- 変換
    if b in ('cvtss2sd', 'cvtsd2ss'):
        d, s1, s2 = x3(fl, i)
        if b == 'cvtss2sd':
            f = f32_src(fl, s2); r = fl.t(); fl.e('%s = fpext float %s to double' % (r, f)); fl.x_set(d, fl.v_with_f64(s1, r))
        else:
            f = f64_src(fl, s2); r = fl.t(); fl.e('%s = fptrunc double %s to float' % (r, f)); fl.x_set(d, fl.v_with_f32(s1, r))
        return False
    if b in ('cvtsi2ss', 'cvtsi2sd'):
        d = xidx(fl, O[0]); s1 = fl.x_get(xidx(fl, O[1])) if len(O) == 3 else fl.x_get(d)
        src = O[-1]; bits = src.size * 8
        v = fl.rd(src, bits)
        if bits == 8: raise Unsupported('cvtsi2 8bit')
        ty = 'float' if b == 'cvtsi2ss' else 'double'
        r = fl.t(); fl.e('%s = sitofp i%d %s to %s' % (r, bits, v, ty))
        fl.x_set(d, fl.v_with_f32(s1, r) if ty == 'float' else fl.v_with_f64(s1, r)); return False
    mcv = re.match(r'cvt(t?)(ss|sd)2si$', b)
    if mcv:
        tr, sz = mcv.groups(); ty = 'float' if sz == 'ss' else 'double'
        v = f32_src(fl, O[1]) if ty == 'float' else f64_src(fl, O[1])
        bits = O[0].size * 8
        fn = {('float', 32): 'fa_cvt32', ('double', 32): 'fa_cvt32d', ('float', 64): 'fa_cvt64', ('double', 64): 'fa_cvt64d'}[(ty, bits)]
        r = fl.t(); fl.e('%s = call i%d @%s(%s %s, i1 %s)' % (r, bits, fn, ty, v, 'true' if tr else 'false'))
        fl.wr(O[0], r, bits); return False
    if b == 'cvtdq2ps':
        d = xidx(fl, O[0]); src = vec_src(fl, O[1]); r = fl.t(); fl.e('%s = sitofp <4 x i32> %s to <4 x float>' % (r, src))
        fl.x_set(d, fl.v_from(r, '<4 x float>')); return False
    if b == 'cvtdq2pd':
        d = xidx(fl, O[0]); src = vec_src(fl, O[1]); lo = fl.t(); fl.e('%s = shufflevector <4 x i32> %s, <4 x i32> undef, <2 x i32> <i32 0, i32 1>' % (lo, src))
        r = fl.t(); fl.e('%s = sitofp <2 x i32> %s to <2 x double>' % (r, lo)); fl.x_set(d, fl.v_from(r, '<2 x double>')); return False
    if b == 'cvtps2pd':
        d = xidx(fl, O[0])
        if O[1].type == CS_OP_MEM:
            p = fl.mem_addr(O[1]); lo = fl.t(); fl.e('%s = load <2 x float>, ptr %s, align 1' % (lo, p))
        else:
            src = fl.v_to(fl.x_get(xidx(fl, O[1])), '<4 x float>'); lo = fl.t()
            fl.e('%s = shufflevector <4 x float> %s, <4 x float> undef, <2 x i32> <i32 0, i32 1>' % (lo, src))
        r = fl.t(); fl.e('%s = fpext <2 x float> %s to <2 x double>' % (r, lo)); fl.x_set(d, fl.v_from(r, '<2 x double>')); return False
    if b in ('cvtpd2ps',):
        d = xidx(fl, O[0]); src = fl.v_to(vec_src(fl, O[1]), '<2 x double>')
        r = fl.t(); fl.e('%s = fptrunc <2 x double> %s to <2 x float>' % (r, src))
        z = fl.t(); fl.e('%s = shufflevector <2 x float> %s, <2 x float> zeroinitializer, <4 x i32> <i32 0, i32 1, i32 2, i32 3>' % (z, r))
        fl.x_set(d, fl.v_from(z, '<4 x float>')); return False
    if b in ('cvtpd2dq', 'cvttpd2dq'):
        d = xidx(fl, O[0]); src = fl.v_to(vec_src(fl, O[1]), '<2 x double>')
        tr = 'true' if b.startswith('cvtt') else 'false'
        res = []
        for lane in (0, 1):
            e = fl.t(); fl.e('%s = extractelement <2 x double> %s, i32 %d' % (e, src, lane))
            r = fl.t(); fl.e('%s = call i32 @fa_cvt32d(double %s, i1 %s)' % (r, e, tr)); res.append(r)
        v0 = fl.t(); fl.e('%s = insertelement <4 x i32> zeroinitializer, i32 %s, i32 0' % (v0, res[0]))
        v1 = fl.t(); fl.e('%s = insertelement <4 x i32> %s, i32 %s, i32 1' % (v1, v0, res[1]))
        fl.x_set(d, v1); return False
    if b in ('cvtps2dq', 'cvttps2dq'):
        d = xidx(fl, O[0]); src = fl.v_to(vec_src(fl, O[1]), '<4 x float>')
        tr = 'true' if b.startswith('cvtt') else 'false'
        v = 'zeroinitializer'
        for lane in range(4):
            e = fl.t(); fl.e('%s = extractelement <4 x float> %s, i32 %d' % (e, src, lane))
            r = fl.t(); fl.e('%s = call i32 @fa_cvt32(float %s, i1 %s)' % (r, e, tr))
            nv = fl.t(); fl.e('%s = insertelement <4 x i32> %s, i32 %s, i32 %d' % (nv, v, r, lane)); v = nv
        fl.x_set(d, v); return False

    # ---- 比較
    if b in ('comiss', 'ucomiss', 'comisd', 'ucomisd') and 'comis_noflags' in fl.M.inject:
        return False
    if b in ('comiss', 'ucomiss'):
        a = fl.v_f32(fl.x_get(xidx(fl, O[0]))); c = f32_src(fl, O[1]); vcmp_flags(fl, a, c, 'float'); return False
    if b in ('comisd', 'ucomisd'):
        a = fl.v_f64(fl.x_get(xidx(fl, O[0]))); c = f64_src(fl, O[1]); vcmp_flags(fl, a, c, 'double'); return False
    if b == 'ldmxcsr':
        v = fl.ld(fl.mem_addr(O[0]), 32); fl.e('store i32 %s, ptr @fa_mxcsr' % v); return False
    if b == 'stmxcsr':
        t = fl.t(); fl.e('%s = load i32, ptr @fa_mxcsr' % t); fl.st(fl.mem_addr(O[0]), t, 32); return False
    return None
