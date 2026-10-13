/* RT-2 本番 pthread ビルドの boot e2e 用 main (shim MT + 本番 emcc フラグ)。
 * PROXY_TO_PTHREAD 下では main は pthread 上で動く。検証項目:
 *   1. shim の MT 自己テスト (tools/shim/test/test_main.c を -Dmain=shim_selftest_main で取り込み)
 *   2. 4 スレッド x 1M atomic add == 4,000,000
 *   3. main が runtime main thread 上で動いていない (= PROXY_TO_PTHREAD が効いている)
 *   4. 192 MiB 確保 (memory grow) を別 pthread で検証 (GROWABLE_ARRAYBUFFERS=2 + shared memory)
 * -DMT_NEG: 2 を非 atomic にしたネガティブコントロール (lost update で 4,000,000 に届かない)。
 * 結果は最終行 "MT_BOOT_RESULT {json}"。
 */
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <emscripten.h>
#include <emscripten/threading.h>

extern int shim_selftest_main(void);

#ifdef MT_NEG
static volatile int counter;
#define INC() (counter++)
#else
static atomic_int counter;
#define INC() atomic_fetch_add(&counter, 1)
#endif

static void *inc(void *a) { (void)a; for (int i = 0; i < 1000000; i++) INC(); return 0; }

#define BIG (192u * 1024u * 1024u)
static uint8_t *big;
static uint64_t big_sum;
static void *summer(void *a) { (void)a; uint64_t s = 0; for (size_t i = 0; i < BIG; i += 4096) s += big[i]; big_sum = s; return 0; }

int main(void) {
  int shim_rc = shim_selftest_main();
  int proxied = !emscripten_is_main_runtime_thread();

  double t0 = emscripten_get_now();
  pthread_t th[4];
  for (int i = 0; i < 4; i++) pthread_create(&th[i], 0, inc, 0);
  for (int i = 0; i < 4; i++) pthread_join(th[i], 0);
  double inc_ms = emscripten_get_now() - t0;

  size_t heap0 = emscripten_get_heap_size();
  big = malloc(BIG);
  uint64_t want = 0;
  if (big) for (size_t i = 0; i < BIG; i += 4096) { big[i] = (uint8_t)(i / 4096); want += (uint8_t)(i / 4096); }
  pthread_t s; pthread_create(&s, 0, summer, 0); pthread_join(s, 0);
  size_t heap1 = emscripten_get_heap_size();
  int grow_ok = big && big_sum == want && heap1 > heap0;

  int ok = shim_rc == 0 && counter == 4000000 && proxied && grow_ok;
  printf("MT_BOOT_RESULT {\"shimRc\":%d,\"counter\":%d,\"expected\":4000000,\"proxied\":%d,\"growOk\":%d,\"heapBeforeMiB\":%zu,\"heapAfterMiB\":%zu,\"incMs\":%.1f,\"cores\":%d,\"ok\":%d}\n",
         shim_rc, (int)counter, proxied, grow_ok, heap0 >> 20, heap1 >> 20, inc_ms, emscripten_num_logical_cores(), ok);
  fflush(stdout);
  return ok ? 0 : 1;
}
