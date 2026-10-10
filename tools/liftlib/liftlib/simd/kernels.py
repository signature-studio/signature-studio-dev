"""kernels.py — x86 SIMD mnemonic の C 実装テーブル (宣言シグネチャ駆動)。

lookup(base, ret, args) -> Spec | None
  base : サフィックス除去済み mnemonic (例 'mulss', 'vfmadd213sd')
  ret  : 'x'(i128) 'q'(i64) 'd'(i32) 'w' 'b' 'v'(void) 'y'(i256)
  args : 型タグのリスト (RetDec の pseudo-asm 引数: 命令の *read* operand を順に渡す)

RetDec の引数規約 (capstone operand access 由来, 3 バイナリの declare で確認):
  - RMW dst (addss xmm1,xmm2) は (dst_old, src), write-only dst (cvtsi2ss, sqrtss, movss load, pshufd) は (src) のみ
  - VEX 3-operand は (src1, src2[, imm]) (dst は write-only なので渡されない)
  - メモリ operand は読出済みスカラ値 (i32/i64) または 128bit (i128)
  - ストア (movss [m],xmm) は src 低位の値を返す (i64/i32)
Spec は C 本体 (引数名 p0,p1,p2) と, 実機 inline asm による検証用テンプレートを持つ。
"""
from collections import namedtuple

Spec = namedtuple("Spec", "body asm ops result imms exact note")


def S(body, asm=None, ops="", result=None, imms=None, exact=True, note=""):
    return Spec(body, asm, ops, result, imms, exact, note)


def f32(i, t):
    return {"x": "F32L(p%d)" % i, "d": "ASF(p%d)" % i}.get(t)


def f64(i, t):
    return {"x": "F64L(p%d)" % i, "q": "ASD(p%d)" % i}.get(t)


IMM_SHUF = [0x00, 0x1b, 0xe4, 0x4e, 0xb1, 0x55, 0xaa, 0xff, 0x36]
IMM_SH = [0, 1, 3, 7, 8, 15, 16, 31, 32, 33, 63, 64, 127, 255]
IMM_B = [0, 1, 2, 3, 4, 7, 8, 15]

# ---------------------------------------------------------------------------------
# 共通 asm 形
# ---------------------------------------------------------------------------------


def asm_binop(mn, vex, t1):
    """(x, T)->x : dst RMW + src (reg/mem)。 T=x -> reg or m128, d -> m32, q -> m64"""
    c = "x" if t1 == "x" else "m"
    if vex:
        return "v%s %%[p1], %%[p0], %%[r]" % mn, "r:=x p0:x p1:%s" % c, "r"
    return "%s %%[p1], %%[p0]" % mn, "p0:+x p1:%s" % c, "p0"


def asm_unop(mn, vex, t0):
    """(T)->x : write-only dst (r preset 0), src reg / mem / gpr"""
    c = {"x": "x", "d": "m", "q": "m"}[t0]
    return "%s%s %%[p0], %%[r]" % ("v" if vex else "", mn), "r:+x p0:%s" % c, "r"


def asm_vex_unop_rr(mn, t1):
    """VEX (x, T)->x の dst-merge 形 (vcvtss2sd, vsqrtss, vcvtsi2ss): vM src2, src1, dst"""
    c = {"x": "x", "d": "m", "q": "m"}[t1]
    return "v%s %%[p1], %%[p0], %%[r]" % mn, "r:=x p0:x p1:%s" % c, "r"


# ---------------------------------------------------------------------------------
# スカラ FP: add/sub/mul/div/min/max (ss/sd), sqrt
# ---------------------------------------------------------------------------------
SC_OPS = {"add": "{a} + {b}", "sub": "{a} - {b}", "mul": "{a} * {b}", "div": "{a} / {b}",
          "min": "x86_min{k}({a}, {b})", "max": "x86_max{k}({a}, {b})"}


def fam_scalar_bin(b, vex, R, A):
    for op, expr in SC_OPS.items():
        for sfx, lane, conv, k in (("ss", "f", f32, "f"), ("sd", "g", f64, "d")):
            if b != op + sfx:
                continue
            if R != "x" or len(A) != 2 or A[0] != "x" or conv(1, A[1]) is None:
                return None
            e = expr.format(a="a.%s[0]" % lane, b=conv(1, A[1]), k=k)
            body = "V a = VQ(p0); a.%s[0] = %s; return a.q;" % (lane, e)
            asm, ops, res = asm_binop(b, vex, A[1])
            return S(body, asm, ops, res)
    return None


def fam_scalar_sqrt(b, vex, R, A):
    for sfx, lane, conv, sq in (("ss", "f", f32, "sqrtf"), ("sd", "g", f64, "sqrt")):
        if b != "sqrt" + sfx:
            continue
        if R != "x":
            return None
        if len(A) == 1 and conv(0, A[0]):
            body = "V r; r.q = 0; r.%s[0] = __builtin_%s(%s); return r.q;" % (lane, sq, conv(0, A[0]))
            asm, ops, res = asm_unop(b, False, A[0])
            if vex:
                return None
            return S(body, asm, ops, res, note="dst 上位 lane は RetDec が dst_old を渡さないため 0")
        if len(A) == 2 and A[0] == "x" and conv(1, A[1]):
            body = "V a = VQ(p0); a.%s[0] = __builtin_%s(%s); return a.q;" % (lane, sq, conv(1, A[1]))
            asm, ops, res = asm_vex_unop_rr(b, A[1])
            return S(body, asm, ops, res)
    return None


# ---------------------------------------------------------------------------------
# packed FP
# ---------------------------------------------------------------------------------
def fam_packed_bin(b, vex, R, A):
    if R != "x" or A != ["x", "x"]:
        return None
    for op, sym in (("add", "+"), ("sub", "-"), ("mul", "*"), ("div", "/")):
        if b == op + "ps":
            body = "V a = VQ(p0), b = VQ(p1); for (int i = 0; i < 4; i++) a.f[i] = a.f[i] %s b.f[i]; return a.q;" % sym
            return S(body, *asm_binop(b, vex, "x"))
        if b == op + "pd":
            body = "V a = VQ(p0), b = VQ(p1); for (int i = 0; i < 2; i++) a.g[i] = a.g[i] %s b.g[i]; return a.q;" % sym
            return S(body, *asm_binop(b, vex, "x"))
    for op in ("min", "max"):
        if b == op + "ps":
            body = "V a = VQ(p0), b = VQ(p1); for (int i = 0; i < 4; i++) a.f[i] = x86_%sf(a.f[i], b.f[i]); return a.q;" % op
            return S(body, *asm_binop(b, vex, "x"))
        if b == op + "pd":
            body = "V a = VQ(p0), b = VQ(p1); for (int i = 0; i < 2; i++) a.g[i] = x86_%sd(a.g[i], b.g[i]); return a.q;" % op
            return S(body, *asm_binop(b, vex, "x"))
    if b == "addsubpd":
        return S("V a = VQ(p0), b = VQ(p1); a.g[0] = a.g[0] - b.g[0]; a.g[1] = a.g[1] + b.g[1]; return a.q;", *asm_binop(b, vex, "x"))
    if b == "addsubps":
        return S("V a = VQ(p0), b = VQ(p1); for (int i = 0; i < 4; i++) a.f[i] = (i & 1) ? a.f[i] + b.f[i] : a.f[i] - b.f[i]; return a.q;", *asm_binop(b, vex, "x"))
    if b == "haddps":
        return S("V a = VQ(p0), b = VQ(p1), r; r.f[0] = a.f[0] + a.f[1]; r.f[1] = a.f[2] + a.f[3]; r.f[2] = b.f[0] + b.f[1]; r.f[3] = b.f[2] + b.f[3]; return r.q;", *asm_binop(b, vex, "x"))
    if b == "haddpd":
        return S("V a = VQ(p0), b = VQ(p1), r; r.g[0] = a.g[0] + a.g[1]; r.g[1] = b.g[0] + b.g[1]; return r.q;", *asm_binop(b, vex, "x"))
    if b == "hsubps":
        return S("V a = VQ(p0), b = VQ(p1), r; r.f[0] = a.f[0] - a.f[1]; r.f[1] = a.f[2] - a.f[3]; r.f[2] = b.f[0] - b.f[1]; r.f[3] = b.f[2] - b.f[3]; return r.q;", *asm_binop(b, vex, "x"))
    if b == "hsubpd":
        return S("V a = VQ(p0), b = VQ(p1), r; r.g[0] = a.g[0] - a.g[1]; r.g[1] = b.g[0] - b.g[1]; return r.q;", *asm_binop(b, vex, "x"))
    return None


def fam_packed_un(b, vex, R, A):
    if R != "x" or A != ["x"]:
        return None
    if b == "sqrtps":
        return S("V a = VQ(p0), r; for (int i = 0; i < 4; i++) r.f[i] = __builtin_sqrtf(a.f[i]); return r.q;", *asm_unop(b, vex, "x"))
    if b == "sqrtpd":
        return S("V a = VQ(p0), r; for (int i = 0; i < 2; i++) r.g[i] = __builtin_sqrt(a.g[i]); return r.q;", *asm_unop(b, vex, "x"))
    if b == "rcpps":
        return S("V a = VQ(p0), r; for (int i = 0; i < 4; i++) r.f[i] = approx_rcp(a.f[i]); return r.q;", *asm_unop(b, vex, "x"), exact=False,
                 note="近似命令 (実機は 12bit テーブル): 相対誤差 < 1.5*2^-12 で検証")
    if b == "rsqrtps":
        return S("V a = VQ(p0), r; for (int i = 0; i < 4; i++) r.f[i] = approx_rsqrt(a.f[i]); return r.q;", *asm_unop(b, vex, "x"), exact=False,
                 note="近似命令: 相対誤差 < 1.5*2^-12 で検証")
    if b == "rcpss":
        return S("V a = VQ(p0), r; r.q = 0; r.f[0] = approx_rcp(a.f[0]); return r.q;", *asm_unop(b, vex, "x"), exact=False, note="近似命令")
    if b == "rsqrtss":
        return S("V a = VQ(p0), r; r.q = 0; r.f[0] = approx_rsqrt(a.f[0]); return r.q;", *asm_unop(b, vex, "x"), exact=False, note="近似命令")
    return None


# ---------------------------------------------------------------------------------
# 論理 / 整数 packed
# ---------------------------------------------------------------------------------
LOGIC = {"andps": "p0 & p1", "andpd": "p0 & p1", "pand": "p0 & p1", "orps": "p0 | p1", "orpd": "p0 | p1", "por": "p0 | p1",
         "xorps": "p0 ^ p1", "xorpd": "p0 ^ p1", "pxor": "p0 ^ p1", "andnps": "~p0 & p1", "andnpd": "~p0 & p1", "pandn": "~p0 & p1"}


def fam_logic(b, vex, R, A):
    if b in LOGIC and R == "x" and A == ["x", "x"]:
        return S("return %s;" % LOGIC[b], *asm_binop(b, vex, "x"))
    return None


INT_LANES = {"b": ("c", 16), "w": ("s", 8), "d": ("i", 4), "q": ("l", 2)}


def fam_int_arith(b, vex, R, A):
    if R != "x" or A != ["x", "x"]:
        return None
    for op, sym in (("padd", "+"), ("psub", "-")):
        for sfx, (lane, n) in INT_LANES.items():
            if b == op + sfx:
                ut = {"c": "u8", "s": "u16", "i": "u32", "l": "u64"}[lane]
                body = ("V a = VQ(p0), b = VQ(p1); for (int i = 0; i < %d; i++) { %s x = (%s)a.%s[i] %s (%s)b.%s[i]; a.%s[i] = (typeof(a.%s[0]))x; } return a.q;"
                        % (n, ut, ut, lane, sym, ut, lane, lane, lane))
                return S(body, *asm_binop(b, vex, "x"))
    for sfx, (lane, n) in INT_LANES.items():
        if b == "pcmpeq" + sfx:
            body = "V a = VQ(p0), b = VQ(p1); for (int i = 0; i < %d; i++) a.%s[i] = (a.%s[i] == b.%s[i]) ? -1 : 0; return a.q;" % (n, lane, lane, lane)
            return S(body, *asm_binop(b, vex, "x"))
        if b == "pcmpgt" + sfx:
            body = "V a = VQ(p0), b = VQ(p1); for (int i = 0; i < %d; i++) a.%s[i] = (a.%s[i] > b.%s[i]) ? -1 : 0; return a.q;" % (n, lane, lane, lane)
            return S(body, *asm_binop(b, vex, "x"))
    if b == "pmullw":
        return S("V a = VQ(p0), b = VQ(p1); for (int i = 0; i < 8; i++) a.s[i] = (int16_t)(a.s[i] * b.s[i]); return a.q;", *asm_binop(b, vex, "x"))
    if b == "pmulld":
        return S("V a = VQ(p0), b = VQ(p1); for (int i = 0; i < 4; i++) a.w[i] = a.w[i] * b.w[i]; return a.q;", *asm_binop(b, vex, "x"))
    if b == "pmuludq":
        return S("V a = VQ(p0), b = VQ(p1), r; r.d[0] = (u64)a.w[0] * b.w[0]; r.d[1] = (u64)a.w[2] * b.w[2]; return r.q;", *asm_binop(b, vex, "x"))
    if b == "pmaddwd":
        return S("V a = VQ(p0), b = VQ(p1), r; for (int i = 0; i < 4; i++) r.i[i] = a.s[2*i] * b.s[2*i] + a.s[2*i+1] * b.s[2*i+1]; return r.q;", *asm_binop(b, vex, "x"))
    # unpack / pack
    if b in ("unpcklps", "punpckldq"):
        return S("V a = VQ(p0), b = VQ(p1), r; r.w[0] = a.w[0]; r.w[1] = b.w[0]; r.w[2] = a.w[1]; r.w[3] = b.w[1]; return r.q;", *asm_binop(b, vex, "x"))
    if b in ("unpckhps", "punpckhdq"):
        return S("V a = VQ(p0), b = VQ(p1), r; r.w[0] = a.w[2]; r.w[1] = b.w[2]; r.w[2] = a.w[3]; r.w[3] = b.w[3]; return r.q;", *asm_binop(b, vex, "x"))
    if b in ("unpcklpd", "punpcklqdq"):
        return S("V a = VQ(p0), b = VQ(p1), r; r.d[0] = a.d[0]; r.d[1] = b.d[0]; return r.q;", *asm_binop(b, vex, "x"))
    if b in ("unpckhpd", "punpckhqdq"):
        return S("V a = VQ(p0), b = VQ(p1), r; r.d[0] = a.d[1]; r.d[1] = b.d[1]; return r.q;", *asm_binop(b, vex, "x"))
    if b == "punpcklbw":
        return S("V a = VQ(p0), b = VQ(p1), r; for (int i = 0; i < 8; i++) { r.b[2*i] = a.b[i]; r.b[2*i+1] = b.b[i]; } return r.q;", *asm_binop(b, vex, "x"))
    if b == "punpckhbw":
        return S("V a = VQ(p0), b = VQ(p1), r; for (int i = 0; i < 8; i++) { r.b[2*i] = a.b[8+i]; r.b[2*i+1] = b.b[8+i]; } return r.q;", *asm_binop(b, vex, "x"))
    if b == "punpcklwd":
        return S("V a = VQ(p0), b = VQ(p1), r; for (int i = 0; i < 4; i++) { r.h[2*i] = a.h[i]; r.h[2*i+1] = b.h[i]; } return r.q;", *asm_binop(b, vex, "x"))
    if b == "punpckhwd":
        return S("V a = VQ(p0), b = VQ(p1), r; for (int i = 0; i < 4; i++) { r.h[2*i] = a.h[4+i]; r.h[2*i+1] = b.h[4+i]; } return r.q;", *asm_binop(b, vex, "x"))
    if b == "packssdw":
        return S("V a = VQ(p0), b = VQ(p1), r; for (int i = 0; i < 4; i++) { r.s[i] = sat_i32_i16(a.i[i]); r.s[4+i] = sat_i32_i16(b.i[i]); } return r.q;", *asm_binop(b, vex, "x"))
    if b == "packsswb":
        return S("V a = VQ(p0), b = VQ(p1), r; for (int i = 0; i < 8; i++) { r.c[i] = sat_i16_i8(a.s[i]); r.c[8+i] = sat_i16_i8(b.s[i]); } return r.q;", *asm_binop(b, vex, "x"))
    if b == "packuswb":
        return S("V a = VQ(p0), b = VQ(p1), r; for (int i = 0; i < 8; i++) { r.b[i] = sat_i16_u8(a.s[i]); r.b[8+i] = sat_i16_u8(b.s[i]); } return r.q;", *asm_binop(b, vex, "x"))
    if b == "movlhps":
        return S("V a = VQ(p0), b = VQ(p1), r; r.d[0] = a.d[0]; r.d[1] = b.d[0]; return r.q;", *asm_binop(b, vex, "x"))
    if b == "movhlps":
        return S("V a = VQ(p0), b = VQ(p1), r; r.d[0] = b.d[1]; r.d[1] = a.d[1]; return r.q;", *asm_binop(b, vex, "x"))
    for nm, pmin in (("pminsw", "a.s[i] < b.s[i]"), ("pmaxsw", "a.s[i] > b.s[i]")):
        if b == nm:
            return S("V a = VQ(p0), b = VQ(p1), r; for (int i = 0; i < 8; i++) r.s[i] = (%s) ? a.s[i] : b.s[i]; return r.q;" % pmin, *asm_binop(b, vex, "x"))
    return None


def fam_shift(b, vex, R, A):
    """psll/psrl/psra (imm または xmm count), pslldq/psrldq (imm)"""
    if R != "x" or len(A) != 2 or A[0] != "x" or A[1] not in ("b", "x"):
        return None
    spec = {"psllw": ("h", 8, 16, "<<", "logical"), "pslld": ("w", 4, 32, "<<", "logical"), "psllq": ("d", 2, 64, "<<", "logical"),
            "psrlw": ("h", 8, 16, ">>", "logical"), "psrld": ("w", 4, 32, ">>", "logical"), "psrlq": ("d", 2, 64, ">>", "logical"),
            "psraw": ("s", 8, 16, ">>", "arith"), "psrad": ("i", 4, 32, ">>", "arith")}
    if b in spec:
        lane, n, w, sh, kind = spec[b]
        cnt = "p1" if A[1] == "b" else "VQ(p1).d[0]"
        if A[1] == "x":
            pre = "u64 cnt = VQ(p1).d[0];"
        else:
            pre = "u64 cnt = (u64)p1;"
        if kind == "logical":
            ut = {"h": "u16", "w": "u32", "d": "u64"}[lane]
            body = ("V a = VQ(p0); %s for (int i = 0; i < %d; i++) a.%s[i] = (cnt > %d) ? 0 : (%s)(a.%s[i] %s cnt); return a.q;"
                    % (pre, n, lane, w - 1, ut, lane, sh))
        else:
            body = ("V a = VQ(p0); %s u64 c = cnt > %d ? %d : cnt; for (int i = 0; i < %d; i++) a.%s[i] = a.%s[i] >> c; return a.q;"
                    % (pre, w - 1, w - 1, n, lane, lane))
        if A[1] == "b":
            asm = ("v%s $$IMM, %%[p0], %%[r]" % b, "r:=x p0:x", "r") if vex else ("%s $$IMM, %%[p0]" % b, "p0:+x", "p0")
            return S(body, *asm, imms=IMM_SH)
        asm = ("v%s %%[p1], %%[p0], %%[r]" % b, "r:=x p0:x p1:x", "r") if vex else ("%s %%[p1], %%[p0]" % b, "p0:+x p1:x", "p0")
        return S(body, *asm)
    if b in ("psrldq", "pslldq") and A[1] == "b":
        if b == "psrldq":
            body = "V a = VQ(p0); return (p1 > 15) ? (u128)0 : (a.q >> (8 * p1));"
        else:
            body = "V a = VQ(p0); return (p1 > 15) ? (u128)0 : (a.q << (8 * p1));"
        asm = ("v%s $$IMM, %%[p0], %%[r]" % b, "r:=x p0:x", "r") if vex else ("%s $$IMM, %%[p0]" % b, "p0:+x", "p0")
        return S(body, *asm, imms=[0, 1, 3, 4, 7, 8, 12, 15])
    return None


def fam_shuffle(b, vex, R, A):
    if R != "x":
        return None
    if b == "pshufd" and A == ["x", "b"]:
        return S("V a = VQ(p0), r; for (int i = 0; i < 4; i++) r.w[i] = a.w[(p1 >> (2*i)) & 3]; return r.q;",
                 "%spshufd $$IMM, %%[p0], %%[r]" % ("v" if vex else ""), "r:=x p0:x", "r", imms=IMM_SHUF)
    if b == "pshuflw" and A == ["x", "b"]:
        return S("V a = VQ(p0), r = a; for (int i = 0; i < 4; i++) r.h[i] = a.h[(p1 >> (2*i)) & 3]; return r.q;",
                 "%spshuflw $$IMM, %%[p0], %%[r]" % ("v" if vex else ""), "r:=x p0:x", "r", imms=IMM_SHUF)
    if b == "pshufhw" and A == ["x", "b"]:
        return S("V a = VQ(p0), r = a; for (int i = 0; i < 4; i++) r.h[4+i] = a.h[4 + ((p1 >> (2*i)) & 3)]; return r.q;",
                 "%spshufhw $$IMM, %%[p0], %%[r]" % ("v" if vex else ""), "r:=x p0:x", "r", imms=IMM_SHUF)
    if b == "shufps" and A == ["x", "x", "b"]:
        body = "V a = VQ(p0), b = VQ(p1), r; r.w[0] = a.w[p2 & 3]; r.w[1] = a.w[(p2 >> 2) & 3]; r.w[2] = b.w[(p2 >> 4) & 3]; r.w[3] = b.w[(p2 >> 6) & 3]; return r.q;"
        asm = ("vshufps $$IMM, %[p1], %[p0], %[r]", "r:=x p0:x p1:x", "r") if vex else ("shufps $$IMM, %[p1], %[p0]", "p0:+x p1:x", "p0")
        return S(body, *asm, imms=IMM_SHUF)
    if b == "shufpd" and A == ["x", "x", "b"]:
        body = "V a = VQ(p0), b = VQ(p1), r; r.d[0] = a.d[p2 & 1]; r.d[1] = b.d[(p2 >> 1) & 1]; return r.q;"
        asm = ("vshufpd $$IMM, %[p1], %[p0], %[r]", "r:=x p0:x p1:x", "r") if vex else ("shufpd $$IMM, %[p1], %[p0]", "p0:+x p1:x", "p0")
        return S(body, *asm, imms=[0, 1, 2, 3])
    if b == "movddup" and len(A) == 1 and A[0] in ("x", "q"):
        e = "F64L(p0)" if A[0] == "x" else "ASD(p0)"
        asm = asm_unop(b, vex, A[0])
        return S("V r; r.g[0] = %s; r.g[1] = r.g[0]; return r.q;" % e, *asm)
    if b == "movshdup" and A == ["x"]:
        return S("V a = VQ(p0), r; r.w[0] = a.w[1]; r.w[1] = a.w[1]; r.w[2] = a.w[3]; r.w[3] = a.w[3]; return r.q;", *asm_unop(b, vex, "x"))
    if b == "movsldup" and A == ["x"]:
        return S("V a = VQ(p0), r; r.w[0] = a.w[0]; r.w[1] = a.w[0]; r.w[2] = a.w[2]; r.w[3] = a.w[2]; return r.q;", *asm_unop(b, vex, "x"))
    if b == "broadcastss" and vex and len(A) == 1:
        e = "p0" if A[0] == "d" else "VQ(p0).w[0]"
        c = "m" if A[0] == "d" else "x"
        return S("V r; r.w[0] = r.w[1] = r.w[2] = r.w[3] = %s; return r.q;" % e, "vbroadcastss %[p0], %[r]", "r:+x p0:" + c, "r")
    return None


# ---------------------------------------------------------------------------------
# 変換
# ---------------------------------------------------------------------------------
def fam_cvt(b, vex, R, A):
    # packed
    if R == "x" and A == ["x"]:
        if b == "cvtdq2ps":
            return S("V a = VQ(p0), r; for (int i = 0; i < 4; i++) r.f[i] = (float)a.i[i]; return r.q;", *asm_unop(b, vex, "x"))
        if b == "cvtdq2pd":
            return S("V a = VQ(p0), r; r.g[0] = (double)a.i[0]; r.g[1] = (double)a.i[1]; return r.q;", *asm_unop(b, vex, "x"))
        if b == "cvtps2pd":
            return S("V a = VQ(p0), r; r.g[0] = (double)a.f[0]; r.g[1] = (double)a.f[1]; return r.q;", *asm_unop(b, vex, "x"))
        if b == "cvtpd2ps":
            return S("V a = VQ(p0), r; r.q = 0; r.f[0] = (float)a.g[0]; r.f[1] = (float)a.g[1]; return r.q;", *asm_unop(b, vex, "x"))
        if b == "cvtps2dq":
            return S("V a = VQ(p0), r; for (int i = 0; i < 4; i++) r.i[i] = x86_cvt_f2i32(a.f[i]); return r.q;", *asm_unop(b, vex, "x"))
        if b == "cvttps2dq":
            return S("V a = VQ(p0), r; for (int i = 0; i < 4; i++) r.i[i] = x86_cvtt_f2i32(a.f[i]); return r.q;", *asm_unop(b, vex, "x"))
        if b == "cvtpd2dq":
            return S("V a = VQ(p0), r; r.q = 0; r.i[0] = x86_cvt_f2i32(a.g[0]); r.i[1] = x86_cvt_f2i32(a.g[1]); return r.q;", *asm_unop(b, vex, "x"))
        if b == "cvttpd2dq":
            return S("V a = VQ(p0), r; r.q = 0; r.i[0] = x86_cvtt_f2i32(a.g[0]); r.i[1] = x86_cvtt_f2i32(a.g[1]); return r.q;", *asm_unop(b, vex, "x"))
        if b == "pmovsxdq":
            return S("V a = VQ(p0), r; r.l[0] = a.i[0]; r.l[1] = a.i[1]; return r.q;", *asm_unop(b, vex, "x"))
    # scalar fp<->fp
    if b == "cvtss2sd" and R == "x":
        if len(A) == 1 and A[0] in ("x", "d"):
            e = f32(0, A[0])
            return S("V r; r.q = 0; r.g[0] = (double)%s; return r.q;" % e, *asm_unop(b, False, A[0])) if not vex else None
        if len(A) == 2 and A[0] == "x" and A[1] in ("x", "d"):
            return S("V a = VQ(p0); a.g[0] = (double)%s; return a.q;" % f32(1, A[1]), *asm_vex_unop_rr(b, A[1]))
    if b == "cvtsd2ss" and R == "x":
        if len(A) == 1 and A[0] in ("x", "q"):
            return S("V r; r.q = 0; r.f[0] = (float)%s; return r.q;" % f64(0, A[0]), *asm_unop(b, False, A[0])) if not vex else None
        if len(A) == 2 and A[0] == "x" and A[1] in ("x", "q"):
            return S("V a = VQ(p0); a.f[0] = (float)%s; return a.q;" % f64(1, A[1]), *asm_vex_unop_rr(b, A[1]))
    # int -> fp
    if b in ("cvtsi2ss", "cvtsi2sd") and R == "x":
        ss = b.endswith("ss")
        lane = "f" if ss else "g"
        cast = "float" if ss else "double"
        if len(A) == 1 and A[0] in ("d", "q") and not vex:
            ity = "int32_t" if A[0] == "d" else "int64_t"
            return S("V r; r.q = 0; r.%s[0] = (%s)(%s)p0; return r.q;" % (lane, cast, ity), "%s %%[p0], %%[r]" % b, "r:+x p0:r", "r")
        if len(A) == 2 and A[0] == "x" and A[1] in ("d", "q") and vex:
            ity = "int32_t" if A[1] == "d" else "int64_t"
            return S("V a = VQ(p0); a.%s[0] = (%s)(%s)p1; return a.q;" % (lane, cast, ity), "v%s %%[p1], %%[p0], %%[r]" % b, "r:=x p0:x p1:r", "r")
    # fp -> int
    if b in ("cvttss2si", "cvtss2si", "cvttsd2si", "cvtsd2si") and R in ("d", "q") and len(A) == 1 and not b.startswith("v"):
        ss = "ss" in b
        trunc = b.startswith("cvtt")
        e = f32(0, A[0]) if ss else f64(0, A[0])
        if e is None:
            return None
        fn = ("x86_cvtt_f2i" if trunc else "x86_cvt_f2i") + ("32" if R == "d" else "64")
        rt = "u32" if R == "d" else "u64"
        return S("return (%s)%s((double)%s);" % (rt, fn, e), "%s%s %%[p0], %%[rr]" % ("v" if vex else "", b),
                 "rr:=r p0:%s" % ("x" if A[0] == "x" else "m"), "rr")
    return None


# ---------------------------------------------------------------------------------
# 比較 (cmp<pred>{ps,pd,ss,sd}), comis
# ---------------------------------------------------------------------------------
CMP_PRED = {"eq": 0, "lt": 1, "le": 2, "unord": 3, "neq": 4, "nlt": 5, "nle": 6, "ord": 7}


def fam_cmp(b, vex, R, A):
    for pn, pv in CMP_PRED.items():
        for sfx in ("ps", "pd", "ss", "sd"):
            if b != "cmp" + pn + sfx:
                continue
            if R != "x" or len(A) != 2 or A[0] != "x":
                return None
            packed = sfx[0] == "p"
            dbl = sfx[1] == "d"
            if packed:
                if A[1] != "x":
                    return None
                if dbl:
                    body = ("V a = VQ(p0), b = VQ(p1), r; for (int i = 0; i < 2; i++) r.d[i] = cmp_pred_d(a.g[i], b.g[i], %d) ? ~0ull : 0; return r.q;" % pv)
                else:
                    body = ("V a = VQ(p0), b = VQ(p1), r; for (int i = 0; i < 4; i++) r.w[i] = cmp_pred_f(a.f[i], b.f[i], %d) ? ~0u : 0; return r.q;" % pv)
            else:
                if dbl:
                    e = f64(1, A[1])
                    body = "V a = VQ(p0); a.d[0] = cmp_pred_d(a.g[0], %s, %d) ? ~0ull : 0; return a.q;" % (e, pv)
                else:
                    e = f32(1, A[1])
                    body = "V a = VQ(p0); a.w[0] = cmp_pred_f(a.f[0], %s, %d) ? ~0u : 0; return a.q;" % (e, pv)
                if e is None:
                    return None
            mn = "cmp" + pn + sfx
            asm, ops, res = asm_binop(mn, vex, A[1])
            return S(body, asm, ops, res)
    return None


def fam_comis(b, vex, R, A):
    if b in ("comiss", "comisd", "ucomiss", "ucomisd") and R == "v" and len(A) == 2:
        return S("(void)p0; (void)p1;", note="フラグは p1 pass が fcmp で再構成 (helper は no-op)", exact=True)
    return None


# ---------------------------------------------------------------------------------
# move / extract / insert
# ---------------------------------------------------------------------------------
def fam_move(b, vex, R, A):
    full = {"movaps", "movapd", "movups", "movupd", "movdqa", "movdqu", "lddqu"}
    if b in full:
        if R == "x" and A == ["x"]:
            return S("return p0;", "%s%s %%[p0], %%[r]" % ("v" if vex else "", b), "r:=x p0:x", "r")
        if R == "q" and A == ["x"]:
            return S("return (u64)p0;", note="ストア形: RetDec は低 64bit を返す (実ストアは IR 側 / S1a)")
        if R == "v" and len(A) == 2:
            return S("(void)p0; (void)p1;", note="S1a で store に復元されなかった残存形")
    if b in ("movntps", "movntpd", "movntdq", "movnti") and R == "v":
        return S("(void)p0; (void)p1;", note="non-temporal store: 通常ストアで代替 (IR 側)")
    if b == "movss":
        if R == "x" and A == ["d"]:
            return S("V r; r.q = 0; r.w[0] = p0; return r.q;", "%smovss %%[p0], %%[r]" % ("v" if vex else ""), "r:=x p0:m", "r")
        if R == "x" and A == ["x", "x"]:
            if vex:
                return S("V a = VQ(p0), b = VQ(p1); a.w[0] = b.w[0]; return a.q;", "vmovss %[p1], %[p0], %[r]", "r:=x p0:x p1:x", "r")
            return S("V a = VQ(p0), b = VQ(p1); a.w[0] = b.w[0]; return a.q;", "movss %[p1], %[p0]", "p0:+x p1:x", "p0")
        if R == "q" and A == ["x"]:
            return S("return (u32)p0;", note="ストア形 (低 32bit)")
        if R == "d" and A == ["x"]:
            return S("return (u32)p0;", note="ストア形 (低 32bit)")
    if b == "movsd":
        if R == "x" and A == ["q"]:
            return S("V r; r.q = 0; r.d[0] = p0; return r.q;", "%smovsd %%[p0], %%[r]" % ("v" if vex else ""), "r:=x p0:m", "r")
        if R == "x" and A == ["x", "x"]:
            if vex:
                return S("V a = VQ(p0), b = VQ(p1); a.d[0] = b.d[0]; return a.q;", "vmovsd %[p1], %[p0], %[r]", "r:=x p0:x p1:x", "r")
            return S("V a = VQ(p0), b = VQ(p1); a.d[0] = b.d[0]; return a.q;", "movsd %[p1], %[p0]", "p0:+x p1:x", "p0")
        if R == "q" and A == ["x"]:
            return S("return (u64)p0;", note="ストア形 (低 64bit)")
    if b == "movd":
        if R == "x" and A == ["d"]:
            return S("V r; r.q = 0; r.w[0] = p0; return r.q;", "%smovd %%[p0], %%[r]" % ("v" if vex else ""), "r:+x p0:r", "r")
        if R == "d" and A == ["x"]:
            return S("return (u32)p0;", "%smovd %%[p0], %%[rr]" % ("v" if vex else ""), "rr:=r p0:x", "rr")
    if b == "movq":
        if R == "x" and A == ["q"]:
            return S("V r; r.q = 0; r.d[0] = p0; return r.q;", "%smovq %%[p0], %%[r]" % ("v" if vex else ""), "r:+x p0:r", "r")
        if R == "x" and A == ["x"]:
            return S("V r; r.q = 0; r.d[0] = (u64)p0; return r.q;", "%smovq %%[p0], %%[r]" % ("v" if vex else ""), "r:+x p0:x", "r")
        if R == "q" and A == ["x"]:
            return S("return (u64)p0;", "%smovq %%[p0], %%[rr]" % ("v" if vex else ""), "rr:=r p0:x", "rr")
    if b in ("movlps", "movlpd") and R == "x" and A == ["x", "q"]:
        return S("V a = VQ(p0); a.d[0] = p1; return a.q;", "%s%s %%[p1], %%[p0]" % ("v" if vex else "", b), "p0:+x p1:m", "p0") if not vex else None
    if b in ("movhps", "movhpd") and R == "x" and A == ["x", "q"]:
        return S("V a = VQ(p0); a.d[1] = p1; return a.q;", "%s %%[p1], %%[p0]" % b, "p0:+x p1:m", "p0") if not vex else None
    if b in ("movlps", "movlpd") and R == "q" and A == ["x"]:
        return S("return (u64)p0;", note="ストア形 (低 64bit)")
    if b in ("movhps", "movhpd") and R == "q" and A == ["x"]:
        return S("V a = VQ(p0); return a.d[1];", note="ストア形 (高 64bit)")
    if b == "movmskps" and R == "d" and A == ["x"]:
        return S("V a = VQ(p0); return ((a.w[0] >> 31) & 1) | (((a.w[1] >> 31) & 1) << 1) | (((a.w[2] >> 31) & 1) << 2) | (((a.w[3] >> 31) & 1) << 3);",
                 "%smovmskps %%[p0], %%[rr]" % ("v" if vex else ""), "rr:=r p0:x", "rr")
    if b == "movmskpd" and R == "d" and A == ["x"]:
        return S("V a = VQ(p0); return (u32)((a.d[0] >> 63) | ((a.d[1] >> 63) << 1));",
                 "%smovmskpd %%[p0], %%[rr]" % ("v" if vex else ""), "rr:=r p0:x", "rr")
    if b == "pmovmskb" and R == "d" and A == ["x"]:
        return S("V a = VQ(p0); u32 m = 0; for (int i = 0; i < 16; i++) m |= (u32)(a.b[i] >> 7) << i; return m;",
                 "%spmovmskb %%[p0], %%[rr]" % ("v" if vex else ""), "rr:=r p0:x", "rr")
    return None


# ---------------------------------------------------------------------------------
# FMA3, round
# ---------------------------------------------------------------------------------
def fam_fma(b, vex, R, A):
    # b: v?fm(add|sub)|fnm(add|sub) (132|213|231) (ss|sd|ps|pd) -- 呼出側で vex 剥がし済みの場合 base は 'fmadd213sd' 等
    import re
    m = re.match(r"^(fmadd|fmsub|fnmadd|fnmsub)(132|213|231)(ss|sd|ps|pd)$", b)
    if not m or not vex:
        return None
    op, order, sfx = m.groups()
    if R != "x" or len(A) != 3 or A[0] != "x" or A[1] != "x":
        return None
    packed = sfx[0] == "p"
    dbl = sfx[1] == "d"
    lane = "g" if dbl else "f"
    cn = "__builtin_fma" if dbl else "__builtin_fmaf"
    n = (2 if dbl else 4) if packed else 1
    third = {"x": "b" if False else None}
    if A[2] == "x":
        c_get = "c.%s[i]" % lane
    elif A[2] == "d" and not dbl:
        c_get = "ASF(p2)"
    elif A[2] == "q" and dbl:
        c_get = "ASD(p2)"
    else:
        return None
    # order: 132: a*c + b ; 213: b*a + c ; 231: b*c + a
    m1, m2, ad = {"132": ("a", "c", "b"), "213": ("b", "a", "c"), "231": ("b", "c", "a")}[order]
    sgn_mul = "-" if op in ("fnmadd", "fnmsub") else ""
    sgn_add = "-" if op in ("fmsub", "fnmsub") else ""

    def term(nm):
        return c_get if nm == "c" else "%s.%s[i]" % (nm, lane)
    body = ("V a = VQ(p0), b = VQ(p1)%s; for (int i = 0; i < %d; i++) a.%s[i] = %s(%s%s, %s, %s%s); return a.q;"
            % (", c = VQ(p2)" if A[2] == "x" else "", n, lane, cn, sgn_mul, term(m1), term(m2), sgn_add, term(ad)))
    # 検証用 asm: vfmadd213sd src3, src2, dst   (dst = p0, src2 = p1, src3 = p2)
    c3 = "x" if A[2] == "x" else "m"
    asm = "v%s %%[p2], %%[p1], %%[p0]" % b
    return S(body, asm, "p0:+x p1:x p2:%s" % c3, "p0")


def fam_round(b, vex, R, A):
    if R != "x":
        return None
    if b in ("roundsd", "roundss") and vex and len(A) == 3 and A[0] == "x" and A[2] == "b" and A[1] in ("x", "q", "d"):
        dbl = b.endswith("sd")
        e = f64(1, A[1]) if dbl else f32(1, A[1])
        if e is None:
            return None
        lane = "g" if dbl else "f"
        fn = "x86_round_d" if dbl else "x86_round_f"
        return S("V a = VQ(p0); a.%s[0] = %s(%s, p2); return a.q;" % (lane, fn, e),
                 "v%s $$IMM, %%[p1], %%[p0], %%[r]" % b, "r:=x p0:x p1:%s" % ("x" if A[1] == "x" else "m"), "r", imms=[0, 1, 2, 3, 4, 8, 9, 10, 11, 12])
    if b in ("roundsd", "roundss") and not vex and len(A) in (2, 3):
        dbl = b.endswith("sd")
        lane = "g" if dbl else "f"
        fn = "x86_round_d" if dbl else "x86_round_f"
        if len(A) == 3 and A[0] == "x" and A[2] == "b":
            e = f64(1, A[1]) if dbl else f32(1, A[1])
            if e is None:
                return None
            return S("V a = VQ(p0); a.%s[0] = %s(%s, p2); return a.q;" % (lane, fn, e),
                     "%s $$IMM, %%[p1], %%[p0]" % b, "p0:+x p1:%s" % ("x" if A[1] == "x" else "m"), "p0", imms=[0, 1, 2, 3, 4, 8, 9, 10, 11, 12])
    if b in ("roundps", "roundpd") and len(A) == 2 and A[0] == "x" and A[1] == "b":
        dbl = b.endswith("pd")
        lane, n, fn = ("g", 2, "x86_round_d") if dbl else ("f", 4, "x86_round_f")
        return S("V a = VQ(p0), r; for (int i = 0; i < %d; i++) r.%s[i] = %s(a.%s[i], p1); return r.q;" % (n, lane, fn, lane),
                 "%s%s $$IMM, %%[p0], %%[r]" % ("v" if vex else "", b), "r:=x p0:x", "r", imms=[0, 1, 2, 3, 4, 8, 9, 10, 11, 12])
    return None


def fam_misc(b, vex, R, A):
    if b in ("int3", "ud2", "sfence", "lfence", "mfence", "pause", "vzeroupper", "emms") and not A:
        return S("return 0;" if R in ("q", "d") else "", note="no-op")
    if b == "int" and R == "v" and A == ["b"]:
        return S("(void)p0;", note="no-op")
    if b in ("ldmxcsr", "stmxcsr") and R == "v" and len(A) == 1:
        return S("(void)p0;", note="MXCSR は wasm で制御不可: no-op")
    return None


FAMILIES = [fam_misc, fam_comis, fam_scalar_bin, fam_scalar_sqrt, fam_packed_bin, fam_packed_un, fam_logic,
            fam_int_arith, fam_shift, fam_shuffle, fam_cvt, fam_cmp, fam_move, fam_fma, fam_round]


def lookup(base, ret, args):
    """(base, ret, args) に対する Spec か None。VEX は 'v' 接頭辞を持つ mnemonic のみ。"""
    cands = [(base, False)]
    if base.startswith("v") and len(base) > 2:
        cands.insert(0, (base[1:], True))
    for b, vex in cands:
        for fam in FAMILIES:
            try:
                sp = fam(b, vex, ret, list(args))
            except Exception:
                sp = None
            if sp is not None:
                return sp
    return None


def known_bases():
    """被覆判定用: テーブルが少なくとも 1 つのシグネチャで扱う mnemonic の列挙は gen.coverage で
    代表シグネチャを当てて行う。"""
    return None
