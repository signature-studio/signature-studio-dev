#!/usr/bin/env python3
"""M11 __asm_* helper 生成 (署名駆動版): lift IR の declare から work/m11_simd.c を生成する.

旧 m11_gensimd.py/m11_fwdgen.py は helper を「名前+IR 内出現順 suffix」で分類していたため, merge 順が変わると
意味が失われ (実測: boot closure の __asm_* 呼出しの大半 = movss/cvtsi2sd/mulsd 等 141 名が既定値 stub 化),
さらに struct を返す cpuid 等が未定義 → wasm-ld unreachable thunk になっていた.
ここでは (base 名 = suffix `__N` を除いた名前, 返り型, 引数型) だけで x86 意味を決め, 宣言された全 symbol を
IR の署名そのままで定義する. 未知の base は「呼ばれたら stderr に出し 0 を返す」stub (= 未実装を可視化).

使い方: python3 m11_simd2.py work/boot_final.ll > work/m11_simd.c  (統計は stderr)
"""
import os, re, sys
from collections import Counter

ll = open(sys.argv[1]).read()
DECL = re.findall(r'^declare (\S+) @(__asm_[\w.$-]+)\((.*?)\) local_unnamed_addr$', ll, re.M)
CT = {'i128': 'u128', 'i64': 'u64', 'i32': 'u32', 'i16': 'u32', 'i8': 'u32', 'i1': 'u32', 'void': 'void', 'ptr': 'void*'}
STATS = Counter()
UNIMPL = []
UT = {8: 'u8', 16: 'u16', 32: 'u32', 64: 'u64'}
IT = {8: 'i8', 16: 'i16', 32: 'i32', 64: 'i64'}


def base_of(n):
    return re.sub(r'(__\d+)+$', '', n[len('__asm_'):])


def tys_of(a):
    return [x.strip().split()[0] for x in a.split(',') if x.strip()]


def lane_ops():
    s = {}
    for bits, T, S in ((8, 'u8', 'i8'), (16, 'u16', 'i16'), (32, 'u32', 'i32'), (64, 'u64', 'i64')):
        sfx = {8: 'b', 16: 'w', 32: 'd', 64: 'q'}[bits]
        mx = (1 << bits) - 1
        s['padd' + sfx] = (bits, '(%s)(x + y)' % T)
        s['psub' + sfx] = (bits, '(%s)(x - y)' % T)
        if bits in (8, 16):
            lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
            s['padds' + sfx] = (bits, '(%s)({ int t = (%s)x + (%s)y; t < %d ? %d : t > %d ? %d : t; })' % (T, S, S, lo, lo, hi, hi))
            s['psubs' + sfx] = (bits, '(%s)({ int t = (%s)x - (%s)y; t < %d ? %d : t > %d ? %d : t; })' % (T, S, S, lo, lo, hi, hi))
            s['paddus' + sfx] = (bits, '(%s)({ unsigned t = (unsigned)x + y; t > %d ? %d : t; })' % (T, mx, mx))
            s['psubus' + sfx] = (bits, '(%s)(x > y ? x - y : 0)' % T)
            s['pavg' + sfx] = (bits, '(%s)(((unsigned)x + y + 1) >> 1)' % T)
        s['pcmpeq' + sfx] = (bits, '(%s)(x == y ? %d : 0)' % (T, mx))
        s['pcmpgt' + sfx] = (bits, '(%s)((%s)x > (%s)y ? %d : 0)' % (T, S, S, mx))
    s['pmullw'] = (16, '(u16)((i32)(i16)x * (i32)(i16)y)')
    s['pmulhw'] = (16, '(u16)(((i32)(i16)x * (i32)(i16)y) >> 16)')
    s['pmulhuw'] = (16, '(u16)(((u32)x * (u32)y) >> 16)')
    s['pmaxsw'] = (16, '((i16)x > (i16)y ? x : y)')
    s['pminsw'] = (16, '((i16)x < (i16)y ? x : y)')
    s['pmaxub'] = (8, '(x > y ? x : y)')
    s['pminub'] = (8, '(x < y ? x : y)')
    s['pand'] = s['andps'] = s['andpd'] = (64, '(x & y)')
    s['pandn'] = s['andnps'] = s['andnpd'] = (64, '(~x & y)')
    s['por'] = s['orps'] = s['orpd'] = (64, '(x | y)')
    s['pxor'] = s['xorps'] = s['xorpd'] = (64, '(x ^ y)')
    return s


LANE = lane_ops()


def emit_lane(width, bits, expr):
    n = width * 8 // bits
    T = UT[bits]
    return ['{ %s xs[%d], ys[%d], rs[%d]; memcpy(xs, &a, %d); memcpy(ys, &b, %d);' % (T, n, n, n, width, width),
            '  for (int i = 0; i < %d; i++) { %s x = xs[i], y = ys[i]; rs[i] = %s; }' % (n, T, expr),
            '  RETT out = 0; memcpy(&out, rs, %d); return out; }' % width]


def emit_shift(width, bits, kind):
    n = width * 8 // bits
    T, S = UT[bits], IT[bits]
    if kind == 'll':
        op = 'c >= %d ? 0 : (%s)(x << c)' % (bits, T)
    elif kind == 'rl':
        op = 'c >= %d ? 0 : (%s)(x >> c)' % (bits, T)
    else:
        op = '(%s)((%s)x >> (c >= %d ? %d : c))' % (T, S, bits, bits - 1)
    return ['{ %s xs[%d], rs[%d]; memcpy(xs, &a, %d); u64 c = (u64)b;' % (T, n, n, width),
            '  for (int i = 0; i < %d; i++) { %s x = xs[i]; rs[i] = %s; }' % (n, T, op),
            '  RETT out = 0; memcpy(&out, rs, %d); return out; }' % width]


def emit_unpack(width, bits, high):
    n = width * 8 // bits
    T = UT[bits]
    h = n // 2
    off = h if high else 0
    return ['{ %s xs[%d], ys[%d], rs[%d]; memcpy(xs, &a, %d); memcpy(ys, &b, %d);' % (T, n, n, n, width, width),
            '  for (int i = 0; i < %d; i++) { rs[2*i] = xs[%d + i]; rs[2*i+1] = ys[%d + i]; }' % (h, off, off),
            '  RETT out = 0; memcpy(&out, rs, %d); return out; }' % width]


def emit_pack(width, src_bits, unsigned_sat):
    dst_bits = src_bits // 2
    n = width * 8 // src_bits
    ST, DT = IT[src_bits], UT[dst_bits]
    if unsigned_sat:
        lo, hi = 0, (1 << dst_bits) - 1
    else:
        lo, hi = -(1 << (dst_bits - 1)), (1 << (dst_bits - 1)) - 1
    sat = '(%s)(v < %d ? %d : v > %d ? %d : v)' % (DT, lo, lo, hi, hi)
    return ['{ %s xs[%d], ys[%d]; %s rs[%d]; memcpy(xs, &a, %d); memcpy(ys, &b, %d);' % (ST, n, n, DT, 2 * n, width, width),
            '  for (int i = 0; i < %d; i++) { i64 v = xs[i]; rs[i] = %s; }' % (n, sat),
            '  for (int i = 0; i < %d; i++) { i64 v = ys[i]; rs[%d + i] = %s; }' % (n, n, sat),
            '  RETT out = 0; memcpy(&out, rs, %d); return out; }' % width]


FOP = {'add': 'x + y', 'sub': 'x - y', 'mul': 'x * y', 'div': 'x / y', 'min': '(x < y ? x : y)', 'max': '(x > y ? x : y)'}


def gen_body(base, R, A):
    n = len(A)
    if base.startswith('v') and not base[1:].startswith(('ucomis', 'comis')):
        # VEX 3 オペランド形は同名 SSE 形へ委譲する (dst 上位は src1 由来で、SSE 形の a 由来と一致する)。
        # comis/ucomis は flag 未モデルのため委譲せず未実装 stub のまま残す (黙って no-op にしない)
        sse = gen_body(base[1:], R, A)
        if sse is not None:
            return sse
    if base in ('pause', 'sfence', 'emms', 'vzeroupper', 'lfence', 'mfence', 'fnclex', 'fnclex0'):
        return ['return 0;']
    if base in ('ldmxcsr', 'stmxcsr'):
        return ['(void)a;']
    if base.startswith('ucomis') or base.startswith('comis'):
        # PLUG_COMIS_FLAGS=1: comis_flags.py が flag を反映した呼出しは消え、残った呼出し (flag slot の無い関数) は unimpl に出す (#3242)
        if os.environ.get('PLUG_COMIS_FLAGS') == '1':
            return None
        return ['(void)a; (void)b; /* flag は IR 側に未反映 (m6 の ir6 [P1] 相当は未移植; 既知の限界) */']
    if base == 'xgetbv':
        return ['return 0; /* OSXSAVE/AVX を広告しない */']
    if base in ('prefetcht0', 'prefetcht1', 'prefetcht2', 'prefetchnta', 'prefetchw') and R == 'void':
        return ['(void)a; /* hint のみ: 状態を変えない */']
    cm = re.match(r'^cmp(eq|lt|le|unord|neq|nlt|nle|ord)(ps|pd)$', base)
    if cm and n == 2 and R == 'i128' and A == ['i128', 'i128']:
        pred, w = cm.groups()
        T, k, U = ('float', 4, 'u32') if w == 'ps' else ('double', 2, 'u64')
        cond = {'eq': 'x == y', 'lt': 'x < y', 'le': 'x <= y', 'unord': '(x != x || y != y)',
                'neq': '!(x == y)', 'nlt': '!(x < y)', 'nle': '!(x <= y)', 'ord': '(x == x && y == y)'}[pred]
        return ['{ %s xs[%d], ys[%d]; %s rs[%d]; memcpy(xs, &a, 16); memcpy(ys, &b, 16);' % (T, k, k, U, k),
                '  for (int i = 0; i < %d; i++) { %s x = xs[i], y = ys[i]; rs[i] = (%s) ? (%s)~(%s)0 : 0; }' % (k, T, cond, U, U),
                '  u128 o; memcpy(&o, rs, 16); return o; }']
    if base in ('movmskps', 'movmskpd') and n == 1 and A[0] == 'i128':
        k, b = (4, 31) if base == 'movmskps' else (2, 63)
        return ['{ u%d xs[%d]; memcpy(xs, &a, 16); u32 m = 0; for (int i = 0; i < %d; i++) m |= (u32)(xs[i] >> %d) << i; return m; }' % (b + 1, k, k, b)]
    if base == 'rep_movsd_memcpy' and R == 'void' and n == 3:
        # rep movsd (DF=0): dword を前方へ 1 個ずつ。 dst が src の直後で重なる場合は memmove と結果が違うので前方ループを維持する
        return ['u8* d = (u8*)a; const u8* s = (const u8*)b;',
                'if (d <= s || d >= s + (size_t)c * 4u) { memmove(d, s, (size_t)c * 4u); }',
                'else { for (u64 i = 0; i < c; i++) { u32 t = ((const volatile u32*)s)[i]; ((volatile u32*)d)[i] = t; } }']
    if base == 'rep_movsq_memcpy':
        return ['memmove(a, b, (size_t)c * 8u); /* rep movsq: c = qword 数 */']
    if base == 'int3' and n == 0:
        return ['abort(); /* int3: 到達すれば意図しない trap */'] + ([] if R == 'void' else ['return 0;'])
    if base == 'int' and n == 1:
        return ['(void)a; abort(); /* int n: 到達すれば意図しない trap */']
    if base == 'rep_movsb_memcpy' and R == 'void' and n == 3:
        return ['u8* d = (u8*)a; const u8* s = (const u8*)b;',
                'if (d <= s || d >= s + (size_t)c) { memmove(d, s, (size_t)c); }',
                'else { for (u64 i = 0; i < c; i++) d[i] = s[i]; }']
    if base == 'rep_stosw_memset' and n == 3 and A == ['ptr', 'i16', 'i64']:
        return ['u16* p = (u16*)a; for (u64 i = 0; i < c; i++) p[i] = (u16)b; /* rep stosw: c = word 数 */']
    if base == 'rep_stosq_memset':
        return ['u64* p = (u64*)a; for (u64 i = 0; i < c; i++) p[i] = b; /* rep stosq */']
    if base == 'rep_stosb_memset' and n == 3 and A == ['ptr', 'i8', 'i64']:
        return ['memset(a, (int)(b & 0xffu), (size_t)c); /* rep stosb: b = AL, c = byte 数 */']
    if base in ('movaps', 'movapd', 'movdqa', 'movdqu', 'movups', 'movupd', 'lddqu', 'vmovaps', 'vmovapd', 'vmovdqa', 'vmovdqu', 'vmovups', 'vmovupd') and n == 1:
        return {'i128': ['return a;'], 'i64': ['return (u64)a;'], 'i32': ['return (u32)a;']}.get(R)
    if base in ('movaps', 'movapd', 'movdqa', 'movdqu', 'movups', 'movupd', 'movntps') and R == 'void':
        return ['(void)a; (void)b; /* store: RetDec が dst を引数に持たない no-op */']
    if base == 'movss':
        if n == 1 and A[0] == 'i32' and R == 'i128': return ['return set_u32_lo(a);']
        if n == 1 and A[0] == 'i128': return ['return (%s)(u32)a;' % CT[R]]
        if n == 2 and R == 'i128': return ['return (a & ~(u128)0xFFFFFFFFu) | (u32)b;']
    if base == 'movsd':
        if n == 1 and A[0] == 'i64' and R == 'i128': return ['return set_u64_lo(a);']
        if n == 1 and A[0] == 'i128': return ['return (%s)(u64)a;' % CT[R]]
        if n == 2 and R == 'i128': return ['return _overwrite_lo64(a, (u64)b);']
    if base == 'movd':
        if n == 1 and R == 'i128': return ['return set_u32_lo((u32)a);']
        if n == 1: return ['return (%s)(u32)a;' % CT[R]]
    if base == 'movq':
        if R == 'void': return ['(void)a; (void)b;']
        if n == 1 and R == 'i128': return ['return set_u64_lo((u64)a);']
        if n == 1: return ['return (%s)(u64)a;' % CT[R]]
    if base in ('movlps', 'movlpd'):
        return ['(void)a; (void)b;'] if R == 'void' else ['return _overwrite_lo64(a, (u64)b);']
    if base in ('movhps', 'movhpd'):
        return ['(void)a; (void)b;'] if R == 'void' else ['return _overwrite_hi64(a, (u64)b);']
    if base == 'movhlps': return ['return _overwrite_lo64(a, lane1_u(b));']
    if base == 'movlhps': return ['return _overwrite_hi64(a, lane0_u(b));']
    sm = re.match(r'^(add|sub|mul|div|min|max)(sd|ss)$', base)
    if sm and n == 2 and R == 'i128':
        op, w = sm.groups()
        if w == 'sd':
            y = 'asd(b)' if A[1] == 'i64' else 'lane0_d(b)'
            x, setf, ty = 'lane0_d(a)', 'lane0d_set', 'double'
        else:
            y = 'asf(b)' if A[1] == 'i32' else 'lane0_f(b)'
            x, setf, ty = 'lane0_f(a)', 'lane0f_set', 'float'
        ex = FOP[op].replace('x', 'X').replace('y', 'Y')
        return ['%s X = %s, Y = %s; return %s(a, %s);' % (ty, x, y, setf, ex)]
    if base == 'sqrtsd' and n == 1: return ['return lane0d_set(a, sqrt(lane0_d(a)));']
    if base == 'sqrtss' and n == 1: return ['return lane0f_set(a, sqrtf(lane0_f(a)));']
    pm = re.match(r'^v?(add|sub|mul|div|min|max)(ps|pd)$', base)
    if pm and n == 2 and A == ['i128', 'i128']:
        op, w = pm.groups()
        T, k = ('float', 4) if w == 'ps' else ('double', 2)
        return ['{ %s xs[%d], ys[%d], rs[%d]; memcpy(xs, &a, 16); memcpy(ys, &b, 16);' % (T, k, k, k),
                '  for (int i = 0; i < %d; i++) { %s x = xs[i], y = ys[i]; rs[i] = %s; }' % (k, T, FOP[op]),
                '  u128 o; memcpy(&o, rs, 16); return o; }']
    if base == 'cvtsi2ss' and n == 2 and A[1] == 'i32' and R == 'i128':
        return ['return lane0f_set(a, (float)(i32)b);']
    if base == 'cvtss2sd' and n == 2 and R == 'i128':
        return ['return _overwrite_lo64(a, das((double)lane0_f(b)));']
    if base == 'cvtsd2ss' and n == 2 and R == 'i128':
        return ['return lane0f_set(a, (float)lane0_d(b));']
    if base == 'cvtsi2sd' and n == 1:
        return ['return set_u64_lo(das((double)%s));' % ('(i64)a' if A[0] == 'i64' else '(i32)a')]
    if base == 'cvtsi2ss' and n == 1:
        return ['return set_u32_lo(fas((float)%s));' % ('(i64)a' if A[0] == 'i64' else '(i32)a')]
    if base == 'cvtss2sd' and n == 1:
        return ['return _overwrite_lo64(a, das((double)lane0_f(a)));'] if A[0] == 'i128' else ['return set_u64_lo(das((double)asf(a)));']
    if base == 'cvtsd2ss' and n == 1:
        return ['return lane0f_set(a, (float)lane0_d(a));'] if A[0] == 'i128' else ['return set_u32_lo(fas((float)asd(a)));']
    if base in ('cvttsd2si', 'cvtsd2si', 'cvttss2si', 'cvtss2si') and n == 1:
        v = 'lane0_d(a)' if 'sd' in base else '(double)lane0_f(a)'
        f = 'trunc' if base.startswith('cvtt') else 'nearbyint'
        if R == 'i32':
            return ['double v = %s(%s); if (!(v > -2147483649.0 && v < 2147483648.0)) return 0x80000000u; return (u32)(i32)v;' % (f, v)]
        return ['double v = %s(%s); if (!(v > -9223372036854775809.0 && v < 9223372036854775808.0)) return 0x8000000000000000ull; return (u64)(i64)v;' % (f, v)]
    if base in ('cvtps2dq', 'cvttps2dq'):
        f = 'nearbyintf' if base == 'cvtps2dq' else 'truncf'
        return ['{ float xs[4]; i32 rs[4]; memcpy(xs, &a, 16);',
                '  for (int i = 0; i < 4; i++) { float v = %s(xs[i]); rs[i] = (v > -2147483649.0f && v < 2147483648.0f) ? (i32)v : (i32)0x80000000; }' % f,
                '  u128 o; memcpy(&o, rs, 16); return o; }']
    if base == 'cvtdq2ps':
        return ['{ i32 xs[4]; float rs[4]; memcpy(xs, &a, 16); for (int i = 0; i < 4; i++) rs[i] = (float)xs[i]; u128 o; memcpy(&o, rs, 16); return o; }']
    if base == 'cvtps2pd':
        return ['{ float xs[4]; double rs[2]; memcpy(xs, &a, 16); rs[0] = xs[0]; rs[1] = xs[1]; u128 o; memcpy(&o, rs, 16); return o; }']
    if base == 'cvtpd2ps':
        return ['{ double xs[2]; float rs[4] = {0, 0, 0, 0}; memcpy(xs, &a, 16); rs[0] = (float)xs[0]; rs[1] = (float)xs[1]; u128 o; memcpy(&o, rs, 16); return o; }']
    if base == 'cvtdq2pd':
        return ['{ i32 xs[4]; double rs[2]; memcpy(xs, &a, 16); rs[0] = xs[0]; rs[1] = xs[1]; u128 o; memcpy(&o, rs, 16); return o; }']
    if base in ('cvtpd2dq', 'cvttpd2dq') and n == 1 and A[0] == 'i128' and R == 'i128':
        f = 'trunc' if base.startswith('cvtt') else 'nearbyint'
        return ['{ double xs[2]; i32 rs[4] = {0, 0, 0, 0}; memcpy(xs, &a, 16);',
                '  for (int i = 0; i < 2; i++) { double v = %s(xs[i]); rs[i] = (v > -2147483649.0 && v < 2147483648.0) ? (i32)v : (i32)0x80000000; }' % f,
                '  u128 o; memcpy(&o, rs, 16); return o; }']
    if base == 'pmovsxdq' and n == 1 and A[0] == 'i128':
        return ['{ i32 xs[4]; i64 rs[2]; memcpy(xs, &a, 16); rs[0] = xs[0]; rs[1] = xs[1]; u128 o; memcpy(&o, rs, 16); return o; }']
    fm = re.match(r'^vf(n?)m(add|sub)(132|213|231)sd$', base)
    if fm and n == 3 and A[:2] == ['i128', 'i128'] and A[2] in ('i64', 'i128') and R == 'i128':
        neg, sub, order = fm.groups()
        stem = ('fn' if neg else 'f') + 'm' + ('s' if sub == 'sub' else ('' if neg else 'a'))
        c = 'asd(c)' if A[2] == 'i64' else 'lane0_d(c)'
        return ['return _%s%ssd(a, b, %s);' % (stem, order, c)]
    width = 16 if A and A[0] == 'i128' else 8
    if base in LANE and n == 2 and A[0] == A[1]:
        bits, expr = LANE[base]
        return emit_lane(width, bits, expr)
    sh = re.match(r'^ps(ll|rl|ra)(w|d|q)$', base)
    if sh and n == 2:
        return emit_shift(width, {'w': 16, 'd': 32, 'q': 64}[sh.group(2)], sh.group(1))
    if base in ('pslldq', 'psrldq') and n == 2:
        return ['return %s;' % ('a << (8u * (b > 15 ? 16 : b))' if base == 'pslldq' else 'a >> (8u * (b > 15 ? 16 : b))')]
    up = re.match(r'^punpck(l|h)(bw|wd|dq)$', base)
    if up and n == 2:
        return emit_unpack(width, {'bw': 8, 'wd': 16, 'dq': 32}[up.group(2)], up.group(1) == 'h')
    if base == 'punpcklqdq': return ['return _overwrite_hi64(a, lane0_u(b));']
    if base == 'punpckhqdq': return ['return lane1_u(a) | ((u128)lane1_u(b) << 64);']
    if base == 'packssdw' and n == 2: return emit_pack(width, 32, False)
    if base == 'packsswb' and n == 2: return emit_pack(width, 16, False)
    if base == 'packuswb' and n == 2: return emit_pack(width, 16, True)
    if base == 'pshufd' and n == 2:
        return ['{ u32 xs[4], rs[4]; memcpy(xs, &a, 16); for (int i = 0; i < 4; i++) rs[i] = xs[(b >> (2 * i)) & 3]; u128 o; memcpy(&o, rs, 16); return o; }']
    if base == 'pshuflw' and n == 2:
        return ['{ u16 xs[8], rs[8]; memcpy(xs, &a, 16); memcpy(rs, xs, 16); for (int i = 0; i < 4; i++) rs[i] = xs[(b >> (2 * i)) & 3]; u128 o; memcpy(&o, rs, 16); return o; }']
    if base == 'pshufhw' and n == 2:
        return ['{ u16 xs[8], rs[8]; memcpy(xs, &a, 16); memcpy(rs, xs, 16); for (int i = 0; i < 4; i++) rs[4 + i] = xs[4 + ((b >> (2 * i)) & 3)]; u128 o; memcpy(&o, rs, 16); return o; }']
    if base == 'pshufw' and n == 2:
        return ['{ u16 xs[4], rs[4]; memcpy(xs, &a, 8); for (int i = 0; i < 4; i++) rs[i] = xs[(b >> (2 * i)) & 3]; u64 o; memcpy(&o, rs, 8); return o; }']
    if base == 'shufps' and n == 3:
        return ['{ u32 xs[4], ys[4], rs[4]; memcpy(xs, &a, 16); memcpy(ys, &b, 16);',
                '  rs[0] = xs[c & 3]; rs[1] = xs[(c >> 2) & 3]; rs[2] = ys[(c >> 4) & 3]; rs[3] = ys[(c >> 6) & 3];',
                '  u128 o; memcpy(&o, rs, 16); return o; }']
    if base in ('unpcklps', 'unpckhps'):
        return emit_unpack(16, 32, base == 'unpckhps')
    if base == 'unpcklpd': return ['return _overwrite_hi64(a, lane0_u(b));']
    if base == 'unpckhpd': return ['return lane1_u(a) | ((u128)lane1_u(b) << 64);']
    if base == 'pmovmskb' and n == 1:
        return ['{ u8 xs[16]; memcpy(xs, &a, 16); u32 m = 0; for (int i = 0; i < 16; i++) m |= (u32)(xs[i] >> 7) << i; return m; }']
    return None


CPUID_BODY = [
    '{ cpuid_t r = {0, 0, 0, 0};',
    '  switch (a) {',
    '  case 0: r.a = 0x0d; r.b = 0x756e6547; r.d = 0x49656e69; r.c = 0x6c65746e; break; /* GenuineIntel */',
    '  case 1: r.a = 0x000306a9; r.b = 0x00000800; r.c = 0; r.d = 0x078bfbff & ~(1u << 28) & ~(1u << 21) & ~(1u << 22); break; /* SSE2 まで広告 (SSE3/AVX/FMA/OSXSAVE なし, HTT なし) */',
    '  case 0x80000000u: r.a = 0x80000008; break;',
    '  case 0x80000001u: r.d = 0x20100800; break;',
    '  case 0x80000002u: r.a = 0x3131204d; r.b = 0x73616d77; r.c = 0x7478206d; r.d = 0x00003638; break;',
    '  default: break;',
    '  }',
    '  return r; }']

out = ['/* m11_simd.c — auto-generated by m11_simd2.py from %s (署名駆動; 手編集禁止) */' % sys.argv[1],
       '#include "../msimd11_core.h"',
       'typedef unsigned short u16; typedef short i16; typedef signed char i8;',
       'typedef struct { u32 a, b, c, d; } cpuid_t;',
       'static int m11_simd_unimpl_once(const char* n) { static int cnt = 0; if (cnt++ < 64) fprintf(stderr, "[m11][simd-unimpl] %s\\n", n); return 0; }',
       '']
seen = set()
for (ret, full, args) in sorted(DECL, key=lambda t: t[1]):
    if full in seen:
        continue
    seen.add(full)
    A = tys_of(args)
    base = base_of(full)
    if 'i256' in A or ret == 'i256':
        STATS['i256_trap'] += 1
        ps = ', '.join('u64 p%d' % i for i in range(4 * sum(1 for t in A if t == 'i256')))
        if ret == 'i256':
            ps = 'void* sret' + (', ' + ps if ps else '')
        out.append('EMSCRIPTEN_KEEPALIVE void %s(%s) { fprintf(stderr, "[m11][simd-i256] %s called (AVX 経路; 未実装)\\n"); abort(); }' % (full, ps or 'void', full))
        continue
    if base == 'cpuid':
        out.append('EMSCRIPTEN_KEEPALIVE cpuid_t %s(u32 a)' % full)
        out.append('{')
        out.extend('    ' + l for l in CPUID_BODY)
        out.append('}')
        STATS['impl'] += 1
        continue
    ct = lambda t: CT.get(t, 'u64')
    params = ', '.join('%s %s' % (ct(t), 'abcdefghijklmnop'[i]) for i, t in enumerate(A)) or 'void'
    body = gen_body(base, ret, A)
    if body is None:
        UNIMPL.append('%s %s(%s)' % (ret, full, ','.join(A)))
        STATS['unimpl'] += 1
        rv = '' if ret == 'void' else ' return 0;'
        out.append('EMSCRIPTEN_KEEPALIVE %s %s(%s) { m11_simd_unimpl_once("%s");%s }' % (ct(ret), full, params, full, rv))
        continue
    STATS['impl'] += 1
    rett = ct(ret)
    out.append('EMSCRIPTEN_KEEPALIVE %s %s(%s)' % (rett, full, params))
    out.append('{')
    out.extend('    ' + l.replace('RETT', rett) for l in body)
    out.append('}')
print('\n'.join(out))
sys.stderr.write('[simd2] declares %d: implemented %d, unimplemented %d, i256 trap %d\n' % (
    len(seen), STATS['impl'], STATS['unimpl'], STATS['i256_trap']))
for u in UNIMPL:
    sys.stderr.write('   unimplemented: %s\n' % u)
