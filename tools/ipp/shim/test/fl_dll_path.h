/* 実 IPP DLL (block24356_PE.bin) のパス解決。FL_WIN64_DIR (fl-win64 の展開先) を必須とし、
   未設定なら exit 2。既定値は持たない (#3830)。直接実行するときは FL_WIN64_DIR=<展開先> を与えるか、
   tools/shared/env.sh を source する。 */
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
