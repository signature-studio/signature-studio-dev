/* shimx 結合グルー (tools/shimx 読み取り専用 API のみ使用): "dsp_ippv2_x64.dll" を擬似モジュールとして登録し、420 名を GetProcAddress で引けるようにする。
   FL の LoadProc は GetProcAddress(plain 名) → (無ければ) "legacy90"+名 の順。plain 名 420 件を登録するので legacy90 には到達しない。
   build: -I tools/shimx/src を付けて本ファイルを lift 側モジュールにリンクし、起動時 (FL の LoadLibraryW より前) に ipp_shim_install_shimx() を 1 回呼ぶ。 */
#include "shimx.h"
#include "ipp_shim.h"

HMODULE ipp_shim_install_shimx(void) {
  static char s_image[4096] __attribute__((aligned(4096)));   /* 擬似モジュールの base (ハンドル値) */
  HMODULE h = shimx_module_register("dsp_ippv2_x64.dll", (HMODULE)(uintptr_t)s_image, "C:\\Program Files\\Image-Line\\FL Studio 2026\\Shared\\dsp_ippv2_x64.dll");
  if (!h) return 0;
  for (int i = 0; i < ipp_shim_table_count; i++) shimx_proc_register(h, ipp_shim_table[i].name, 0, (void *)(uintptr_t)ipp_shim_cookie(i));
  return h;
}
