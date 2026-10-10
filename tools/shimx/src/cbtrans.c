/* cbtrans.c — R2 コールバック変換の実体 + R3 lift ABI トークン表 (CAB-177 / shimx REPORT T2 hostbridge 接続)。
 *
 * 背景: lifted コード (FLEngine closure) が shimx API に渡す関数ポインタは guest VA / LVA の整数であって
 * wasm 関数テーブル index ではない。shimx がそのまま呼ぶと call_indirect が
 * "table index is out of bounds" で trap する (実測: M11 純リンク unit 18 の function_447860 →
 * EnumCalendarInfoW(0x4476d0)。tools/m11/shimx_link/REPORT.md §3-#3)。
 * CAB-211 (R2) で設けたフック口 shimx_set_callback_translator() の**変換実体**が本ファイル。
 *
 * 設計 (契約):
 *   - lift 側は VA→関数解決の正本 (tools/icall の __icall_dispatch 関数表+BLK 方式, または
 *     M11 の m11_icall) を **invoke 関数** `u64 invoke(u64 va, u64 a0..a7)` として登録する
 *     (shimx_cbtrans_set_invoke)。未知 va は例外ではなく 0 を返す規約 (列挙の穏当な打切り)。
 *   - 本モジュールは API 名別の **型付きトランポリン** (shimx がコールバックを呼ぶ wasm 署名と一致) を
 *     64 スロットのプールで提供し、slot→VA→invoke でlift 側へ落とす (uniform u64×8 ABI)。
 *   - 判別規則: コールバック値 < shimx_get_intptr_limit() (R1 の閾値, 既定 0x10000) は
 *     実 C 関数ポインタ (wasm テーブル index) とみなして恒等通過 (= M4 互換テスト等の直接 C 呼出を壊さない)。
 *     ≥ 閾値は guest VA とみなしてトランポリンへ (invoke が未知なら 0 = 穏当な縮退, trap しない)。
 *   - **寿命契約** (tools/shimx/REPORT.md §5「コールバック (R2)」の確定版):
 *     スロットは一度割当てると解放しない (同一 VA は常に同一トランポリン)。ゆえに
 *     同期系 (Enum* / InitOnceExecuteOnce: 呼出中のみ有効) はもちろん、
 *     非同期系 (CreateThread / FlsAlloc / CreateTimerQueueTimer / CreateThreadpoolWork:
 *     shimx オブジェクトが保持し続ける) でもトランポリンが無効化されない。
 *     コスト = 登録された distinct VA 数 × スロット (解放しないのでプロセス寿命で単調増加, 上限 64)。
 *   - トランスレータは shimx がコールバック引数を取る全 7 API の**登録時に 1 回**走る
 *     (CAB-211 検収コメントのフック契約どおり)。呼出は翻訳結果 (トランポリン) に対して行われる。
 *
 * R3 (同チケット): GetProcAddress で返す IL* (shell32 序数 16..190) / kernel32 UI言語 3 本を
 * **lift 側関数表から解決可能な実アドレス (トークン)** にする。トークン = SHX_LIFTTAB_TOKEN_BASE+index
 * (wasm メモリ上限外の値なので実ポインタと衝突しない)。shimx_lifttab_proc_resolver() を
 * shimx_set_proc_resolver() に登録すると GetProcAddress がトークンを返す。lift 側 dispatch
 * (--wrap=m11_icall 等) は shimx_lifttab_trampoline(token) で型付き thunk (u64×8 → 実 C 署名) を
 * 引いて呼べば lifted コードからの間接呼出しが実体接続される。
 * (現行 M11 IR は間接 call を lift しない = トークン実呼出は icall 復元 route 採用時に発生。往復実証は
 *  tools/hostbridge/cb/ ハーネスと tools/shimx/test/test_cbtrans.c で実施。)
 */
#include "shimx_internal.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#define SHX_CB_SLOTS 64
#define SHX_LIFTTAB_TOKEN_BASE 0x7F000000ull
#define SHX_LIFTTAB_N 13

typedef unsigned long long u64x;

/* ---- スロットプール + invoke ---- */
static shx_mutex_t g_cb_lk;
static shimx_cb_invoke_fn g_invoke;
static struct { uint32_t va; } g_slot[SHX_CB_SLOTS];
static int g_slots_used;
static uint32_t g_cb_reg, g_cb_calls;

static u64x slot_call(int s, uint32_t a0, uint32_t a1, uint32_t a2) {
    shimx_cb_invoke_fn f = g_invoke;
    uint32_t va = g_slot[s].va;
    g_cb_calls++;
    if (!f || !va) return 0;
    return f(va, (u64x)a0, (u64x)a1, (u64x)a2, 0, 0, 0, 0, 0);
}

/* 型付きトランポリン (shimx がコールバックを呼ぶ署名と wasm 型一致: ptr/int は i32)。
 * 6 形 × SHX_CB_SLOTS を X-macro で生成。arg 長は shimx の typedef に一致させる
 * (EnumCalendarInfoW は shimx の CALINFO_ENUMPROCW が 1 引数 = shimx 側契約に従う)。 */
#define CB_TRAMP_DEFS(s)                                                          \
    static int sxcb_i1_##s(uintptr_t a0) { return (int)slot_call(s, (uint32_t)a0, 0, 0); }          \
    static int sxcb_i2_##s(uintptr_t a0, uintptr_t a1) { return (int)slot_call(s, (uint32_t)a0, (uint32_t)a1, 0); } \
    static int sxcb_i3_##s(uintptr_t a0, uintptr_t a1, uintptr_t a2) { return (int)slot_call(s, (uint32_t)a0, (uint32_t)a1, (uint32_t)a2); } \
    static void sxcb_v1_##s(uintptr_t a0) { (void)slot_call(s, (uint32_t)a0, 0, 0); }               \
    static void sxcb_v2_##s(uintptr_t a0, uintptr_t a1) { (void)slot_call(s, (uint32_t)a0, (uint32_t)a1, 0); } \
    static void sxcb_v3_##s(uintptr_t a0, uintptr_t a1, uintptr_t a2) { (void)slot_call(s, (uint32_t)a0, (uint32_t)a1, (uint32_t)a2); }

#define X(s) CB_TRAMP_DEFS(s)
X(0) X(1) X(2) X(3) X(4) X(5) X(6) X(7) X(8) X(9) X(10) X(11) X(12) X(13) X(14) X(15)
X(16) X(17) X(18) X(19) X(20) X(21) X(22) X(23) X(24) X(25) X(26) X(27) X(28) X(29) X(30) X(31)
X(32) X(33) X(34) X(35) X(36) X(37) X(38) X(39) X(40) X(41) X(42) X(43) X(44) X(45) X(46) X(47)
X(48) X(49) X(50) X(51) X(52) X(53) X(54) X(55) X(56) X(57) X(58) X(59) X(60) X(61) X(62) X(63)
#undef X

#define A(s) sxcb_i1_##s,
static int (*const g_tr_i1[SHX_CB_SLOTS])(uintptr_t) = {
A(0) A(1) A(2) A(3) A(4) A(5) A(6) A(7) A(8) A(9) A(10) A(11) A(12) A(13) A(14) A(15)
A(16) A(17) A(18) A(19) A(20) A(21) A(22) A(23) A(24) A(25) A(26) A(27) A(28) A(29) A(30) A(31)
A(32) A(33) A(34) A(35) A(36) A(37) A(38) A(39) A(40) A(41) A(42) A(43) A(44) A(45) A(46) A(47)
A(48) A(49) A(50) A(51) A(52) A(53) A(54) A(55) A(56) A(57) A(58) A(59) A(60) A(61) A(62) A(63)
};
#undef A
#define A(s) sxcb_i2_##s,
static int (*const g_tr_i2[SHX_CB_SLOTS])(uintptr_t, uintptr_t) = {
A(0) A(1) A(2) A(3) A(4) A(5) A(6) A(7) A(8) A(9) A(10) A(11) A(12) A(13) A(14) A(15)
A(16) A(17) A(18) A(19) A(20) A(21) A(22) A(23) A(24) A(25) A(26) A(27) A(28) A(29) A(30) A(31)
A(32) A(33) A(34) A(35) A(36) A(37) A(38) A(39) A(40) A(41) A(42) A(43) A(44) A(45) A(46) A(47)
A(48) A(49) A(50) A(51) A(52) A(53) A(54) A(55) A(56) A(57) A(58) A(59) A(60) A(61) A(62) A(63)
};
#undef A
#define A(s) sxcb_i3_##s,
static int (*const g_tr_i3[SHX_CB_SLOTS])(uintptr_t, uintptr_t, uintptr_t) = {
A(0) A(1) A(2) A(3) A(4) A(5) A(6) A(7) A(8) A(9) A(10) A(11) A(12) A(13) A(14) A(15)
A(16) A(17) A(18) A(19) A(20) A(21) A(22) A(23) A(24) A(25) A(26) A(27) A(28) A(29) A(30) A(31)
A(32) A(33) A(34) A(35) A(36) A(37) A(38) A(39) A(40) A(41) A(42) A(43) A(44) A(45) A(46) A(47)
A(48) A(49) A(50) A(51) A(52) A(53) A(54) A(55) A(56) A(57) A(58) A(59) A(60) A(61) A(62) A(63)
};
#undef A
#define A(s) sxcb_v1_##s,
static void (*const g_tr_v1[SHX_CB_SLOTS])(uintptr_t) = {
A(0) A(1) A(2) A(3) A(4) A(5) A(6) A(7) A(8) A(9) A(10) A(11) A(12) A(13) A(14) A(15)
A(16) A(17) A(18) A(19) A(20) A(21) A(22) A(23) A(24) A(25) A(26) A(27) A(28) A(29) A(30) A(31)
A(32) A(33) A(34) A(35) A(36) A(37) A(38) A(39) A(40) A(41) A(42) A(43) A(44) A(45) A(46) A(47)
A(48) A(49) A(50) A(51) A(52) A(53) A(54) A(55) A(56) A(57) A(58) A(59) A(60) A(61) A(62) A(63)
};
#undef A
#define A(s) sxcb_v2_##s,
static void (*const g_tr_v2[SHX_CB_SLOTS])(uintptr_t, uintptr_t) = {
A(0) A(1) A(2) A(3) A(4) A(5) A(6) A(7) A(8) A(9) A(10) A(11) A(12) A(13) A(14) A(15)
A(16) A(17) A(18) A(19) A(20) A(21) A(22) A(23) A(24) A(25) A(26) A(27) A(28) A(29) A(30) A(31)
A(32) A(33) A(34) A(35) A(36) A(37) A(38) A(39) A(40) A(41) A(42) A(43) A(44) A(45) A(46) A(47)
A(48) A(49) A(50) A(51) A(52) A(53) A(54) A(55) A(56) A(57) A(58) A(59) A(60) A(61) A(62) A(63)
};
#undef A
#define A(s) sxcb_v3_##s,
static void (*const g_tr_v3[SHX_CB_SLOTS])(uintptr_t, uintptr_t, uintptr_t) = {
A(0) A(1) A(2) A(3) A(4) A(5) A(6) A(7) A(8) A(9) A(10) A(11) A(12) A(13) A(14) A(15)
A(16) A(17) A(18) A(19) A(20) A(21) A(22) A(23) A(24) A(25) A(26) A(27) A(28) A(29) A(30) A(31)
A(32) A(33) A(34) A(35) A(36) A(37) A(38) A(39) A(40) A(41) A(42) A(43) A(44) A(45) A(46) A(47)
A(48) A(49) A(50) A(51) A(52) A(53) A(54) A(55) A(56) A(57) A(58) A(59) A(60) A(61) A(62) A(63)
};
#undef X

typedef enum { CB_I1, CB_I2, CB_I3, CB_V1, CB_V2, CB_V3 } CbShape;

/* api 名 → トランポリン形状 (shimx の typedef = 呼出側 wasm 署名)。
 * 未知名は fail-fast (形状不明のまま返すと call_indirect 署名不一致 trap になるため) */
static CbShape shape_of(const char* api) {
    if (!strcmp(api, "EnumSystemLocalesW")) return CB_I1;
    if (!strcmp(api, "EnumCalendarInfoW")) return CB_I1;   /* shimx の CALINFO_ENUMPROCW は 1 引数 */
    if (!strcmp(api, "CreateThread")) return CB_I1;        /* DWORD (LPVOID) */
    if (!strcmp(api, "FlsAlloc")) return CB_V1;
    if (!strcmp(api, "CreateTimerQueueTimer")) return CB_V2;
    if (!strcmp(api, "CreateThreadpoolWork")) return CB_V3;
    if (!strcmp(api, "InitOnceExecuteOnce")) return CB_I3;
    fprintf(stderr, "[shimx] FAIL-FAST: cbtrans: unknown callback API '%s'\n", api);
    abort();
}

static const void* tr_addr(CbShape sh, int s) {
    switch (sh) {
    case CB_I1: return (const void*)g_tr_i1[s];
    case CB_I2: return (const void*)g_tr_i2[s];
    case CB_I3: return (const void*)g_tr_i3[s];
    case CB_V1: return (const void*)g_tr_v1[s];
    case CB_V2: return (const void*)g_tr_v2[s];
    case CB_V3: return (const void*)g_tr_v3[s];
    }
    return NULL;
}

/* slot 割当 (同一 va は同一 slot)。満杯は fail-fast (shimx 流儀: 問題を隠さない) */
static int slot_of(uint32_t va) {
    shx_mutex_lock(&g_cb_lk);
    int s = -1;
    for (int i = 0; i < SHX_CB_SLOTS; i++) {
        if (g_slot[i].va == va) { s = i; break; }
        if (s < 0 && !g_slot[i].va) s = i;
    }
    if (s >= 0 && !g_slot[s].va) { g_slot[s].va = va; g_slots_used++; g_cb_reg++; }
    shx_mutex_unlock(&g_cb_lk);
    if (s < 0) {
        fprintf(stderr, "[shimx] FAIL-FAST: cbtrans: callback slot exhausted (%d distinct VAs)\n", SHX_CB_SLOTS);
        abort();
    }
    return s;
}

void* shimx_cb_translator(const char* api, void* cb) {
    uintptr_t v = (uintptr_t)cb;
    if (shx_is_iptr(v)) return cb;                 /* C 関数ポインタ (wasm テーブル index) / 整数 → 恒等 */
    CbShape sh = shape_of(api);
    int s = slot_of((uint32_t)v);
    SHX_TRACE("cbtrans: %s VA 0x%x -> trampoline slot %d (invoke=%p)", api, (unsigned)v, s, (void*)g_invoke);
    return (void*)tr_addr(sh, s);
}

void shimx_cbtrans_set_invoke(shimx_cb_invoke_fn fn) { g_invoke = fn; }
shimx_cb_invoke_fn shimx_cbtrans_get_invoke(void) { return g_invoke; }

void* shimx_cbtrans_install(void) {
    void* prev = shimx_get_callback_translator();
    shimx_set_callback_translator(shimx_cb_translator);
    return prev;
}

int shimx_cbtrans_slots(void) { return g_slots_used; }
uint32_t shimx_cbtrans_registrations(void) { return g_cb_reg; }
uint32_t shimx_cbtrans_calls(void) { return g_cb_calls; }
uint32_t shimx_cbtrans_slot_va(int slot) { return (slot >= 0 && slot < SHX_CB_SLOTS) ? g_slot[slot].va : 0; }

void shimx_cbtrans_reset(void) {
    shx_mutex_lock(&g_cb_lk);
    memset(g_slot, 0, sizeof g_slot);
    g_slots_used = 0; g_cb_reg = 0; g_cb_calls = 0;
    shx_mutex_unlock(&g_cb_lk);
}

/* ===============================================================
 * R3: lift ABI トークン表 (shell32 IL* 10 本 + kernel32 UI言語 3 本)
 * =============================================================== */
typedef u64x (*shx_lift_thunk_fn)(u64x, u64x, u64x, u64x, u64x, u64x, u64x, u64x);

/* u64×8 (lift 側 uniform ABI) → 実 C 署名の marshal thunk */
#define THUNK(nm, expr) \
    static u64x th_##nm(u64x a0, u64x a1, u64x a2, u64x a3, u64x a4, u64x a5, u64x a6, u64x a7) { \
        (void)a1; (void)a2; (void)a3; (void)a4; (void)a5; (void)a6; (void)a7; \
        return (u64x)(expr); \
    }
THUNK(ILFindLastID,      (uintptr_t)ILFindLastID((const void*)(uintptr_t)a0))
THUNK(ILRemoveLastID,    (uint32_t)ILRemoveLastID((void*)(uintptr_t)a0))
THUNK(ILClone,           (uintptr_t)ILClone((const void*)(uintptr_t)a0))
THUNK(ILCloneFirst,      (uintptr_t)ILCloneFirst((const void*)(uintptr_t)a0))
THUNK(ILIsEqual,         (uint32_t)ILIsEqual((const void*)(uintptr_t)a0, (const void*)(uintptr_t)a1))
THUNK(ILCombine,         (uintptr_t)ILCombine((const void*)(uintptr_t)a0, (const void*)(uintptr_t)a1))
THUNK(ILGetSize,         (uint32_t)ILGetSize((const void*)(uintptr_t)a0))
THUNK(ILGetNext,         (uintptr_t)ILGetNext((const void*)(uintptr_t)a0))
static u64x th_ILFree(u64x a0, u64x a1, u64x a2, u64x a3, u64x a4, u64x a5, u64x a6, u64x a7) {
    (void)a1; (void)a2; (void)a3; (void)a4; (void)a5; (void)a6; (void)a7;
    ILFree((void*)(uintptr_t)a0);
    return 0;
}
THUNK(ILCreateFromPathW, (uintptr_t)ILCreateFromPathW((LPCWSTR)(uintptr_t)a0))
THUNK(GetThreadPreferredUILanguages,
    (uint32_t)GetThreadPreferredUILanguages((DWORD)a0, (ULONG*)(uintptr_t)a1, (LPWSTR)(uintptr_t)a2, (ULONG*)(uintptr_t)a3))
THUNK(SetThreadPreferredUILanguages,
    (uint32_t)SetThreadPreferredUILanguages((DWORD)a0, (LPCWSTR)(uintptr_t)a1, (ULONG*)(uintptr_t)a2))
THUNK(GetThreadUILanguage, (uint32_t)GetThreadUILanguage())

typedef struct { const char* name; DWORD ordinal; int dll; shx_lift_thunk_fn th; } LiftEnt;
/* dll: 0 = shell32.dll (名前+序数), 1 = kernel32.dll (名前) */
static const LiftEnt g_lifttab[SHX_LIFTTAB_N] = {
    { "ILFindLastID", 16, 0, th_ILFindLastID },
    { "ILRemoveLastID", 17, 0, th_ILRemoveLastID },
    { "ILClone", 18, 0, th_ILClone },
    { "ILCloneFirst", 19, 0, th_ILCloneFirst },
    { "ILIsEqual", 21, 0, th_ILIsEqual },
    { "ILCombine", 25, 0, th_ILCombine },
    { "ILGetSize", 152, 0, th_ILGetSize },
    { "ILGetNext", 153, 0, th_ILGetNext },
    { "ILFree", 155, 0, th_ILFree },
    { "ILCreateFromPathW", 190, 0, th_ILCreateFromPathW },
    { "GetThreadPreferredUILanguages", 0, 1, th_GetThreadPreferredUILanguages },
    { "SetThreadPreferredUILanguages", 0, 1, th_SetThreadPreferredUILanguages },
    { "GetThreadUILanguage", 0, 1, th_GetThreadUILanguage },
};

int shimx_lifttab_count(void) { return SHX_LIFTTAB_N; }
const char* shimx_lifttab_name(int i) { return (i >= 0 && i < SHX_LIFTTAB_N) ? g_lifttab[i].name : NULL; }

unsigned shimx_lifttab_token(const char* name, DWORD ordinal) {
    if (!name && !ordinal) return 0;
    for (int i = 0; i < SHX_LIFTTAB_N; i++) {
        if (ordinal) { if (g_lifttab[i].dll == 0 && g_lifttab[i].ordinal == ordinal) return SHX_LIFTTAB_TOKEN_BASE + (unsigned)i; }
        else if (name && !strcmp(g_lifttab[i].name, name)) return SHX_LIFTTAB_TOKEN_BASE + (unsigned)i;
    }
    return 0;
}

shimx_lift_thunk_fn shimx_lifttab_trampoline(unsigned token) {
    unsigned i = token >= SHX_LIFTTAB_TOKEN_BASE ? token - SHX_LIFTTAB_TOKEN_BASE : 0xffffffffu;
    if (i >= SHX_LIFTTAB_N) return NULL;
    return (shimx_lift_thunk_fn)g_lifttab[i].th;
}

/* shimx_set_proc_resolver 用: shell32 (序数/名前) と kernel32 (UI言語 3 本) をトークンで解決。
 * 戻り = トークン (lift 関数表から解決可能)。該当無しは NULL → shimx は組込み表 (実 C ポインタ) にフォールバック */
static int is_shell32(HMODULE m) {
    const char* n = shx_mod_name(m);
    return n && (!strcmp(n, "shell32.dll") || !strcmp(n, "shell32"));
}
static int is_kernel32(HMODULE m) {
    const char* n = shx_mod_name(m);
    return n && (!strncmp(n, "kernel32", 8));
}
void* shimx_lifttab_proc_resolver(HMODULE m, const char* name, DWORD ordinal) {
    unsigned t = 0;
    if (ordinal && is_shell32(m)) t = shimx_lifttab_token(NULL, ordinal);
    else if (name && is_shell32(m)) t = shimx_lifttab_token(name, 0);
    else if (name && is_kernel32(m)) t = shimx_lifttab_token(name, 0);
    if (!t) return NULL;
    SHX_TRACE("lifttab: %s # orm=%u -> token 0x%x", name ? name : "(null)", (unsigned)ordinal, t);
    return (void*)(uintptr_t)t;
}
