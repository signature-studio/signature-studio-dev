/* glue.c — startup-glue 実装 (CAB-101 / ST-T1)。
 *
 * 結線規約 (初期化順) と THostInstance/CreateFruityInstance スタブを実装する。
 * 実 FL lift コード (m11 boot closure) 未到達のため、各段階は「呼べる API」として
 * 定義し、順序違反の検出のみを行う (副作用は依存 component の既存 API を呼ぶだけ)。
 *
 * 依存 (全て読取専用 component):
 *   pathreg  … マウント表・正規化・レジストリ hash/seed 口 (tools/shimx/pathreg)
 *   vreg     … 運用フック (vreg_generation / vreg_clear_root / vreg_export_root)
 *   pump     … RING ABI (pump_ring_addr / pump_set_wait_mode / pump_clock_*)
 */
#include "glue.h"
#include "pathreg.h"
#include "vreg.h"
#include "pump_internal.h"     /* g_pring (リング実体・読取) */
#include "pump_api.h"          /* pump_get_wait_mode 等の宣言 (読取) */

#include <stdarg.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

/* ---------------------------------------------------------------- trace */
static char  g_trace[GLUE_TRACE_MAX_LINES][GLUE_TRACE_LINE_CAP];
static int   g_trace_n;
static int   g_trace_dropped;

static void tracef_(const char* fmt, ...) {
    char line[GLUE_TRACE_LINE_CAP];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    if (g_trace_n >= GLUE_TRACE_MAX_LINES) { g_trace_dropped++; return; }
    snprintf(g_trace[g_trace_n], GLUE_TRACE_LINE_CAP, "%s", line);
    g_trace_n++;
    printf("[glue] %s\n", line);
}

/* ---------------------------------------------------------------- 段階状態 */
static unsigned g_done;                     /* bit i = stage i 完了 */
static int      g_next     = GLUE_STAGE_FIRST;
static int      g_violations;
static char     g_username[64] = "webstudio";
static char     g_cmdline[GLUE_CMDLINE_CAP];
static char     g_zero_page[64];            /* +0x20/+0x28 の指す先 (FL64.exe の 0x140069820 相当) */

/* host / iface (wasm メモリ内の静的オブジェクト = glue が ensure する) */
static GlueHostInstance g_host;
static GlueHostVtbl     g_host_vtbl;
static char             g_cmdline_buf[GLUE_CMDLINE_CAP];

/* CreateFruityInstance スタブの iface (Destroy スロットのみ) */
typedef struct GlueStubIface {
    void* vtbl[1];
} GlueStubIface;
static GlueStubIface g_stub_iface;

static int (*g_create_fruity)(void* host, void** iface) = glue_stub_create_fruity_instance;
static int  g_boot_calls;
static void* g_last_iface;

/* pump 段階の要求値 */
static int  g_pump_mode_req = -1;
static int  g_pump_calib_req;

/* ---------------------------------------------------------------- 順序規約 */
static const struct { int id; const char* name; } kStages[] = {
    { GLUE_STAGE_PATHS,      "paths"      },
    { GLUE_STAGE_REGISTRY,   "registry"   },
    { GLUE_STAGE_PUMP,       "pump"       },
    { GLUE_STAGE_VFS,        "vfs"        },
    { GLUE_STAGE_PRE_DLLMAIN,"pre_dllmain"},
    { GLUE_STAGE_DLLMAIN,    "dllmain"    },
    { GLUE_STAGE_HOST,       "host"       },
    { GLUE_STAGE_BOOT,       "boot"       },
    { GLUE_STAGE_POST,       "post"       },
    { GLUE_STAGE_SHUTDOWN,   "shutdown"   },
};

static int stage_index(int stage) {
    if (stage < GLUE_STAGE_FIRST || stage > GLUE_STAGE_LAST) return -1;
    return stage;
}

/* 段階開始: 順序が合っていれば 0。違反は trace に残し GLUE_EORDER */
static int enter(int stage) {
    int i = stage_index(stage);
    char a[48], b[48];
    if (i < 0) { tracef_("bad-stage id=%d", stage); g_violations++; return GLUE_EARG; }
    glue_stage_name(stage, a, sizeof a);
    if (g_done & (1u << stage)) {
        tracef_("stage=%s already-done (no-op re-enter)", a);
        return GLUE_OK;                       /* 冪等 (再入場は許す) */
    }
    if (stage != g_next) {
        glue_stage_name(g_next, b, sizeof b);
        tracef_("order-violation stage=%s expected=%s (violation #%d)", a, b, g_violations + 1);
        g_violations++;
        return GLUE_EORDER;
    }
    tracef_("stage=%s enter", a);
    return GLUE_OK;
}

static void leave(int stage) {
    char a[48];
    if (stage_index(stage) < 0) return;
    g_done |= 1u << stage;
    if (g_next == stage) g_next = stage + 1;
    glue_stage_name(stage, a, sizeof a);
    tracef_("stage=%s ok (next=%s)", a, g_next > GLUE_STAGE_LAST ? "done" : kStages[g_next].name);
}

/* THostInstance の逐語 slot 実装 (stub_plan §2) */
static void* vtbl_slot0(void* self, int32_t a, int32_t b, int32_t c) {
    GlueHostInstance* h = (GlueHostInstance*)self;
    tracef_("host.slot0 forward a=%d b=%d c=%d", (int)a, (int)b, (int)c);
    return h->vtbl ? ((GlueHostVtbl*)h->vtbl)->slot2(h, a, b, c) : (void*)0;
}
static void vtbl_slot1(void* self) { (void)self; tracef_("host.slot1 ret"); }
static void* vtbl_slot2(void* self, int32_t a, int32_t b, int32_t c) {
    (void)self; (void)c;
    a -= 2;
    int r = (a == 1 && (uint32_t)b <= 1u) ? 1 : 0;
    tracef_("host.slot2 feature a=%d b=%d -> %d", (int)a, (int)b, r);
    return (void*)(intptr_t)r;
}

/* ---------------------------------------------------------------- CreateFruityInstance スタブ */
static void stub_destroy(void* self, void* arg) { (void)self; (void)arg; tracef_("iface.slot0 destroy"); }

int glue_stub_create_fruity_instance(void* host, void** iface) {
    g_boot_calls++;
    g_stub_iface.vtbl[0] = (void*)stub_destroy;
    g_last_iface = &g_stub_iface;
    if (iface) *iface = &g_stub_iface;
    GlueHostInstance* h = (GlueHostInstance*)host;
    tracef_("stub-create-fruity ver=%u flags=0x%x title=%s iface=%p",
            h ? h->version : 0u, h ? h->flags : 0u, (h && h->title) ? h->title : "(null)", (void*)&g_stub_iface);
    if (!h || h->version != GLUE_HOST_VERSION) return GLUE_EBOOT;
    if (!iface) return GLUE_EARG;
    return 0;                      /* native は 0 or 2 が正常終了 */
}

void glue_set_create_fruity_instance(int (*fn)(void* host, void** iface)) { g_create_fruity = fn; }
int  (*glue_get_create_fruity_instance(void))(void*, void**) { return g_create_fruity; }
int  glue_create_fruity_instance_called(void) { return g_boot_calls; }
void* glue_last_iface(void) { return g_last_iface; }

int glue_call_engine_entry(uint32_t a, uint32_t b, void* host, void** iface) {
    tracef_("engine-entry a=0x%x b=0x%x host=%p iface=%p", (unsigned)a, (unsigned)b, host, (void*)iface);
    if (a != GLUE_HSHAKE_A || b != GLUE_HSHAKE_B) {
        tracef_("handshake-mismatch (expected 0x%x/0x%x)", GLUE_HSHAKE_A, GLUE_HSHAKE_B);
        return GLUE_EBOOT;
    }
    if (!g_create_fruity) return GLUE_EARG;
    return g_create_fruity(host, iface);
}

/* ---------------------------------------------------------------- 段階実装 */
int glue_stage_paths(const char* username) {
    int rc = enter(GLUE_STAGE_PATHS);
    if (rc) return rc;
    if (username && *username) {
        size_t n = strlen(username);
        if (n >= sizeof g_username) n = sizeof g_username - 1;
        memcpy(g_username, username, n); g_username[n] = 0;
    }
    PathRegPaths p;
    pathreg_paths_init(&p);
    static char g_profile[128];
    snprintf(g_profile, sizeof g_profile, "C:\\Users\\%s", g_username);
    /* 注意 (pathreg 既知の落し穴・REPORT 記載): pathreg_map() は初回だけ pr_ensure_defaults() を実行し、
     * そちらは「既定 (C:\Users\webstudio) の表を作り直す」。set_paths より後に既定ロードが
     * 初回実行されるとカスタム表が Web 既定で上書きされる。→ set_paths の「前」に 1 回
     * pathreg_mount_count() (pr_ensure_defaults の公開口) を呼んで既定ロードを先に済ませる。 */
    (void)pathreg_mount_count();
    p.userProfile = g_profile;                 /* 既定 C:\Users\webstudio。<username> で上書き */
    rc = pathreg_set_paths(&p);
    if (rc != 0) { tracef_("pathreg_set_paths failed rc=%d", rc); return GLUE_EARG; }
    pathreg_install();
    char out[512];
    char pHome[256], pTmp[256], pFl[256];
    snprintf(pHome, sizeof pHome, "C:\\Users\\%s\\Documents\\Image-Line\\FL Studio\\Settings\\Manifest.xml", g_username);
    snprintf(pTmp,  sizeof pTmp,  "C:\\Users\\%s\\AppData\\Local\\Temp\\Image-Line\\1-2\\x.tmp", g_username);
    snprintf(pFl,   sizeof pFl,   "C:\\Program Files\\Image-Line\\FL Studio 2026\\System\\x.dll");
    const char* probes[] = { pHome, pTmp, pFl, NULL };
    for (int i = 0; probes[i]; i++) {
        int m = pathreg_map(probes[i], out, sizeof out);
        tracef_("map %-72s -> %d %s", probes[i], m, m == 0 ? out : "(fallback)");
    }
    tracef_("mounts=%d username=%s", pathreg_mount_count(), g_username);
    leave(GLUE_STAGE_PATHS);
    return GLUE_OK;
}

int glue_stage_registry(void) {
    int rc = enter(GLUE_STAGE_REGISTRY);
    if (rc) return rc;
    /* seed import の契約はホスト側 (RegBridge / vreg seed.json)。C 側は flush 基準を作るだけ。
     * (import 済みとみなして mark_saved → 以降 pathreg_reg_changed() で差分検出) */
    uint64_t h = 0;
    int hr = pathreg_reg_hash(&h);
    pathreg_reg_mark_saved();
    tracef_("registry hash=0x%016llx (rc=%d) mark_saved gen=%d", (unsigned long long)h, hr, vreg_generation());
    leave(GLUE_STAGE_REGISTRY);
    return GLUE_OK;
}

int glue_stage_pump(int wait_mode) {
    int rc = enter(GLUE_STAGE_PUMP);
    if (rc) return rc;
    g_pump_mode_req = wait_mode;
    if (wait_mode >= 0) pump_set_wait_mode(wait_mode);
    /* リングは C 側 constructor が初期化する。magic/capacity を読んで起動確認する */
    uint32_t magic = (uint32_t)g_pring.hdr[PR_H_MAGIC];
    uint32_t cap   = (uint32_t)g_pring.hdr[PR_H_CAPACITY];
    int addr = pump_ring_addr();
    int mode = pump_get_wait_mode();
    tracef_("pump ring addr=%d magic=0x%x cap=%u wait_mode=%d", addr, (unsigned)magic, cap, mode);
    if (magic != PR_MAGIC) { tracef_("pump ring not initialized"); return GLUE_EARG; }
    g_pump_calib_req = 1;                        /* host が clock calibration を行う要求 */
    tracef_("pump calibrate-request=1 (host: node=直接差 / browser=page ping-pong)");
    leave(GLUE_STAGE_PUMP);
    return GLUE_OK;
}

int glue_stage_vfs(void) {
    int rc = enter(GLUE_STAGE_VFS);
    if (rc) return rc;
    /* wvfs mount の実体はホスト側 (Wvfs.open + FS.mount)。C 側は mount 表 (/fl・/c/home・/c/tmp) の
     * 整合と「書込対象パスが home/tmp に落ちる」ことを確認する。*/
    int home_ok = 0, tmp_ok = 0, fl_ok = 0;
    char out[512];
    char kHome[256], kTmp[256];
    snprintf(kHome, sizeof kHome, "C:\\Users\\%s\\Documents\\Image-Line\\FL Studio\\Settings\\Manifest.xml", g_username);
    snprintf(kTmp,  sizeof kTmp,  "C:\\Users\\%s\\AppData\\Local\\Temp\\Image-Line\\1-2\\tmp.bin", g_username);
    static const char* kFl = "C:\\Program Files\\Image-Line\\FL Studio 2026\\System\\FLEngine_x64.dll";
    if (pathreg_map(kHome, out, sizeof out) == 0) home_ok = (strncmp(out, "/c/home/", 8) == 0);
    if (pathreg_map(kTmp,  out, sizeof out) == 0) tmp_ok  = (strncmp(out, "/c/tmp/",  7) == 0);
    if (pathreg_map(kFl,   out, sizeof out) == 0) fl_ok   = (strncmp(out, "/fl/",     4) == 0);
    tracef_("vfs targets home=%d(/c/home) tmp=%d(/c/tmp) fl=%d(/fl)", home_ok, tmp_ok, fl_ok);
    if (!home_ok || !tmp_ok || !fl_ok) { tracef_("vfs mount targets mismatch"); return GLUE_EARG; }
    tracef_("vfs expects host: Wvfs.open(home) + Wvfs.open(tmp) + FS.mount(/c/home,/c/tmp) / /fl RO");
    leave(GLUE_STAGE_VFS);
    return GLUE_OK;
}

int glue_stage_pre_dllmain(const char* cmdline) {
    int rc = enter(GLUE_STAGE_PRE_DLLMAIN);
    if (rc) return rc;
    if (cmdline) {
        size_t n = strlen(cmdline);
        if (n >= sizeof g_cmdline) n = sizeof g_cmdline - 1;
        memcpy(g_cmdline, cmdline, n); g_cmdline[n] = 0;
    }
    g_cmdline_buf[0] = 0;
    size_t n = strlen(g_cmdline);
    if (n) memcpy(g_cmdline_buf, g_cmdline, n);
    g_cmdline_buf[n] = 0;
    tracef_("pre-dllmain cmdline=%zuB <%s>", strlen(g_cmdline_buf), g_cmdline_buf);
    leave(GLUE_STAGE_PRE_DLLMAIN);
    return GLUE_OK;
}

int glue_stage_dllmain(void) {
    int rc = enter(GLUE_STAGE_DLLMAIN);
    if (rc) return rc;
    /* 実体は m11 の DllMain closure。ここでは規約上の位置 (S09) を記録するだけ */
    tracef_("dllmain hook (m11 closure: Delphi unit initialization) — 未結線");
    leave(GLUE_STAGE_DLLMAIN);
    return GLUE_OK;
}

int glue_stage_host(void) {
    int rc = enter(GLUE_STAGE_HOST);
    if (rc) return rc;
    memset(&g_host, 0, sizeof g_host);
    g_host_vtbl.slot0 = vtbl_slot0;
    g_host_vtbl.slot1 = vtbl_slot1;
    g_host_vtbl.slot2 = vtbl_slot2;
    g_host.vtbl        = &g_host_vtbl;
    g_host.version     = GLUE_HOST_VERSION;
    g_host.flags       = 0;
    g_host.hwnd_parent = 0;
    g_host.title       = GLUE_HOST_TITLE;
    g_host.p20         = g_zero_page;
    g_host.p28         = g_zero_page;
    g_host.cmdline     = g_cmdline_buf;
    tracef_("THostInstance size=%u vtbl=%p ver=%u flags=0x%x title=%s cmdline=%p",
            (unsigned)sizeof(GlueHostInstance), (void*)&g_host_vtbl, g_host.version,
            g_host.flags, g_host.title, (void*)g_host.cmdline);
    leave(GLUE_STAGE_HOST);
    return GLUE_OK;
}

int glue_stage_boot(void) {
    int rc = enter(GLUE_STAGE_BOOT);
    if (rc) return rc;
    void* iface = 0;
    int r = glue_call_engine_entry(GLUE_HSHAKE_A, GLUE_HSHAKE_B, &g_host, &iface);
    tracef_("CreateFruityInstance -> %d iface=%p", r, iface);
    leave(GLUE_STAGE_BOOT);
    return r == 0 ? GLUE_OK : r;
}

int glue_stage_post(void) {
    int rc = enter(GLUE_STAGE_POST);
    if (rc) return rc;
    void* iface = glue_last_iface();
    tracef_("post iface=%p (rc∈{0,2} なら iface->vtbl[0]() Destroy を呼ぶ規約)", iface);
    if (iface) {
        GlueStubIface* i = (GlueStubIface*)iface;
        if (i->vtbl[0]) ((void (*)(void*, void*))i->vtbl[0])(iface, 0);
    }
    leave(GLUE_STAGE_POST);
    return GLUE_OK;
}

int glue_stage_shutdown(void) {
    int rc = enter(GLUE_STAGE_SHUTDOWN);
    if (rc) return rc;
    /* 終了処理の規約: (1) レジストリ差分の保存基準を確定 (2) host が wvfs flush/syncfs を
     * 呼ぶ (3) trace dump。C 側は (1)(3) を行い、(2) はホスト側 API に対して要求を残す。 */
    uint64_t h = 0;
    pathreg_reg_hash(&h);
    int changed = pathreg_reg_changed();
    pathreg_reg_mark_saved();
    tracef_("shutdown reg hash=0x%016llx changed=%d mark_saved", (unsigned long long)h, changed);
    tracef_("shutdown host-side required: regbridge.onPageHide() + wvfs flush/syncfs + trace dump");
    leave(GLUE_STAGE_SHUTDOWN);
    return GLUE_OK;
}

/* ---------------------------------------------------------------- 検査 API */
GlueHostInstance* glue_host_instance(void) { return &g_host; }
int               glue_host_addr(void)       { return (int)(uintptr_t)&g_host; }
const char*       glue_username(void)        { return g_username; }
const char*       glue_cmdline(void)         { return g_cmdline_buf; }
int               glue_pump_mode_req(void)   { return g_pump_mode_req; }
int               glue_pump_calib_req(void)  { return g_pump_calib_req; }

int glue_stage_is_done(int stage) {
    int i = stage_index(stage);
    return i < 0 ? 0 : (int)((g_done >> stage) & 1u);
}
int glue_stage_next(void) { return g_next > GLUE_STAGE_LAST ? -1 : g_next; }
int glue_order_violations(void) { return g_violations; }
int glue_stage_name(int stage, char* out, int cap) {
    int i = stage_index(stage);
    if (i < 0 || !out || cap <= 0) return -1;
    int n = (int)strlen(kStages[i].name);
    if (n >= cap) n = cap - 1;
    memcpy(out, kStages[i].name, n); out[n] = 0;
    return n;
}

int glue_run_all(const char* username) {
    int rc;
    if ((rc = glue_stage_paths(username)))      return rc;
    if ((rc = glue_stage_registry()))           return rc;
    if ((rc = glue_stage_pump(-1)))             return rc;
    if ((rc = glue_stage_vfs()))                return rc;
    if ((rc = glue_stage_pre_dllmain("")))      return rc;
    if ((rc = glue_stage_dllmain()))            return rc;
    if ((rc = glue_stage_host()))               return rc;
    if ((rc = glue_stage_boot()))               return rc;
    if ((rc = glue_stage_post()))               return rc;
    if ((rc = glue_stage_shutdown()))           return rc;
    return GLUE_OK;
}

void glue_reset(void) {
    g_done = 0;
    g_next = GLUE_STAGE_FIRST;
    g_violations = 0;
    g_boot_calls = 0;
    g_last_iface = 0;
    g_pump_mode_req = -1;
    g_pump_calib_req = 0;
    memset(g_cmdline, 0, sizeof g_cmdline);
    memset(g_cmdline_buf, 0, sizeof g_cmdline_buf);
    snprintf(g_username, sizeof g_username, "webstudio");
    glue_trace_clear();
}

/* ---------------------------------------------------------------- trace API */
int  glue_trace_count(void) { return g_trace_n; }
int  glue_trace_line(int i, char* out, int cap) {
    if (i < 0 || i >= g_trace_n || !out || cap <= 0) return -1;
    int n = (int)strlen(g_trace[i]);
    if (n >= cap) n = cap - 1;
    memcpy(out, g_trace[i], n); out[n] = 0;
    return n;
}
int glue_trace_contains(const char* needle) {
    if (!needle || !*needle) return 0;
    size_t nl = strlen(needle);
    for (int i = 0; i < g_trace_n; i++) {
        const char* line = g_trace[i];
        size_t ll = strlen(line);
        for (size_t j = 0; j + nl <= ll; j++)
            if (memcmp(line + j, needle, nl) == 0) return 1;
    }
    return 0;
}
void glue_trace_clear(void) { g_trace_n = 0; g_trace_dropped = 0; }
void glue_trace_dump(void) {
    for (int i = 0; i < g_trace_n; i++) printf("%s\n", g_trace[i]);
    if (g_trace_dropped) printf("... (%d trace lines dropped)\n", g_trace_dropped);
}
int glue_trace_dropped(void) { return g_trace_dropped; }

/* 起動時の既定状態 (constructor): host は未構築・trace 空 */
__attribute__((constructor)) static void glue_init_(void) {
    snprintf(g_username, sizeof g_username, "webstudio");
    tracef_("glue module ready (stages=%d, canonical order=%s)",
            GLUE_STAGE_COUNT,
            "paths>registry>pump>vfs>pre_dllmain>dllmain>host>boot>post>shutdown");
}
