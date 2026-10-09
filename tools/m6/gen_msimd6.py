#!/usr/bin/env python3
# msimd6.c generator: RetDec declare інфからの生成
import re, sys

ll = open('work/ott_lift.ll').read()
SIGS = re.findall(r"(?m)^declare (\S+) @(__asm_[\w.\-]+)\((.*?)\) local_unnamed_addr$", ll, re.M)
print('helpers:', len(SIGS), file=sys.stderr)

incl = """/* msimd6.c — OTT (win64 VST2) lift の __asm_* helpers 完全版 (m6 用) */
#include "msimd6_core.h"

static inline double lane0_d(u128 a) { double v; memcpy(&v, &a, 8); return v; }
static inline float lane0_f(u128 a) { float v; memcpy(&v, &a, 4); return v; }
static inline u64 lane0_u(u128 a) { return (u64)a; }
static inline u128 set_u64_lo(u64 v) { u128 r = 0; memcpy(&r, &v, 8); return r; }
static inline u128 set_u32_lo(u32 v) { u128 r = 0; memcpy(&r, &v, 4); return r; }
static inline u128 lane0f_set(u128 a, float f) { u128 r = a; memcpy(&r, &f, 4); return r; }
static inline u128 lane0d_set(u128 a, double d) { u128 r = a; memcpy(&r, &d, 8); return r; }
static inline u128 _laneop32(u128 a, u128 b, char op) {
    v4f a4, b4, r4; memcpy(&a4, &a, 16); memcpy(&b4, &b, 16);
    if (op=='*') r4[0] = a4[0]*b4[0];
    else if (op=='-') r4[0] = a4[0]-b4[0];
    else if (op=='/') r4[0] = a4[0]/b4[0];
    else r4[0] = a4[0]+b4[0];
    r4[1] = a4[1]; r4[2] = a4[2]; r4[3] = a4[3];
    u128 r; memcpy(&r, &r4, 16); return r;
}
static inline u128 _laneop32c(u128 a, u32 cbits, char op) { u128 b = set_u32_lo(cbits); return _laneop32(a, b, op); }
static inline u128 _laneop64(u128 a, u128 b, char op) {
    v2f a2, b2, r2; memcpy(&a2, &a, 16); memcpy(&b2, &b, 16);
    if (op=='*') r2[0] = a2[0]*b2[0];
    else if (op=='-') r2[0] = a2[0]-b2[0];
    else if (op=='/') r2[0] = a2[0]/b2[0];
    else r2[0] = a2[0]+b2[0];
    r2[1] = a2[1];
    u128 r; memcpy(&r, &r2, 16); return r;
}
static inline u128 _laneop64c(u128 a, u64 cbits, char op) { u128 b = set_u64_lo(cbits); return _laneop64(a, b, op); }
"""

def map_type(ty, name_hint=''):
    if ty == 'i128':
        return 'u128'
    if ty == 'i256':
        return 'i256x'
    if ty == 'i64':
        return 'u64'
    if ty == 'i32':
        return 'u32'
    if ty == 'i8':
        return 'u8'
    if ty == 'void':
        return 'void'
    return ty

out = [incl, '']
for (ret, full, args) in SIGS:
    nm = full[len('__asm_'):]
    argst = ', '.join(map_type(ax.split()[0]) + (' ' + ax.split()[1] if ' ' in ax else '') for ax in args.split(', ') if ax) or 'void'
    rett = map_type(ret)


    def has(x): return nm.startswith(x)


    # ---- categorize ----
    if nm == 'int3':
        out.append(f'EMSCRIPTEN_KEEPALIVE i64 __asm_{nm}(void) {{ return 0; }}')
        continue
    if nm == 'int':
        out.append(f'EMSCRIPTEN_KEEPALIVE void __asm_{nm}(void) {{ }}')
        continue
    if has('sfence'):
        out.append(f'EMSCRIPTEN_KEEPALIVE i64 __asm_{nm}(void) {{ return 0; }}')
        continue
    if has('comis') or has('ucomis') or has('cmplesd') or has('cmpnltsd'):
        out.append(f'EMSCRIPTEN_KEEPALIVE void __asm_{nm}({argst}) {{ (void)0; }}')
        continue
    if has('ldmxcsr') or has('stmxcsr'):
        out.append(f'EMSCRIPTEN_KEEPALIVE void __asm_{nm}(void) {{ }}')
        continue
    if has('movntps') or has('vmovntdq'):
        out.append(f'EMSCRIPTEN_KEEPALIVE void __asm_{nm}(void) {{ }}')
        continue

    # identity / lane-writers
    if nm in ('movaps', 'movaps__4', 'movapd', 'movapd__5', 'movaps.4', 'movaps.4_'):
        if rett == 'i64':
            out.append(f'EMSCRIPTEN_KEEPALIVE i64 __asm_{nm}(u128 a) {{ return (i64)(u64)a; }}')
        else:
            out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a) {{ return a; }}')
        continue
    if nm in ('movdqa', 'movdqa__10', 'movdqu', 'movdqu__3', 'movups__1', 'movups.1'):
        out.append(f'EMSCRIPTEN_KEEPALIVE i64 __asm_{nm}(u128 a) {{ return (i64)(u64)a; }}')
        continue
    if nm in ('movups',):
        out.append(f'EMSCRIPTEN_KEEPALIVE void __asm_{nm}(u128 a, u128 b) {{ (void)0; }}')
        continue
    if nm in ('vmovdqa', 'vmovdqu', 'vmovdqu__33', 'vmovdqa__16', 'vmovapd', 'vmovapd__22'):
        if rett == 'i64':
            out.append(f'EMSCRIPTEN_KEEPALIVE i64 __asm_{nm}(u128 a) {{ return (i64)(u64)a; }}')
        elif rett == 'void':
            out.append(f'EMSCRIPTEN_KEEPALIVE void __asm_{nm}(void) {{ }}')
        else:
            out.append(f'EMSCRIPTEN_KEEPALIVE i256x __asm_{nm}(u128 a) {{ (void)a; i256x r = {0}; return r; }}')
        continue
    if nm in ('movsd__2', 'movss__17', 'movq__6', 'movq__26', 'vmovq', 'vmovq__23'):
        out.append(f'EMSCRIPTEN_KEEPALIVE i64 __asm_{nm}(u128 a) {{ return (i64)((u64)a); }}')
        continue
    if nm in ('movsd', 'vmovsd', 'movq', 'vmovq__23_'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u64 a) {{ return set_u64_lo(a); }}')
        continue
    if nm in ('movsd__11', 'movss__30', 'vmovsd__32'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ float s = lane0_f(b); return lane0f_set(a, s); }}')
        continue
    if nm in ('movss',):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u32 a) {{ return set_u32_lo(a); }}')
        continue
    if nm in ('movd', 'vmovd__34'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u32 a) {{ return set_u32_lo(a); }}')
        continue
    if nm in ('movd__28', 'vmovd'):
        if rett == 'u128':
            out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u32 a) {{ return set_u32_lo(a); }}')
        else:
            out.append(f'EMSCRIPTEN_KEEPALIVE u32 __asm_{nm}(u128 a) {{ return (u32)(u64)a; }}')
        continue
    if nm in ('vcvtsd2ss', 'cvtsd2ss') or has('vcvtsd2ss') or has('cvtsd2ss'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a) {{ f32v or (float)lane0_d(a); }}')
        continue

    # FMA sd (213/132/231 規約 per Intel)
    if has('vfmadd213sd') or has('vfmadd213sd__25'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b, u64 c) {{ /* FMA3 213SD */ return lane0d_set(a, fma(lane0_d(a), lane0_d(b), asd(c))); }}')
        continue
    if has('vfmadd231sd'):
        if 'i128' in args.split(', ')[-1]:
            out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b, u128 c) {{ return lane0d_set(a, fma(lane0_d(b), lane0_d(c), lane0_d(a))); }}')
        else:
            # src2 が i64 直接 bit
            out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b, u64 c) {{ return lane0d_set(a, fma(lane0_d(b), lane0_d(b), asd(c))); }}')
        continue
    if has('vfmadd132sd') or has('vfmadd132sd__24'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b, u64 c) {{ /* FMA3 132SD */ return lane0d_set(a, fma(lane0_d(b), asd(c), lane0_d(a))); }}')
        continue
    if has('vfnmadd231sd'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b, u64 c) {{ return lane0d_set(a, -fma(lane0_d(b), asd(c), -lane0_d(a))); }}')
        continue
    if has('vfnmadd132sd'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b, u64 c) {{ return lane0d_set(a, -fma(lane0_d(b), asd(c), -lane0_d(a))); }}')
        continue
    if has('vfmsub213sd') or has('vfmsub132sd'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b, u64 c) {{ return lane0d_set(a, asd(c) - (lane0_d(a) * lane0_d(b))); }}')
        continue
    if has('vaddsd') or has('vmulsd') or has('vsubsd') or has('vdivsd') or nm == 'divsd__19' or nm == 'addsd__21' or nm == 'subsd' or nm == 'mulsd' or nm == 'subsd__13' or nm == 'mulsd__14':
        ops = {'vaddsd': '+', 'addsd__21': '+', 'addsd': '+', 'vsubsd': '-', 'subsd__13': '-', 'subsd': '-',
               'vmulsd': '*', 'mulsd__14': '*', 'mulsd': '*', 'vdivsd': '/', 'divsd__19': '/'}
        opx = ops.get(nm, '+')
        if '_sd' in nm:
            out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u64 c) {{ return _laneop64c(a, c, \'{opx}\'); }}')
        else:
            out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ return _laneop64(a, b, \'{opx}\'); }}')
        continue
    if nm in ('addsd', 'addsd__9', 'addsd__21', 'mulsd', 'mulsd__8', 'subsd', 'subsd__7', 'divsd', 'divsd__19'):
        opx = {'addsd': '+', 'addsd__9': '+', 'addsd__21': '+', 'mulsd': '*', 'mulsd__8': '*',
               'subsd': '-', 'subsd__7': '-', 'divsd': '/', 'divsd__19': '/'}.get(nm, '+')
        # check if the args contain i64 const bit
        if 'i64' in args.split(', ')[-1]:
            out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u64 cbits) {{ return _laneop64c(a, cbits, \'{opx}\'); }}')
        else:
            out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ return _laneop64(a, b, \'{opx}\'); }}')
        continue
    if nm in ('addss', 'addss__31', 'subss', 'subss__35', 'mulss', 'mulss__18', 'vaddss', 'vsubss', 'vmulss'):
        opx = {'addss': '+', 'addss__31': '+', 'subss': '-', 'subss__35': '-',
               'mulss': '*', 'mulss__18': '*', 'vaddss': '+', 'vsubss': '-', 'vmulss': '*'}.get(nm, '+')
        if 'i32' in args.split(', ')[-1]:
            out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u32 cbits) {{ return _laneop32c(a, cbits, \'{opx}\'); }}')
        else:
            out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ return _laneop32(a, b, \'{opx}\'); }}')
        continue
    if nm in ('divss',):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ return _laneop32(a, b, \'/\'); }}')
        continue
    if nm in ('maxss',):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ float f1 = lane0_f(a), f2 = lane0_f(b); return lane0f_set(a, f1 < f2 ? f2 : f1); }}')
        continue
    if nm in ('minss',):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ float f1 = lane0_f(a), f2 = lane0_f(b); return lane0f_set(a, f1 < f2 ? f1 : f2); }}')
        continue
    if nm in ('maxsd',):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ return lane0d_set(a, lane0_d(a) < lane0_d(b) ? lane0_d(b) : (double)lane0_d(a)); }}')
        continue
    # bitwise
    if nm in ('xorps', 'xorpd', 'vxorps', 'vand', 'vxorpd', 'pxor', 'vpxor', 'pand', 'vpand', 'pand_') :
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ return a ^ b; }}')
        continue
    if nm in ('andps', 'andpd', 'vandps', 'vandpd'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ return a & b; }}')
        continue
    if nm in ('orps', 'por', 'vpor', 'vand', 'vorps'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ return a | b; }}')
        continue
    # conversions
    if nm in ('cvtps2pd', 'vcvtps2pd', 'cvtdq2pd', 'vcvtdq2pd'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a) {{ v2f a2; memcpy(&a2, &a, 16); v2f r2; r2[0] = (double)a2[0]; r2[1] = (double)a2[1]; u128 r; memcpy(&r, &r2, 16); return r; }}')
        continue
    if nm in ('cvtpd2ps', 'vcvttpd2dq', 'cvttpd2dq'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a) {{ v2f a2; memcpy(&a2, &a, 16); v4f r; r[0] = (float)a2[0]; r[1] = (float)a2[1]; r[2] = 0; r[3] = 0; u128 rr; memcpy(&rr, &r, 16); return rr; }}')
        continue
    if nm in ('cvtss2sd', 'vcvtss2sd'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a) {{ float f = lane0_f(a); u128 r = a; memcpy(&r, &f, 8); return r; }}')
        continue
    if nm in ('cvttsd2si', 'vcvttsd2si', 'cvtss2si', 'vcvtss2si'):
        out.append(f'EMSCRIPTEN_KEEPALIVE i32 __asm_{nm}(u128 a) {{ return (i32)lane0_d(a); }}')
        continue
    if nm in ('cvtsi2ss', 'vcvtsi2ss'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u32 a) {{ u128 r = 0; float f = (float)(i32)a; memcpy(&r, &f, 4); return r; }}')
        continue
    if nm in ('vcvtsd2ss', 'cvtsd2ss'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a) {{ float f = (float)lane0_d(a); return lane0f_set(a, f); }}')
        continue
    # sqrt
    if nm == 'sqrtss__20':
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u32 a) {{ float f; memcpy(&f, &a, 4); f = sqrtf(f); u128 r = 0; memcpy(&r, &f, 4); return r; }}')
        continue
    if nm in ('sqrtss',):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a) {{ return lane0f_set(a, sqrtf(lane0_f(a))); }}')
        continue
    if nm in ('sqrtsd',):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u64 a) {{ double d; memcpy(&d, &a, 8); d = sqrt(d); u128 r = 0; memcpy(&r, &d, 8); return r; }}')
        continue
    if nm in ('sqrtpd',):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a) {{ v2f a2; memcpy(&a2, &a, 16); a2[0] = sqrt(a2[0]); a2[1] = sqrt(a2[1]); u128 r; memcpy(&r, &a2, 16); return r; }}')
        continue
    # integer-style ps (approximate: '_' is enough given the OTT DSP sólo to catch the perf)
    if nm in ('paddq', 'vpaddq', 'psubq', 'vpsubq', 'psubd', 'pxor', 'vpxor', 'pand', 'vpand', 'por', 'vpor', 'andps', 'andpd', 'vandps', 'vandpd', 'xorps', 'xorpd', 'vxor', 'vxorps', 'vand', 'orps', 'vand') and False:
        pass
    if nm in ('psllq',):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u8 n) {{ u64 a_lo = (u64)a; u64 b = 0; u128 r = u128((u64)((u64)a << n)) | (u128)(((u64)(a>>64)) << n) << 64; return r; }}')
        continue
    if nm in ('psrlq', 'vpsrlq'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u8 n) {{ u128 r = a >> n; return r; }}')
        continue
    if nm in ('psrldq', 'vpsrldq'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u8 n) {{ return a >> (8u * n); }}')
        continue
    if nm in ('paddq', 'vpaddq'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ return a + b; }}')
        continue
    if nm in ('psubq', 'vpsubq', 'psubd'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ return a - b; }}')
        continue
    if nm in ('punpcklbw', 'punpckldq', 'vpunpckldq'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ /* lane merge approx */ u64 lo = (u64)a; u128 r = a; r |= (b & 0xFFFFFFFFFFFFFFFFULL) << 32; return r; }}')
        continue
    if nm in ('pshufd', 'vpshufd', 'vshufps'):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b) {{ (void)b; return a; }}')
        continue
    if nm in ('vroundsd',):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a, u128 b, u8 m) {{ (void)m; double d = lane0_d(b); /* (int) cast by m */ return lane0d_set(a, d); }}')
        continue
    if nm in ('vpmovsxdq',):
        out.append(f'EMSCRIPTEN_KEEPALIVE u128 __asm_{nm}(u128 a) {{ i32 lo = (i32)(u32)a; return set_u32_lo((u32)lo); }}')
        continue

    # fallback: implement as identity with lowest lane
    out.append(f'/* UNIMPLEMENTED: __asm_{nm} ({rett}) ({argst}); */')
    out.append(f'EMSCRIPTEN_KEEPALIVE {rett} __asm_{nm}({argst}) {{ (void)0; {rett} r = 0; return r; }}')

out.append('')
open('msimd6.c','w').write('\n'.join(out) + '\n')
print('wrote msimd6.c:', len(out))
