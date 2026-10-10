/* SR-2b authstub 実行ハーネス (wasm)。
 *
 * 検証対象: lift 実 IR (patched_base_lf → mkrun_ll 抽出の function_1800c2b50 / function_18004fad0)
 *   - controller setState: patched (function_1800c2b50) と pre (function_1800c2b50_pre) を同梱し差を実測
 *   - DSP setState (function_18004fad0, patched)
 * callee は全て mock (分岐駆動 stub)。JSON 実体・DOM は含まない。
 * mock は lift IR の declare 署名に完全一致させる (wasm-ld signature mismatch 防止)。
 * mock 契約 (IR 解析で確定):
 *   - function_1801bf1c0(doc,start,len) → doc = {flag=1, root=&g_dom}, return 1 (parse OK)
 *   - function_180034560(doc,out,keyA,keyB) → out に SSO 文字列
 *       key=="component": DSP fn → "processor" (len9, out+16) / controller fn → "controller" (len10, LF1)
 *       key=="productVersion" → "" (len0)
 *   - function_180023360(root,key) → *(i64*)root (未発見) / g_found_demoVersion 時は +8 (発見)
 *   - function_180024330 → g_version_ok / function_18007b280 → g_marker
 *   - function_180024390 → double を __authstub_dbl_ret0 へ (LF2: xmm0 戻りの束縛先)
 */
#include <stdint.h>
#include <stddef.h>
#include <string.h>

typedef unsigned __int128 u128;
typedef int64_t i64;
typedef int32_t i32;

/* ---- LF 束縛先 (.ll 側は external 宣言、定義はここ 1 箇所) ---- */
int64_t __authstub_str_len0 = 0;   /* LF1: controller setState の tag 文字列 len */
int64_t __authstub_doc_root = 0;   /* LF5/LF6: 解析済み JSON DOM root */
u128 __authstub_dbl_ret0 = 0;      /* LF2: DSP setState の version double (xmm0 戻り) */

/* ---- PE 定数 (dg_ctrl.c / dg_dsp.c で定義) ---- */
extern const uint8_t global_var_180fbabb1[]; /* "component" */
extern const uint8_t global_var_180fc8ff8[]; /* "demoVersion" */
extern const uint8_t global_var_180fc8fe9[]; /* "productVersion" */

/* ---- lift 対象関数 ---- */
extern i64 function_1800c2b50(i64 obj, i64 stream);     /* patched controller setState */
extern i64 function_1800c2b50_pre(i64 obj, i64 stream); /* pre (rename 同梱) */
extern i64 function_18004fad0(i64 obj, i64 stream);     /* patched DSP setState */

/* ---- 観測変数 ---- */
static int g_parse_ret = 1;
static int g_version_ok = 1;
static int g_marker = 0;
static int g_found_demoVersion = 0;
static double g_version_val = 2.0;
static int g_dsp_fn = 0;
static int g_load_entered = 0;
static int g_dialog_entered = 0;
static int g_restore_entered = 0;
static int g_trap = 0;
static uint32_t g_deferred_flags = 0;
static uint64_t g_deferred_holder[2]; /* +0x90 先オブジェクト: machine は [ptr+8] に OR する */

#define OBJ_SIZE 0x400000
static unsigned char g_obj[OBJ_SIZE];
static unsigned char g_dom[64];

/* ---- __asm_* ヘルパ (liftlib kernels.py 流儀: x86 命令の C 意味論) ---- */
u128 __asm_movaps__5(u128 a) { return a; }           /* load 形 identity */
u128 __asm_movups(u128 a) { return a; }
u128 __asm_movupd(u128 a) { return a; }
u128 __asm_movapd__3(u128 a) { return a; }
uint64_t __asm_movaps(u128 a) { return (uint64_t)a; } /* store 形残存: 低 64bit */
uint64_t __asm_movapd(u128 a) { return (uint64_t)a; }
void __asm_movupd__2(u128 p0, u128 p1) { (void)p0; (void)p1; } /* S1a 残存形 (liftlib 同様 no-op) */
u128 __asm_xorps(u128 a, u128 b) { return a ^ b; }
u128 __asm_xorpd(u128 a, u128 b) { return a ^ b; }
void __asm_ucomisd(u128 a, u128 b) { (void)a; (void)b; }      /* flag は LF3/LF4 が fcmp で再構成 */
void __asm_ucomisd__1(u128 a, i64 b) { (void)a; (void)b; }
i64 __asm_pause(void) { return 0; }
i64 __asm_int3(void) { g_trap = 1; return 0; }

/* ---- callee mocks (declare 署名どおり) ---- */
i64 function_180411b00(void *pos) { memset(pos, 0, 16); return 0; }
i64 function_1801bf1c0(void *doc, i64 start, i64 len) {
    (void)start; (void)len;
    ((unsigned char *)doc)[0] = 1;      /* doc flag (alloca = 呼出 arg 先, IR も同一 alloca を読む) */
    __authstub_doc_root = (int64_t)g_dom; /* LF5/LF6 束縛: root は IR 側で global から読む */
    return g_parse_ret;
}
static void write_sso(void *out, const char *s) {
    uint64_t *q = (uint64_t *)out;
    size_t n = strlen(s);
    uint64_t lo = 0, hi = 0;
    if (n > 8) { memcpy(&lo, s, 8); memcpy(&hi, s + 8, n - 8); }
    else if (n) { memcpy(&lo, s, n); }
    q[0] = lo; q[1] = hi;
    __authstub_str_len0 = (int64_t)n; /* LF1/LF7 束縛 (両 fn とも len はこの global から読む) */
    q[2] = n; q[3] = 15;              /* out+16 = len, out+24 = cap (将来の alloca 整合用) */
}
i64 function_180034560(void *doc, void *out, const void *keyA, const void *keyB) {
    (void)doc; (void)keyB;
    if (keyA == (const void *)global_var_180fbabb1) {
        /* tag キーは両 fn 共通。期待値は各 fn の判定と対:
           DSP setState → "processor" (len 9) / controller setState → "controller" (len 10) */
        write_sso(out, g_dsp_fn ? "processor" : "controller");
        return 0;
    }
    write_sso(out, ""); /* productVersion 等は空文字 (len0) */
    return 0;
}
i64 function_180023360(i64 root, const void *key) {
    i64 end = *(i64 *)root;
    if (g_found_demoVersion && key == (const void *)global_var_180fc8ff8)
        return end + 8; /* 見つかった (≠ end) */
    return end;         /* 見つからず */
}
i64 function_180024330(void *doc, i32 mode) { (void)doc; (void)mode; return g_version_ok; }
i64 function_1800c3080(i64 obj, void *doc, i64 r8) { (void)obj; (void)doc; (void)r8; g_load_entered = 1; return 0; }
i64 function_18007b280(void *doc, const void *key, void *out) {
    (void)doc; (void)key;
    if (out) *(unsigned char *)out = (unsigned char)g_marker;
    return g_marker;
}
i64 function_18000a280(i64 p) { (void)p; return 0; }
i64 function_180273320(i64 a, const char *b) { return strcmp((const char *)a, b); }
i64 function_180450970(i64 p) { (void)p; return 0; }
i64 function_1800226b0(void *p, uint8_t b) { (void)p; (void)b; return 0; }
i64 function_1809a4bbc(i64 a, i64 b, i64 c) { (void)a; (void)b; (void)c; return 0; }
i64 function_1809e1604(i32 a, i32 b, i32 c, i32 d, i64 e) { (void)a; (void)b; (void)c; (void)d; (void)e; g_trap = 1; return 0; }
i64 function_18000e490(i64 p, const void *k) { (void)p; (void)k; return 0; }
i64 function_18049e5d0(i64 p) { (void)p; return 0; }
i64 function_180024390(void *doc, const void *key, void *out) {
    (void)doc; (void)key; (void)out;
    u128 v = 0;
    memcpy(&v, &g_version_val, 8);
    __authstub_dbl_ret0 = v; /* LF2 束縛 (IR はここから version double を読む) */
    return 0;
}
i64 function_1800244f0(void *doc, i64 b) { (void)doc; (void)b; return 0; }
i64 function_1800501c0(i64 p, void *a, void *b) { (void)p; (void)a; (void)b; g_dialog_entered = 1; return 0; }
i64 function_1800506b0(i64 p, void *doc) { (void)p; (void)doc; g_restore_entered = 1; return 0; }
i64 function_180052f70(i64 p) { (void)p; return 0; }
i64 function_1800929d0(i64 p) { (void)p; return 0; }

/* ---- ドライバ ---- */
static void reset_obj(void) {
    memset(g_obj, 0, OBJ_SIZE);
    memset(g_dom, 0, sizeof g_dom);
    *(i64 *)g_dom = 0x1234; /* end sentinel */
    g_load_entered = g_dialog_entered = g_restore_entered = g_trap = 0;
    g_dsp_fn = 0;
    g_deferred_flags = 0;
    g_dsp_fn = 0;
    __authstub_str_len0 = 0;
    __authstub_doc_root = 0;
    __authstub_dbl_ret0 = 0;
}

/* controller setState 1 実行。
   戻り packing: bit0..7 = 戻り値, bit8..15 = obj+0x22792 (demo bit),
                 bit16 = FUN_1800c3080 実行, bit17 = trap,
                 bit20..51 = +0x90 先 pending flags dword (deferred 通知キュー) */
uint64_t authstub_ctrl_case(int pre, int marker, int with_deferred, uint32_t *flags_out) {
    reset_obj();
    g_marker = marker;
    unsigned char *obj = g_obj;
    *(uint32_t *)(obj + 0xdc) = 1;     /* demo-bit ブロックの実行条件 (machine: cmp dword [obj+0xdc],1) */
    *(uint64_t *)(obj + 0x223b0) = 15; /* +0x22398 文字列の SSO cap */
    g_deferred_holder[0] = 0; g_deferred_holder[1] = 0;
    if (with_deferred) *(uint64_t *)(obj + 0x90) = (i64)g_deferred_holder; /* flags は [ptr+8] */
    i64 r = pre ? function_1800c2b50_pre((i64)obj, 0x1000)
                : function_1800c2b50((i64)obj, 0x1000);
    g_deferred_flags = (uint32_t)g_deferred_holder[1];
    if (flags_out) *flags_out = g_deferred_flags;
    return (uint64_t)(r & 0xff)
         | ((uint64_t)obj[0x22792] << 8)
         | ((uint64_t)(g_load_entered ? 1 : 0) << 16)
         | ((uint64_t)(g_trap ? 1 : 0) << 17)
         | ((uint64_t)g_deferred_flags << 20);
}

/* DSP setState 1 実行。
   戻り packing: bit0..7 = 戻り値, bit8 = demo ダイアログ実行, bit9 = DSP 復元 (1800506b0) 実行, bit10 = trap */
uint64_t authstub_dsp_case(int found_demoVersion, int version_x10) {
    reset_obj();
    g_found_demoVersion = found_demoVersion;
    g_version_val = version_x10 / 10.0;
    g_dsp_fn = 1;
    unsigned char *obj = g_obj;
    *(uint64_t *)(obj + 0x3f0) = 15; /* +0x3f0 文字列の SSO cap (範囲外 path の copy 先) */
    i64 r = function_18004fad0((i64)obj, 0x1000);
    return (uint64_t)(r & 0xff)
         | ((uint64_t)(g_dialog_entered ? 1 : 0) << 8)
         | ((uint64_t)(g_restore_entered ? 1 : 0) << 9)
         | ((uint64_t)(g_trap ? 1 : 0) << 10);
}
