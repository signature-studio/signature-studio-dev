/* pathreg C 単体テスト: 正規化 / マウント表 / shimx_path_to_posix 結合 / ファイル I/O / レジストリ変更検出。
 * 実行: bash tools/shimx/pathreg/scripts/build.sh test → node build/test_pathreg.cjs
 * 成功基準: "PATHREG ALL PASS" 出力・exit 0
 */
#include "test_common.h"
#include "../src/pathreg_internal.h"   /* shx_ensure_init (shimx 遅延初期化) */

static char g_buf[2048];

/* ---------------------------------------------------------------
 * 1. 正規化
 * --------------------------------------------------------------- */
static void test_normalize(void) {
    struct { const char* in; const char* want; } cases[] = {
        { "C:\\foo\\bar",                          "C:\\foo\\bar" },
        { "c:\\foo\\bar",                          "C:\\foo\\bar" },                 /* ドライブ大文字化 */
        { "C:/foo/bar",                            "C:\\foo\\bar" },                 /* 区切り統一 */
        { "C:\\\\foo\\\\\\\\bar\\",                "C:\\foo\\bar" },                 /* 連続区切り + 末尾 */
        { "C:\\foo\\.\\baz\\..\\qux",              "C:\\foo\\qux" },                 /* '.' '..' 畳み込み */
        { "C:\\foo\\..\\bar",                      "C:\\bar" },
        { "C:\\",                                  "C:\\" },                          /* ルート保持 */
        { "C:",                                    "C:\\" },
        { "\\\\?\\C:\\x\\y",                       "C:\\x\\y" },                      /* \\?\ 剥がし */
        { "\\\\.\\C:\\x",                          "C:\\x" },
        { "\\\\?\\UNC\\srv\\share\\f.txt",         "\\\\srv\\share\\f.txt" },         /* UNC 復元 */
        { "\\\\srv\\share\\x",                     "\\\\srv\\share\\x" },             /* 素の UNC */
        { "\\\\?\\UNC\\srv\\share",                "\\\\srv\\share" },
        { "\\foo\\bar",                            "\\foo\\bar" },                    /* ルート付き (カレントドライブ) */
        { "foo\\bar",                              "foo\\bar" },                      /* 相対は触らない */
        { "C:\\foo\\..\\..\\bar",                  "C:\\bar" },                       /* 根を超える pop (ドライブ保護) */
        { "C:\\foo\\",                             "C:\\foo" },
        { "C:\\Foo\\BAR",                          "C:\\Foo\\BAR" },                  /* 大小は保持 (比較のみ無視) */
    };
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        CHECK(pathreg_normalize(cases[i].in, g_buf, sizeof g_buf) == 0);
        CHECK(strcmp(g_buf, cases[i].want) == 0);
    }
    /* 満杯バッファ */
    CHECK(pathreg_normalize("C:\\x", g_buf, 3) == -1);
    CHECK(pathreg_normalize("", g_buf, sizeof g_buf) == -1);
    CHECK(pathreg_normalize(NULL, g_buf, sizeof g_buf) == -1);
    printf("OK pathreg: normalize (%d cases)\n", (int)(sizeof cases / sizeof cases[0]));
}

/* ---------------------------------------------------------------
 * 2. マウント表 + 写像
 * --------------------------------------------------------------- */
static void test_mounts(void) {
    PathRegPaths p;
    pathreg_paths_init(&p);
    CHECK(pathreg_set_paths(&p) == 0);
    int n0 = pathreg_mount_count();
    CHECK(n0 >= 9);                                   /* install + 2 profiles × 5 + C: */

    /* 取得・監査 */
    PathRegMount m;
    CHECK(pathreg_get_mount(0, &m) == 0);
    CHECK(m.flags == PATHREG_RO);
    CHECK(pathreg_get_mount(-1, &m) == -1);
    CHECK(pathreg_get_mount(n0, &m) == -1);

    /* 追加・削除・クリア */
    CHECK(pathreg_add_mount("D:\\tools", "/d/tools", PATHREG_PERSIST) == 0);
    CHECK(pathreg_mount_count() == n0 + 1);
    CHECK(pathreg_remove_mount("d:\\TOOLS") == 0);    /* 大小無視 */
    CHECK(pathreg_mount_count() == n0);
    CHECK(pathreg_remove_mount("E:\\nope") == -1);
    CHECK(pathreg_add_mount("", "/x", 0) == -1);
    CHECK(pathreg_add_mount("X:", "", 0) == -1);

    printf("OK pathreg: mounts (count=%d)\n", n0);
}

static void test_map(void) {
    PathRegPaths p;
    pathreg_paths_init(&p);
    CHECK(pathreg_set_paths(&p) == 0);
    pathreg_clear_mounts();                            /* 明示的に作り直して最長一致を検査 */
    CHECK(pathreg_add_mount("C:\\Program Files\\Image-Line\\FL Studio 2026", "/fl", PATHREG_RO) == 0);
    CHECK(pathreg_add_mount("C:\\Users\\user\\Documents\\Image-Line", "/c/home/Documents/Image-Line", PATHREG_PERSIST) == 0);
    CHECK(pathreg_add_mount("C:\\Users\\user\\AppData\\Local\\Temp\\Image-Line", "/c/tmp", PATHREG_TMP) == 0);
    CHECK(pathreg_add_mount("C:\\Users\\user\\AppData\\Local", "/c/home/AppData/Local", PATHREG_PERSIST) == 0);
    CHECK(pathreg_add_mount("C:", "/c", PATHREG_PERSIST) == 0);

    struct { const char* in; const char* want; } cases[] = {
        /* E asset bundle (読取専用)。nfo REPORT §3 の Plugin database は Shared data 側 */
        { "C:\\Program Files\\Image-Line\\FL Studio 2026\\Data\\System\\Empty.flp", "/fl/Data/System/Empty.flp" },
        { "c:/PROGRAM FILES/image-line/fl studio 2026/Plugins/Fruity/Generators/Fruity Wrapper/Fruity Wrapper_x64.dll",
          "/fl/Plugins/Fruity/Generators/Fruity Wrapper/Fruity Wrapper_x64.dll" },
        /* Shared data (永続): vreg seed paths / nfo 配置規則 */
        { "C:\\Users\\user\\Documents\\Image-Line\\FL Studio\\Settings\\Manifest.xml",
          "/c/home/Documents/Image-Line/FL Studio/Settings/Manifest.xml" },
        { "C:\\Users\\user\\Documents\\Image-Line\\FL Studio\\Presets\\Plugin database\\Installed\\Effects\\VST\\Xfer Records, OTT.nfo",
          "/c/home/Documents/Image-Line/FL Studio/Presets/Plugin database/Installed/Effects/VST/Xfer Records, OTT.nfo" },
        /* Temp (TMP) は Local (PERSIST) より長い接頭辞で勝つ (stub_plan §4: Temp\Image-Line\<pid>-<id>\ → /c/tmp/…) */
        { "C:\\Users\\user\\AppData\\Local\\Temp\\Image-Line\\123-1\\pack.zip", "/c/tmp/123-1/pack.zip" },
        { "C:\\Users\\user\\AppData\\Local\\Image-Line\\cache.dat", "/c/home/AppData/Local/Image-Line/cache.dat" },
        /* 残余ドライブ C: → /c (shimx 既定と同じ形) */
        { "C:\\Windows\\notepad.exe", "/c/Windows/notepad.exe" },
        /* フォールバック (表に無いドライブ) → shimx 既定写像に委譲 */
        { "D:\\foo\\bar", NULL },
    };
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        int r = pathreg_map(cases[i].in, g_buf, sizeof g_buf);
        if (cases[i].want) {
            if (r != 0 || strcmp(g_buf, cases[i].want) != 0)
                fprintf(stderr, "[pathreg-test] map mismatch: in=[%s] rc=%d got=[%s] want=[%s]\n", cases[i].in, r, r == 0 ? g_buf : "-", cases[i].want);
            CHECK(r == 0);
            CHECK(strcmp(g_buf, cases[i].want) == 0);
        } else {
            CHECK(r < 0);                              /* 非対応 → shimx 既定へ */
        }
    }
    /* shimx 結合: mapper 設置後、shimx_path_to_posix (UTF-8 入力) が写像結果を返す。非対応は既定写像にフォールバック */
    pathreg_install();
    CHECK(shimx_path_to_posix("C:\\Program Files\\Image-Line\\FL Studio 2026\\Data\\System\\Empty.flp", g_buf, sizeof g_buf) == 0);
    CHECK(strcmp(g_buf, "/fl/Data/System/Empty.flp") == 0);
    CHECK(shimx_path_to_posix("C:\\Windows\\notepad.exe", g_buf, sizeof g_buf) == 0);
    CHECK(strcmp(g_buf, "/c/Windows/notepad.exe") == 0);            /* フォールバック */
    CHECK(shimx_path_to_posix("/posix/abs/path", g_buf, sizeof g_buf) == 0);
    CHECK(strcmp(g_buf, "/posix/abs/path") == 0);                   /* M4 互換: POSIX 素通し */
    CHECK(shimx_path_to_posix("rel\\ative.txt", g_buf, sizeof g_buf) == 0);
    CHECK(strncmp(g_buf, "/c/", 3) == 0);                            /* Win cwd (既定 C:\) 基準 */

    /* 逆写像 */
    CHECK(pathreg_unmap("/fl/Data/System/Empty.flp", g_buf, sizeof g_buf) == 0);
    CHECK(strcmp(g_buf, "C:\\Program Files\\Image-Line\\FL Studio 2026\\Data\\System\\Empty.flp") == 0);
    CHECK(pathreg_unmap("/elsewhere/x", g_buf, sizeof g_buf) == -1);
    printf("OK pathreg: map + shimx_path_to_posix (%d cases)\n", (int)(sizeof cases / sizeof cases[0]));
}

/* ---------------------------------------------------------------
 * 3. ファイル I/O 結合 (mapper 経由の CreateFileW)
 * --------------------------------------------------------------- */
static void test_file_io(void) {
    PathRegPaths p;
    pathreg_paths_init(&p);
    CHECK(pathreg_set_paths(&p) == 0);
    pathreg_install();
    shx_ensure_init();

    /* 読取: asset bundle 側 (/fl) に実ファイルを作り、Win パスで CreateFileW から読む */
    const char* asset = "/fl/Data/System/Empty.flp";
    mkdir_p("/fl/Data/System");
    int fd = open(asset, O_CREAT | O_WRONLY | O_TRUNC, 0444);        /* 0444 = E の読取専用相当 */
    CHECK(fd >= 0);
    const char payload[] = "FLhd____empty-flp-payload";
    CHECK(write(fd, payload, sizeof payload) == (ssize_t)sizeof payload);
    close(fd);

    HANDLE h = CreateFileW(W("C:\\Program Files\\Image-Line\\FL Studio 2026\\Data\\System\\Empty.flp"),
                           GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    CHECK(h != INVALID_HANDLE_VALUE);
    char got[64] = {0};
    DWORD rd = 0;
    CHECK(ReadFile(h, got, sizeof got, &rd, NULL) && rd == sizeof payload);
    CHECK(memcmp(got, payload, sizeof payload) == 0);
    CloseHandle(h);
    /* 読取専用領域への書込は失敗 (E の EPERM 相当) */
    HANDLE hw = CreateFileW(W("C:\\Program Files\\Image-Line\\FL Studio 2026\\Data\\System\\Empty.flp"),
                            GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
    CHECK(hw == INVALID_HANDLE_VALUE);
    CHECK(GetLastError() == ERROR_ACCESS_DENIED);

    /* 書込: 永続領域 (/c/home/Documents/Image-Line)。shimx が親 dir も作る経路 = 先に posix mkdir */
    const char* setdir = "/c/home/Documents/Image-Line/FL Studio/Settings";
    mkdir_p(setdir);
    HANDLE h2 = CreateFileW(W("C:\\Users\\user\\Documents\\Image-Line\\FL Studio\\Settings\\Manifest.xml"),
                            GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
    CHECK(h2 != INVALID_HANDLE_VALUE);
    const char xml[] = "<manifest>webstudio</manifest>";
    DWORD wr = 0;
    CHECK(WriteFile(h2, xml, (DWORD)sizeof xml, &wr, NULL) && wr == sizeof xml);
    CloseHandle(h2);
    int fd2 = open("/c/home/Documents/Image-Line/FL Studio/Settings/Manifest.xml", O_RDONLY);
    CHECK(fd2 >= 0);
    char got2[64] = {0};
    ssize_t r2 = read(fd2, got2, sizeof got2);
    close(fd2);
    CHECK(r2 == (ssize_t)sizeof xml);
    CHECK(memcmp(got2, xml, sizeof xml) == 0);
    printf("OK pathreg: file I/O via mapper (read RO + write persist)\n");
}

/* ---------------------------------------------------------------
 * 4. レジストリ変更検出 + seed 投入
 * --------------------------------------------------------------- */
static void test_regpersist(void) {
    shx_ensure_init();
    uint64_t h1 = 0;
    CHECK(pathreg_reg_hash(&h1) == 0);

    CHECK(pathreg_reg_seed_text(
        "[HKEY_CURRENT_USER\\Software\\Image-Line\\pathreg-test]\n"
        "\"Value\"=\"v1\"\n\"Count\"=dword:0000002a\n") == 2);

    uint64_t h2 = 0;
    CHECK(pathreg_reg_hash(&h2) == 0);
    CHECK(h1 != h2);                                   /* seed で変化 */
    CHECK(pathreg_reg_changed() == 1);                 /* 基準未設定 → 変化あり */
    pathreg_reg_mark_saved();
    CHECK(pathreg_reg_changed() == 0);                 /* 保存直後は無変更 */
    CHECK(pathreg_reg_saved_hash() == h2);

    CHECK(shimx_reg_set_sz("HKCU\\Software\\Image-Line\\pathreg-test", "Value", "v2") == 0);
    CHECK(pathreg_reg_changed() == 1);
    pathreg_reg_mark_saved();
    CHECK(pathreg_reg_changed() == 0);
    uint64_t h3 = 0;
    CHECK(pathreg_reg_hash(&h3) == 0);
    CHECK(h3 != h2);
    printf("OK pathreg: registry hash/changed/mark_saved\n");
}

int main(void) {
    test_normalize();
    test_mounts();
    test_map();
    test_file_io();
    test_regpersist();
    printf("PATHREG ALL PASS (build=%s)\n",
#if defined(__EMSCRIPTEN_PTHREADS__)
        "mt(pthreads)"
#else
        "st"
#endif
    );
    return 0;
}
