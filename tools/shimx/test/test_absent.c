/* shimx 単体テスト (#658 ST-T19): 不在パスの属性 / 検索のエラーコードを VFS 写像 (pathreg) 経由で検査する。
 *   ユーザ側       C:\Users\webstudio\...                          → /c/home/...
 *   インストール側 C:\Program Files\Image-Line\FL Studio 2026\...   → /fl/...
 * 期待値 (Win32 準拠): 親ディレクトリが無い → ERROR_PATH_NOT_FOUND (3) / 親はあるがエントリが無い → ERROR_FILE_NOT_FOUND (2)。
 * 各不在パスの隣に実在エントリを置き、同じ経路で成功することを確認する (ネガティブコントロール)。
 */
#include "test_common.h"
#include "../../pathreg/include/pathreg.h"

#define INSTALL_DIR "C:\\Program Files\\Image-Line\\FL Studio 2026"

static void put_file_abs(const WCHAR* path, const char* data) {
    HANDLE h = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, 0);
    CHECK(h != INVALID_HANDLE_VALUE);
    DWORD w = 0; CHECK(WriteFile(h, data, (DWORD)strlen(data), &w, NULL) && w == strlen(data));
    CHECK(CloseHandle(h));
}

static void check_mapping(const char* win, const char* posix) {
    char px[512];
    CHECK(shimx_path_to_posix(win, px, sizeof px) == 0 && !strcmp(px, posix));
}

/* 不在パス: GetFileAttributesW / FindFirstFileW / FindFirstFileExW の三者が同じ wantErr を返すこと */
static void expect_absent(const char* win, DWORD wantErr) {
    SetLastError(0xFFFFFFFFu);
    DWORD a = GetFileAttributesW(W(win));
    DWORD e1 = GetLastError();
    WIN32_FIND_DATAW fd;
    SetLastError(0xFFFFFFFFu);
    HANDLE h1 = FindFirstFileW(W(win), &fd);
    DWORD e2 = GetLastError();
    SetLastError(0xFFFFFFFFu);
    HANDLE h2 = FindFirstFileExW(W(win), FindExInfoStandard, &fd, 0, NULL, 0);
    DWORD e3 = GetLastError();
    if (a != INVALID_FILE_ATTRIBUTES || e1 != wantErr || h1 != INVALID_HANDLE_VALUE || e2 != wantErr || h2 != INVALID_HANDLE_VALUE || e3 != wantErr)
        fprintf(stderr, "[absent-path] %s: GetFileAttributesW attr=%08x err=%u / FindFirstFileW h=%p err=%u / FindFirstFileExW h=%p err=%u (want err=%u)\n",
                win, a, e1, (void*)h1, e2, (void*)h2, e3, wantErr);
    CHECK(a == INVALID_FILE_ATTRIBUTES && e1 == wantErr);
    CHECK(h1 == INVALID_HANDLE_VALUE && e2 == wantErr);
    CHECK(h2 == INVALID_HANDLE_VALUE && e3 == wantErr);
}

/* 実在パス (ネガティブコントロール): 属性と検索結果 (cFileName) が成功すること */
static void expect_present(const char* win, DWORD wantAttr, const char* wantName) {
    SetLastError(0xFFFFFFFFu);
    DWORD a = GetFileAttributesW(W(win));
    if (a != wantAttr) fprintf(stderr, "[absent-path] %s: GetFileAttributesW attr=%08x err=%u (want %08x)\n", win, a, GetLastError(), wantAttr);
    CHECK(a == wantAttr);
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(W(win), &fd);
    if (h == INVALID_HANDLE_VALUE) fprintf(stderr, "[absent-path] %s: FindFirstFileW err=%u\n", win, GetLastError());
    CHECK(h != INVALID_HANDLE_VALUE && wstr_eq(fd.cFileName, wantName));
    CHECK(FindClose(h));
}

void run_absent_path_tests(void) {
    PathRegPaths p;
    pathreg_paths_init(&p);
    CHECK(pathreg_set_paths(&p) == 0);
    pathreg_install();                                                    /* shimx_set_path_mapper(pathreg_map) */
    check_mapping("C:\\Users\\webstudio\\Languages\\en.moe", "/c/home/Languages/en.moe");
    check_mapping("C:\\Program Files\\Image-Line\\FL Studio 2026\\Languages\\en.moe", "/fl/Languages/en.moe");

    CHECK(CreateDirectoryW(W("C:\\Users\\webstudio"), NULL));
    CHECK(CreateDirectoryW(W("C:\\Users\\webstudio\\Languages"), NULL));
    CHECK(CreateDirectoryW(W(INSTALL_DIR), NULL));
    CHECK(CreateDirectoryW(W(INSTALL_DIR "\\Languages"), NULL));
    put_file_abs(W("C:\\Users\\webstudio\\Languages\\present.moe"), "u");
    put_file_abs(W(INSTALL_DIR "\\Languages\\present.moe"), "i");

    /* ユーザ側 (/c/home): 親あり・不在 → 2, 親なし → 3 */
    expect_absent("C:\\Users\\webstudio\\Languages\\en.moe", ERROR_FILE_NOT_FOUND);
    expect_absent("C:\\Users\\webstudio\\Missing\\en.moe", ERROR_PATH_NOT_FOUND);
    expect_absent("C:\\Users\\webstudio\\Languages\\sub\\en.moe", ERROR_PATH_NOT_FOUND);
    /* インストール側 (/fl) */
    expect_absent(INSTALL_DIR "\\Languages\\en.moe", ERROR_FILE_NOT_FOUND);
    expect_absent(INSTALL_DIR "\\System\\Languages\\en.moe", ERROR_PATH_NOT_FOUND);

    /* ネガティブコントロール: 同じ側・同じ dir の実在エントリは成功すること */
    expect_present("C:\\Users\\webstudio\\Languages\\present.moe", FILE_ATTRIBUTE_ARCHIVE, "present.moe");
    expect_present("C:\\Users\\webstudio\\Languages", FILE_ATTRIBUTE_DIRECTORY, "Languages");
    expect_present(INSTALL_DIR "\\Languages\\present.moe", FILE_ATTRIBUTE_ARCHIVE, "present.moe");
    expect_present(INSTALL_DIR "\\Languages", FILE_ATTRIBUTE_DIRECTORY, "Languages");

    shimx_set_path_mapper(NULL);                                          /* 既定写像へ戻す (後続テストへ影響させない) */
}
