/* lifted コード → shimx のコールバック引数アダプタ (暫定; shimx REPORT T2 hostbridge の先取り, --fix 時のみリンク)。
 * lifted コードが渡す関数ポインタは VA/LVA (整数) で wasm の table index ではない。shimx がそのまま呼ぶと call_indirect が
 * "table index is out of bounds" で trap する (実測: unit 18 の function_447860 → EnumCalendarInfoW)。
 * ここでは列挙系 (同期呼出し・コールバックは呼出し中のみ) だけ、m11_icall (VA→トランポリン表) 経由のトランポリンに差し替える。
 * 非同期コールバック (CreateThread / タイマ / FlsAlloc) は未対応 (REPORT の要求リスト)。 */
typedef unsigned long long u64;
extern u64 m11_icall(u64 target, u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7);
extern int __real_EnumCalendarInfoW(void*, unsigned, unsigned, unsigned);
extern int __real_EnumSystemLocalesW(void*, unsigned);
extern unsigned sxcb_count;

static u64 g_cb;
unsigned sxcb_count;   /* アダプタ経由の呼出し回数 (診断) */
static int tramp1(void* s) { sxcb_count++; return (int)m11_icall(g_cb, (u64)(unsigned long)s, 0, 0, 0, 0, 0, 0, 0); }

int __wrap_EnumCalendarInfoW(void* proc, unsigned loc, unsigned cal, unsigned type) {
    u64 prev = g_cb; g_cb = (u64)(unsigned long)proc;
    int r = __real_EnumCalendarInfoW(proc ? (void*)tramp1 : 0, loc, cal, type);
    g_cb = prev; return r;
}
int __wrap_EnumSystemLocalesW(void* proc, unsigned flags) {
    u64 prev = g_cb; g_cb = (u64)(unsigned long)proc;
    int r = __real_EnumSystemLocalesW(proc ? (void*)tramp1 : 0, flags);
    g_cb = prev; return r;
}
