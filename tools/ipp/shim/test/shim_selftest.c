/* shim 自己検査 (native x86-64, 実 IPP DLL 不要):
   [abi]    thunk デコーダ (本番 thunk と同じ生成器) を実 MS x64 呼出 (gcc ms_abi + 手書き asm トランポリン) で検証。
            スタック上の float/double、値渡し struct 4B/8B、16B 構造体の参照渡し、狭い整数、13 引数。
   [loader] 420 名の GetProcAddress 解決 / legacy90 / LoadLibraryW 名判定 / 未知名
   [stub]   未実装名 (420 - 実装。実装数は e2e が sigs_summary.json から渡す) を全て呼んで fail-soft (eax=0, xmm0=0, 呼出カウンタ・初回順) を確認
   usage: shim_selftest <names.txt>   (1 行 1 名; flengine_ipp_names.json 由来) */
#include "../src/ipp_shim.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "../gen/ipp_proto.h"
#define MS __attribute__((ms_abi))
extern void *ipp_tramp_for(int idx);

static int fails = 0, checks = 0;
static int g_exp_impl = -1, g_exp_stub = -1;
#define CHK(c, ...) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static struct { uint64_t u[16]; double d[8]; float f[8]; Ipp32fc c; Ipp64fc z; IppiSize s; IppiRect r; IppiPoint p; Ipp16sc q; const void *ptr[4]; int i[8]; } G;
IppStatus probe_narrow(Ipp8u a, Ipp16s b, unsigned int c, Ipp64s d, double e, float f) { G.u[0] = a; G.u[1] = (uint64_t)(int64_t)b; G.u[2] = c; G.u[3] = (uint64_t)d; G.d[0] = e; G.f[0] = f; return 101; }
IppStatus probe_float(float a, double b, float c, double d, double e, float f) { G.f[0] = a; G.d[0] = b; G.f[1] = c; G.d[1] = d; G.d[2] = e; G.f[2] = f; return -102; }
IppStatus probe_struct(IppiSize s, Ipp32fc c, IppiRect r, Ipp64fc z, IppiPoint p, Ipp16sc q) { G.s = s; G.c = c; G.r = r; G.z = z; G.p = p; G.q = q; return 103; }
IppStatus probe_mixed(double a, int b, double c, int d, int e, double f) { G.d[0] = a; G.i[0] = b; G.d[1] = c; G.i[1] = d; G.i[2] = e; G.d[2] = f; return 104; }
IppStatus probe_many(const Ipp8u* pSrc, IppiSize srcSize, int srcStep, IppiRect srcRoi, Ipp8u* pDst, int dstStep, IppiRect dstRoi, double xF, double yF, double xS, double yS, int interp, Ipp8u* pBuf) {
  G.ptr[0] = pSrc; G.s = srcSize; G.i[0] = srcStep; G.r = srcRoi; G.ptr[1] = pDst; G.i[1] = dstStep; G.d[0] = xF; G.d[1] = yF; G.d[2] = xS; G.d[3] = yS; G.i[2] = interp; G.ptr[2] = pBuf;
  G.u[0] = (uint64_t)dstRoi.x << 48 | (uint64_t)dstRoi.y << 32 | (uint64_t)dstRoi.width << 16 | (uint64_t)dstRoi.height; return 105; }
void *probe_ptr(int n) { return (void *)(uintptr_t)(0x7000000000ULL + (unsigned)n); }

static uint64_t callg(int idx, uint64_t a, uint64_t b, uint64_t c, uint64_t d) { return ((uint64_t (MS *)(uint64_t, uint64_t, uint64_t, uint64_t))ipp_tramp_for(idx))(a, b, c, d); }

static void test_abi(void) {
  int B = 420;
  memset(&G, 0, sizeof G);
  int r = ((int (MS *)(Ipp8u, Ipp16s, unsigned, Ipp64s, double, float))ipp_tramp_for(B + 0))(0xA5, -12345, 0xDEADBEEFu, -0x123456789ABCLL, 3.14159265358979, 2.5f);
  CHK(r == 101 && G.u[0] == 0xA5 && (int64_t)G.u[1] == -12345 && G.u[2] == 0xDEADBEEFu && (int64_t)G.u[3] == -0x123456789ABCLL && G.d[0] == 3.14159265358979 && G.f[0] == 2.5f, "narrow/stack-double/stack-float");
  memset(&G, 0, sizeof G);
  r = ((int (MS *)(float, double, float, double, double, float))ipp_tramp_for(B + 1))(1.5f, -2.25, 3.75f, 1e-300, 6.5e100, -0.125f);
  CHK(r == -102 && G.f[0] == 1.5f && G.d[0] == -2.25 && G.f[1] == 3.75f && G.d[1] == 1e-300 && G.d[2] == 6.5e100 && G.f[2] == -0.125f, "xmm0-3 float/double + stack");
  memset(&G, 0, sizeof G);
  IppiSize s = {640, 480}; Ipp32fc c = {1.5f, -2.5f}; IppiRect rc = {1, 2, 3, 4}; Ipp64fc z = {9.25, -8.5}; IppiPoint p = {-7, 11}; Ipp16sc q = {-3, 300};
  r = ((int (MS *)(IppiSize, Ipp32fc, IppiRect, Ipp64fc, IppiPoint, Ipp16sc))ipp_tramp_for(B + 2))(s, c, rc, z, p, q);
  CHK(r == 103 && !memcmp(&G.s, &s, 8) && !memcmp(&G.c, &c, 8) && !memcmp(&G.r, &rc, 16) && !memcmp(&G.z, &z, 16) && !memcmp(&G.p, &p, 8) && !memcmp(&G.q, &q, 4), "struct 8B GPR / 16B by-ref / stack struct");
  memset(&G, 0, sizeof G);
  r = ((int (MS *)(double, int, double, int, int, double))ipp_tramp_for(B + 3))(1.25, 7, -6.5, 9, 11, 0.375);
  CHK(r == 104 && G.d[0] == 1.25 && G.i[0] == 7 && G.d[1] == -6.5 && G.i[1] == 9 && G.i[2] == 11 && G.d[2] == 0.375, "positional mix (xmm0, rdx, xmm2, r9, stack)");
  memset(&G, 0, sizeof G);
  IppiRect sr = {10, 20, 300, 400}, dr = {1, 2, 3, 4}; IppiSize ss = {1920, 1080}; uint8_t sbuf[4], dbuf[4], bbuf[4];
  r = ((int (MS *)(const Ipp8u *, IppiSize, int, IppiRect, Ipp8u *, int, IppiRect, double, double, double, double, int, Ipp8u *))ipp_tramp_for(B + 4))(sbuf, ss, 7680, sr, dbuf, 3840, dr, 0.5, 2.0, -0.25, 0.75, 2, bbuf);
  CHK(r == 105 && G.ptr[0] == sbuf && !memcmp(&G.s, &ss, 8) && G.i[0] == 7680 && !memcmp(&G.r, &sr, 16) && G.ptr[1] == dbuf && G.i[1] == 3840 && G.d[0] == 0.5 && G.d[1] == 2.0 && G.d[2] == -0.25 && G.d[3] == 0.75 && G.i[2] == 2 && G.ptr[2] == bbuf &&
      G.u[0] == ((uint64_t)1 << 48 | (uint64_t)2 << 32 | (uint64_t)3 << 16 | 4), "13-arg ippiResizeSqrPixel-like (stack args 5..13, doubles on stack, by-ref rects)");
  uint64_t pr = callg(B + 5, 0xFFFFFFFF00000005ULL, 0, 0, 0);
  CHK(pr == 0x7000000005ULL, "pointer return in rax (n=low32 of rcx) got %llx", (unsigned long long)pr);
}

static void test_loader(const char *namesfile) {
  FILE *f = fopen(namesfile, "r"); char nm[256]; int n = 0, miss = 0, dup = 0; uint64_t prev[512]; int np = 0;
  CHK(ipp_shim_table_count == 420, "table count %d", ipp_shim_table_count);
  while (f && fgets(nm, sizeof nm, f)) {
    nm[strcspn(nm, "\r\n")] = 0; if (!*nm) continue; n++;
    uint64_t c = ipp_shim_getproc(nm); char l9[300]; snprintf(l9, sizeof l9, "legacy90%s", nm);
    if (!c) { miss++; printf("  unresolved: %s\n", nm); continue; }
    CHK(ipp_shim_getproc(l9) == c, "legacy90 %s", nm); CHK(ipp_shim_owns(c), "owns %s", nm);
    for (int i = 0; i < np; i++) if (prev[i] == c) dup++;
    prev[np++] = c;
  }
  if (f) fclose(f);
  CHK(n == 420 && miss == 0 && dup == 0, "names=%d unresolved=%d dup=%d", n, miss, dup);
  CHK(ipp_shim_getproc("ippsNoSuchFunc") == 0 && ipp_shim_getproc("") == 0 && ipp_shim_getproc(NULL) == 0, "unknown -> 0");
  static const uint16_t a[] = u"dsp_ippv2_x64.dll", b[] = u"C:\\Program Files\\Image-Line\\FL Studio\\Shared\\DSP_IPPV2.DLL", c2[] = u"dsp_ippv2", d[] = u"dsp_ippv2_x64.dylib", e[] = u"kernel32.dll", g[] = u"dsp_ippv2_x64.dll.bak", h[] = u"dsp_ipp.dll";
  uint64_t H = ipp_shim_load_library_w(a);
  CHK(H && ipp_shim_load_library_w(b) == H && ipp_shim_load_library_w(c2) == H && ipp_shim_load_library_w(d) == H, "LoadLibraryW name forms");
  CHK(!ipp_shim_load_library_w(e) && !ipp_shim_load_library_w(g) && !ipp_shim_load_library_w(h) && !ipp_shim_load_library_w(NULL), "LoadLibraryW non-ipp -> 0");
  CHK(ipp_shim_get_proc_address(H, "ippsMulC_32f_I") == ipp_shim_getproc("ippsMulC_32f_I") && !ipp_shim_get_proc_address(H + 1, "ippsMulC_32f_I"), "GetProcAddress(handle)");
  IppBlk blk; memset(&blk, 0, sizeof blk); blk.target = 0x1234; blk.rax = 77;
  CHK(ipp_shim_dispatch(&blk) == 0 && blk.rax == 77, "foreign target not handled");
}

static void test_stubs(void) {
  ipp_shim_reset(); int ns = 0, ni = 0; int order[420], no = 0;
  for (int i = 0; i < ipp_shim_table_count; i++) {
    const IppShimEntry *e = &ipp_shim_table[i];
    if (e->impl) { ni++; continue; }
    ns++;
    uint64_t r = callg(i, 0xDEADBEEFCAFEF00DULL, 0x1111, 0x2222, 0x3333); order[no++] = i;
    CHK(r == 0 && ipp_shim_calls(i) == 1 && ipp_shim_last_stub() == i, "stub %s ret=%llx calls=%u", e->name, (unsigned long long)r, ipp_shim_calls(i));
    callg(i, 0, 0, 0, 0); CHK(ipp_shim_calls(i) == 2, "stub count x2 %s", e->name);
  }
  CHK(ni + ns == ipp_shim_table_count && (g_exp_impl < 0 || (ni == g_exp_impl && ns == g_exp_stub)), "impl %d stubs %d (表 %d, 期待 %d/%d)", ni, ns, ipp_shim_table_count, g_exp_impl, g_exp_stub);
  CHK(ipp_shim_stub_calls_total() == (uint32_t)(2 * ns) && ipp_shim_stub_distinct() == ns, "totals %u distinct %d", ipp_shim_stub_calls_total(), ipp_shim_stub_distinct());
  int ordok = 1; for (int k = 0; k < no; k++) if (ipp_shim_stub_first(k) != order[k]) ordok = 0;
  CHK(ordok && ipp_shim_stub_first(no) == -1, "first-hit order");
  ipp_shim_reset(); CHK(ipp_shim_stub_calls_total() == 0 && ipp_shim_stub_distinct() == 0 && ipp_shim_last_stub() == -1, "reset");
  printf("stub-selftest: stubs=%d impl=%d\n", ns, ni);
}

int main(int argc, char **argv) {
  if (argc < 2) return 2;
  /* 期待 impl/stub 数 (任意): gen_shim.py の sigs_summary.json 由来。実装追加のたびのピン更新を不要にする。
     省略時は 420 = impl + stub の整合のみ見る。 */
  if (argc >= 4) { g_exp_impl = atoi(argv[2]); g_exp_stub = atoi(argv[3]); }
  test_abi(); test_loader(argv[1]); test_stubs();
  printf("shim_selftest: checks=%d failed=%d\n", checks, fails);
  return fails ? 1 : 0;
}
