/* glue_unit.c — glue の C 単体テスト (CAB-101)。
 * 「初期化順序規約」「THostInstance レイアウト」「CreateFruityInstance スタブ/ハンドシェイク」
 * 「vtbl slot 逐語仕様」「trace 順序突合」を検証する。
 * 実行: host/build.sh link ST work/unit_st.cjs unit test/glue_unit.c
 */
#include "glue.h"
#include "pathreg.h"
#include <stdio.h>
#include <string.h>

static int g_pass, g_fail;
static void ok(int cond, const char* msg) {
    printf(cond ? "  ok   %s\n" : "  FAIL %s\n", msg);
    if (cond) g_pass++; else g_fail++;
}

int main(void) {
    printf("[glue-unit] stages=%d canonical=%s\n", GLUE_STAGE_COUNT,
           "paths>registry>pump>vfs>pre_dllmain>dllmain>host>boot>post>shutdown");

    /* ---- 1. THostInstance レイアウト (stub_plan §2 と一致) ---- */
    ok(sizeof(GlueHostInstance) == GLUE_HOST_SIZE, "THostInstance size == 0x38");
    ok(offsetof(GlueHostInstance, version) == 0x08, "version offset +0x08");
    ok(offsetof(GlueHostInstance, flags) == 0x0c, "flags offset +0x0c");
    ok(offsetof(GlueHostInstance, hwnd_parent) == 0x10, "hwnd_parent offset +0x10");
    ok(offsetof(GlueHostInstance, title) == 0x18, "title offset +0x18");
    ok(offsetof(GlueHostInstance, cmdline) == 0x30, "cmdline offset +0x30");

    /* ---- 2. 正規順で全段階 ---- */
    glue_reset();
    int rc = glue_run_all("webstudio");
    ok(rc == GLUE_OK, "glue_run_all(webstudio) == 0");
    ok(glue_order_violations() == 0, "order violations == 0 (canonical order)");
    ok(glue_stage_next() == -1, "next stage == -1 (all done)");
    for (int i = GLUE_STAGE_FIRST; i <= GLUE_STAGE_LAST; i++) {
        char n[64]; glue_stage_name(i, n, sizeof n);
        int d = glue_stage_is_done(i);
        printf("       stage %-12s done=%d\n", n, d);
        if (!d) g_fail++; else g_pass++;
    }
    ok(glue_stage_is_done(GLUE_STAGE_BOOT) == 1, "boot stage done");
    ok(glue_create_fruity_instance_called() == 1, "CreateFruityInstance called exactly once");
    ok(glue_last_iface() != NULL, "stub iface written to *iface");

    /* ---- 3. 生成された THostInstance の内容 ---- */
    GlueHostInstance* h = glue_host_instance();
    ok(h->version == GLUE_HOST_VERSION, "host.version == 1");
    ok(h->flags == 0, "host.flags == 0");
    ok(h->hwnd_parent == 0, "host.hwnd_parent == 0");
    ok(h->title && strcmp(h->title, GLUE_HOST_TITLE) == 0, "host.title == \"FL Studio\"");
    ok(h->p20 == h->p28 && h->p20 != NULL, "p20 == p28 == &zero_page");
    ok(h->cmdline != NULL, "host.cmdline -> buf[0x8000]");
    ok(strlen(glue_cmdline()) == 0, "cmdline empty by default");

    /* ---- 4. vtbl slot 逐語仕様 (stub_plan §2) ---- */
    GlueHostVtbl* v = (GlueHostVtbl*)h->vtbl;
    ok(v->slot0 != NULL && v->slot1 != NULL && v->slot2 != NULL, "vtbl 3 slots non-NULL");
    ok((int)(intptr_t)v->slot2(h, 3, 0, 0) == 1, "slot2(3,0) -> 1  (a=3,b=0)");
    ok((int)(intptr_t)v->slot2(h, 3, 1, 0) == 1, "slot2(3,1) -> 1  (a=3,b=1)");
    ok((int)(intptr_t)v->slot2(h, 3, 2, 0) == 0, "slot2(3,2) -> 0  (a=3,b=2)");
    ok((int)(intptr_t)v->slot2(h, 4, 0, 0) == 0, "slot2(4,0) -> 0  (a=2)");
    v->slot1(h);                                  /* ret — 落ちなければ OK */
    ok(1, "slot1(this) -> ret (no crash)");
    ok((int)(intptr_t)v->slot0(h, 3, 0, 0) == 1, "slot0 forwards to slot2 (3,0)->1");

    /* ---- 5. ハンドシェイク定数 (0xC0 / 0xEDE95A) ---- */
    void* iface = NULL;
    ok(glue_call_engine_entry(GLUE_HSHAKE_A, GLUE_HSHAKE_B, h, &iface) == 0, "engine-entry with real handshake == 0");
    ok(glue_call_engine_entry(0xC1u, GLUE_HSHAKE_B, h, &iface) == GLUE_EBOOT, "engine-entry wrong magic -> GLUE_EBOOT");
    ok(glue_call_engine_entry(GLUE_HSHAKE_A, 0xEDE95Bu, h, &iface) == GLUE_EBOOT, "engine-entry wrong magic2 -> GLUE_EBOOT");

    /* ---- 6. 初期化順序規約の違反検出 (ネガティブコントロール) ---- */
    glue_reset();
    ok(glue_stage_is_done(GLUE_STAGE_PATHS) == 0, "after reset: paths not done");
    ok(glue_stage_vfs() == GLUE_EORDER, "stage vfs before pump -> GLUE_EORDER");
    ok(glue_order_violations() == 1, "violations == 1 (one out-of-order call)");
    ok(glue_stage_is_done(GLUE_STAGE_VFS) == 0, "violating stage does NOT become done");
    glue_reset();
    ok(glue_stage_pump(-1) == GLUE_EORDER && glue_stage_registry() == GLUE_EORDER,
       "pump/registry before paths -> GLUE_EORDER");
    ok(glue_order_violations() == 2, "violations == 2 (both rejected)");
    ok(glue_stage_paths("webstudio") == GLUE_OK, "paths after reset ok");
    ok(glue_stage_paths("webstudio") == GLUE_OK, "paths re-enter is idempotent");
    ok(glue_order_violations() == 2, "re-enter does not add violation");

    /* ---- 7. 段階の個別呼出 (独立 API) ---- */
    glue_reset();
    ok(glue_stage_paths("webstudio") == GLUE_OK && glue_stage_registry() == GLUE_OK &&
       glue_stage_pump(-1) == GLUE_OK && glue_stage_vfs() == GLUE_OK, "4 stages called individually");
    ok(glue_stage_next() == GLUE_STAGE_PRE_DLLMAIN, "next == pre_dllmain after 4 stages");
    ok(glue_pump_calib_req() == 1, "pump calibration requested to host");
    ok(glue_pump_mode_req() == -1, "pump mode default (-1)");
    glue_reset();

    /* ---- 8. username の反映と trace 突合 ---- */
    glue_reset();
    ok(glue_run_all("webstudio") == GLUE_OK, "run_all with username=webstudio");
    ok(strcmp(glue_username(), "webstudio") == 0, "username stored");
    ok(glue_trace_contains("/c/home") == 1, "trace: documents map to /c/home");
    ok(glue_trace_contains("/c/tmp") == 1, "trace: temp maps to /c/tmp");
    ok(glue_trace_contains("/fl/") == 1, "trace: install maps to /fl");
    ok(glue_trace_contains("C:\\Users\\user") == 0, "trace: no C:\\Users\\user residue");
    int n = glue_trace_count();
    printf("       trace lines=%d dropped=%d\n", n, glue_trace_dropped());
    ok(n > 0 && glue_trace_dropped() == 0, "trace lines recorded without drop");

    /* 順序の突合: stage= の enter 行が規約順に並んでいること */
    {
        const char* expect[] = {"paths","registry","pump","vfs","pre_dllmain","dllmain","host","boot","post","shutdown"};
        int idx = 0, i;
        for (i = 0; i < n; i++) {
            char line[GLUE_TRACE_LINE_CAP];
            if (glue_trace_line(i, line, sizeof line) < 0) break;
            char needle[32];
            snprintf(needle, sizeof needle, "stage=%s enter", expect[idx]);
            if (strstr(line, needle)) { idx++; if (idx > GLUE_STAGE_LAST) break; }
        }
        ok(idx == GLUE_STAGE_COUNT, "trace stage order matches canonical order");
    }


    /* ---- 10. username 上書き (pathreg 既定表の webstudio を指す) ---- */
    glue_reset();
    ok(glue_stage_paths("alpha") == GLUE_OK, "glue_stage_paths(alpha) ok");
    {
        char a[512], b[512];
        int ra = pathreg_map("C:\\Users\\alpha\\Documents\\Image-Line\\x.txt", a, sizeof a);
        int rb = pathreg_map("C:\\Users\\webstudio\\Documents\\Image-Line\\x.txt", b, sizeof b);
        printf("       alpha=%d %s / webstudio=%d %s\n", ra, a, rb, b);
        ok(ra == 0 && strncmp(a, "/c/home/", 8) == 0, "alpha profile -> /c/home");
        ok(rb == 0 && strncmp(b, "/c/Users/webstudio/", 17) == 0, "webstudio out of table -> /c/Users/webstudio");
    }
    ok(glue_stage_paths("webstudio") == GLUE_OK, "restore default username");
    {
        char c[512];
        int rcw = pathreg_map("C:\\Users\\webstudio\\Documents\\Image-Line\\x.txt", c, sizeof c);
        printf("       alpha-stage -> webstudio map: %d %s\n", rcw, c);
        ok(rcw == 0 && strncmp(c, "/c/home/", 8) == 0, "webstudio profile -> /c/home again");
    }

    /* ---- 9. マウント表の実体 ---- */
    ok(pathreg_mount_count() >= 6, "pathreg mount count >= 6 (既定表)");

    printf("[glue-unit] GLUE %s (pass=%d fail=%d)\n", g_fail ? "FAIL" : "ALL PASS", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
