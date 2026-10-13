/* gui_simd.h — GDI 行カーネル (ROP / AlphaBlend / 2x 拡大 / 不透明化コピー)。
 * 各カーネルは scalar 参照実装 (gs_*_scalar, 常にコンパイルされる) と wasm SIMD128 実装 (gs_*_simd) を持ち、
 * gs_* は __wasm_simd128__ かつ !GUI_NO_SIMD のとき simd へ、それ以外は scalar へ振り分ける。
 * 契約: simd は scalar と画素完全一致 (test/simd_test.c が乱数入力・全長 0..70 の端数で検査)。
 * 画素は BGRA32 (alpha は出力時に 0xFF 固定; AlphaBlend も出力 alpha = 0xFF; 現行 scalar の挙動を保存)。 */
#ifndef GUI_SIMD_H
#define GUI_SIMD_H
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#if defined(__wasm_simd128__) && !defined(GUI_NO_SIMD)
#include <wasm_simd128.h>
#define GUI_HAVE_SIMD 1
#else
#define GUI_HAVE_SIMD 0
#endif

#define GS_OPAQUE 0xFF000000u

/* ネガティブコントロール用の故意の欠陥注入 (test/simd_e2e.sh --negctl のみが -DGS_FAULT=n で使う; 通常ビルドでは 0)。
 * 1: div255 の丸めバイアス 128->127 / 2: SRCINVERT を OR にする / 3: 2x 拡大の shuffle を誤る / 4: 不透明化コピーで OR を落とす */
#ifndef GS_FAULT
#define GS_FAULT 0
#endif

/* ---- ROP 番号 (Win32 ternary ROP の上位ワード 0xXX0000 を含む完全値; gui_win32.h と同値) ---- */
enum {
  GS_SRCCOPY = 0x00CC0020, GS_SRCPAINT = 0x00EE0086, GS_SRCAND = 0x008800C6, GS_SRCINVERT = 0x00660046,
  GS_SRCERASE = 0x00440328, GS_NOTSRCCOPY = 0x00330008, GS_NOTSRCERASE = 0x001100A6, GS_MERGECOPY = 0x00C000CA,
  GS_PATCOPY = 0x00F00021, GS_PATINVERT = 0x005A0049, GS_PATPAINT = 0x00FB0A09, GS_DSTINVERT = 0x00550009,
  GS_BLACKNESS = 0x00000042, GS_WHITENESS = 0x00FF0062, GS_MERGEPAINT = 0x00BB0226
};

static inline uint32_t gs_div255(uint32_t x) { x += 128; return (x + (x >> 8)) >> 8; }

/* ---- 1 画素 scalar (参照; 現行 gui_gdi.c rop_pix / AlphaBlend と同一式) ---- */
static inline uint32_t gs_rop_px(uint32_t rop, uint32_t s, uint32_t d, uint32_t pat) {
  switch (rop) {
    case GS_SRCCOPY: return s;
    case GS_SRCPAINT: return s | d;
    case GS_SRCAND: return s & d;
    case GS_SRCINVERT: return s ^ d;
    case GS_SRCERASE: return s & ~d;
    case GS_NOTSRCCOPY: return ~s;
    case GS_NOTSRCERASE: return ~(s | d);
    case GS_MERGECOPY: return s & pat;
    case GS_MERGEPAINT: return ~s | d;
    case GS_PATCOPY: return pat;
    case GS_PATINVERT: return pat ^ d;
    case GS_PATPAINT: return d | pat | ~s;
    case GS_DSTINVERT: return ~d;
    case GS_BLACKNESS: return 0;
    case GS_WHITENESS: return 0xFFFFFFFFu;
  }
  return 0;
}
static inline int gs_rop_supported(uint32_t rop) {
  switch (rop) {
    case GS_SRCCOPY: case GS_SRCPAINT: case GS_SRCAND: case GS_SRCINVERT: case GS_SRCERASE: case GS_NOTSRCCOPY:
    case GS_NOTSRCERASE: case GS_MERGECOPY: case GS_MERGEPAINT: case GS_PATCOPY: case GS_PATINVERT: case GS_PATPAINT:
    case GS_DSTINVERT: case GS_BLACKNESS: case GS_WHITENESS: return 1;
  }
  return 0;
}
static inline uint32_t gs_alpha_px(uint32_t s, uint32_t dv, uint32_t sca, uint32_t afmt) {
  uint32_t o = GS_OPAQUE, sa = afmt ? (s >> 24) : 255;
  for (int sh = 0; sh < 24; sh += 8) {
    uint32_t sc = (s >> sh) & 0xFF, dc = (dv >> sh) & 0xFF, r;
    if (afmt) { uint32_t scs = gs_div255(sc * sca); uint32_t a = gs_div255(sa * sca); r = scs + gs_div255(dc * (255 - a)); }
    else r = gs_div255(sc * sca) + gs_div255(dc * (255 - sca));
    if (r > 255) r = 255;
    o |= r << sh;
  }
  return o;
}

/* ---- 行カーネル scalar ---- */
/* d[i] = rop(s[i], d[i], pat) | alpha。s は d と重ならない行 (呼出側が保証)。 */
static inline void gs_rop_row_scalar(uint32_t rop, uint32_t *d, const uint32_t *s, size_t n, uint32_t pat) {
  for (size_t i = 0; i < n; i++) d[i] = gs_rop_px(rop, s[i], d[i], pat) | GS_OPAQUE;
}
static inline void gs_alpha_row_scalar(uint32_t *d, const uint32_t *s, size_t n, uint32_t sca, uint32_t afmt) {
  for (size_t i = 0; i < n; i++) d[i] = gs_alpha_px(s[i], d[i], sca, afmt);
}
static inline void gs_opaque_copy_scalar(uint32_t *d, const uint32_t *s, size_t n) {   /* StretchDIBits 1:1 (32bpp: alpha を捨てる) */
  for (size_t i = 0; i < n; i++) d[i] = s[i] | GS_OPAQUE;
}
static inline void gs_dup2_scalar(uint32_t *d, const uint32_t *s, size_t n_out) {      /* 2x 水平拡大: d[i] = s[i/2], n_out 画素 (偶数開始) */
  for (size_t i = 0; i < n_out; i++) d[i] = s[i >> 1];
}

#if GUI_HAVE_SIMD
/* ---- wasm SIMD128 ---- */
#define GS_ROP_LOOP(EXPR) do { for (; i + 4 <= n; i += 4) { \
    v128_t sv = wasm_v128_load(s + i), dv = wasm_v128_load(d + i); (void)sv; (void)dv; \
    wasm_v128_store(d + i, wasm_v128_or((EXPR), op)); } } while (0)
static inline void gs_rop_row_simd(uint32_t rop, uint32_t *d, const uint32_t *s, size_t n, uint32_t pat) {
  v128_t p = wasm_i32x4_splat((int32_t)pat), op = wasm_i32x4_splat((int32_t)GS_OPAQUE);
  size_t i = 0;
  switch (rop) {
    case GS_SRCCOPY: GS_ROP_LOOP(sv); break;
    case GS_SRCPAINT: GS_ROP_LOOP(wasm_v128_or(sv, dv)); break;
    case GS_SRCAND: GS_ROP_LOOP(wasm_v128_and(sv, dv)); break;
#if GS_FAULT == 2
    case GS_SRCINVERT: GS_ROP_LOOP(wasm_v128_or(sv, dv)); break;
#else
    case GS_SRCINVERT: GS_ROP_LOOP(wasm_v128_xor(sv, dv)); break;
#endif
    case GS_SRCERASE: GS_ROP_LOOP(wasm_v128_andnot(sv, dv)); break;
    case GS_NOTSRCCOPY: GS_ROP_LOOP(wasm_v128_not(sv)); break;
    case GS_NOTSRCERASE: GS_ROP_LOOP(wasm_v128_not(wasm_v128_or(sv, dv))); break;
    case GS_MERGECOPY: GS_ROP_LOOP(wasm_v128_and(sv, p)); break;
    case GS_MERGEPAINT: GS_ROP_LOOP(wasm_v128_or(wasm_v128_not(sv), dv)); break;
    case GS_PATCOPY: GS_ROP_LOOP(p); break;
    case GS_PATINVERT: GS_ROP_LOOP(wasm_v128_xor(p, dv)); break;
    case GS_PATPAINT: GS_ROP_LOOP(wasm_v128_or(wasm_v128_or(dv, p), wasm_v128_not(sv))); break;
    case GS_DSTINVERT: GS_ROP_LOOP(wasm_v128_not(dv)); break;
    case GS_BLACKNESS: GS_ROP_LOOP(wasm_i32x4_const_splat(0)); break;
    case GS_WHITENESS: GS_ROP_LOOP(wasm_i32x4_const_splat(-1)); break;
  }
  if (i < n) gs_rop_row_scalar(rop, d + i, s + i, n - i, pat);
}
static inline void gs_opaque_copy_simd(uint32_t *d, const uint32_t *s, size_t n) {
  v128_t op = wasm_i32x4_splat((int32_t)GS_OPAQUE); size_t i = 0;
#if GS_FAULT == 4
  for (; i + 4 <= n; i += 4) wasm_v128_store(d + i, wasm_v128_load(s + i));
#else
  for (; i + 4 <= n; i += 4) wasm_v128_store(d + i, wasm_v128_or(wasm_v128_load(s + i), op));
#endif
  for (; i < n; i++) d[i] = s[i] | GS_OPAQUE;
}
static inline void gs_dup2_simd(uint32_t *d, const uint32_t *s, size_t n_out) {
  size_t i = 0;
  for (; i + 8 <= n_out; i += 8) {
    v128_t v = wasm_v128_load(s + (i >> 1));
    wasm_v128_store(d + i, wasm_i32x4_shuffle(v, v, 0, 0, 1, 1));
#if GS_FAULT == 3
    wasm_v128_store(d + i + 4, wasm_i32x4_shuffle(v, v, 2, 3, 3, 3));
#else
    wasm_v128_store(d + i + 4, wasm_i32x4_shuffle(v, v, 2, 2, 3, 3));
#endif
  }
  for (; i < n_out; i++) d[i] = s[i >> 1];
}
/* 16bit レーン (4 画素 x 4ch の下位/上位 2 画素 = 8 レーン) の div255: (x+128 + ((x+128)>>8)) >> 8。x <= 65025 なので u16 内で収まる */
static inline v128_t gs_div255_u16(v128_t x) {
#if GS_FAULT == 1
  x = wasm_i16x8_add(x, wasm_i16x8_splat(127));
#else
  x = wasm_i16x8_add(x, wasm_i16x8_splat(128));
#endif
  return wasm_u16x8_shr(wasm_i16x8_add(x, wasm_u16x8_shr(x, 8)), 8);
}
/* 2 画素 (8 レーン [b g r a b g r a]) 分: d, s は u16 レーン。afmt != 0 で src alpha を使う */
static inline v128_t gs_alpha_lanes(v128_t s16, v128_t d16, v128_t sca, int afmt) {
  v128_t scs = gs_div255_u16(wasm_i16x8_mul(s16, sca));
  v128_t w;
  if (afmt) {
    v128_t a = gs_div255_u16(wasm_i16x8_mul(s16, sca));            /* lane3 = div255(sa*sca) */
    w = wasm_i16x8_shuffle(a, a, 3, 3, 3, 3, 7, 7, 7, 7);          /* 画素ごとに a を 4 レーンへ複製 */
  } else {
    w = sca;
  }
  v128_t inv = wasm_i16x8_sub(wasm_i16x8_splat(255), w);
  v128_t dd = gs_div255_u16(wasm_i16x8_mul(d16, inv));
  return wasm_i16x8_add(scs, dd);                                  /* <= 510; 呼出側の narrow で 255 へ飽和 */
}
static inline void gs_alpha_row_simd(uint32_t *d, const uint32_t *s, size_t n, uint32_t sca, uint32_t afmt) {
  v128_t vs = wasm_i16x8_splat((int16_t)sca), op = wasm_i32x4_splat((int32_t)GS_OPAQUE);
  size_t i = 0;
  for (; i + 4 <= n; i += 4) {
    v128_t sv = wasm_v128_load(s + i), dv = wasm_v128_load(d + i);
    v128_t lo = gs_alpha_lanes(wasm_u16x8_extend_low_u8x16(sv), wasm_u16x8_extend_low_u8x16(dv), vs, afmt != 0);
    v128_t hi = gs_alpha_lanes(wasm_u16x8_extend_high_u8x16(sv), wasm_u16x8_extend_high_u8x16(dv), vs, afmt != 0);
    wasm_v128_store(d + i, wasm_v128_or(wasm_u8x16_narrow_i16x8(lo, hi), op));
  }
  if (i < n) gs_alpha_row_scalar(d + i, s + i, n - i, sca, afmt);
}
#endif

#if GUI_HAVE_SIMD
#define gs_rop_row gs_rop_row_simd
#define gs_alpha_row gs_alpha_row_simd
#define gs_opaque_copy gs_opaque_copy_simd
#define gs_dup2 gs_dup2_simd
#else
#define gs_rop_row gs_rop_row_scalar
#define gs_alpha_row gs_alpha_row_scalar
#define gs_opaque_copy gs_opaque_copy_scalar
#define gs_dup2 gs_dup2_scalar
#endif

#endif
