// Emscripten FS 経由で VFS を読む C プローブ (fopen/fread/fseek/stat/opendir)
#include <stdio.h>
#include <stdint.h>
#include <dirent.h>
#include <sys/stat.h>
#include <string.h>

int main(int argc, char **argv) {
  if (argc < 3) return 2;
  FILE *f = fopen(argv[1], "rb");
  if (!f) { printf("OPEN_FAIL %s\n", argv[1]); return 1; }
  uint32_t h = 2166136261u;
  size_t total = 0, n;
  static unsigned char buf[65536];
  while ((n = fread(buf, 1, sizeof buf, f)) > 0) {
    for (size_t i = 0; i < n; i++) { h ^= buf[i]; h *= 16777619u; }
    total += n;
  }
  fseek(f, 0, SEEK_END);
  long sz = ftell(f);
  fseek(f, 5, SEEK_SET);
  unsigned char b5[4] = {0};
  fread(b5, 1, 4, f);
  printf("FILE size=%zu ftell=%ld fnv=%08x b5=%02x%02x%02x%02x\n", total, sz, h, b5[0], b5[1], b5[2], b5[3]);
  fclose(f);
  DIR *d = opendir(argv[2]);
  int c = 0;
  if (d) { struct dirent *e; while ((e = readdir(d))) c++; closedir(d); }
  printf("DIR entries=%d\n", c);
  struct stat st;
  int r = stat(argv[1], &st);
  printf("STAT rc=%d size=%ld isreg=%d\n", r, (long)st.st_size, S_ISREG(st.st_mode) ? 1 : 0);
  FILE *g = fopen("/fl/does/not/exist", "rb");
  printf("MISSING %s\n", g ? "opened(BUG)" : "ENOENT");
  FILE *w = fopen("/fl/newfile", "wb");
  printf("WRITE %s\n", w ? "opened(BUG)" : "denied");
  return 0;
}
