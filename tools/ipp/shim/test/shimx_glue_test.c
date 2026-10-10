/* shimx 結合 e2e: shimx の LoadLibraryW/GetProcAddress 経由で "dsp_ippv2_x64.dll" の関数を引き、返値を cookie として ipp_shim_dispatch で実行する。
   (FL の LoadProc と同じ手順: LoadLibraryW -> GetProcAddress(plain 名) -> 取得値を VAR に保持 -> 呼出時は間接 call = icall ブロック経由で dispatch) */
#include <stdio.h>
#include <string.h>
#include "shimx.h"
#include "../src/ipp_shim.h"
extern HMODULE ipp_shim_install_shimx(void);
static int fails;
#define CHK(c, ...) do { if (!(c)) { fails++; printf("FAIL %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)
int main(void) {
  static const WCHAR dll[] = u"dsp_ippv2_x64.dll", other[] = u"nonexistent_ipp.dll";
  CHK(LoadLibraryW(dll) == 0, "before install: not loadable");
  HMODULE inst = ipp_shim_install_shimx(); CHK(inst != 0, "install");
  HMODULE h = LoadLibraryW(dll); CHK(h == inst, "LoadLibraryW after install");
  static const WCHAR full[] = u"C:\\Program Files\\Image-Line\\FL Studio 2026\\Shared\\dsp_ippv2_x64.dll";
  CHK(LoadLibraryW(full) == inst, "LoadLibraryW with full Win path (FL builds an absolute path)");
  CHK(LoadLibraryW(other) == 0, "other dll not found");
  int ok = 0, n = 0; FILE *f = fopen("/names.txt", "r"); char nm[256];
  while (f && fgets(nm, sizeof nm, f)) { nm[strcspn(nm, "\r\n")] = 0; if (!*nm) continue; n++; void *p = GetProcAddress(h, nm); if (p && (uint64_t)(uintptr_t)p == ipp_shim_getproc(nm)) ok++; }
  CHK(n == 420 && ok == 420, "GetProcAddress resolved %d/%d", ok, n);
  CHK(GetProcAddress(h, "ippsNoSuchFunc") == NULL, "unknown name -> NULL");
  /* ippsMulC_32f_I(val=2.0f in xmm0, pSrcDst in rdx, len in r8) を FL の呼出どおりのレジスタブロックで実行 */
  float buf[4] = {1.f, -2.f, 3.5f, 0.f}; float two = 2.0f; uint32_t tb; memcpy(&tb, &two, 4);
  IppBlk b; memset(&b, 0, sizeof b);
  b.target = (uint64_t)(uintptr_t)GetProcAddress(h, "ippsMulC_32f_I"); b.xmm[0] = tb | (0xDEADBEEFull << 32); b.gp[1] = (uint64_t)(uintptr_t)buf; b.gp[2] = 4 | (0xCAFEull << 32);
  CHK(ipp_shim_dispatch(&b) == 1 && (int32_t)b.rax == 0, "dispatch MulC_32f_I status");
  CHK(buf[0] == 2.f && buf[1] == -4.f && buf[2] == 7.f && buf[3] == 0.f, "MulC result %g %g %g %g", buf[0], buf[1], buf[2], buf[3]);
  memset(&b, 0, sizeof b); b.target = (uint64_t)(uintptr_t)GetProcAddress(h, "ippsConv_32f"); b.rax = 0x55;
  CHK(ipp_shim_dispatch(&b) == 1 && b.rax == 0 && ipp_shim_stub_distinct() == 1, "stub is fail-soft through shimx-resolved pointer");
  printf("shimx_glue_test: %s (resolved %d/%d)\n", fails ? "FAIL" : "PASS", ok, n);
  return fails ? 1 : 0;
}
