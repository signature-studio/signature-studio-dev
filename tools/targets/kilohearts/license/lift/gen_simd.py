#!/usr/bin/env python3
"""gen_simd.py — lift 済み IR の `declare ... @__asm_*` から SSE helper の C 実装を生成する (declare 駆動, KH-2 の原型)。

RetDec は SSE 命令を `@__asm_<mnemonic>[.N]` の extern 関数呼び出しにし、シグネチャは
「dst が読まれるなら第1引数 (i128), src は i128(reg)/i32,i64(メモリ), 即値 i8, 戻り値 = 新 dst(i128) か store 値(i64/i32)」。
名前の接尾 `.N`/`__N` は同一バイナリ内の overload 通番でバイナリ(関数集合)ごとに変わるので、
ここでは **名前ではなくシグネチャ** で意味を決める。意味は x86 SSE 仕様準拠 (Intel SDM)。

  gen_simd.py IN.ll OUT.c [--report OUT.json]
未知 mnemonic / 未対応シグネチャは abort() スタブ + 報告 (undefined helper として可視化)。
"""
import json
import os
import re
import sys

CT = {'i128': 'u128', 'i64': 'u64', 'i32': 'u32', 'i16': 'unsigned short', 'i8': 'u8', 'float': 'float', 'double': 'double', 'void': 'void'}
DECL = re.compile(r'^declare (\S+) @(__asm_[\w.]+)\(([^)]*)\)')

HEAD = r'''/* 自動生成 (gen_simd.py): declare 駆動 SSE helper。手編集禁止。 */
#include "msimd6_core.h"
#include <emscripten.h>
#include <math.h>
typedef union { u128 q; u32 w[4]; u64 d[2]; float f[4]; double g[2]; } L128;
static inline float F(u32 b) { float f; __builtin_memcpy(&f, &b, 4); return f; }
static inline double D(u64 b) { double f; __builtin_memcpy(&f, &b, 8); return f; }
static inline u32 FB(float f) { u32 b; __builtin_memcpy(&b, &f, 4); return b; }
static inline u64 DB(double f) { u64 b; __builtin_memcpy(&b, &f, 8); return b; }
static inline int cvtt32(double x) { return (x > -2147483649.0 && x < 2147483648.0) ? (int)x : (int)0x80000000; }
static inline long long cvtt64(double x) { return (x > -9223372036854775809.0 && x < 9223372036854775808.0) ? (long long)x : (long long)0x8000000000000000ULL; }
#define EX EMSCRIPTEN_KEEPALIVE
'''


def split_params(s):
    return [p.strip() for p in s.split(',') if p.strip()]


def base_of(name):
    n = name[len('__asm_'):]
    n = re.sub(r'(__\d+|\.\d+)$', '', n)
    return n


def lane_arg(ty, nm, kind):
    """src オペランドを f32/f64 低位 lane として取り出す C 式"""
    if kind == 'ss':
        return ('F(%s)' % nm) if ty == 'i32' else 'x_%s.f[0]' % nm
    return ('D(%s)' % nm) if ty == 'i64' else 'x_%s.g[0]' % nm


V256_LANES = {'vpcmpeqb': 'i8', 'vpcmpeqw': 'i16', 'vpcmpeqd': 'i32'}


def gen256(name, ret, params):
    """VEX.256 (ymm) の整数語彙を LLVM IR 定義として返す。None = 未対応。
    C に i256 の正体型が無いため C ではなく IR で定義する (呼出側と ABI を揃える)。
    引数順は VEX 形 (a0 = src1, a1 = src2 / a2 = imm8)。lane 0 = bit [31:0] (LLVM の bitcast 順と一致)。"""
    b = base_of(name)
    ptys = [p.split()[0] for p in params]
    if b in V256_LANES and ret == 'i256' and ptys == ['i256', 'i256']:
        t = V256_LANES[b]
        cnt = 256 // int(t[1:])
        return ('define i256 @%s(i256 %%a0, i256 %%a1) {\n'
                '  %%x = bitcast i256 %%a0 to <%d x %s>\n'
                '  %%y = bitcast i256 %%a1 to <%d x %s>\n'
                '  %%c = icmp eq <%d x %s> %%x, %%y\n'
                '  %%s = sext <%d x i1> %%c to <%d x %s>\n'
                '  %%o = bitcast <%d x %s> %%s to i256\n'
                '  ret i256 %%o\n}') % (name, cnt, t, cnt, t, cnt, t, cnt, cnt, t, cnt, t)
    if b == 'vpmovmskb' and ret == 'i32' and ptys == ['i256']:
        return ('define i32 @%s(i256 %%a0) {\n'
                '  %%x = bitcast i256 %%a0 to <32 x i8>\n'
                '  %%c = icmp slt <32 x i8> %%x, zeroinitializer\n'
                '  %%m = bitcast <32 x i1> %%c to i32\n'
                '  ret i32 %%m\n}') % name
    if b == 'vinsertf128' and ret == 'i256' and ptys == ['i256', 'i128', 'i8']:
        return ('define i256 @%s(i256 %%a0, i128 %%a1, i8 %%a2) {\n'
                '  %%sel = and i8 %%a2, 1\n'
                '  %%c = icmp eq i8 %%sel, 0\n'
                '  %%lo = trunc i256 %%a0 to i128\n'
                '  %%hs = lshr i256 %%a0, 128\n'
                '  %%hi = trunc i256 %%hs to i128\n'
                '  %%L = select i1 %%c, i128 %%a1, i128 %%lo\n'
                '  %%H = select i1 %%c, i128 %%hi, i128 %%a1\n'
                '  %%zl = zext i128 %%L to i256\n'
                '  %%zh = zext i128 %%H to i256\n'
                '  %%sh = shl i256 %%zh, 128\n'
                '  %%o = or i256 %%zl, %%sh\n'
                '  ret i256 %%o\n}') % name
    return None


def stub256(name, ret, params):
    """未対応の i256 宣言は abort() スタブ (SSE の未対応と同じ扱い)。呼ばれたら abort する。"""
    sig = ', '.join('%s %%a%d' % (p.split()[0], i) for i, p in enumerate(params))
    return 'define %s @%s(%s) {\n  call void @abort()\n  unreachable\n}' % (ret, name, sig)


def gen(name, ret, params):
    R_ = ret
    """(C 本体文字列, 理由) を返す。None = 未対応"""
    b = base_of(name)
    n = len(params)
    # ---- vzeroupper: 下位 128bit (xmm) は不変。上位は後続の ymm グローバル undef 書込みで表す (no-op)
    if b == 'vzeroupper' and n == 0 and R_ == 'void':
        return '(void)0;'
    # ---- FMA3 scalar/packed: vf[n]m{add,sub}{132,213,231}{sd,ss,pd,ps}  (a=dest, b=src2, c=src3(reg|mem)); fma() は単一丸め = FMA3 hardware と等価
    mf = re.match(r'^vf(n?)m(add|sub)(132|213|231)(sd|ss|pd|ps)$', b)
    if mf and n == 3 and params[0].startswith('i128') and R_ == 'i128':
        neg, sub, order, k = mf.group(1) == 'n', mf.group(2) == 'sub', mf.group(3), mf.group(4)
        sc = k in ('sd', 'ss')
        fld, ty, fn_, cnt = ('g', 'double', 'fma', 1 if sc else 2) if k in ('sd', 'pd') else ('f', 'float', 'fmaf', 1 if sc else 4)
        pt = [p.split()[0] for p in params]
        src3 = lambda i: ('%s(a2)' % ('D' if ty == 'double' else 'F')) if pt[2] in ('i64', 'i32') else 'x2.%s[%d]' % (fld, i)
        xs, ys, zs = {'132': ('x0.%s[{i}]', 'SRC3', 'x1.%s[{i}]'), '213': ('x1.%s[{i}]', 'x0.%s[{i}]', 'SRC3'), '231': ('x1.%s[{i}]', 'SRC3', 'x0.%s[{i}]')}[order]
        body_ = ['L128 x0, x1, x2; x0.q = a0; x1.q = a1; x2.q = (pt[2] == "i128") ? a2 : 0;'.replace('(pt[2] == "i128") ? a2 : 0', 'a2' if pt[2] == 'i128' else '0'), 'L128 r; r.q = x0.q;']
        for i in range(cnt):
            f_ = lambda t_: (src3(i) if t_ == 'SRC3' else t_.replace('{i}', str(i)) % fld)
            x_, y_, z_ = f_(xs), f_(ys), f_(zs)
            if neg:
                x_ = '(-%s)' % x_
            if sub:
                z_ = '(-%s)' % z_
            body_.append('r.%s[%d] = %s(%s, %s, %s);' % (fld, i, fn_, x_, y_, z_))
        return ' '.join(body_) + ' return r.q;'
    # ---- VEX prefix は SSE 版と同じ意味 (3 operand 形は src1 を第1引数に取るため upper lane 規則が一致)
    if b.startswith('v') and b[1:] in ('addsd', 'subsd', 'mulsd', 'divsd', 'minsd', 'maxsd', 'sqrtsd', 'addss', 'subss', 'mulss', 'divss', 'minss', 'maxss', 'sqrtss',
                                         'addpd', 'subpd', 'mulpd', 'divpd', 'addps', 'subps', 'mulps', 'divps', 'andpd', 'andps', 'andnpd', 'andnps', 'orpd', 'orps',
                                         'xorpd', 'xorps', 'movapd', 'movaps', 'movdqa', 'movdqu', 'movupd', 'movups', 'movq', 'movd', 'movsd', 'movss', 'unpcklpd',
                                         'unpckhpd', 'unpcklps', 'unpckhps', 'shufpd', 'shufps', 'cvttpd2dq', 'psrldq', 'pslldq', 'psrlq', 'psllq', 'haddpd', 'haddps', 'movddup'):
        b = b[1:]
    ptys = [p.split()[0] for p in params]
    R = ret
    # ---- 引数を共通化: i128 は L128 に載せる
    pre = []
    for i, t in enumerate(ptys):
        if t == 'i128':
            pre.append('L128 x_a%d; x_a%d.q = a%d;' % (i, i, i))
    pre = ' '.join(pre)
    A = lambda i: 'x_a%d' % i

    def S(kind, i):  # src を lane0 として
        t = ptys[i]
        if kind == 'ss':
            return 'F(a%d)' % i if t == 'i32' else '%s.f[0]' % A(i)
        return 'D(a%d)' % i if t == 'i64' else '%s.g[0]' % A(i)

    body = None
    # ----- scalar arithmetic (ss/sd)
    m = re.match(r'^(add|sub|mul|div|min|max|sqrt)(ss|sd)$', b)
    if m and R == 'i128' and n == 2 and ptys[0] == 'i128':
        op, k = m.group(1), m.group(2)
        ty = 'float' if k == 'ss' else 'double'
        la = '%s.%s[0]' % (A(0), 'f' if k == 'ss' else 'g')
        sv = S(k, 1)
        e = {'add': '(%s + %s)' % (la, sv), 'sub': '(%s - %s)' % (la, sv), 'mul': '(%s * %s)' % (la, sv), 'div': '(%s / %s)' % (la, sv),
             'min': '((%s < %s) ? %s : %s)' % (la, sv, la, sv), 'max': '((%s > %s) ? %s : %s)' % (la, sv, la, sv),
             'sqrt': ('sqrtf(%s)' if k == 'ss' else 'sqrt(%s)') % sv}[op]
        body = '%s %s.%s[0] = %s; return %s.q;' % (pre, A(0), 'f' if k == 'ss' else 'g', e, A(0))
    # ----- packed arithmetic
    m = re.match(r'^(add|sub|mul|div|min|max)(ps|pd)$', b)
    if m and R == 'i128' and n == 2 and ptys == ['i128', 'i128']:
        op, k = m.group(1), m.group(2)
        cnt, fld = (4, 'f') if k == 'ps' else (2, 'g')
        sym = {'add': '+', 'sub': '-', 'mul': '*', 'div': '/'}.get(op)
        loops = []
        for i in range(cnt):
            x, y = '%s.%s[%d]' % (A(0), fld, i), '%s.%s[%d]' % (A(1), fld, i)
            e = '%s %s %s' % (x, sym, y) if sym else ('(%s < %s ? %s : %s)' % (x, y, x, y) if op == 'min' else '(%s > %s ? %s : %s)' % (x, y, x, y))
            loops.append('r.%s[%d] = %s;' % (fld, i, e))
        body = '%s L128 r; %s return r.q;' % (pre, ' '.join(loops))
    # ----- bitwise
    m = re.match(r'^(and|andn|or|xor)(ps|pd)$|^(pand|pandn|por|pxor)$', b)
    if m and R == 'i128' and n == 2 and ptys == ['i128', 'i128']:
        op = (m.group(1) or m.group(3)).lstrip('p') if True else ''
        op = {'and': 'a0 & a1', 'andn': '~a0 & a1', 'or': 'a0 | a1', 'xor': 'a0 ^ a1'}[op]
        body = 'return %s;' % op
    # ----- moves
    if re.match(r'^mov(aps|ups|apd|upd|dqa|dqu)$', b) and n == 1 and ptys[0] == 'i128':
        body = 'return (%s)a0;' % CT[R]
    if b == 'movss':
        if n == 1 and ptys[0] == 'i32' and R == 'i128':
            body = 'L128 r; r.q = 0; r.w[0] = a0; return r.q;'
        elif n == 1 and ptys[0] == 'i128':
            body = '%s return (%s)%s.w[0];' % (pre, CT[R], A(0))
        elif n == 2 and ptys == ['i128', 'i128'] and R == 'i128':
            body = '%s %s.w[0] = %s.w[0]; return %s.q;' % (pre, A(0), A(1), A(0))
    if b == 'movsd':
        if n == 1 and ptys[0] == 'i64' and R == 'i128':
            body = 'L128 r; r.q = 0; r.d[0] = a0; return r.q;'
        elif n == 1 and ptys[0] == 'i128':
            body = '%s return (%s)%s.d[0];' % (pre, CT[R], A(0))
        elif n == 2 and ptys == ['i128', 'i128'] and R == 'i128':
            body = '%s %s.d[0] = %s.d[0]; return %s.q;' % (pre, A(0), A(1), A(0))
    if b == 'movq':
        if n == 1 and ptys[0] == 'i128' and R == 'i128':
            body = 'return (u128)(u64)a0;'
        elif n == 1 and ptys[0] == 'i128':
            body = 'return (%s)(u64)a0;' % CT[R]
        elif n == 1 and ptys[0] == 'i64' and R == 'i128':
            body = 'return (u128)a0;'
    if b == 'movd':
        if n == 1 and ptys[0] in ('i32', 'i64') and R == 'i128':
            body = 'return (u128)(u32)a0;'
        elif n == 1 and ptys[0] == 'i128':
            body = 'return (%s)(u32)a0;' % CT[R]
    if b in ('movlps', 'movlpd'):
        if n == 1 and ptys[0] == 'i128':
            body = 'return (%s)(u64)a0;' % CT[R]
        elif n == 2 and ptys == ['i128', 'i64'] and R == 'i128':
            body = '%s %s.d[0] = a1; return %s.q;' % (pre, A(0), A(0))
    if b in ('movhps', 'movhpd'):
        if n == 1 and ptys[0] == 'i128':
            body = 'return (%s)(u64)(a0 >> 64);' % CT[R]
        elif n == 2 and ptys == ['i128', 'i64'] and R == 'i128':
            body = '%s %s.d[1] = a1; return %s.q;' % (pre, A(0), A(0))
    if b == 'movddup' and R == 'i128':
        if n == 1 and ptys[0] == 'i128':
            body = 'u64 l = (u64)a0; return ((u128)l << 64) | l;'
        elif n == 1 and ptys[0] == 'i64':
            body = 'return ((u128)a0 << 64) | a0;'
    if b == 'movshdup' and n == 1 and ptys[0] == 'i128' and R == 'i128':
        body = '%s L128 r; r.w[0] = r.w[1] = %s.w[1]; r.w[2] = r.w[3] = %s.w[3]; return r.q;' % (pre, A(0), A(0))
    if b == 'movsldup' and n == 1 and ptys[0] == 'i128' and R == 'i128':
        body = '%s L128 r; r.w[0] = r.w[1] = %s.w[0]; r.w[2] = r.w[3] = %s.w[2]; return r.q;' % (pre, A(0), A(0))
    if b in ('movmskps', 'movmskpd', 'pmovmskb'):
        pass
    # ----- shuffles / unpack
    if b in ('unpcklps', 'punpckldq') and ptys == ['i128', 'i128'] and R == 'i128':
        body = '%s L128 r; r.w[0] = %s.w[0]; r.w[1] = %s.w[0]; r.w[2] = %s.w[1]; r.w[3] = %s.w[1]; return r.q;' % (pre, A(0), A(1), A(0), A(1))
    if b in ('unpckhps', 'punpckhdq') and ptys == ['i128', 'i128'] and R == 'i128':
        body = '%s L128 r; r.w[0] = %s.w[2]; r.w[1] = %s.w[2]; r.w[2] = %s.w[3]; r.w[3] = %s.w[3]; return r.q;' % (pre, A(0), A(1), A(0), A(1))
    if b in ('unpcklpd', 'punpcklqdq') and ptys == ['i128', 'i128'] and R == 'i128':
        body = '%s L128 r; r.d[0] = %s.d[0]; r.d[1] = %s.d[0]; return r.q;' % (pre, A(0), A(1))
    if b in ('unpckhpd', 'punpckhqdq') and ptys == ['i128', 'i128'] and R == 'i128':
        body = '%s L128 r; r.d[0] = %s.d[1]; r.d[1] = %s.d[1]; return r.q;' % (pre, A(0), A(1))
    if b == 'shufps' and ptys == ['i128', 'i128', 'i8'] and R == 'i128':
        body = ('%s L128 r; r.w[0] = %s.w[a2 & 3]; r.w[1] = %s.w[(a2 >> 2) & 3]; r.w[2] = %s.w[(a2 >> 4) & 3]; r.w[3] = %s.w[(a2 >> 6) & 3]; return r.q;'
                % (pre, A(0), A(0), A(1), A(1)))
    if b == 'shufpd' and ptys == ['i128', 'i128', 'i8'] and R == 'i128':
        body = '%s L128 r; r.d[0] = %s.d[a2 & 1]; r.d[1] = %s.d[(a2 >> 1) & 1]; return r.q;' % (pre, A(0), A(1))
    if b == 'pshufd' and ptys == ['i128', 'i8'] and R == 'i128':
        body = '%s L128 r; for (int i = 0; i < 4; i++) r.w[i] = %s.w[(a1 >> (2 * i)) & 3]; return r.q;' % (pre, A(0))
    if b in ('haddps', 'haddpd') and ptys == ['i128', 'i128'] and R == 'i128':
        if b == 'haddps':
            body = '%s L128 r; r.f[0] = %s.f[0] + %s.f[1]; r.f[1] = %s.f[2] + %s.f[3]; r.f[2] = %s.f[0] + %s.f[1]; r.f[3] = %s.f[2] + %s.f[3]; return r.q;' % (pre, A(0), A(0), A(0), A(0), A(1), A(1), A(1), A(1))
        else:
            body = '%s L128 r; r.g[0] = %s.g[0] + %s.g[1]; r.g[1] = %s.g[0] + %s.g[1]; return r.q;' % (pre, A(0), A(0), A(1), A(1))
    # ----- conversions
    if b in ('cvtsi2ss', 'cvtsi2sd') and n == 1 and R == 'i128':
        sg = 'int' if ptys[0] == 'i32' else 'long long'
        if b == 'cvtsi2ss':
            body = 'L128 r; r.q = 0; r.f[0] = (float)(%s)a0; return r.q;' % sg
        else:
            body = 'L128 r; r.q = 0; r.g[0] = (double)(%s)a0; return r.q;' % sg
    if b == 'cvtss2sd' and n in (1, 2) and R == 'i128':
        si = n - 1
        s = S('ss', si)
        body = '%s L128 r; r.q = %s; r.g[0] = (double)%s; return r.q;' % (pre, A(0) + '.q' if n == 2 else '0', s)
    if b == 'cvtsd2ss' and n in (1, 2) and R == 'i128':
        si = n - 1
        s = S('sd', si)
        body = '%s L128 r; r.q = %s; r.f[0] = (float)%s; return r.q;' % (pre, A(0) + '.q' if n == 2 else '0', s)
    if b == 'cvtps2pd' and n == 1 and ptys[0] == 'i128' and R == 'i128':
        body = '%s L128 r; r.g[0] = (double)%s.f[0]; r.g[1] = (double)%s.f[1]; return r.q;' % (pre, A(0), A(0))
    if b == 'cvtpd2ps' and n == 1 and ptys[0] == 'i128' and R == 'i128':
        body = '%s L128 r; r.q = 0; r.f[0] = (float)%s.g[0]; r.f[1] = (float)%s.g[1]; return r.q;' % (pre, A(0), A(0))
    if b in ('cvttss2si', 'cvttsd2si') and n == 1 and R in ('i32', 'i64'):
        k = 'ss' if b == 'cvttss2si' else 'sd'
        s = S(k, 0)
        body = '%s return (%s)%s((double)%s);' % (pre, CT[R], 'cvtt64' if R == 'i64' else 'cvtt32', s)
    if b in ('cvtss2si', 'cvtsd2si') and n == 1 and R in ('i32', 'i64'):
        k = 'ss' if b == 'cvtss2si' else 'sd'
        s = S(k, 0)
        body = '%s return (%s)%s(nearbyint((double)%s));' % (pre, CT[R], 'cvtt64' if R == 'i64' else 'cvtt32', s)
    # ----- packed int / byte shifts, conversions (SSE2)
    if b in ('psrldq', 'pslldq') and n == 2 and ptys == ['i128', 'i8'] and R == 'i128':
        body = 'return (a1 > 15) ? (u128)0 : %s;' % ('(a0 >> (8 * a1))' if b == 'psrldq' else '(a0 << (8 * a1))')
    if b in ('psrlq', 'psllq') and n == 2 and ptys == ['i128', 'i8'] and R == 'i128':
        op = '>>' if b == 'psrlq' else '<<'
        body = '%s L128 r; r.d[0] = (a1 > 63) ? 0 : (%s.d[0] %s a1); r.d[1] = (a1 > 63) ? 0 : (%s.d[1] %s a1); return r.q;' % (pre, A(0), op, A(0), op)
    if b in ('cvttpd2dq', 'cvtpd2dq') and n == 1 and ptys[0] == 'i128' and R == 'i128':
        f = 'cvtt32(%s.g[%d])' if b == 'cvttpd2dq' else 'cvtt32(nearbyint(%s.g[%d]))'
        body = '%s L128 r; r.q = 0; r.w[0] = (u32)%s; r.w[1] = (u32)%s; return r.q;' % (pre, f % (A(0), 0), f % (A(0), 1))
    if b == 'cvtdq2pd' and n == 1 and ptys[0] == 'i128' and R == 'i128':
        body = '%s L128 r; r.g[0] = (double)(int)%s.w[0]; r.g[1] = (double)(int)%s.w[1]; return r.q;' % (pre, A(0), A(0))
    if b == 'cvtdq2ps' and n == 1 and ptys[0] == 'i128' and R == 'i128':
        body = '%s L128 r; for (int i = 0; i < 4; i++) r.f[i] = (float)(int)%s.w[i]; return r.q;' % (pre, A(0))
    if b == 'cvtps2pd' and n == 1 and ptys[0] == 'i64' and R == 'i128':
        body = 'L128 r; r.g[0] = (double)F((u32)a0); r.g[1] = (double)F((u32)(a0 >> 32)); return r.q;'
    if b == 'movhlps' and ptys == ['i128', 'i128'] and R == 'i128':
        body = '%s L128 r; r.d[0] = %s.d[1]; r.d[1] = %s.d[1]; return r.q;' % (pre, A(1), A(0))
    if b == 'movlhps' and ptys == ['i128', 'i128'] and R == 'i128':
        body = '%s L128 r; r.d[0] = %s.d[0]; r.d[1] = %s.d[0]; return r.q;' % (pre, A(0), A(1))
    # sqrt 1 引数形 (dest を落とす; 上位 lane は kh_lower[merge] が復元)
    if b in ('sqrtsd', 'sqrtss') and n == 1 and R == 'i128':
        body = ('%s L128 r; r.q = 0; r.g[0] = sqrt(%s); return r.q;' % (pre, S('sd', 0))) if b == 'sqrtsd' else ('%s L128 r; r.q = 0; r.f[0] = sqrtf(%s); return r.q;' % (pre, S('ss', 0)))
    # ----- compares
    m = re.match(r'^cmp(eq|lt|le|unord|neq|nlt|nle|ord)(ss|sd)$', b)
    if m and n == 2 and ptys[0] == 'i128' and R == 'i128':
        pr, k = m.group(1), m.group(2)
        x = '%s.%s[0]' % (A(0), 'f' if k == 'ss' else 'g')
        y = S(k, 1)
        e = {'eq': '%s == %s', 'lt': '%s < %s', 'le': '%s <= %s', 'unord': '(%s != %s || %s == %s)', 'neq': '!(%s == %s)', 'nlt': '!(%s < %s)', 'nle': '!(%s <= %s)', 'ord': '(%s == %s || %s != %s)'}[pr]
        cond = (e % (x, y)) if pr not in ('unord', 'ord') else None
        if pr == 'unord':
            cond = '(isnan(%s) || isnan(%s))' % (x, y)
        if pr == 'ord':
            cond = '(!isnan(%s) && !isnan(%s))' % (x, y)
        if k == 'ss':
            body = '%s %s.w[0] = (%s) ? 0xffffffffu : 0; return %s.q;' % (pre, A(0), cond, A(0))
        else:
            body = '%s %s.d[0] = (%s) ? ~0ULL : 0; return %s.q;' % (pre, A(0), cond, A(0))
    # ----- store 形 (void, ポインタ無し): RetDec が store を落とした形。実装不能 → store128 pass が除去する前提。
    #       pass を外すと silent no-op になる (poc_gain はこの状態で 6/6 通過していた = 検出力不足の実例)
    if re.match(r'^mov(aps|ups|apd|upd|dqa|dqu|ntps|ntdq)$', b) and R == 'void' and n == 2:
        body = '(void)a0; (void)a1;'
    # ----- ucomis*/comis*: フラグは kh_passes[flags] が fcmp 化済み → 呼出は no-op
    if re.match(r'^v?u?comis[sd]$', b) and R == 'void':
        body = '(void)a0; (void)a1;'
    if body is None:
        return None
    return body


def main():
    src, dst = sys.argv[1], sys.argv[2]
    rep = {'generated': [], 'undefined': []}
    seen = set()
    out = [HEAD]
    ll_out = []
    for line in open(src):
        m = DECL.match(line)
        if not m or m.group(2) in seen:
            continue
        ret, name, ps = m.group(1), m.group(2), split_params(m.group(3))
        seen.add(name)
        if 'i256' in [ret] + [p.split()[0] for p in ps]:
            ir = gen256(name, ret, ps)
            if ir is None:
                rep['undefined'].append('%s %s(%s)' % (ret, name, ','.join(p.split()[0] for p in ps)))
                ir = stub256(name, ret, ps)
            else:
                rep['generated'].append('%s %s(%s)' % (ret, name, ','.join(p.split()[0] for p in ps)))
            ll_out.append(ir)
            continue
        ptys = [p.split()[0] for p in ps]
        sig = '%s %s(%s)' % (CT[ret], name, ', '.join('%s a%d' % (CT[t], i) for i, t in enumerate(ptys)) or 'void')
        body = gen(name, ret, ps)
        if body is None:
            rep['undefined'].append('%s %s(%s)' % (ret, name, ','.join(ptys)))
            if ret == 'void':
                out.append('EX %s { abort(); }' % sig)
            else:
                out.append('EX %s { abort(); return (%s)0; }' % (sig, CT[ret]))
        else:
            rep['generated'].append('%s %s(%s)' % (ret, name, ','.join(ptys)))
            out.append('EX %s { %s }' % (sig, body))
    open(dst, 'w').write('\n'.join(out) + '\n')
    ll_dst = dst + '.i256.ll'
    if ll_out:
        open(ll_dst, 'w').write('\n'.join(['declare void @abort()'] + ll_out) + '\n')
    elif os.path.exists(ll_dst):
        os.remove(ll_dst)
    if len(sys.argv) > 4 and sys.argv[3] == '--report':
        json.dump(rep, open(sys.argv[4], 'w'), indent=1)
    print('[gen_simd] helpers %d, undefined(abort stub) %d %s' % (len(rep['generated']), len(rep['undefined']), rep['undefined'][:8]))


if __name__ == '__main__':
    main()
