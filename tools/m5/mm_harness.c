/* M5 (b) FastMM 短絡化ハーネス:
 * - RetDec lift した FastMM allocator (function_412d60, M2 実測 66B)
 *   の IR を wasm heap shim (tools/shim/src/heap.c の HeapAlloc/HeapFree)
 *   経由で動かす。
 * - FastMM のブロックレイアウト (lift IR 実測 0x414ad0 と合致):
 *     [base+0 .. +3] 予約 / [base+4 .. +7] (内部管理)
 *     [base+8 ..+11] refcount (i32)   ← 412d60 が ptr-8 で読む
 *     [base+12..+15] length (i32)     ← 414ad0 が ptr-4 で書く
 *     [base+16 ....] payload (data)   ← ユーザポインタ (= data)
 *   mm_alloc(n) は shim HeapAlloc(16+n) を割当て, header を初期化し
 *   data = base+16 を返す。
 * - mm_free_inner(base) は 412d60 の free 路線 (function_409440 呼出) を
 *   ir5_patch [C9] redirect でここへ束ねた入口。free-bit shadow で
 *   double-free を検知 (fail-fast abort)。refcount<1 (underflow) は
 *   IR 側の分岐 (<1 → exit) で解放されないため, 呼び出し側で検知する。
 * - 整合性検証: mm_test_1000 で 1000 回の alloc+release (解放数カウント)。
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <emscripten.h>

/* shim heap (M4) を静的リンクする (tools/shim/src/heap.c)。 */
int64_t mm_free_inner(int64_t base_i64);   /* 前方宣言 (mm_resz で使用) */
extern void* HeapAlloc(void* heap, unsigned flags, size_t bytes);
extern int   HeapFree(void* heap, unsigned flags, void* p);

/* lifted IR 側 (ir5_patch で select された関数) */
extern int64_t function_412d60(int64_t arg1, int64_t arg2);
/* c_main.ll 内では ptr 引数形の IR define があるため wasm-ld 警告 — 実体(実装)
   はこの (i64,i64) 形で統一する。 */   /* FastMM release path (M2 実測 IR) */

/* FastMM block 定数 */
#define MM_HDR_SIZE      16
#define MM_REFCOUNT_OFF  8
#define MM_LEN_OFF       12

/* 内部 free-bit shadow: base → 状態 (1=live, 2=freed)。double-free 検知用。 */
#define MM_TRACK_CAP 8192
static uint64_t mm_track_base[MM_TRACK_CAP];
static uint8_t  mm_track_state[MM_TRACK_CAP];
static int32_t mm_track_probe_min = 0, mm_track_probe_max = 0;
static uint32_t mm_alloc_count = 0;
static uint32_t mm_free_count = 0;

static int track_index(uint64_t base, int create, int* existed) {
    uint64_t h = base ^ (base >> 20);
    int i = (int)(h & (MM_TRACK_CAP - 1));
    { int lo_ = (int)((h & 0xffff)) & 1; (void)lo_; }
    for (int k = 0; k < MM_TRACK_CAP; k++) {
        int j = (i + k) & (MM_TRACK_CAP - 1);
        if (mm_track_base[j] == base) {
            if (existed) *existed = 1;
            return j;
        }
        if (mm_track_base[j] == 0) {
            if (!create) {
                if (existed) *existed = 0;
                return -1;
            }
            mm_track_base[j] = base;
            if (existed) *existed = 0;
            return j;
        }
    }
    /* overflow → fail-fast */
    fprintf(stderr, "[mm] FAIL-FAST: track table overflow\n");
    fflush(stderr);
    abort();
    return -1;
}

static void* mm_raw_alloc(size_t n, int32_t refcount, int32_t len) {
    void* base = HeapAlloc((void*)0x1, 0 /*HEAP_ZERO 相当は要求しない*/, MM_HDR_SIZE + n);
    if (!base) return 0;
    /* FastMM 布局 (lift IR 0x414ad0 実測): block base への refcount@+8, len@+12,
     * payload は base+16 (= 返す data ポインタ)。412d60 は data-8 / data-16 を読む。 */
    *(int32_t*)((unsigned char*)base + MM_REFCOUNT_OFF) = refcount;
    *(int32_t*)((unsigned char*)base + MM_LEN_OFF) = len;
    if (getenv("MM_TRACE")) { fprintf(stderr, "[mm][trace] mm_allocw len=%d base=0x%llx\n", len, (unsigned long long)(uintptr_t)base); fflush(stderr); }
    mm_alloc_count++;
    int idx = track_index((uint64_t)(uintptr_t)base, 1, 0);
    mm_track_state[idx] = 1;
    return (void*)((unsigned char*)base + MM_HDR_SIZE);
}

/* 409470 (FastMM ResizeBlock 相当; native asm 0x409470 の IR 実測語義で
 * 新ブロックを割替える最小模倣 — 戻り値 = 新ブロック base)。
 * IR 側 (414b2b) は戻り値ではなくスタック上の新 base を利用するため、
 * C は IR が期待する「新 base をスタック引数に書く」契約で返す。 */
EMSCRIPTEN_KEEPALIVE
int64_t mm_resz(int64_t varpp_i64, int64_t newSize) {
    void* oldVarPtr = (void*)(uintptr_t)(uint32_t)(unsigned int)varpp_i64;
    /* old data ptr (その block base = old - 16) */
    void* oldData = 0;
    if (oldVarPtr) oldData = (void*)(uintptr_t)(*(uint64_t*)(uint8_t*)oldVarPtr);
    void* oldBase = oldData;   /* stack_var_-48 には block base (=data-16) が入る */
    void* nb = HeapAlloc((void*)0x1, 0, 24 + (size_t)newSize + 2);
    if (!nb) return 0;
    if (oldData) {
        /* 内容の copy (min(oldLen, newSize)) */
        int32_t oldLen = *(int32_t*)((unsigned char*)oldBase + MM_LEN_OFF);
        {int32_t ol2 = *(int32_t*)((unsigned char*)oldData - MM_HDR_SIZE + MM_LEN_OFF); (void)ol2;}
        int32_t copy = oldLen < (int32_t)newSize ? oldLen : (int32_t)newSize;
        __builtin_memcpy((unsigned char*)nb, (unsigned char*)oldData, (size_t)copy);
        /* old block を自由化済として count 埋める (IR は 412d60 で後続解放するが,
         * resize 路線では oldBase をそのまま捨てるため C 側で整合) */
        mm_free_inner((int64_t)(uintptr_t)oldBase);
    }
    if (getenv("MM_TRACE")) { fprintf(stderr, "[mm][trace] mm_resz newSize=%d base=0x%llx\n", (int)newSize, (unsigned long long)(uintptr_t)nb); fflush(stderr); }
    mm_alloc_count++;
    int idx = track_index((uint64_t)(uintptr_t)nb, 1, 0);
    mm_track_state[idx] = 1;
    /* IR: 新 base をスタック上の var に書く (414b2b 旧実装と同型) */
    if (oldVarPtr) *(uint64_t*)(uint8_t*)oldVarPtr = (uint64_t)(uintptr_t)nb;
    return (int64_t)(uintptr_t)nb;
}

/* lifted IR extern (c_main.ll 由来; CallSite 整合) */
extern int64_t function_414ad0(int64_t a, int64_t b);
extern int64_t function_409ef0(int64_t a, int64_t b);

/* 1000 回整合テストの本体: alloc → payload 書込/検証 → release (rotch IR 経由) */
EMSCRIPTEN_KEEPALIVE
void* mm_alloc(int n) {
    return (void*)mm_raw_alloc((size_t)n, 1, n);
}
EMSCRIPTEN_KEEPALIVE
void* mm_alloc_ref0(int n) {
    /* underflow シナリオ用: refcount=0 のブロック */
    return (void*)mm_raw_alloc((size_t)n, 0, n);
}
EMSCRIPTEN_KEEPALIVE
int32_t mm_refcount(void* data) {
    return *(int32_t*)((unsigned char*)data - MM_HDR_SIZE + MM_REFCOUNT_OFF);
}
EMSCRIPTEN_KEEPALIVE
int32_t mm_is_freed(void* data) {
    void* base = (unsigned char*)data - MM_HDR_SIZE;
    int existed = 1;
    int idx = track_index((uint64_t)(uintptr_t)base, 0, &existed);
    if (!existed || idx < 0) return 0;
    return mm_track_state[idx] == 2;
}
EMSCRIPTEN_KEEPALIVE
uint32_t mm_get_alloc_count(void) { return mm_alloc_count; }
EMSCRIPTEN_KEEPALIVE
uint32_t mm_get_free_count(void)  { return mm_free_count; }

/* shim heap free ビト (重複 free 検知 fail-fast)。412d60 closure 内の
 * function_409440 呼出 (block free) がここへ [C9] redirect される。 */
EMSCRIPTEN_KEEPALIVE
int64_t mm_free_inner(int64_t base_i64) {
    void* base = (void*)(uintptr_t)(uint32_t)(unsigned int)base_i64;
    int existed = 1;
    int idx = track_index((uint64_t)(uintptr_t)base, 0, &existed);
    if (!existed || idx < 0 || mm_track_state[idx] == 2) {
        fprintf(stderr,
                "[mm] FAIL-FAST: double-free 検知 base=0x%llx (track existed=%d idx=%d state=%d)\n",
                (unsigned long long)(uint32_t)(unsigned int)base_i64,
                existed, idx, existed ? mm_track_state[idx] : -1);
        fflush(stderr);
        abort();
    }
    mm_track_state[idx] = 2;
    if (!HeapFree((void*)0x1, 0, base)) {
        fprintf(stderr, "[mm] FAIL-FAST: HeapFree 失敗 base=0x%llx\n",
                (unsigned long long)(uint32_t)(unsigned int)base_i64);
        fflush(stderr);
        abort();
    }
    mm_free_count++;
    return 0;
}

/* FastMM release 正規路線: lifted function_412d60 (IR) を呼ぶ
 * (IR: store 0 at [ptr]; refcnt--[ptr-8]; if refcnt==1 → mm_free_inner(ptr-16)) */
EMSCRIPTEN_KEEPALIVE
int64_t mm_release(void* data) {
    return function_412d60((int64_t)(uintptr_t)data, 0);
}

/* 1000 回整合テスト: alloc → payload 書込/検証 → release (IR 経由)。
 * 戻り値: 0=OK (1000 alloc / 1000 free が消化), 非 0=不一致 */
EMSCRIPTEN_KEEPALIVE
int32_t mm_test_1000(void) {
    uint32_t a0 = mm_alloc_count, f0 = mm_free_count;
    static const int sizes[8] = {8, 16, 24, 48, 96, 160, 256, 512};
    for (int i = 0; i < 1000; i++) {
        int n = sizes[i & 7];
        void* data = mm_alloc(n);
        if (!data) return 10;
        void* base = (unsigned char*)data - MM_HDR_SIZE;
        if (mm_refcount(data) != 1) return 11;
        /* payload パターン書込+検証 (32bit 単位) */
        volatile uint32_t* p32 = (volatile uint32_t*)data;
        int words = n / 4;
        for (int w = 0; w < words; w++) p32[w] = (uint32_t)(0x53484d34u + (uint32_t)i + (uint32_t)w);
        for (int w = 0; w < words; w++)
            if (p32[w] != (uint32_t)(0x53484d34u + (uint32_t)i + (uint32_t)w)) return 12;
        function_412d60((int64_t)(uintptr_t)data, 0);
        /* release 後: IR が store 0 at [data] を行い refcnt==1 で mm_free_inner 呼出 */
        if (mm_free_count != f0 + (uint32_t)(i + 1)) return 13;
    }
    if (mm_alloc_count - a0 != 1000) return 14;
    if (mm_free_count - f0 != 1000) return 15;
    fprintf(stderr, "[mm] mm_test_1000 OK: alloc=1000 free=1000 (wasm heap shim 経由)\n");
    fflush(stderr);
    return 0;
}

/* double-free fail-fast テスト (呼ぶと abort する; node から別プロセスで実行) */
EMSCRIPTEN_KEEPALIVE
void mm_failfast_double_free(void) {
    /* 明示的な mm_free_inner 重複呼出 (IR 層を迂回した shim 層の検知を確認) */
    void* data = mm_alloc(32);
    void* base = (unsigned char*)data - MM_HDR_SIZE;
    mm_track_state[track_index((uint64_t)(uintptr_t)base, 1, 0)] = 1;
    mm_free_inner((int64_t)(uintptr_t)base);   /* 1 回目: OK */
    /* 2 回目: track state==2 → 検知 → abort (fail-fast) */
    int64_t spare = 0;
    mm_free_inner((int64_t)(uintptr_t)base);
    (void)spare;
}

/* underflow (refcount 0 でリリース → IR は解離せず残り, リリースされない) 検知 */
EMSCRIPTEN_KEEPALIVE
int32_t mm_test_underflow_leak(void) {
    void* data = mm_alloc_ref0(32);   /* refcount=0 */
    function_412d60((int64_t)(uintptr_t)data, 0);   /* IR: refcnt<1 → 何もしない */
    /* リリースされないことを検知 → リーク (underflow 避けの IR 分岐が効いている) */
    int freed = mm_is_freed(data);
    if (freed) {
        fprintf(stderr, "[mm] FAIL-FAST: underflow 対象が意図せず free された\n");
        fflush(stderr);
        abort();
    }
    /* 手動解放で後始末 (リーク状態を正当化しておく) */
    void* base = (unsigned char*)data - MM_HDR_SIZE;
    mm_free_inner((int64_t)(uintptr_t)base);
    return 1;
}

/* ---- (c) try-finally 実測用: 0x409fe0 (ParamCount 相当) の FastMM 送給側 —
 * 0x412c20 (System._LStrNew 相当, lift IR 0x412c79 段の語義) を
 * wasm-heap shim 上に置換実装する:
 *   base = HeapAlloc(len + 24); (中身は未初期化 → IR が書く)
 *   実装側で refcount@base+8 = 0 に.RestController は IR が行う (lift IR 実測:
 *   +8=refcount 1, +12=len, +6=flag 2, +4=global flag, データ末尾 NUL)。
 *   戻り値は data (base+16)。
 */
EMSCRIPTEN_KEEPALIVE
int64_t mm_allocw(int64_t len_i64) {
    int32_t len = (int32_t)len_i64;
    void* base = HeapAlloc((void*)0x1, 0, 24 + (size_t)len + 2);
    if (!base) return 0;
    *(int32_t*)((unsigned char*)base + MM_REFCOUNT_OFF) = 1;   /* FastMM 本物合わせ (412d60 free 分岐稼働) */
    *(int32_t*)((unsigned char*)base + MM_LEN_OFF) = len;
    if (getenv("MM_TRACE")) { fprintf(stderr, "[mm][trace] mm_allocw len=%d base=0x%llx\n", len, (unsigned long long)(uintptr_t)base); fflush(stderr); }
    mm_alloc_count++;
    int idx = track_index((uint64_t)(uintptr_t)base, 1, 0);
    mm_track_state[idx] = 1;
    return (int64_t)(uintptr_t)((unsigned char*)base + MM_HDR_SIZE);
}

/* 0x414850 (native 実測: `mov rax, rcx; if rcx==0: rax = [global]+16`
 * — "nil ⇒ 既定ブロックデータ領域" を wasm 上で模す (実測値は node の使用 RAM の
 * 置換ではなく lift IR 引数の意味で: IR [%46 = call 414850(i64 %7)] は
 * 引数 x == 0 でない限り x をそのまま返すので C で再現する).
 */
EMSCRIPTEN_KEEPALIVE
int64_t mm_nilex(int64_t x) {
    return x;
}

/* 0x409c80 (FastMM サブパス; lift work_c47 IR 実測: ret 値は呼び出し側で使われず,
   ヘッダ内部処理のみ) — Mini-PoC では no-op とする (実効果は 412c20/412d60 側の
   header と整合し, alloc/free カウンタの一致は mm_allocw/mm_free_inner 側で担保される)。 */
EMSCRIPTEN_KEEPALIVE
int64_t mm_stub_c80(int64_t a, int64_t b, int64_t c) {
    (void)a; (void)b; (void)c;
    return 0;
}

/* GetCommandLineW 相当 (C 側保持 VA 提供者; node が VA を事前登録) */
static int64_t g_cmdline_va = 0;
EMSCRIPTEN_KEEPALIVE
void mm_set_cmdline_va(int64_t va) { g_cmdline_va = va; }
EMSCRIPTEN_KEEPALIVE
void* GetCommandLineW(void) { return (void*)(uintptr_t)g_cmdline_va; }

/* (c) 本体: lifted function_409fe0 (ParamCount 相当, UHANDLER=try-finally を含む)
 * を実行し, 戻り値 (パラメタ数) を返す。finally 路線 (末尾 412d60 呼出) の
 * feed は正常 exit で走る — alloc/free カウンタ一致 (1000 回ではなく 1 回の側
 * but 同型) は node 側で mm_get_alloc/free_count の差分で確認。 */
extern int64_t function_409fe0(void);
extern int64_t function_407040(void);

EMSCRIPTEN_KEEPALIVE
int64_t m5_run_paramcount(void) {
    return function_409fe0();
}
