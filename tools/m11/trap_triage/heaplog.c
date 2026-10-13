/* #483 heap ログ (試験用): 実 FreeMem / GetMem 裏の 407e20 / 407a50 を包み, 全 free 番地を [free] 行, 全 alloc を [alloc] 行で stderr に出す.
 * 使い方: cat m11_ov.c trap_triage/heaplog.c > work/ov_ablate.c → emcc -c → work/obj/ov.o → m11_build.sh → SV_PROG=1 SV_TRACE_AT=99999 node trap_triage/survey_units.mjs; "unit N" 行と突合して alloc 履歴に無い free (= 非 heap 番地の free) を探す */
extern u64 function_407a50__lifted(u64); extern u64 function_407e20__lifted(u64);
u64 function_407a50(u64 n) { u64 r = function_407a50__lifted(n); fprintf(stderr, "[alloc] %llx n=%llu\n", r, n); return r; }
u64 function_407e20(u64 p) { fprintf(stderr, "[free] %llx\n", p); return function_407e20__lifted(p); }
