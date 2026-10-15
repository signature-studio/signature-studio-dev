/* gui_headless.h — native テスト用 host 代替 (gui_headless.c) */
#ifndef GUI_HEADLESS_H
#define GUI_HEADLESS_H
#include <stddef.h>
#include <stdint.h>
/* surface 統計 (gui_hl_stats.c)。RGB 3 バイト列の定義・背景の与え方は REPORT §21 */
typedef struct { uint32_t w, h, bg; uint64_t nonbg; uint32_t colors; uint8_t sha256[32]; } GuiHlStats;
void gui_hl_stats(const uint32_t *px, uint32_t w, uint32_t h, uint32_t bg, GuiHlStats *out);
int  gui_hl_nontrivial(const GuiHlStats *s); /* 非背景 > 0 かつ 色数 >= 2 */
void gui_sha256(const uint8_t *p, size_t n, uint8_t out[32]);
void gui_hl_start(uint32_t w, uint32_t h, int threaded); /* threaded=0 なら呼出側が gui_hl_drain() を回す */
void gui_hl_stop(void);
void gui_hl_drain(void);
void gui_hl_input(uint32_t type, uint32_t surf, int32_t x, int32_t y, uint32_t a, uint32_t b);
int  gui_hl_wait_line(const char *prefix, int timeout_ms);
const char *gui_hl_line(int i);
int  gui_hl_nlines(void);
uint32_t *gui_hl_desktop(void);
void gui_hl_recompose(void);
int  gui_hl_dump_ppm(const char *path);
#endif
