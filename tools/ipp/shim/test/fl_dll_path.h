/* 実 IPP DLL (block24356_PE.bin) の既定パス解決。tools/shared/env.sh・paths.py と同じ優先順:
   $FL_WIN64_DIR → $ANALYSIS_DIR/win64 → 従来の VM 既定値 (FL_DLL_DEFAULT_ANALYSIS_DIR)/win64。
   env を source しなくても動く。既定値を変えるときは env.sh・paths.py・paths.mjs と揃えること。 */
#ifndef FL_DLL_PATH_H
#define FL_DLL_PATH_H
#include <stdio.h>
#include <stdlib.h>

static const char *fl_ipp_dll_path(void) {
  static char buf[4096];
  const char *d = getenv("FL_WIN64_DIR");
  if (!d || !*d) {
    fprintf(stderr, "FL_WIN64_DIR が未設定 (tools/shared/env.sh を source する)\n");
    exit(2);
  }
  snprintf(buf, sizeof buf, "%s/extracted/block24356_PE.bin", d);
  return buf;
}
#endif
