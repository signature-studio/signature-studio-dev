/* ft_engine_dump.c — GUI-9 (#186): gui_ft.c (text engine) 単体の決定性ダンプ。native と wasm32 (pthread/atomics ビルドの FreeType) の出力が一致することを
 * ft_wasm.sh で検証する (headless host は native 専用のため engine だけを wasm で走らせる)。usage: ft_engine_dump <fontdir> */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gui_ft.h"
void gui_failfast(const char *a, const char *w) { fprintf(stderr, "failfast %s %s\n", a, w ? w : ""); exit(3); }
static uint8_t *slurp(const char *dir, const char *f, size_t *n) {
  char p[512]; snprintf(p, sizeof p, "%s/%s", dir, f); FILE *fp = fopen(p, "rb"); if (!fp) exit(2);
  fseek(fp, 0, SEEK_END); *n = (size_t)ftell(fp); fseek(fp, 0, SEEK_SET); uint8_t *b = malloc(*n); if (fread(b, 1, *n, fp) != *n) exit(2); fclose(fp); return b;
}
int main(int argc, char **argv) {
  size_t n1, n2; uint8_t *os = slurp(argv[1], "OpenSans-Regular.ttf", &n1), *ba = slurp(argv[1], "Barlow-Regular.ttf", &n2);
  gui_ft_register_face("Open Sans", os, n1); gui_ft_register_face("Barlow", ba, n2);
  const GuiTextEngine *e = gui_ft_engine(); const char *names[2] = { "Open Sans", "Barlow" }; int hs[] = { -9, -12, -16, 13, -24 };
  const char *txt = "Hello, World! gjpqy 0123 @#%&";
  unsigned long long total = 1469598103934665603ULL;
  for (int fi = 0; fi < 2; fi++) for (int hi = 0; hi < 5; hi++) {
    uint16_t nm[32] = { 0 }; for (int i = 0; names[fi][i]; i++) nm[i] = (uint8_t)names[fi][i];
    void *f = e->open(nm, hs[hi], 400, 0); GuiTextMetrics m; e->metrics(f, &m);
    unsigned long long h = 1469598103934665603ULL; int adv = 0;
    for (const char *c = txt; *c; c++) { GuiGlyph g; e->glyph(f, (uint8_t)*c, 1, &g); adv += g.advance; for (int i = 0; i < g.w * g.h; i++) h = (h ^ g.cov[i]) * 1099511628211ULL; h = (h ^ (unsigned)(g.left + 64 * g.top + 4096 * g.advance)) * 1099511628211ULL; free(g.cov); }
    printf("%s %d asc=%d desc=%d avg=%d max=%d adv=%d cov=%016llx\n", names[fi], hs[hi], m.ascent, m.descent, m.avg_width, m.max_width, adv, h);
    total = (total ^ h) * 1099511628211ULL; e->close(f);
  }
  printf("TOTAL %016llx\n", total); return 0;
}
