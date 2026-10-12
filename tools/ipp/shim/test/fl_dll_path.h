/* 実 IPP DLL (block24356_PE.bin) の既定パス: $FL_WIN64_DIR/extracted/block24356_PE.bin。
   FL_WIN64_DIR の既定値は tools/shared/env.sh が持つ (`source tools/shared/env.sh` 後に実行する)。 */
#ifndef FL_DLL_PATH_H
#define FL_DLL_PATH_H
#include <stdio.h>
#include <stdlib.h>

static const char *fl_ipp_dll_path(void) {
  static char buf[4096];
  const char *d = getenv("FL_WIN64_DIR");
  if (!d || !*d) {
    fprintf(stderr, "FL_WIN64_DIR 未設定: `source tools/shared/env.sh` するか DLL パスを引数で渡すこと\n");
    exit(2);
  }
  snprintf(buf, sizeof buf, "%s/extracted/block24356_PE.bin", d);
  return buf;
}
#endif
