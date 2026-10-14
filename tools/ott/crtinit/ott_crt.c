/* ott_crt.c — CAB-138 (OTT-T5): lift 済み OTT wasm 用の CRT 初期化相当 + UCRT api-set 実装。
 *
 * native 側 (crtinit/crt_native.c) と**同一の状態**を作る:
 *
 * 1. ott_crt_init_tables():
 *    UCRT は関数ポインタを __security_cookie (image 0x180260ce0 = 静的既定 0x2b992ddfa232)
 *    で encode して .data に置く。decode(x) = ror(x ^ cookie, cookie & 0x3f)。
 *    .data 生値 0 を decode すると ror(cookie,50) = 0xae64b77e88c8000 という garbage 非ゼロに
 *    なり「解決済み」と誤解されて CFG dispatch (0x1801d2750 jmp rax) が暴走する — これが
 *    native SIGSEGV / wasm ott_unlifted の共通 root cause (実測: 両側 ret=0x...1c3e06 で一致)。
 *    実 CRT 初期化の観測可能な効果 = 全 encoded slot を enc(NULL) = cookie に初期化する
 *    ことなので、ここでは api-set 表 (0x18026c9f0, 34 entry) と個別 encoded slot
 *    (0x18026c028 / 0x18026c388 / 0x18026cb40 / 0x18026cb88 = _matherr user hook) に
 *    cookie を書く。DllMain / _initterm_e / _initterm は実行しない ((a) 実 lift ではなく
 *    (b) C 等価置換の判断 — 根拠は REPORT.md §2)。
 *    加えて __FlsIndex (0x1802610e4) に 1 を設定 (__acrt_initialize_thread_local_storage の
 *    等価処理: FlsAlloc の第 1 return 値。以降 getptd は FlsGetValue/FlsSetValue 経路を通る)。
 *
 * 2. imp_* : loader 系 Win32 import (lift 側からは IAT call として現れる)。
 *    native の同名実装と同じ意味論 (LoadLibraryExW = ハンドル代わりに名前ポインタ等)。
 *
 * 3. ovr_* : GetProcAddress が返す「関数ポインタ」の wasm 表現 = trampoline VA
 *    (0x1802f9000+16*i, image 末尾パディング = data_gen も jump table 窓も使わない領域)。
 *    x64c の --override で f_<trampoline> を C 実装に差し替え、ott_dispatch が解決する。
 *    native は実 C 関数ポインタを返す (mean 論理は同一)。
 */
#include "ott_cpu.h"

#define RET() (R[RSP] += 8)

/* ---- guest 側 image data への書き込み (ott_data_install 後に呼ぶこと) ---- */
/* guest image 内の番地は RVA (image VA - 0x180000000) で持ち、ott_gbase (wasm 上の base) を足して使う。
 * 既定 base 0x30000000 では従来の絶対番地 (0x30260ce0 等) と同一値になる。 */
#define GADDR(rva) (ott_gbase + (rva))
#define COOKIE_RVA 0x260ce0ull
#define APISET_TABLE_RVA 0x26c9f0ull
#define APISET_N 34              /* 0x18026c9f0〜0x18026cb00 (0x110 B)。CRT 初期化 0x1801c43a4 の rep stosq 個数 (and ecx,0x22) と一致 */
#define FLS_INDEX_RVA 0x2610e4ull
#define TRAMP_RVA 0x2f9000ull            /* trampoline 窓 (FlsAlloc = +0x00, 以下 16 B 刻み) */
static const uint64_t ENCODED_SLOT_RVA[] = { 0x26c028, 0x26c388, 0x26cb40, 0x26cb88 };
#define N_ESLOT (sizeof(ENCODED_SLOT_RVA) / sizeof(ENCODED_SLOT_RVA[0]))

/* MXCSR の software shadow (stmxcsr/ldmxcsr 用) は rt/ott_cpu.c の ott_mxcsr (既定 0x1f80) を共有 */

void ott_crt_init_tables(void) {
    uint64_t cookie = LD64(GADDR(COOKIE_RVA));
    for (int i = 0; i < APISET_N; i++) ST64(GADDR(APISET_TABLE_RVA + 8 * (uint64_t)i), cookie);
    for (unsigned k = 0; k < N_ESLOT; k++) ST64(GADDR(ENCODED_SLOT_RVA[k]), cookie);
    ST32(GADDR(FLS_INDEX_RVA), 1u);        /* __FlsIndex = FlsAlloc 第 1 return (native と共有の選択) */
}

/* ---- TLS/FLS slot (native k_TlsGetValue/TlsSetValue と同一意味論) ---- */
static void* g_tls[64];
static uint32_t g_fls_next = 2;            /* 1 は ott_crt_init_tables が __FlsIndex に割当済み */

/* ---- imp_* : IAT import (callee 側が ret 相当 R[RSP] += 8 を行う) ---- */
void imp_LoadLibraryExW(void) {            /* (name, res, flags) → ハンドル = 名前ポインタ自体 */
    R[RAX] = R[RCX];
    RET();
}
void imp_FreeLibrary(void) { R[RAX] = 1; RET(); }
void imp_GetModuleHandleW(void) { R[RAX] = R[RCX] ? R[RCX] : 0x1000; RET(); }

/* GetProcAddress(hmod, name) → api table の実体 (trampoline VA) or NULL。
 * native (crt_native.c PROCS) と同名一致の同じ表。 */
void imp_GetProcAddress(void) {
    uint64_t name = R[RDX];
    uint64_t fn = 0;
    if (name && (name >> 16)) {            /* MAKEINTRESOURCE (序数) は未対応 → NULL */
        char buf[48];
        unsigned i = 0;
        while (i < sizeof(buf) - 1) {
            uint8_t c = LD8(name + i);
            buf[i++] = (char)c;
            if (!c) break;
        }
        buf[sizeof(buf) - 1] = 0;
        const struct { const char* n; uint64_t fn; } T[] = {
            {"FlsAlloc", TRAMP_RVA + 0x00},
            {"FlsFree", TRAMP_RVA + 0x10},
            {"FlsGetValue", TRAMP_RVA + 0x20},
            {"FlsSetValue", TRAMP_RVA + 0x30},
            {"TlsGetValue", TRAMP_RVA + 0x20},
            {"TlsSetValue", TRAMP_RVA + 0x30},
            {"InitializeCriticalSectionEx", TRAMP_RVA + 0x40},
            {"GetSystemTimePreciseAsFileTime", TRAMP_RVA + 0x50},
        };
        for (unsigned k = 0; k < sizeof(T) / sizeof(T[0]); k++) {
            const char* a = T[k].n;
            unsigned j = 0;
            while (a[j] && a[j] == buf[j]) j++;
            if (!a[j] && !buf[j]) { fn = GADDR(T[k].fn); break; }
        }
    }
    R[RAX] = fn;
    RET();
}

void imp_TlsGetValue(void) { R[RAX] = (uint64_t)(uintptr_t)g_tls[R[RCX] & 63]; RET(); }
void imp_TlsSetValue(void) { g_tls[R[RCX] & 63] = (void*)(uintptr_t)R[RDX]; R[RAX] = 1; RET(); }
/* GetCurrentProcess / Rtl* / SEH 系 / TerminateProcess は意図的に未実装:
 * native も未実装 (missing import → exit 99) なので weak fail-fast で挙動を合わせる。 */
void imp_IsDebuggerPresent(void) { R[RAX] = 0; RET(); }
void imp_IsProcessorFeaturePresent(void) { R[RAX] = 1; RET(); }
void imp_RaiseException(void) {           /* native と同様 fail-fast (exit code 相当) */
    fprintf(stderr, "[ott] RaiseException(0x%llx) 到達 — fail-fast\n", (unsigned long long)R[RCX]);
    abort();
}

/* ---- ovr_* : trampoline override bodies (lifted ABI) ---- */
void ovr_fls_alloc(void) {                 /* FlsAlloc(cb) → index (native k_FlsAlloc と同一) */
    R[RAX] = (g_fls_next < 128) ? g_fls_next++ : 0xffffffffull;
    RET();
}
void ovr_fls_free(void) { R[RAX] = 1; RET(); }
void ovr_fls_get(void) { R[RAX] = (uint64_t)(uintptr_t)g_tls[R[RCX] & 63]; RET(); }
void ovr_fls_set(void) { g_tls[R[RCX] & 63] = (void*)(uintptr_t)R[RDX]; R[RAX] = 1; RET(); }
void ovr_cs_ex(void) { R[RAX] = 1; RET(); }             /* InitializeCriticalSectionAndSpinCount → TRUE */
void ovr_gstpaft(void) {                                /* GetSystemTimePreciseAsFileTime → 決定論固定 0 (FILETIME 8B) */
    ST64(R[RCX], 0);
    RET();
}
