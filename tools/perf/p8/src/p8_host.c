/* P8 MAIN_MODULE 側ホスト: side module を dlopen し、chain_block で N plugin を直列に呼ぶ。
 * 静的リンク版 (P8_STATIC) は p0_/p1_ ... を直接呼ぶ。 */
#include <stdint.h>
#include <string.h>
#ifdef P8_STATIC
extern void p0_plg_process(void);
#define DECL(n) extern void p##n##_plg_process(void); extern uint32_t p##n##_plg_in(void); extern uint32_t p##n##_plg_out(void); extern void p##n##_plg_init(void);
#include "static_decl.h"
static void (*proc[P8_N])(void) = {
#define E(n) p##n##_plg_process,
#include "static_tab.h"
};
static uint32_t (*pin[P8_N])(void) = {
#define E(n) p##n##_plg_in,
#include "static_tab.h"
};
static uint32_t (*pout[P8_N])(void) = {
#define E(n) p##n##_plg_out,
#include "static_tab.h"
};
static void (*pinit[P8_N])(void) = {
#define E(n) p##n##_plg_init,
#include "static_tab.h"
};
int chain_n(void) { return P8_N; }
#else
#include <dlfcn.h>
#define MAXP 128
static void (*proc[MAXP])(void); static uint32_t (*pin[MAXP])(void), (*pout[MAXP])(void); static void (*pinit[MAXP])(void);
static int np;
int load_plugin(const char* path) {
  void* h = dlopen(path, RTLD_NOW);
  if (!h) return -1;
  proc[np] = (void (*)(void))dlsym(h, "plg_process"); pin[np] = (uint32_t (*)(void))dlsym(h, "plg_in");
  pout[np] = (uint32_t (*)(void))dlsym(h, "plg_out"); pinit[np] = (void (*)(void))dlsym(h, "plg_init");
  if (!proc[np] || !pin[np] || !pout[np] || !pinit[np]) return -2;
  pinit[np]();
  return np++;
}
int chain_n(void) { return np; }
#endif

#ifdef P8_STATIC
void init_all(void) { for (int i = 0; i < P8_N; i++) pinit[i](); }
#endif
static float host_in[256];
float* host_in_ptr(void) { return host_in; }
uint32_t plugin_in(int i) { return pin[i](); }
uint32_t plugin_out(int i) { return pout[i](); }
/* 1 ブロック: host_in → plugin0.in → ... → pluginN-1.out (plugin 間は同一 memory 内 memcpy 1KiB) */
void chain_block(int n) {
  memcpy((void*)pin[0](), host_in, 1024);
  for (int i = 0; i < n; i++) {
    proc[i]();
    if (i + 1 < n) memcpy((void*)pin[i + 1](), (void*)pout[i](), 1024);
  }
}
/* 単体: plugin i を 1 回 (JS ホストが plugin 毎に呼ぶ構成との比較用) */
void call_one(int i) { proc[i](); }
