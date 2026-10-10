// wvfs (Emscripten FS adapter) の C 側 probe: stdio の read/write が mount を通って
// Wvfs に届くこと。dir は事前に JS 側で作っておく (C stdio に mkdir は無い)。
#include <stdio.h>
#include <string.h>

int main(void) {
  // /fl (MEMFS): 読取系 mount との共存
  FILE* f = fopen("/fl/seed.txt", "rb");
  if (!f) { printf("ERR fl open\n"); return 1; }
  char b0[64] = {0};
  fread(b0, 1, 63, f);
  fclose(f);
  printf("FL=%s\n", b0);

  // /c/home (Wvfs): 新規書込 + 読み戻し
  FILE* o = fopen("/c/home/probe/dir/hello.bin", "wb");
  if (!o) { printf("ERR home open\n"); return 1; }
  const char* msg = "HELLO-WVFS";
  fwrite(msg, 1, strlen(msg), o);
  fclose(o);
  FILE* i2 = fopen("/c/home/probe/dir/hello.bin", "rb");
  if (!i2) { printf("ERR home reopen\n"); return 1; }
  char b1[64] = {0};
  fread(b1, 1, 63, i2);
  fclose(i2);
  printf("RT=%s match=%d\n", b1, strcmp(b1, msg) == 0);

  // /c/tmp (Wvfs): バイナリ
  FILE* t = fopen("/c/tmp/t.bin", "wb");
  if (!t) { printf("ERR tmp open\n"); return 1; }
  fwrite("\x01\x02\x03\x04", 1, 4, t);
  fclose(t);

  // JS が書いたファイルの読み
  FILE* j = fopen("/c/home/fromjs.bin", "rb");
  if (!j) { printf("ERR fromjs open\n"); return 1; }
  char b2[64] = {0};
  fread(b2, 1, 63, j);
  fclose(j);
  printf("JS=%s\n", b2);
  return 0;
}
