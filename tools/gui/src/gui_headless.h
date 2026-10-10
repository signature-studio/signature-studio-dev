/* gui_headless.h — native テスト用 host 代替 (gui_headless.c) */
#ifndef GUI_HEADLESS_H
#define GUI_HEADLESS_H
#include <stdint.h>
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
