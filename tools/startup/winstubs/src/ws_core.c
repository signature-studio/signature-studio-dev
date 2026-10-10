/* winstubs 中核: 設定 / 統計 / 初期化 / cpuid 返値表。 */
#include "ws_internal.h"
#include <strings.h>

WsStats g_ws;
WsConfig g_ws_cfg;
static int g_inited;
static HMODULE g_engine;

void winstubs_defaults(WsConfig* c) {
    memset(c, 0, sizeof *c);
    c->trust = 1;
    c->cpu_profile = WS_CPU_SSE2;
    c->user = "webstudio";
    c->screen_w = 1920; c->screen_h = 1080;
}
const WsStats* winstubs_stats(void) { return &g_ws; }
void winstubs_stats_reset(void) { memset(&g_ws, 0, sizeof g_ws); }
HMODULE winstubs_engine_module(void) { return g_engine; }

static void setenv_user(const char* name, const char* fmt, const char* user) {
    char v[512]; snprintf(v, sizeof v, fmt, user);
    shimx_setenv_utf8(name, v);
}

void winstubs_init(const WsConfig* in) {
    WsConfig c;
    winstubs_defaults(&c);
    if (in) {
        c = *in;
        if (!c.user || !*c.user) c.user = "webstudio";
        if (c.screen_w <= 0) c.screen_w = 1920;
        if (c.screen_h <= 0) c.screen_h = 1080;
    }
    static char user[64];
    snprintf(user, sizeof user, "%s", c.user);
    c.user = user;
    g_ws_cfg = c;

    shimx_init();
    shimx_set_trust_ok(c.trust ? 1 : 0);                       /* G03 */
    shimx_set_version(10, 0, 19045, 0, 0);                     /* G16: Windows 10 22H2 (vreg seed CurrentBuild=19045 と一致) */
    shimx_set_shell_execute_hook(ws_shell_hook);               /* B: ShellExecute 分類 */

    /* vreg_seed.json の _env / _known_folders に合わせる (shimx 既定は "user") */
    setenv_user("USERNAME", "%s", user);
    setenv_user("USERPROFILE", "C:\\Users\\%s", user);
    setenv_user("HOMEPATH", "\\Users\\%s", user);
    setenv_user("APPDATA", "C:\\Users\\%s\\AppData\\Roaming", user);
    setenv_user("LOCALAPPDATA", "C:\\Users\\%s\\AppData\\Local", user);
    setenv_user("TEMP", "C:\\Users\\%s\\AppData\\Local\\Temp", user);
    setenv_user("TMP", "C:\\Users\\%s\\AppData\\Local\\Temp", user);
    shimx_setenv_utf8("LANG", "en");

    if (!g_engine)
        g_engine = shimx_module_register("FLEngine_x64.dll", 0, "C:\\Program Files\\Image-Line\\FL Studio 2026\\FLEngine_x64.dll");
    if (!g_inited) { ws_register_procs(); g_inited = 1; }
}

/* ---------------------------------------------------------------
 * cpuid (G05): leaf1.EDX に CMOV(15)/TSC(4)/MMX(23)/FXSR(24)/SSE(25)/SSE2(26)。leaf7 は AVX2(EBX bit5) を立てない。
 * --------------------------------------------------------------- */
void winstubs_cpuid(uint32_t leaf, uint32_t sub, uint32_t o[4]) {
    uint32_t a = 0, b = 0, c = 0, d = 0;
    (void)sub;
    WS_INC(cpuid);
    switch (leaf) {
        case 0:
            a = (g_ws_cfg.cpu_profile == WS_CPU_PLAN) ? 0x16 : 0x0d;
            b = 0x756e6547; d = 0x49656e69; c = 0x6c65746e;         /* "GenuineIntel" */
            break;
        case 1:
            a = 0x000906ea;                                          /* family 6 model 158 stepping 10 (shimx PROCESSOR_IDENTIFIER と一致) */
            b = 0x00000800;                                          /* CLFLUSH line 64B, 論理 CPU ID 0 */
            c = (g_ws_cfg.cpu_profile == WS_CPU_PLAN) ? 0x00980201u : 0u;   /* SSE3(0) SSSE3(9) SSE4.1(19) SSE4.2(20) POPCNT(23) */
            d = 0x078bfbff;                                          /* FPU TSC CX8 CMOV MMX FXSR SSE SSE2 ほか (HTT/AVX 系なし) */
            break;
        case 7:  break;                                              /* 拡張機能なし: AVX2/BMI/AVX512 すべて 0 */
        case 0x80000000u: a = 0x80000008; break;
        case 0x80000001u: c = 1; d = 0x20100800; break;              /* LAHF / SYSCALL, NX, LM */
        case 0x80000002u: case 0x80000003u: case 0x80000004u: {
            static const char brand[48] __attribute__((aligned(4))) = "WebStudio wasm32 SIMD128 virtual CPU";
            const uint32_t* w = (const uint32_t*)brand + (leaf - 0x80000002u) * 4;
            a = w[0]; b = w[1]; c = w[2]; d = w[3];
            break;
        }
        default: break;
    }
    o[0] = a; o[1] = b; o[2] = c; o[3] = d;
}
