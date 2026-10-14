/* icall_rt.c — icall_rewrite/ir_icall_restore 経路の runtime (memory-ABI + 間接 call dispatch + OTT 用 import 最小実装)
 * BLK レイアウト = icall_rewrite.py と一致: +0 target / +8 rcx / +0x10 rdx / +0x18 r8 / +0x20 r9 / +0x28..0x40 xmm0-3(low64) / +0x48 stk (= ICALL_BLK+0x100: 第 5 引数以降 12 語の連続コピー。呼出し点で [rsp+0x20+8k] を store) / +0x80 rax / +0x88 xmm0
 * 全 lifted 関数は `i64 f(void)` (引数/戻り値は BLK 経由) なので dispatch は VA→表引きして f() を呼ぶだけ。
 * 未登録 target / 未実装 import は呼び出し位置 (site VA) を表示して abort (fail-fast)。 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef ICALL_BLK
#define ICALL_BLK 0x34308000u
#endif
#ifdef ICALL_BLK_GLOBAL   /* #2128: BLK を wasm 内 global (IR の @__icall_blk と同一シンボル) に置く。固定 VA を使わない */
unsigned char __icall_blk[0x200] __attribute__((aligned(16)));
#define BLK_ADDR ((uintptr_t)__icall_blk)
#else
#define BLK_ADDR ((uintptr_t)ICALL_BLK)
#endif
#define BLKQ(off) (*(volatile uint64_t*)(BLK_ADDR + (off)))
#define SHIFT_NEW 0x30000000ull

extern const uint32_t icall_tbl_va[];
extern long long (*const icall_tbl_fn[])(void);
extern const unsigned icall_tbl_n;
extern const uint32_t icall_cfg_va[];
extern const unsigned icall_cfg_n;
void ott_data_install(void);

static uint64_t g_cur_site;
static unsigned g_depth;

static long long (*lookup(uint32_t va))(void) {
    unsigned lo = 0, hi = icall_tbl_n;
    while (lo < hi) {
        unsigned mid = (lo + hi) / 2;
        if (icall_tbl_va[mid] < va) lo = mid + 1; else hi = mid;
    }
    if (lo < icall_tbl_n && icall_tbl_va[lo] == va) return icall_tbl_fn[lo];
    return 0;
}

#define BLK_STK_OFF 0x48
#define BLK_STKBUF_OFF 0x100
#ifdef ICALL_IPP_SHIM   /* IPP shim 結合 (tools/ipp/shim): target が shim の cookie なら実行して戻る (それ以外は 0 で素通り) */
extern int ipp_shim_dispatch(void* blk);
#endif
#ifdef ICALL_CHECK_STK
static unsigned long long g_stk_n, g_stk_bad, g_stk_ptr_bad;
unsigned long long icall_stk_checked(void) { return g_stk_n; }
unsigned long long icall_stk_nonzero(void) { return g_stk_bad; }
unsigned long long icall_stk_ptr_bad(void) { return g_stk_ptr_bad; }
#endif

void __icall_dispatch(uint64_t site) {
    BLKQ(BLK_STK_OFF) = BLK_ADDR + BLK_STKBUF_OFF;
#ifdef ICALL_IPP_SHIM
    if (ipp_shim_dispatch((void*)BLK_ADDR)) return;
#endif
#ifdef ICALL_CHECK_STK   /* BLK+0x48 の pointer が BLK+0x100 と一致 / 8 byte 整列 / STKBUF 全体 (12 語) が線形メモリ内か。外れは g_stk_ptr_bad */
    { uint64_t p = BLKQ(BLK_STK_OFF);
      if (p != BLK_ADDR + BLK_STKBUF_OFF || (p & 7) || p + 8 * 12 > (uint64_t)__builtin_wasm_memory_size(0) * 65536) g_stk_ptr_bad++; }
#endif
#ifdef ICALL_CHECK_STK   /* 統計: 呼出し点ごとの stack コピー 12 語のうち非 0 の語数 (全 0 の site は stack 引数なし or 未配線) */
    { g_stk_n++; for (int k = 0; k < 12; k++) if (BLKQ(BLK_STKBUF_OFF + 8 * k)) { g_stk_bad++; break; } }
#endif
    uint64_t t = BLKQ(0);
    for (unsigned k = 0; k < icall_cfg_n; k++)   /* MSVC CFG thunk (jmp rax) 経由 → 実 target は rax-in */
        if ((uint32_t)t == icall_cfg_va[k]) { t = BLKQ(0x90); break; }
    long long (*f)(void) = lookup((uint32_t)t);
    if (!f || (t >> 32)) {
        fprintf(stderr, "[icall] FAIL-FAST: unresolved indirect target 0x%llx at site VA 0x%llx (shifted target; unshifted 0x%llx)\n",
                (unsigned long long)t, (unsigned long long)site, (unsigned long long)(t + 0x150000000ull));
        abort();
    }
#ifdef ICALL_TRACE_ALL
    { static int n; if (n++ < ICALL_TRACE_ALL) fprintf(stderr, "[icall] site 0x%llx -> target 0x%llx (fn %p)\n", (unsigned long long)site, (unsigned long long)t, (void*)f); }
#endif
    g_cur_site = site;
    g_depth++;
    f();
    g_depth--;
}

/* JS 入口: ABI は tools/ott/rt/ott_glue.c の ott_run と同形 (va は shifted 32bit) */
uint64_t ott_run(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3, uint64_t x0, uint64_t x1, uint64_t x2, uint64_t x3) {
    BLKQ(8) = a0; BLKQ(0x10) = a1; BLKQ(0x18) = a2; BLKQ(0x20) = a3;
    BLKQ(0x28) = x0; BLKQ(0x30) = x1; BLKQ(0x38) = x2; BLKQ(0x40) = x3;
    long long (*f)(void) = lookup(va);
    if (!f) { fprintf(stderr, "[icall] ott_run: unknown entry 0x%x\n", va); abort(); }
    f();
    return BLKQ(0x80);
}
uint64_t ott_xmm0(void) { return BLKQ(0x88); }

/* ---- alloc log (native 参照との heap レイアウト再生用: tools/ott/rt/ott_rt.c と同形式) ---- */
#define OTT_ALOG ((volatile uint32_t*)0x35f00000)
static void ott_alog(void* p, long long n) {
    uint32_t c = OTT_ALOG[0];
    if (c < 0x8000u) { OTT_ALOG[2 + 2 * c] = (uint32_t)(uintptr_t)p; OTT_ALOG[3 + 2 * c] = (uint32_t)n; OTT_ALOG[0] = c + 1; }
}
static void ff(const char* nm) { fprintf(stderr, "[icall] FAIL-FAST: %s called (site 0x%llx)\n", nm, (unsigned long long)g_cur_site); abort(); }

/* ---- Win32 import (RetDec が型付き signature で call する) ---- */
void* HeapAlloc(void* h, int flags, int size) {
    (void)h;
    void* p = (flags & 8) ? calloc(1, (size_t)size) : malloc((size_t)size);
    ott_alog(p, size);
    return p;
}
int HeapFree(void* h, int flags, void* p) { (void)h; (void)flags; (void)p; return 1; }
unsigned GetCurrentThreadId(void) { return 1; }  /* native 参照 (tools/ott/native/ott_native.c k_GetCurrentThreadId) と同値 */
int GetLastError(void) { return 0; }
void SetLastError(int e) { (void)e; }
void EnterCriticalSection(void* cs) { (void)cs; }
void LeaveCriticalSection(void* cs) { (void)cs; }
#define FF(name) void name(void) { ff(#name); }
FF(IsProcessorFeaturePresent) FF(UnhandledExceptionFilter) FF(RtlVirtualUnwind) FF(RtlLookupFunctionEntry) FF(RtlCaptureContext)
FF(GetStringTypeW) FF(RtlPcToFileHeader) FF(RaiseException) FF(TlsGetValue) FF(WriteConsoleW) FF(TlsSetValue) FF(LoadLibraryExW)
FF(CreateFileW) FF(WriteFile) FF(IsDebuggerPresent) FF(CloseHandle) FF(SetUnhandledExceptionFilter) FF(GetCurrentProcess)
FF(ExitProcess) FF(TerminateProcess) FF(FreeLibrary) FF(GetModuleHandleW) FF(GetModuleHandleExW) FF(GetProcAddress)
FF(MultiByteToWideChar) FF(WideCharToMultiByte) FF(GetConsoleOutputCP) FF(GetConsoleMode) FF(SetFilePointerEx) FF(__readgsqword)

/* ---- RetDec が decode せず declare のみにした CRT 小関数 (BLK から引数を読む adapter) ---- */
#define RCX BLKQ(8)
#define RDX BLKQ(0x10)
#define R8 BLKQ(0x18)
#define RAXW(v) (BLKQ(0x80) = (uint64_t)(v))
__attribute__((weak)) long long function_1801a2a00(void) { if ((int64_t)R8 > 0) memcpy((void*)(uintptr_t)RCX, (void*)(uintptr_t)RDX, (size_t)R8); RAXW(RCX); return 0; }
__attribute__((weak)) long long function_1801a30b0(void) { if ((int64_t)R8 > 0) memset((void*)(uintptr_t)RCX, (int)(RDX & 0xff), (size_t)R8); RAXW(RCX); return 0; }
#define UNL(a) __attribute__((weak)) long long function_##a(void) { ff("function_" #a " (decode されなかった内部関数)"); return 0; }
UNL(1801207f1) UNL(1801b2190) UNL(1801b21c5) UNL(1801c0c0c) UNL(1801cabc0)

/* comis/ucomis → EFLAGS(AH 形式: bit0 CF, bit2 PF, bit6 ZF) を BLK+0xB0 に書く (icall_rewrite.py の sahf 経路)。
 * 入力: BLK+0xA0/0xA8 = xmm low64, BLK+0xB8 = kind (0 comisd /1 ucomisd /2 comiss /3 ucomiss)。 */
void __icall_comis(void) {
    uint64_t a = BLKQ(0xA0), b = BLKQ(0xA8); uint32_t k = (uint32_t)BLKQ(0xB8);
    double x, y;
    if (k < 2) { memcpy(&x, &a, 8); memcpy(&y, &b, 8); }
    else { float fx, fy; uint32_t ia = (uint32_t)a, ib = (uint32_t)b; memcpy(&fx, &ia, 4); memcpy(&fy, &ib, 4); x = fx; y = fy; }
    uint8_t fl;
    if (x != x || y != y) fl = 0x01 | 0x04 | 0x40;      /* unordered: ZF=PF=CF=1 */
    else if (x > y) fl = 0;
    else if (x < y) fl = 0x01;
    else fl = 0x40;
    BLKQ(0xB0) = fl;
}
