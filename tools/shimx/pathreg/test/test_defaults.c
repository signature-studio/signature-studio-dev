/* test_defaults.c — 既定マウント表の遅延ロード経路だけを検証する C 単体テスト (CAB-271)。
 * test_pathreg.c と別プロセスにした理由: pathreg_set_paths() は「明示設定」として
 * 以降の既定ロードを禁止するため、同一プロセス内では既定経路を开头 (pristine) で
 * 検証できない。本 binary は pathreg_set_paths() を **一度も呼ばない**。
 * 実行: bash scripts/build.sh test → node build/test_defaults_{st,mt}.cjs
 * 成功基準: "PATHREG DEFAULTS ALL PASS" 出力・exit 0
 */
#include "test_common.h"

static char g_buf[2048];

int main(void) {
    /* set_paths 未使用 = 既定経路。初回の照合で既定マウント表が遅延ロードされる */
    CHECK(pathreg_mount_count() == 8);                       /* install + webstudio×6 + C: */
    /* 既定表の内容 (stub_plan §4 / vreg seed paths 整合) */
    struct { const char* in; const char* want; } cases[] = {
        { "C:\\Program Files\\Image-Line\\FL Studio 2026\\Data\\System\\Empty.flp", "/fl/Data/System/Empty.flp" },
        { "C:\\Users\\webstudio\\Documents\\Image-Line\\FL Studio\\Settings\\Manifest.xml",
          "/c/home/Documents/Image-Line/FL Studio/Settings/Manifest.xml" },
        { "C:\\Users\\webstudio\\AppData\\Roaming\\Image-Line\\Shared\\config.xml",
          "/c/home/AppData/Roaming/Image-Line/Shared/config.xml" },
        { "C:\\Users\\webstudio\\AppData\\Local\\Temp\\Image-Line\\9-2\\zip\\inner.bin", "/c/tmp/9-2/zip/inner.bin" },
        { "C:\\Users\\webstudio\\Desktop\\x.txt",             "/c/home/Desktop/x.txt" },
        { "C:\\Windows\\notepad.exe",                         "/c/Windows/notepad.exe" },
        { "\\\\srv\\share\\folder\\file.dat",                 NULL },   /* UNC は既定表に無い → shimx 既定へ */
        { "D:\\unmapped\\path.txt",                           NULL },
        { "/posix/abs/path",                                  NULL },
    };
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        int r = pathreg_map(cases[i].in, g_buf, sizeof g_buf);
        if (cases[i].want) {
            if (r != 0 || strcmp(g_buf, cases[i].want) != 0)
                fprintf(stderr, "[pathreg-test] map mismatch: in=[%s] rc=%d got=[%s] want=[%s]\n",
                        cases[i].in, r, r == 0 ? g_buf : "-", cases[i].want);
            CHECK(r == 0);
            CHECK(strcmp(g_buf, cases[i].want) == 0);
        } else {
            CHECK(r < 0);
        }
    }
    /* 既定表の flags・順序 (install が先頭・C: が末尾) */
    PathRegMount m;
    CHECK(pathreg_get_mount(0, &m) == 0);
    CHECK(m.flags == PATHREG_RO);
    CHECK(strcmp(m.winPrefix, "C:\\Program Files\\Image-Line\\FL Studio 2026") == 0);
    CHECK(strcmp(m.vfsTarget, "/fl") == 0);
    CHECK(pathreg_get_mount(7, &m) == 0);
    CHECK(strcmp(m.winPrefix, "C:\\") == 0);
    CHECK(pathreg_get_mount(8, &m) == -1);
    /* 逆写像も既定表 (webstudio) を返す */
    CHECK(pathreg_unmap("/fl/Data/System/Empty.flp", g_buf, sizeof g_buf) == 0);
    CHECK(strcmp(g_buf, "C:\\Program Files\\Image-Line\\FL Studio 2026\\Data\\System\\Empty.flp") == 0);
    CHECK(pathreg_unmap("/c/home/Desktop/x.txt", g_buf, sizeof g_buf) == 0);
    CHECK(strcmp(g_buf, "C:\\Users\\webstudio\\Desktop\\x.txt") == 0);
    CHECK(pathreg_unmap("/elsewhere/x", g_buf, sizeof g_buf) == -1);
    /* add/remove は既定表の「後」に追加される (既定表が壊れていない) */
    CHECK(pathreg_add_mount("D:\\tools", "/d/tools", PATHREG_PERSIST) == 0);
    CHECK(pathreg_mount_count() == 9);
    CHECK(pathreg_map("D:\\tools\\a.dll", g_buf, sizeof g_buf) == 0);
    CHECK(strcmp(g_buf, "/d/tools/a.dll") == 0);
    CHECK(pathreg_remove_mount("D:\\TOOLS") == 0);
    CHECK(pathreg_mount_count() == 8);

    printf("PATHREG DEFAULTS ALL PASS (build=%s)\n",
#if defined(__EMSCRIPTEN_PTHREADS__)
           "mt(pthreads)"
#else
           "st"
#endif
    );
    return 0;
}
