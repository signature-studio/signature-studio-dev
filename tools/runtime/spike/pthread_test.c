// emscripten pthread (PROXY_TO_PTHREAD + プリウォームプール) が headless Chrome で動くかの実機確認。
#include <pthread.h>
#include <stdio.h>
#include <stdatomic.h>
#include <emscripten.h>
#include <emscripten/threading.h>
static atomic_int counter;
static void *inc(void *a) { for (int i = 0; i < 1000000; i++) atomic_fetch_add(&counter, 1); return 0; }
static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER; static pthread_cond_t cv = PTHREAD_COND_INITIALIZER; static int turn; /* 0=main 1=worker */
static void *pong(void *a) { for (int i = 0; i < 5000; i++) { pthread_mutex_lock(&mu); while (turn != 1) pthread_cond_wait(&cv, &mu); turn = 0; pthread_cond_broadcast(&cv); pthread_mutex_unlock(&mu); } return 0; }
int main(void) {
  double t0 = emscripten_get_now();
  pthread_t th[4];
  for (int i = 0; i < 4; i++) pthread_create(&th[i], 0, inc, 0);
  for (int i = 0; i < 4; i++) pthread_join(th[i], 0);
  double t1 = emscripten_get_now();
  pthread_t p; pthread_create(&p, 0, pong, 0);
  double t2 = emscripten_get_now();
  for (int i = 0; i < 5000; i++) { pthread_mutex_lock(&mu); turn = 1; pthread_cond_broadcast(&cv); while (turn != 0) pthread_cond_wait(&cv, &mu); pthread_mutex_unlock(&mu); }
  pthread_join(p, 0);
  double t3 = emscripten_get_now();
  printf("{\"counter\":%d,\"expected\":4000000,\"spawnJoin4Ms\":%.1f,\"condPingPong5000Ms\":%.1f,\"rttUs\":%.1f,\"cores\":%d}\n", counter, t1 - t0, t3 - t2, (t3 - t2) * 1000 / 5000, emscripten_num_logical_cores());
  return 0;
}
