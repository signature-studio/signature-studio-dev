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


def gen(name, ret, params):
    R_ = ret
    """(C 本体文字列, 理由) を返す。None = 未対応"""
    b = base_of(name)
    n = len(params)
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
                                         'unpckhpd', 'unpcklps', 'unpckhps', 'shufpd', 'shufps', 'cvttpd2dq', 'psrldq', 'pslldq', 'psrlq', 'psllq', 'haddpd', 'haddps', 'movddup',
                                         'pand', 'pandn', 'por', 'pxor', 'paddd', 'psubd', 'psrld', 'pslld', 'cvtdq2ps', 'cvtdq2pd', 'cvtpd2dq', 'cvttpd2dq', 'cvtps2pd',
                                         'cvtpd2ps', 'cvtsd2ss', 'cvtss2sd', 'cvtsi2sd', 'cvtsi2ss', 'cvtss2si', 'cvtsd2si', 'cvttsd2si', 'cvttss2si', 'paddq', 'psubq', 'psrad',
                                         'punpckldq', 'punpckhdq', 'punpcklqdq', 'punpckhqdq', 'pshufd', 'ldmxcsr', 'stmxcsr'):
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
    if b in ('cvtsi2ss', 'cvtsi2sd') and n in (1, 2) and R == 'i128':
        sg = 'int' if (ptys[n - 1] == 'i32') else 'long long'
        keep = 'r.q = a0; ' if n == 2 else 'r.q = 0; '
        if b == 'cvtsi2ss':
            body = 'L128 r; %sr.f[0] = (float)(%s)a%d; return r.q;' % (keep, sg, n - 1)
        else:
            body = 'L128 r; %sr.g[0] = (double)(%s)a%d; return r.q;' % (keep, sg, n - 1)
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
    if b == 'cvttps2dq' and n == 1 and ptys[0] == 'i128' and R == 'i128':
        body = '%s L128 r; r.q = 0; for (int i = 0; i < 4; i++) r.w[i] = (u32)cvtt32(%s.f[i]); return r.q;' % (pre, A(0))
    # ----- packed dword 算術/シフト (log10f 等の int 経路; すべて厳密整数 = exact)
    if b in ('paddd', 'psubd') and ptys == ['i128', 'i128'] and R == 'i128':
        op = '+' if b == 'paddd' else '-'
        body = ('%s L128 r; for (int i = 0; i < 4; i++) r.w[i] = (u32)(%s.w[i] %s %s.w[i]); return r.q;'
                % (pre, A(0), op, A(1)))
    if b in ('paddq', 'psubq') and ptys == ['i128', 'i128'] and R == 'i128':
        op = '+' if b == 'paddq' else '-'
        body = ('%s L128 r; for (int i = 0; i < 2; i++) r.d[i] = (u64)((long long)%s.d[i] %s (long long)%s.d[i]); return r.q;'
                % (pre, A(0), op, A(1)))
    if b == 'psrad' and R == 'i128' and (ptys == ['i128', 'i8'] or ptys == ['i128', 'i128']):
        cnt = ('(u64)a1' if ptys[1] == 'i8' else '(u64)x_a1.d[0]') + ' & 63'
        body = ('%s L128 r; { unsigned long long c = %s; for (int i = 0; i < 4; i++) r.w[i] = (u32)((int)(%s.w[i]) >> (c > 31 ? 31 : c)); } return r.q;'
                % (pre, cnt, A(0)))
    if b in ('psrld', 'pslld') and R == 'i128' and (ptys == ['i128', 'i128'] or ptys == ['i128', 'i8']):
        op = '>>' if b == 'psrld' else '<<'
        # imm8 形: count > 31 → 0 (Intel SDM)。レジスタ形: count = 下位 qword mod 64、その後 > 31 → 0
        cnt = ('(u64)a1' if ptys[1] == 'i8' else '(u64)(u64)x_a1.d[0]') + ' & 63'
        body = ('%s L128 r; { unsigned long long c = %s; for (int i = 0; i < 4; i++) r.w[i] = (c > 31) ? 0u : (%s.w[i] %s (unsigned)c); } return r.q;'
                % (pre, cnt, A(0), op))
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
    m = re.match(r'^cmp(eq|lt|le|unord|neq|nlt|nle|ord)(ss|sd|ps|pd)$', b)
    if m and n == 2 and ptys[0] == 'i128' and R == 'i128':
        pr, k = m.group(1), m.group(2)
        packed = k in ('ps', 'pd')
        cnt = (4 if k == 'ps' else 2) if packed else 1
        rf, xf = ('w', 'f') if k in ('ss', 'ps') else (('d', 'g') if packed else ('w', 'f') if k == 'ss' else ('d', 'g'))
        mask = '0xffffffffu' if k in ('ss', 'ps') else '~0ULL'
        x = lambda i: '%s.%s[%d]' % (A(0), xf, i) if packed else ('%s.%s[0]' % (A(0), 'f' if k == 'ss' else 'g'))
        y = lambda i: ('%s.%s[%d]' % (A(1), xf, i)) if packed else S(k, 1)
        e = {'eq': '%s == %s', 'lt': '%s < %s', 'le': '%s <= %s', 'neq': '!(%s == %s)', 'nlt': '!(%s < %s)', 'nle': '!(%s <= %s)'}[pr]
        conds = []
        for i in range(cnt):
            c = (e % (x(i), y(i)))
            if pr == 'unord':
                c = '(isnan(%s) || isnan(%s))' % (x(i), y(i))
            elif pr == 'ord':
                c = '(!isnan(%s) && !isnan(%s))' % (x(i), y(i))
            conds.append(c)
        if not packed:
            body = '%s %s.%s[0] = (%s) ? %s : 0; return %s.q;' % (pre, A(0), rf, conds[0], mask, A(0))
        else:
            body = '%s L128 r; %s return r.q;' % (pre, ' '.join('r.%s[%d] = (%s) ? %s : 0;' % (rf, i, c, mask) for i, c in enumerate(conds)))
    # ----- 近似命令 (rcp/rsqrt): wasm 側は IEEE の 1/x, 1/sqrt(x) (仕様上限 1.5*2^-12 内)。
    #       実機 x86 の近似表との差は CAB-224 の許容誤差 gate (tools/liftlib/liftlib/simd/simdtest.py と同一基準) で判定する。
    if b in ('rcpps', 'rcpss') and n == 1 and ptys[0] == 'i128' and R == 'i128':
        cnt = 4 if b == 'rcpps' else 1
        body = '%s L128 r; r.q = %s.q; %s return r.q;' % (pre, A(0), ' '.join('r.f[%d] = 1.0f / %s.f[%d];' % (i, A(0), i) for i in range(cnt)))
    if b in ('rsqrtps', 'rsqrtss') and n == 1 and ptys[0] == 'i128' and R == 'i128':
        cnt = 4 if b == 'rsqrtps' else 1
        body = '%s L128 r; r.q = %s.q; %s return r.q;' % (pre, A(0), ' '.join('r.f[%d] = 1.0f / sqrtf(%s.f[%d]);' % (i, A(0), i) for i in range(cnt)))
    # ----- store 形 (void, ポインタ無し): RetDec が store を落とした形。実装不能 → store128 pass が除去する前提。
    #       pass を外すと silent no-op になる (poc_gain はこの状態で 6/6 通過していた = 検出力不足の実例)
    if re.match(r'^mov(aps|ups|apd|upd|dqa|dqu|ntps|ntdq)$', b) and R == 'void' and n == 2:
        body = '(void)a0; (void)a1;'
    # ----- ucomis*/comis*: フラグは kh_passes[flags] が fcmp 化済み → 呼出は no-op
    if re.match(r'^v?u?comis[sd]$', b) and R == 'void':
        body = '(void)a0; (void)a1;'
    # ----- MXCSR: wasm は固定環境 (round-nearest, no exceptions)。既存 9 snap-in も MXCSR を使わない。
    if b in ('ldmxcsr', 'stmxcsr') and R == 'void' and n == 1:
        body = '(void)a0;' if b == 'ldmxcsr' else '*(u32*)(unsigned int)a0 = 0x1f80;'
    if b in ('ldmxcsr', 'stmxcsr') and R == 'i32' and n == 1:
        body = 'return 0x1f80;'
    if body is None:
        return None
    return body


def main():
    src, dst = sys.argv[1], sys.argv[2]
    rep = {'generated': [], 'undefined': []}
    seen = set()
    out = [HEAD]
    for line in open(src):
        m = DECL.match(line)
        if not m or m.group(2) in seen:
            continue
        ret, name, ps = m.group(1), m.group(2), split_params(m.group(3))
        seen.add(name)
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
    if len(sys.argv) > 4 and sys.argv[3] == '--report':
        json.dump(rep, open(sys.argv[4], 'w'), indent=1)
    print('[gen_simd] helpers %d, undefined(abort stub) %d %s' % (len(rep['generated']), len(rep['undefined']), rep['undefined'][:8]))


if __name__ == '__main__':
    main()
