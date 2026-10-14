/* crt_native.c — CAB-138 (OTT-T5): CRT 初期化相当を native 参照側で成立させるハーネス。
 *
 * 背景: tools/ott/native/ott_native.c は CRT 初期化 (DllMain) を走らせない。UCRT の
 * api-set 遅延解決表 (0x18026c9f0, kernel32 代替表 0x18026c950) は .data 静的値 0 のまま。
 * float formatter (effGetParamDisplay float / op34) や数学エラー経路 (_handle_error) が
 * 最初の __acrt_getptd() で FlsSetValue 解決に入り、
 *   decode(table[6]) = ror(0 ^ cookie, cookie & 0x3f) = ror(0x2b992ddfa232, 50)
 *                    = 0xae64b77e88c8000 (非 0 ゆえ「解決済み」と誤認)
 *   → CFG dispatch (0x1801d2750 jmp rax) が garbage jump → native SIGSEGV / wasm ott_unlifted
 * という同一 fail-fast になる (native/wasm で rip/ret アドレスまで一致, 実測)。
 *
 * 本ハーネスの CRT 初期化 = **解決面の等価置換**: LoadLibraryExW / GetProcAddress / FreeLibrary /
 * GetModuleHandleW を実装して IAT 差し替えし、DLL 自身の解決機械語 (0x1801c38c8, native 実機械語 /
 * wasm は lift 済み) に表を埋めさせる。DllMain / _initterm は実行しない (=
 * 「(a) 実 lift」ではなく「(b) C 等価置換」判断の根拠は REPORT.md §2)。
 *
 * 使い方: ott_native.c を無改変 include (entry_native.c と同規約) し、ott_crt_patch() を
 * ott_load() 後に 1 回呼ぶ。OTT_CRTINIT=0 で差し替えを skip → 旧 fail-fast の陰性対照。
 *
 * entry_native.c (am_host) も取り込む: 入口 scenario 駆動に ott_am_addr / ott_am_counts が必要。
 */
#include "../entry/entry_native.c"   /* (内部で ../native/ott_native.c を include) */

/* ---- api-set / kernel32 関数の実装 (GetProcAddress が返す実体) ---- */

static uint32_t g_fls_next = 2;   /* FlsAlloc が返す index (1 は ott_crt_init_tables が __FlsIndex へ割当済み — wasm ott_crt.c と同一) */

static MS void* k_FlsAlloc(void* cb) { (void)cb; if (g_fls_next < 128) return (void*)(uint64_t)g_fls_next++; return (void*)(uint64_t)-1; }
static MS int k_FlsFree(uint32_t i) { (void)i; return 1; }
/* FlsGetValue / FlsSetValue は ott_native.c 側の k_TlsGetValue / k_TlsSetValue (g_tls[64]) を再利用 */

/* GetSystemTimePreciseAsFileTime: 決定論固定 (時刻は DSP/表示経路の観測対象でない。
 * 実行されても native/wasm 同一値にする意味で 0 固定)。FILETIME は 8 byte。 */
static MS void k_GetSystemTimePreciseAsFileTime(uint64_t* out) { *out = 0; }

/* api-set 関数表: 解決して返す名前 → 実体。NULL は「未提供」= resolver が -1 sentinel 化し
 * 呼出側は Tls 系 fallback / 失敗経路に落ちる (両側同一挙動)。 */
typedef struct { const char* name; void* fn; } ProcImpl;
static const ProcImpl PROCS[] = {
    {"FlsAlloc", (void*)k_FlsAlloc},
    {"FlsFree", (void*)k_FlsFree},
    {"FlsGetValue", (void*)k_TlsGetValue},
    {"FlsSetValue", (void*)k_TlsSetValue},
    {"TlsGetValue", (void*)k_TlsGetValue},
    {"TlsSetValue", (void*)k_TlsSetValue},
    {"InitializeCriticalSectionEx", (void*)k_CSi},
    {"GetSystemTimePreciseAsFileTime", (void*)k_GetSystemTimePreciseAsFileTime},
    {NULL, NULL}};

static MS void* k_LoadLibraryExW(const void* name, void* res, uint32_t flags) {
    (void)res; (void)flags;
    /* 実モジュールは不要: ハンドルは名前ポインタ自体を返す (GetProcAddress は名前引数のみ参照) */
    return (void*)name;
}
static MS int k_FreeLibrary(void* h) { (void)h; return 1; }
static MS void* k_GetModuleHandleW(const void* name) { return (void*)(name ? name : (const void*)0x1000); }

static MS void* k_GetProcAddress(void* hmod, const char* name) {
    (void)hmod;
    if (!name || !((uint64_t)name >> 16)) return NULL;   /* MAKEINTRESOURCE (序数) は未対応 → NULL */
    for (const ProcImpl* p = PROCS; p->name; p++)
        if (!strcmp(p->name, name)) return p->fn;
    return NULL;
}

/* ---- CRT 初期化の C 等価置換 (encoded slot の事前初期化) ----
 *
 * UCRT は関数ポインタを __security_cookie (0x180260ce0, 静的既定 0x2b992ddfa232) で
 * encode して .data に置く。decode(x) = ror(x ^ cookie, cookie & 0x3f)。
 * .data の生の 0 を decode すると ror(cookie, 50) = 0xae64b77e88c8000 (非 0) になり
 * 「解決済みポインタ」と誤解されるのが本 fail-fast の根因。
 * 実 CRT 初期化は「全 encoded slot を enc(NULL) = cookie に事前初期化」する
 * (decode(cookie) = 0 → 未解決 → 遅延解決 or 永久 unavailable (-1))。
 * → 本 equivalent init は各 encoded slot に cookie 値を書くだけ。DllMain/_initterm は不要。
 */
#define COOKIE_ADDR 0x180260ce0ULL
#define APISET_TABLE 0x18026c9f0ULL     /* UCRT api-set 関数ポインタ表 (idx 0..33, 34 entry) */
#define APISET_N 34                     /* ott_crt.c と同一 (rep stosq 個数 0x22 由来) */
/* そのほかの encoded slot (実測: cookie xor + ror 逆解析) */
static const uint64_t ENCODED_SLOTS[] = {
    0x18026c028, 0x18026c388, 0x18026cb40, 0x18026cb88,  /* matherr user hook = cb88 */
};
#define N_ESLOT (sizeof(ENCODED_SLOTS) / sizeof(ENCODED_SLOTS[0]))

void ott_crt_init_tables(void) {
    uint64_t cookie;
    memcpy(&cookie, (void*)(uintptr_t)COOKIE_ADDR, 8);
    uint64_t* t = (uint64_t*)(uintptr_t)APISET_TABLE;
    for (int i = 0; i < APISET_N; i++) t[i] = cookie;   /* enc(NULL) = 未解決 */
    for (size_t k = 0; k < N_ESLOT; k++) *(uint64_t*)(uintptr_t)ENCODED_SLOTS[k] = cookie;
    *(uint32_t*)(uintptr_t)0x1802610e4 = 1u;   /* __FlsIndex = FlsAlloc 第 1 return (wasm ott_crt.c と同一) */
}

/* ---- IAT 差し替え: Import Directory を再走査し、指定名の thunk slot を上書き ---- */
int ott_crt_patch(void) {
    /* ott_native.c の g_img に敷設済み。PE ヘッダは g_img 先頭に copy 済み */
    uint32_t pe; memcpy(&pe, g_img + 0x3c, 4);
    uint16_t osz; memcpy(&osz, g_img + pe + 20, 2);
    uint32_t idrva; memcpy(&idrva, g_img + pe + 24 + 112 + 8, 4);
    int patched = 0;
    for (uint8_t* d = g_img + idrva;; d += 20) {
        uint32_t oft, nm, ft; memcpy(&oft, d, 4); memcpy(&nm, d + 12, 4); memcpy(&ft, d + 16, 4);
        if (!nm) break;
        uint64_t* thunk = (uint64_t*)(g_img + ft);
        uint64_t* orig = (uint64_t*)(g_img + (oft ? oft : ft));
        for (; *orig; orig++, thunk++) {
            char name[96];
            if (*orig >> 63) snprintf(name, sizeof name, "%s!#%u", (char*)(g_img + nm), (unsigned)(*orig & 0xffff));
            else snprintf(name, sizeof name, "%s", (char*)(g_img + (*orig & 0x7fffffff) + 2));
            void* impl = NULL;
            if (!strcmp(name, "LoadLibraryExW")) impl = (void*)k_LoadLibraryExW;
            else if (!strcmp(name, "GetProcAddress")) impl = (void*)k_GetProcAddress;
            else if (!strcmp(name, "FreeLibrary")) impl = (void*)k_FreeLibrary;
            else if (!strcmp(name, "GetModuleHandleW")) impl = (void*)k_GetModuleHandleW;
            if (impl) { *thunk = (uint64_t)impl; patched++; }
        }
    }
    return patched;
}
