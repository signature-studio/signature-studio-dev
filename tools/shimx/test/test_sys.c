/* shimx 単体テスト (sys): 文字列 / ロケール / レジストリ / ファイル / 時刻 / heap / モジュール / 環境 / SEH / システム情報。 */
#include "test_common.h"

/* ---------------------------------------------------------------
 * 文字列 / ロケール
 * --------------------------------------------------------------- */
static void test_strings(void) {
    WCHAR w[64]; char a[64];
    const char* s = "A\xE3\x81\x82\xE3\x81\x84";       /* "Aあい" */
    int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, NULL, 0);
    CHECK(n == 4);
    CHECK(MultiByteToWideChar(CP_UTF8, 0, s, -1, w, 64) == 4 && w[0] == 'A' && w[1] == 0x3042 && w[2] == 0x3044 && w[3] == 0);
    CHECK(WideCharToMultiByte(CP_UTF8, 0, w, -1, NULL, 0, NULL, NULL) == 8);
    CHECK(WideCharToMultiByte(CP_UTF8, 0, w, -1, a, 64, NULL, NULL) == 8 && !strcmp(a, s));
    CHECK(WideCharToMultiByte(CP_UTF8, 0, w, -1, a, 3, NULL, NULL) == 0 && GetLastError() == ERROR_INSUFFICIENT_BUFFER);
    CHECK(MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, "\xFF\xFE", -1, w, 64) == 0 && GetLastError() == ERROR_NO_UNICODE_TRANSLATION);
    CHECK(MultiByteToWideChar(CP_UTF8, 0, "\xF0\x9F\x8E\xB5", -1, w, 64) == 3 && w[0] == 0xD83C && w[1] == 0xDFB5);
    CHECK(MultiByteToWideChar(1252, 0, "\x80\xE9", 2, w, 64) == 2 && w[0] == 0x20AC && w[1] == 0xE9);
    BOOL used = FALSE;
    const WCHAR jp[] = { 0x3042, 'x', 0 };
    CHECK(WideCharToMultiByte(1252, 0, jp, -1, a, 64, NULL, &used) == 3 && a[0] == '?' && a[1] == 'x' && used);
    CHECK(WideCharToMultiByte(CP_ACP, 0, W("\xE2\x82\xAC"), 1, a, 64, NULL, &used) == 1 && (unsigned char)a[0] == 0x80);
    CHECK(MultiByteToWideChar(932, 0, "a", -1, w, 64) == 0 && GetLastError() == ERROR_INVALID_PARAMETER);   /* DBCS 非対応 */
    CHECK(GetACP() == 1252 && GetOEMCP() == 437 && IsValidCodePage(65001) && !IsValidCodePage(932));
    CPINFO ci; CHECK(GetCPInfo(CP_UTF8, &ci) && ci.MaxCharSize == 4);
    CHECK(IsDBCSLeadByteEx(1252, 0x81) == FALSE);

    CHECK(lstrlenW(W("hello")) == 5 && lstrlenW(NULL) == 0);
    CHECK(lstrcmpiW(W("Hello"), W("hELLO")) == 0 && lstrcmpW(W("a"), W("b")) < 0 && lstrcmpW(W("b"), W("a")) > 0);
    lstrcpynW(w, W("abcdef"), 4); CHECK(wstr_eq(w, "abc"));
    lstrcpyW(w, W("ab")); lstrcatW(w, W("cd")); CHECK(wstr_eq(w, "abcd"));
    CHECK(MulDiv(3, 5, 2) == 8 && MulDiv(-3, 5, 2) == -8 && MulDiv(1, 1, 0) == -1 && MulDiv(0x7FFFFFFF, 2, 1) == -1);
    CHECK(MulDiv(100, 3, 4) == 75 && MulDiv(7, 1, 2) == 4);

    CHECK(CompareStringW(0, 0, W("abc"), -1, W("abc"), -1) == CSTR_EQUAL);
    CHECK(CompareStringW(0, NORM_IGNORECASE, W("abc"), -1, W("ABC"), -1) == CSTR_EQUAL);
    CHECK(CompareStringW(0, 0, W("a"), -1, W("A"), -1) == CSTR_LESS_THAN);       /* culture 比較: 小文字 < 大文字 */
    CHECK(CompareStringW(0, 0, W("a"), -1, W("b"), -1) == CSTR_LESS_THAN);
    CHECK(CompareStringW(0, 0, W("ab"), -1, W("a"), -1) == CSTR_GREATER_THAN);
    CHECK(CompareStringW(0, 0, W("abc"), 2, W("ab"), 2) == CSTR_EQUAL);
    CHECK(CompareStringA(0, NORM_IGNORECASE, "Foo", -1, "fOO", -1) == CSTR_EQUAL);
    WCHAR up[16]; lstrcpyW(up, W("abc\xC3\xA9z")); CharUpperW(up);
    CHECK(wstr_eq(up, "ABC\xC3\x89Z"));
    CHECK((uintptr_t)CharLowerW((LPWSTR)(uintptr_t)'Q') == 'q');                   /* 単一文字モード */
    CHECK(CharUpperBuffW(up, 2) == 2);
    CHECK(LCMapStringW(0, LCMAP_LOWERCASE, W("AbC"), -1, w, 64) == 4 && wstr_eq(w, "abc"));
    CHECK(LCMapStringW(0, LCMAP_UPPERCASE, W("AbC"), 3, w, 64) == 3 && w[2] == 'C');
    WORD ct[4];
    CHECK(GetStringTypeW(CT_CTYPE1, W("aZ1 !"), 5, ct));
    CHECK((ct[0] & C1_LOWER) && (ct[1] & C1_UPPER) && (ct[2] & C1_DIGIT) && (ct[3] & C1_SPACE));
    CHECK(CharNextW(W("ab")) != NULL);

    CHECK(GetUserDefaultLCID() == 0x0409 && GetThreadLocale() == 0x0409 && IsValidLocale(0x0409, 1) && !IsValidLocale(0x1234, 1));
    CHECK(GetLocaleInfoW(0x0409, 0x0E /*SDECIMAL*/, w, 64) == 2 && w[0] == '.');
    CHECK(GetLocaleInfoW(0x0409, 0x38 /*SMONTHNAME1*/, w, 64) > 0 && wstr_eq(w, "January"));
    DWORD num = 0;
    CHECK(GetLocaleInfoW(0x0409, LOCALE_RETURN_NUMBER | 0x1004 /*IDEFAULTANSICODEPAGE*/, (LPWSTR)&num, 2) == 2 && num == 1252);
    CHECK(GetLocaleInfoW(0x0409, 0x0E, w, 1) == 0 && GetLastError() == ERROR_INSUFFICIENT_BUFFER);
    CHECK(LocaleNameToLCID(W("ja-JP"), 0) == 0x0411 && GetSystemDefaultLocaleName(w, 64) == 6 && wstr_eq(w, "en-US"));
    SYSTEMTIME st = { 2024, 3, 5, 15, 13, 5, 9, 0 };
    CHECK(GetDateFormatW(0x0409, 0, &st, NULL, w, 64) > 0 && wstr_eq(w, "3/15/2024"));
    CHECK(GetDateFormatW(0x0409, 0, &st, W("yyyy-MM-dd ddd"), w, 64) > 0 && wstr_eq(w, "2024-03-15 Fri"));
    CHECK(GetTimeFormatW(0x0409, 0, &st, NULL, w, 64) > 0 && wstr_eq(w, "1:05:09 PM"));
    CHECK(GetTimeFormatW(0x0409, 8 /*FORCE24*/, &st, W("HH:mm"), w, 64) > 0 && wstr_eq(w, "13:05"));

    CHECK(FormatMessageW(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, NULL, ERROR_FILE_NOT_FOUND, 0, w, 64, NULL) > 0);
    CHECK(strncmp(U8(w), "The system cannot find the file specified.", 20) == 0);
    LPWSTR alloc = NULL;
    uint64_t args[2] = { (uint64_t)(uintptr_t)W("world"), 42 };
    CHECK(FormatMessageW(FORMAT_MESSAGE_FROM_STRING | FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_ARGUMENT_ARRAY, W("Hello %1, n=%2!d!%%"), 0, 0, (LPWSTR)&alloc, 0, args) > 0);
    CHECK(alloc && wstr_eq(alloc, "Hello world, n=42%"));
    LocalFree((HLOCAL)alloc);
    CHECK(FormatMessageW(FORMAT_MESSAGE_FROM_SYSTEM, NULL, 0xDEAD, 0, w, 64, NULL) == 0);    /* 未知 ID */
    char ab[128];
    CHECK(FormatMessageA(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, NULL, ERROR_ACCESS_DENIED, 0, ab, 128, NULL) > 0 && !strncmp(ab, "Access is denied.", 17));
    CHECK(PathUnExpandEnvStringsW(W("C:\\Users\\user\\AppData\\Roaming\\x.dat"), w, 64) && wstr_eq(w, "%APPDATA%\\x.dat"));
    CHECK(PathUnExpandEnvStringsW(W("D:\\none"), w, 64) == FALSE);
}

/* ---------------------------------------------------------------
 * レジストリ
 * --------------------------------------------------------------- */
static void test_registry(void) {
    HKEY k = 0, k2 = 0; DWORD disp = 0;
    CHECK(RegCreateKeyExW(HKEY_CURRENT_USER, W("Software\\ShimxTest\\Sub"), 0, NULL, 0, KEY_ALL_ACCESS, NULL, &k, &disp) == ERROR_SUCCESS);
    CHECK(disp == REG_CREATED_NEW_KEY && k);
    CHECK(RegCreateKeyExW(HKEY_CURRENT_USER, W("software\\SHIMXTEST\\sub"), 0, NULL, 0, KEY_ALL_ACCESS, NULL, &k2, &disp) == ERROR_SUCCESS);
    CHECK(disp == REG_OPENED_EXISTING_KEY);                       /* 大小無視で既存 */
    RegCloseKey(k2);

    const WCHAR* sv = W("hello \xE3\x81\x82");
    CHECK(RegSetValueExW(k, W("Str"), 0, REG_SZ, (const BYTE*)sv, (DWORD)(lstrlenW(sv) + 1) * 2) == ERROR_SUCCESS);
    DWORD dw = 0xCAFE;
    CHECK(RegSetValueExW(k, W("Num"), 0, REG_DWORD, (const BYTE*)&dw, 4) == ERROR_SUCCESS);
    const BYTE bin[5] = { 1, 2, 3, 4, 5 };
    CHECK(RegSetValueExW(k, W("Bin"), 0, REG_BINARY, bin, 5) == ERROR_SUCCESS);
    CHECK(RegSetValueExW(k, NULL, 0, REG_SZ, (const BYTE*)W("def"), 8) == ERROR_SUCCESS);     /* 既定値 */

    DWORD type = 0, cb = 0;
    CHECK(RegQueryValueExW(k, W("STR"), NULL, &type, NULL, &cb) == ERROR_SUCCESS && type == REG_SZ && cb == (DWORD)(lstrlenW(sv) + 1) * 2);
    WCHAR buf[64]; cb = sizeof buf;
    CHECK(RegQueryValueExW(k, W("Str"), NULL, &type, (LPBYTE)buf, &cb) == ERROR_SUCCESS && wstr_eq(buf, "hello \xE3\x81\x82"));
    cb = 4;
    CHECK(RegQueryValueExW(k, W("Str"), NULL, &type, (LPBYTE)buf, &cb) == ERROR_MORE_DATA && cb == (DWORD)(lstrlenW(sv) + 1) * 2);
    DWORD out = 0; cb = 4;
    CHECK(RegQueryValueExW(k, W("Num"), NULL, &type, (LPBYTE)&out, &cb) == ERROR_SUCCESS && type == REG_DWORD && out == 0xCAFE);
    cb = sizeof buf;
    CHECK(RegQueryValueExW(k, NULL, NULL, &type, (LPBYTE)buf, &cb) == ERROR_SUCCESS && wstr_eq(buf, "def"));
    CHECK(RegQueryValueExW(k, W("nope"), NULL, &type, NULL, &cb) == ERROR_FILE_NOT_FOUND);

    char ab[32]; cb = sizeof ab;
    CHECK(RegSetValueExA(k, "AnsiVal", 0, REG_SZ, (const BYTE*)"abc", 4) == ERROR_SUCCESS);
    CHECK(RegQueryValueExA(k, "AnsiVal", NULL, &type, (LPBYTE)ab, &cb) == ERROR_SUCCESS && !strcmp(ab, "abc") && cb == 4);
    DWORD cb2 = sizeof buf;
    CHECK(RegQueryValueExW(k, W("AnsiVal"), NULL, &type, (LPBYTE)buf, &cb2) == ERROR_SUCCESS && wstr_eq(buf, "abc"));

    HKEY c1, c2;
    CHECK(RegCreateKeyExW(k, W("zeta"), 0, NULL, 0, KEY_ALL_ACCESS, NULL, &c1, NULL) == 0);
    CHECK(RegCreateKeyExW(k, W("Alpha"), 0, NULL, 0, KEY_ALL_ACCESS, NULL, &c2, NULL) == 0);
    WCHAR nm[32]; DWORD ncch = 32;
    CHECK(RegEnumKeyExW(k, 0, nm, &ncch, NULL, NULL, NULL, NULL) == 0 && wstr_eq(nm, "Alpha") && ncch == 5);   /* 名前順 */
    ncch = 32; CHECK(RegEnumKeyExW(k, 1, nm, &ncch, NULL, NULL, NULL, NULL) == 0 && wstr_eq(nm, "zeta"));
    ncch = 32; CHECK(RegEnumKeyExW(k, 2, nm, &ncch, NULL, NULL, NULL, NULL) == ERROR_NO_MORE_ITEMS);
    ncch = 2;  CHECK(RegEnumKeyExW(k, 0, nm, &ncch, NULL, NULL, NULL, NULL) == ERROR_MORE_DATA);
    ncch = 32; cb = sizeof buf;
    CHECK(RegEnumValueW(k, 0, nm, &ncch, NULL, &type, (LPBYTE)buf, &cb) == 0 && wstr_eq(nm, "Str"));        /* 作成順 */
    DWORD nsub, maxsub, nval, maxvn, maxvd;
    CHECK(RegQueryInfoKeyW(k, NULL, NULL, NULL, &nsub, &maxsub, NULL, &nval, &maxvn, &maxvd, NULL, NULL) == 0);
    CHECK(nsub == 2 && maxsub == 5 && nval == 5 && maxvn == 7 && maxvd == (DWORD)(lstrlenW(sv) + 1) * 2);
    CHECK(RegDeleteKeyW(HKEY_CURRENT_USER, W("Software\\ShimxTest\\Sub")) == ERROR_ACCESS_DENIED);   /* 子ありキー */
    CHECK(RegCloseKey(c1) == 0 && RegCloseKey(c2) == 0);
    CHECK(RegDeleteKeyW(k, W("zeta")) == 0 && RegDeleteKeyW(k, W("Alpha")) == 0);
    CHECK(RegDeleteValueW(k, W("Bin")) == 0 && RegDeleteValueW(k, W("Bin")) == ERROR_FILE_NOT_FOUND);
    cb2 = 4; CHECK(RegGetValueW(k, NULL, W("Num"), RRF_RT_REG_DWORD, &type, &out, &cb2) == 0 && out == 0xCAFE);
    cb2 = 4; CHECK(RegGetValueW(k, NULL, W("Num"), RRF_RT_REG_SZ, &type, &out, &cb2) == 1630);
    CHECK(RegCloseKey(k) == 0);
    CHECK(RegCloseKey(k) == ERROR_INVALID_HANDLE);
    CHECK(RegOpenKeyExW(HKEY_CURRENT_USER, W("Software\\ShimxTest\\Sub"), 0, KEY_READ, &k2) == 0);
    CHECK(RegDeleteKeyW(HKEY_CURRENT_USER, W("Software\\ShimxTest\\Sub")) == 0);
    cb = 0; CHECK(RegQueryValueExW(k2, W("Str"), NULL, &type, NULL, &cb) == 1018);        /* ERROR_KEY_DELETED */
    RegCloseKey(k2);
    CHECK(RegOpenKeyExW(HKEY_CURRENT_USER, W("Software\\ShimxTest\\Sub"), 0, KEY_READ, &k2) == ERROR_FILE_NOT_FOUND);
    RegDeleteKeyW(HKEY_CURRENT_USER, W("Software\\ShimxTest"));

    CHECK(RegOpenKeyExW(HKEY_LOCAL_MACHINE, W("SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion"), 0, KEY_READ, &k) == 0);
    cb = sizeof buf; CHECK(RegQueryValueExW(k, W("CurrentBuildNumber"), NULL, &type, (LPBYTE)buf, &cb) == 0 && wstr_eq(buf, "19045"));
    RegCloseKey(k);
    CHECK(RegOpenKeyExW(HKEY_CLASSES_ROOT, NULL, 0, KEY_READ, &k) == 0 && k == HKEY_CLASSES_ROOT);

    CHECK(shimx_reg_set_sz("HKCU\\Software\\Image-Line\\FL Studio", "InstallDir", "C:\\FL") == 0);
    CHECK(shimx_reg_set_dword("HKEY_CURRENT_USER\\Software\\Image-Line\\FL Studio", "Build", 5653) == 0);
    int imported = shimx_reg_import_text(
        "Windows Registry Editor Version 5.00\n\n"
        "[HKEY_CURRENT_USER\\Software\\ShimxImp]\n"
        "@=\"default\"\n\"s\"=\"a\\\\b\\\"c\"\n\"d\"=dword:0000002a\n\"b\"=hex:de,ad,be,ef\n\"m\"=hex(7):41,00,00,00,42,00,00,00,00,00\n");
    CHECK(imported == 5);
    CHECK(RegOpenKeyExW(HKEY_CURRENT_USER, W("Software\\ShimxImp"), 0, KEY_READ, &k) == 0);
    cb = sizeof buf; CHECK(RegQueryValueExW(k, W("s"), NULL, &type, (LPBYTE)buf, &cb) == 0 && wstr_eq(buf, "a\\b\"c"));
    cb = sizeof buf; CHECK(RegQueryValueExW(k, W("m"), NULL, &type, (LPBYTE)buf, &cb) == 0 && type == REG_MULTI_SZ && cb == 10);
    RegCloseKey(k);
    char* txt = shimx_reg_export_text();
    CHECK(strstr(txt, "[HKEY_CURRENT_USER\\Software\\Image-Line\\FL Studio]") && strstr(txt, "\"InstallDir\"=\"C:\\\\FL\"") && strstr(txt, "\"Build\"=dword:00001615"));
    CHECK(strstr(txt, "\"b\"=hex:de,ad,be,ef") && strstr(txt, "\"m\"=hex(7):41,00,00,00,42,00,00,00,00,00") && strstr(txt, "@=\"default\""));
    int keys0, vals0; shimx_reg_stats(&keys0, &vals0);
    shimx_reg_reset();                                              /* 全消去 → 既定シードのみに戻る */
    CHECK(RegOpenKeyExW(HKEY_CURRENT_USER, W("Software\\ShimxImp"), 0, KEY_READ, &k) == ERROR_FILE_NOT_FOUND);
    CHECK(shimx_reg_import_text(txt) > 0);                          /* export したテキストから復元 */
    CHECK(RegOpenKeyExW(HKEY_CURRENT_USER, W("Software\\ShimxImp"), 0, KEY_READ, &k) == 0);
    cb = sizeof buf; CHECK(RegQueryValueExW(k, W("s"), NULL, &type, (LPBYTE)buf, &cb) == 0 && wstr_eq(buf, "a\\b\"c"));
    RegCloseKey(k);
    int keys1, vals1; shimx_reg_stats(&keys1, &vals1);
    CHECK(keys1 == keys0 && vals1 == vals0);
    free(txt);

    HANDLE tok = 0; DWORD el = 99, ret = 0;
    CHECK(OpenProcessToken(GetCurrentProcess(), 8, &tok) && tok);
    CHECK(GetTokenInformation(tok, 20, &el, 4, &ret) && el == 0 && ret == 4);
    CloseHandle(tok);
}

/* ---------------------------------------------------------------
 * ファイル (Win パス写像 / Find / INI / マッピング / 大小無視)
 * --------------------------------------------------------------- */
static void put_file(const WCHAR* path, const void* data, DWORD n) {
    HANDLE h = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, 0);
    CHECK(h != INVALID_HANDLE_VALUE);
    DWORD w = 0; CHECK(WriteFile(h, data, n, &w, NULL) && w == n);
    CHECK(CloseHandle(h));
}

static void test_files(void) {
    char px[512];
    CHECK(shimx_path_to_posix("C:\\foo\\bar.txt", px, sizeof px) == 0 && !strcmp(px, "/c/foo/bar.txt"));
    CHECK(shimx_path_to_posix("c:/a/./b/../c", px, sizeof px) == 0 && !strcmp(px, "/c/a/c"));
    CHECK(shimx_path_to_posix("\\\\?\\D:\\x", px, sizeof px) == 0 && !strcmp(px, "/d/x"));
    CHECK(shimx_path_to_posix("\\\\srv\\share\\f", px, sizeof px) == 0 && !strcmp(px, "/unc/srv/share/f"));
    CHECK(shimx_path_to_posix("/abs/ok", px, sizeof px) == 0 && !strcmp(px, "/abs/ok"));      /* POSIX 絶対は素通し */
    CHECK(shimx_path_to_posix("rel\\x", px, sizeof px) == 0 && !strcmp(px, "/c/rel/x"));       /* cwd=C:\ 基準 */

    CHECK(CreateDirectoryW(W("C:\\shimx_t"), NULL));
    CHECK(CreateDirectoryW(W("C:\\shimx_t"), NULL) == FALSE && GetLastError() == ERROR_ALREADY_EXISTS);
    CHECK(CreateDirectoryW(W("C:\\nodir\\sub"), NULL) == FALSE && GetLastError() == ERROR_PATH_NOT_FOUND);
    put_file(W("C:\\shimx_t\\Alpha.TXT"), "0123456789", 10);
    put_file(W("C:\\shimx_t\\beta.dat"), "xy", 2);
    CHECK(CreateDirectoryW(W("C:\\shimx_t\\Sub"), NULL));
    CHECK(GetFileAttributesW(W("c:\\SHIMX_T\\alpha.txt")) == FILE_ATTRIBUTE_ARCHIVE);        /* 大小無視 */
    CHECK(GetFileAttributesW(W("C:\\shimx_t\\Sub")) & FILE_ATTRIBUTE_DIRECTORY);
    CHECK(GetFileAttributesW(W("C:\\shimx_t\\nope")) == INVALID_FILE_ATTRIBUTES && GetLastError() == ERROR_FILE_NOT_FOUND);
    CHECK(GetFileAttributesW(W("C:\\nodir\\nope")) == INVALID_FILE_ATTRIBUTES && GetLastError() == ERROR_PATH_NOT_FOUND);
    WIN32_FILE_ATTRIBUTE_DATA ad;
    CHECK(GetFileAttributesExW(W("C:\\shimx_t\\Alpha.TXT"), 0, &ad) && ad.nFileSizeLow == 10 && ad.ftLastWriteTime.dwHighDateTime > 0x01D00000);

    WIN32_FIND_DATAW fd;
    HANDLE f = FindFirstFileW(W("C:\\shimx_t\\*"), &fd);
    CHECK(f != INVALID_HANDLE_VALUE && wstr_eq(fd.cFileName, "."));
    const char* expect[] = { "..", "Alpha.TXT", "beta.dat", "Sub" };
    for (int i = 0; i < 4; i++) { CHECK(FindNextFileW(f, &fd)); CHECK(wstr_eq(fd.cFileName, expect[i])); }
    CHECK(FindNextFileW(f, &fd) == FALSE && GetLastError() == ERROR_NO_MORE_FILES);
    CHECK(FindClose(f));
    f = FindFirstFileW(W("C:\\shimx_t\\*.TXT"), &fd);
    CHECK(f != INVALID_HANDLE_VALUE && wstr_eq(fd.cFileName, "Alpha.TXT") && fd.nFileSizeLow == 10);
    CHECK(FindNextFileW(f, &fd) == FALSE); FindClose(f);
    f = FindFirstFileW(W("C:\\shimx_t\\b?ta.*"), &fd);
    CHECK(f != INVALID_HANDLE_VALUE && wstr_eq(fd.cFileName, "beta.dat")); FindClose(f);
    CHECK(FindFirstFileW(W("C:\\shimx_t\\*.zzz"), &fd) == INVALID_HANDLE_VALUE && GetLastError() == ERROR_FILE_NOT_FOUND);
    CHECK(FindFirstFileW(W("C:\\nodir\\*"), &fd) == INVALID_HANDLE_VALUE && GetLastError() == ERROR_PATH_NOT_FOUND);

    CHECK(CopyFileW(W("C:\\shimx_t\\Alpha.TXT"), W("C:\\shimx_t\\copy.txt"), TRUE));
    CHECK(CopyFileW(W("C:\\shimx_t\\Alpha.TXT"), W("C:\\shimx_t\\copy.txt"), TRUE) == FALSE && GetLastError() == ERROR_FILE_EXISTS);
    CHECK(MoveFileW(W("C:\\shimx_t\\copy.txt"), W("C:\\shimx_t\\moved.txt")));
    CHECK(MoveFileW(W("C:\\shimx_t\\moved.txt"), W("C:\\shimx_t\\beta.dat")) == FALSE && GetLastError() == ERROR_ALREADY_EXISTS);
    CHECK(MoveFileExW(W("C:\\shimx_t\\moved.txt"), W("C:\\shimx_t\\beta.dat"), MOVEFILE_REPLACE_EXISTING));
    CHECK(GetFileAttributesW(W("C:\\shimx_t\\moved.txt")) == INVALID_FILE_ATTRIBUTES);
    CHECK(DeleteFileW(W("C:\\shimx_t\\beta.dat")) && DeleteFileW(W("C:\\shimx_t\\beta.dat")) == FALSE);
    CHECK(DeleteFileW(W("C:\\shimx_t\\Sub")) == FALSE && GetLastError() == ERROR_ACCESS_DENIED);
    CHECK(RemoveDirectoryW(W("C:\\shimx_t")) == FALSE && GetLastError() == ERROR_DIR_NOT_EMPTY);

    HANDLE h = CreateFileW(W("C:\\shimx_t\\Alpha.TXT"), GENERIC_READ, FILE_SHARE_READ, NULL, CREATE_NEW, 0, 0);
    CHECK(h == INVALID_HANDLE_VALUE && GetLastError() == ERROR_FILE_EXISTS);
    h = CreateFileW(W("C:\\shimx_t\\Alpha.TXT"), GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_ALWAYS, 0, 0);
    CHECK(h != INVALID_HANDLE_VALUE && GetLastError() == ERROR_ALREADY_EXISTS);
    BY_HANDLE_FILE_INFORMATION bi;
    CHECK(GetFileInformationByHandle(h, &bi) && bi.nFileSizeLow == 10 && bi.dwFileAttributes == FILE_ATTRIBUTE_ARCHIVE);
    CHECK(GetFileType(h) == FILE_TYPE_DISK);
    WCHAR fp[300];
    CHECK(GetFinalPathNameByHandleW(h, fp, 300, 0) > 0 && wstr_eq(fp, "\\\\?\\C:\\shimx_t\\Alpha.TXT"));
    CHECK(FlushFileBuffers(h));
    CloseHandle(h);
    h = CreateFileW(W("C:\\shimx_t"), GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, 0);
    CHECK(h == INVALID_HANDLE_VALUE && GetLastError() == ERROR_ACCESS_DENIED);          /* ディレクトリは BACKUP_SEMANTICS 必須 */
    h = CreateFileW(W("C:\\shimx_t"), 0, 0, NULL, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, 0);
    CHECK(h != INVALID_HANDLE_VALUE); CloseHandle(h);
    h = CreateFileW(W("C:\\shimx_t\\Alpha.TXT"), GENERIC_READ, 0, NULL, TRUNCATE_EXISTING, 0, 0);
    CHECK(h == INVALID_HANDLE_VALUE && GetLastError() == ERROR_INVALID_PARAMETER);

    WCHAR full[300]; LPWSTR part = NULL;
    CHECK(GetFullPathNameW(W("sub\\..\\x.txt"), 300, full, &part) > 0 && wstr_eq(full, "C:\\x.txt") && part && wstr_eq(part, "x.txt"));
    CHECK(GetFullPathNameW(W("C:\\a\\.\\b\\..\\c.txt"), 300, full, &part) > 0 && wstr_eq(full, "C:\\a\\c.txt"));
    CHECK(GetFullPathNameW(W("/flp/q.bin"), 300, full, &part) > 0 && wstr_eq(full, "/flp/q.bin"));
    CHECK(SetCurrentDirectoryW(W("C:\\shimx_t")) && GetCurrentDirectoryW(300, full) > 0 && wstr_eq(full, "C:\\shimx_t"));
    put_file(W("rel.txt"), "R", 1);                                                   /* 相対パス → cwd 基準 */
    CHECK(GetFileAttributesW(W("C:\\shimx_t\\rel.txt")) != INVALID_FILE_ATTRIBUTES);
    CHECK(SetCurrentDirectoryW(W("C:\\nodir")) == FALSE);
    SetCurrentDirectoryW(W("C:\\"));
    CHECK(GetTempPathW(300, full) > 0 && wstr_eq(full, "C:\\Users\\user\\AppData\\Local\\Temp\\"));
    WCHAR tmp[300];
    UINT u = GetTempFileNameW(full, W("shx"), 0, tmp);
    CHECK(u != 0 && GetFileAttributesW(tmp) != INVALID_FILE_ATTRIBUTES && strstr(U8(tmp), "\\shx") != NULL);
    DeleteFileW(tmp);

    CHECK(GetLogicalDrives() == 4 && GetDriveTypeW(W("C:\\")) == DRIVE_FIXED && GetDriveTypeW(W("Z:\\")) == DRIVE_NO_ROOT_DIR);
    WCHAR vol[32], fs[16]; DWORD ser, mc, fl;
    CHECK(GetVolumeInformationW(W("C:\\"), vol, 32, &ser, &mc, &fl, fs, 16) && wstr_eq(fs, "NTFS") && mc == 255);
    CHECK(GetLogicalDriveStringsW(32, full) == 4 && wstr_eq(full, "C:\\"));
    CHECK(QueryDosDeviceW(W("C:"), full, 100) > 0 && wstr_eq(full, "\\Device\\HarddiskVolume1"));
    DWORD spc, bps, fc, tc; CHECK(GetDiskFreeSpaceW(W("C:\\"), &spc, &bps, &fc, &tc) && bps == 512);

    WCHAR ini[64]; lstrcpyW(ini, W("C:\\shimx_t\\a.ini"));
    CHECK(WritePrivateProfileStringW(W("Audio"), W("Rate"), W("48000"), ini));
    CHECK(WritePrivateProfileStringW(W("Audio"), W("Name"), W("Out 1"), ini));
    CHECK(WritePrivateProfileStringW(W("Midi"), W("Dev"), W("x"), ini));
    WCHAR iv[64];
    CHECK(GetPrivateProfileStringW(W("audio"), W("RATE"), W("def"), iv, 64, ini) == 5 && wstr_eq(iv, "48000"));
    CHECK(GetPrivateProfileIntW(W("Audio"), W("Rate"), 1, ini) == 48000);
    CHECK(GetPrivateProfileStringW(W("Audio"), W("Missing"), W("def"), iv, 64, ini) == 3 && wstr_eq(iv, "def"));
    CHECK(GetPrivateProfileStringW(W("Audio"), W("Name"), W(""), iv, 4, ini) == 3 && wstr_eq(iv, "Out"));     /* 切り詰め */
    WCHAR multi[64];
    DWORD mn = GetPrivateProfileStringW(W("Audio"), NULL, W(""), multi, 64, ini);
    CHECK(mn == 10 && wstr_eq(multi, "Rate") && wstr_eq(multi + 5, "Name"));                                    /* キー名一覧 (multi-sz) */
    mn = GetPrivateProfileStringW(NULL, NULL, W(""), multi, 64, ini);
    CHECK(mn == 11 && wstr_eq(multi, "Audio") && wstr_eq(multi + 6, "Midi"));
    CHECK(WritePrivateProfileStringW(W("Audio"), W("Rate"), W("44100"), ini));                                 /* 上書き */
    CHECK(GetPrivateProfileIntW(W("Audio"), W("Rate"), 1, ini) == 44100);
    CHECK(WritePrivateProfileStringW(W("Audio"), W("Name"), NULL, ini));                                       /* キー削除 */
    CHECK(GetPrivateProfileStringW(W("Audio"), W("Name"), W("gone"), iv, 64, ini) == 4);
    CHECK(WritePrivateProfileStringW(W("Midi"), NULL, NULL, ini));                                             /* セクション削除 */
    CHECK(GetPrivateProfileStringW(W("Midi"), W("Dev"), W("gone"), iv, 64, ini) == 4);

    HANDLE m1 = CreateFileMappingW(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, 4096, W("shimx_shm"));
    CHECK(m1);
    char* v1 = (char*)MapViewOfFile(m1, FILE_MAP_WRITE, 0, 0, 0);
    CHECK(v1); strcpy(v1, "shared");
    HANDLE m2 = CreateFileMappingW(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, 4096, W("shimx_shm"));
    CHECK(m2 && GetLastError() == ERROR_ALREADY_EXISTS);
    char* v2 = (char*)MapViewOfFile(m2, FILE_MAP_READ, 0, 0, 0);
    CHECK(v2 == v1 && !strcmp(v2, "shared"));
    CHECK(UnmapViewOfFile(v1) && UnmapViewOfFile(v2) && UnmapViewOfFile(v2) == FALSE);
    CloseHandle(m1); CloseHandle(m2);
    h = CreateFileW(W("C:\\shimx_t\\map.bin"), GENERIC_READ | GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, 0);
    DWORD wr; WriteFile(h, "abcdefgh", 8, &wr, NULL);
    m1 = CreateFileMappingW(h, NULL, PAGE_READWRITE, 0, 0, NULL);
    CHECK(m1);
    CloseHandle(h);                                                                     /* ファイルハンドルを閉じてもマッピングは有効 */
    v1 = (char*)MapViewOfFile(m1, FILE_MAP_WRITE, 0, 0, 0);
    CHECK(v1 && !memcmp(v1, "abcdefgh", 8));
    v1[0] = 'Z';
    CHECK(FlushViewOfFile(v1, 0));
    UnmapViewOfFile(v1); CloseHandle(m1);
    h = CreateFileW(W("C:\\shimx_t\\map.bin"), GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, 0);
    char rb[8]; DWORD rd; ReadFile(h, rb, 8, &rd, NULL);
    CHECK(rd == 8 && !memcmp(rb, "Zbcdefgh", 8));
    CloseHandle(h);

    WCHAR from[64]; memset(from, 0, sizeof from); lstrcpyW(from, W("C:\\shimx_t"));
    uint8_t op[56]; memset(op, 0, sizeof op);
    *(uint32_t*)(op + 8) = 3;                       /* FO_DELETE */
    *(uint64_t*)(op + 16) = (uint64_t)(uintptr_t)from;
    CHECK(SHFileOperationW(op) == 0);
    CHECK(GetFileAttributesW(W("C:\\shimx_t")) == INVALID_FILE_ATTRIBUTES);

    HANDLE so = GetStdHandle(STD_OUTPUT_HANDLE);
    CHECK(so && so != INVALID_HANDLE_VALUE && GetFileType(so) == FILE_TYPE_CHAR);
    DWORD cm; CHECK(GetConsoleMode(so, &cm) == FALSE);                                  /* 常に非コンソール */
    CHECK(GetConsoleOutputCP() == 437);
}

/* ---------------------------------------------------------------
 * 時刻
 * --------------------------------------------------------------- */
static void test_time(void) {
    SYSTEMTIME st = { 2000, 1, 6, 1, 0, 0, 0, 0 };
    FILETIME ft;
    CHECK(SystemTimeToFileTime(&st, &ft) && ft.dwHighDateTime == 0x01BF53EBu && ft.dwLowDateTime == 0x256D4000u);
    SYSTEMTIME back;
    CHECK(FileTimeToSystemTime(&ft, &back) && back.wYear == 2000 && back.wMonth == 1 && back.wDay == 1 && back.wDayOfWeek == 6);
    SYSTEMTIME leap = { 2024, 2, 0, 29, 23, 59, 58, 123 };
    CHECK(SystemTimeToFileTime(&leap, &ft) && FileTimeToSystemTime(&ft, &back) && back.wDay == 29 && back.wDayOfWeek == 4 && back.wMilliseconds == 123);
    SYSTEMTIME bad2 = { 1500, 1, 0, 1, 0, 0, 0, 0 };
    CHECK(SystemTimeToFileTime(&bad2, &ft) == FALSE);
    FILETIME a = { 1, 5 }, b = { 2, 5 };
    CHECK(CompareFileTime(&a, &b) == -1 && CompareFileTime(&b, &a) == 1 && CompareFileTime(&a, &a) == 0);
    WORD dd, dt;
    SYSTEMTIME ds = { 2024, 3, 0, 15, 13, 45, 30, 0 };
    CHECK(SystemTimeToFileTime(&ds, &ft) && FileTimeToDosDateTime(&ft, &dd, &dt));
    CHECK(dd == (WORD)(((2024 - 1980) << 9) | (3 << 5) | 15) && dt == (WORD)((13 << 11) | (45 << 5) | 15));
    FILETIME ft2; CHECK(DosDateTimeToFileTime(dd, dt, &ft2) && CompareFileTime(&ft, &ft2) == 0);
    FILETIME now; GetSystemTimeAsFileTime(&now);
    CHECK(now.dwHighDateTime > 0x01DC0000u);                      /* 2024 年以降 */
    SYSTEMTIME sys, loc; GetSystemTime(&sys); GetLocalTime(&loc);
    CHECK(sys.wYear >= 2024 && loc.wYear >= 2024);
    FILETIME lft, uft;
    CHECK(FileTimeToLocalFileTime(&now, &lft) && LocalFileTimeToFileTime(&lft, &uft) && CompareFileTime(&now, &uft) == 0);
    TIME_ZONE_INFORMATION tz; CHECK(GetTimeZoneInformation(&tz) != 0xFFFFFFFFu);
    SYSTEMTIME l2; CHECK(SystemTimeToTzSpecificLocalTime(&tz, &ds, &l2) && TzSpecificLocalTimeToSystemTime(&tz, &l2, &back) && back.wHour == ds.wHour);
    LARGE_INTEGER f, c1, c2; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&c1); Sleep(10); QueryPerformanceCounter(&c2);
    CHECK(f.QuadPart == 1000000 && c2.QuadPart - c1.QuadPart >= 5000);
    CHECK(timeBeginPeriod(1) == 0 && timeEndPeriod(1) == 0 && timeGetTime() > 0);
}

/* ---------------------------------------------------------------
 * heap / Global / Virtual / メモリ状態
 * --------------------------------------------------------------- */
static void test_memory(void) {
    HEAP_HANDLE ph = GetProcessHeap();
    CHECK(ph && ph == GetProcessHeap());
    for (int i = 1; i < 50; i++) {
        void* p = HeapAlloc(ph, HEAP_ZERO_MEMORY, (SIZE_T)i * 7);
        CHECK(p && ((uintptr_t)p & 15) == 0);                      /* 16B 整列 (M4 は 4B) */
        CHECK(HeapSize(ph, 0, p) == (SIZE_T)i * 7 && HeapValidate(ph, 0, p));
        CHECK(*(uint8_t*)((char*)p + i * 7 - 1) == 0);
        CHECK(HeapFree(ph, 0, p));
    }
    char* p = (char*)HeapAlloc(ph, 0, 10); memcpy(p, "0123456789", 10);
    p = (char*)HeapReAlloc(ph, HEAP_ZERO_MEMORY, p, 100);
    CHECK(p && !memcmp(p, "0123456789", 10) && p[99] == 0 && HeapSize(ph, 0, p) == 100);
    CHECK(HeapFree(ph, 0, p));
    CHECK(HeapSize(ph, 0, (void*)0x10) == (SIZE_T)-1);
    HEAP_HANDLE h2 = HeapCreate(0, 0, 0);
    CHECK(h2 && h2 != ph && HeapDestroy(h2) && HeapDestroy(ph) == FALSE);

    HGLOBAL g = GlobalAlloc(GHND, 64);
    CHECK(g && GlobalSize(g) == 64);
    char* gp = (char*)GlobalLock(g); CHECK(gp == (char*)g && gp[63] == 0);
    CHECK(GlobalUnlock(g) && GlobalUnlock(g) == FALSE && GetLastError() == 158);
    g = GlobalReAlloc(g, 256, GMEM_ZEROINIT); CHECK(g && GlobalSize(g) == 256);
    CHECK(GlobalFree(g) == 0);
    HLOCAL l = LocalAlloc(LMEM_ZEROINIT, 12); CHECK(l && LocalSize(l) == 12 && LocalFree(l) == 0);

    void* v = VirtualAlloc(NULL, 100000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    CHECK(v && ((uintptr_t)v & 0xFFFF) == 0 && *(char*)v == 0);
    memset(v, 0xAB, 100000);
    CHECK(VirtualAlloc(v, 4096, MEM_COMMIT, PAGE_READWRITE) == v);   /* 予約済み範囲の commit */
    MEMORY_BASIC_INFORMATION64 mbi;
    CHECK(VirtualQuery((char*)v + 5000, &mbi, sizeof mbi) == sizeof mbi);
    CHECK(mbi.AllocationBase == (uint64_t)(uintptr_t)v && mbi.State == MEM_COMMIT && mbi.BaseAddress == (uint64_t)(uintptr_t)v + 4096 && mbi.RegionSize >= 90000);
    CHECK(sizeof(MEMORY_BASIC_INFORMATION64) == 48 && VirtualQuery(v, &mbi, 8) == 0);
    DWORD old; CHECK(VirtualProtect(v, 4096, PAGE_READONLY, &old) && old == PAGE_READWRITE);
    CHECK(VirtualFree(v, 4096, MEM_DECOMMIT) && *(char*)v == 0 && ((unsigned char*)v)[8192] == 0xAB);
    CHECK(VirtualFree(v, 100000, MEM_RELEASE) == FALSE);           /* RELEASE は size=0 必須 */
    CHECK(VirtualFree(v, 0, MEM_RELEASE));
    CHECK(VirtualAlloc((void*)0x1000, 4096, MEM_COMMIT, PAGE_READWRITE) == NULL);
    CHECK(VirtualQuery((void*)0x8, &mbi, sizeof mbi) == sizeof mbi && mbi.State == MEM_FREE);

    MEMORYSTATUSEX ms; ms.dwLength = sizeof ms;
    CHECK(GlobalMemoryStatusEx(&ms) && ms.ullTotalPhys > ms.ullAvailPhys && sizeof(MEMORYSTATUSEX) == 64);
    MEMORYSTATUS64 ms2; ms2.dwLength = sizeof ms2; GlobalMemoryStatus(&ms2);
    CHECK(sizeof ms2 == 56 && ms2.dwTotalVirtual > 0);
    char stackv[16];
    CHECK(IsBadWritePtr(stackv, 16) == FALSE && IsBadReadPtr(NULL, 4) == TRUE && IsBadReadPtr((void*)0xFFFFFFF0u, 64) == TRUE);
    void* cm = CoTaskMemAlloc(40); CHECK(cm); memset(cm, 1, 40); CoTaskMemFree(cm);
}

/* ---------------------------------------------------------------
 * モジュール / プロセス / 環境 / システム情報 / SEH
 * --------------------------------------------------------------- */
static void* g_resolver_hits;
static void* my_resolver(HMODULE m, const char* name, DWORD ord) { (void)m; (void)ord; if (name && !strcmp(name, "HostOnly")) { g_resolver_hits = (void*)0xBEEF; return (void*)0xBEEF; } return NULL; }
static HMODULE my_load_hook(const char* name, DWORD flags) { (void)flags; return !strcmp(name, "hostlib.dll") ? (HMODULE)0x40000 : 0; }
static void dummy_fn(void) {}
static const void* res_provider(HMODULE m, const WCHAR* name, const WCHAR* type, DWORD* size) {
    static const char data[] = "RESDATA";
    (void)m;
    if (name == (const WCHAR*)(uintptr_t)101 && type == (const WCHAR*)(uintptr_t)10) { *size = 7; return data; }
    return NULL;
}

static LONG g_veh_calls;
static LONG my_veh(EXCEPTION_POINTERS64* ep) {
    EXCEPTION_RECORD64* r = (EXCEPTION_RECORD64*)(uintptr_t)ep->ExceptionRecord;
    g_veh_calls++;
    return (r->ExceptionCode == 0xE0000001u && r->NumberParameters == 2 && r->ExceptionInformation[1] == 0x22) ? EXCEPTION_CONTINUE_EXECUTION : EXCEPTION_CONTINUE_SEARCH;
}

static void test_process_module(void) {
    HMODULE exe = GetModuleHandleW(NULL), k32 = GetModuleHandleW(W("KERNEL32"));
    CHECK(exe && k32 && exe != k32 && GetModuleHandleW(W("kernel32.dll")) == k32 && GetModuleHandleA("Kernel32.DLL") == k32);
    CHECK(GetModuleHandleW(W("nosuch.dll")) == 0 && GetLastError() == ERROR_MOD_NOT_FOUND);
    WCHAR path[300];
    CHECK(GetModuleFileNameW(NULL, path, 300) > 0 && wstr_eq(path, "C:\\Program Files\\Image-Line\\FL Studio 2026\\FL64.exe"));
    CHECK(GetModuleFileNameW(NULL, path, 6) == 6 && GetLastError() == ERROR_INSUFFICIENT_BUFFER);
    CHECK(GetModuleFileNameW(k32, path, 300) > 0 && wstr_eq(path, "C:\\Windows\\System32\\kernel32.dll"));
    shimx_set_exe_path("C:\\X\\Y.exe");
    CHECK(GetModuleFileNameW(NULL, path, 300) > 0 && wstr_eq(path, "C:\\X\\Y.exe"));
    uint8_t* nt = (uint8_t*)ImageNtHeader(exe);
    CHECK(nt && *(uint32_t*)nt == 0x4550 && *(uint16_t*)(nt + 24) == 0x20B);
    CHECK(ImageNtHeader((void*)path) == NULL);
    ULONG sz; CHECK(ImageDirectoryEntryToData(exe, TRUE, 1, &sz) == NULL && sz == 0);

    void* cf = GetProcAddress(k32, "CreateFileW");
    CHECK(cf == (void*)CreateFileW && GetProcAddress(k32, "FlsAlloc") == (void*)FlsAlloc);
    CHECK(GetProcAddress(GetModuleHandleW(W("advapi32")), "RegOpenKeyExW") == (void*)RegOpenKeyExW);
    CHECK(GetProcAddress(GetModuleHandleW(W("kernelbase")), "GetTickCount64") == (void*)GetTickCount64);   /* api-set 系は kernel32 を探す */
    CHECK(GetProcAddress(k32, "NoSuchApiXyz") == NULL && GetLastError() == ERROR_PROC_NOT_FOUND);
    CHECK(GetProcAddress(GetModuleHandleW(W("user32")), "RegOpenKeyExW") == NULL);                           /* DLL 違いは不一致 */
    CHECK(GetProcAddress(0, "x") == NULL);
    HMODULE host = shimx_module_register("FLEngine_x64.dll", (HMODULE)0x20000, "C:\\Program Files\\Image-Line\\FL Studio 2026\\FLEngine_x64.dll");
    CHECK(host == (HMODULE)0x20000 && LoadLibraryW(W("c:\\x\\FLEngine_x64.dll")) == host && GetModuleHandleW(W("FLEngine_x64")) == host);
    CHECK(shimx_proc_register(host, "Exported", 0, (void*)dummy_fn) == 0 && shimx_proc_register(host, NULL, 7, (void*)dummy_fn) == 0);
    CHECK(GetProcAddress(host, "Exported") == (void*)dummy_fn && GetProcAddress(host, (LPCSTR)(uintptr_t)7) == (void*)dummy_fn);
    shimx_set_proc_resolver(my_resolver);
    CHECK(GetProcAddress(host, "HostOnly") == (void*)0xBEEF && g_resolver_hits);
    CHECK(LoadLibraryW(W("hostlib.dll")) == 0 && GetLastError() == ERROR_MOD_NOT_FOUND);
    shimx_set_load_hook(my_load_hook);
    CHECK(LoadLibraryW(W("hostlib.dll")) == (HMODULE)0x40000 && GetModuleHandleW(W("hostlib")) == (HMODULE)0x40000);
    CHECK(FreeLibrary(host) && FreeLibrary((HMODULE)0x9999) == FALSE);
    HMODULE mx = 0;
    CHECK(GetModuleHandleExW(4u | 2u, (LPCWSTR)(uintptr_t)0x20010, &mx) && mx == host);          /* FROM_ADDRESS */
    shimx_set_strict(1);                                                                          /* strict: 登録モジュールは NULL のまま (組込み DLL のみ fail-fast) */
    CHECK(GetProcAddress(host, "NotThere") == NULL);
    shimx_set_strict(0);
    CHECK(FindResourceW(host, (LPCWSTR)(uintptr_t)101, (LPCWSTR)(uintptr_t)10) == 0 && GetLastError() == ERROR_RESOURCE_DATA_NOT_FOUND);
    shimx_set_resource_provider(res_provider);
    HRSRC rs = FindResourceW(host, (LPCWSTR)(uintptr_t)101, (LPCWSTR)(uintptr_t)10);
    CHECK(rs && SizeofResource(host, rs) == 7 && !memcmp(LockResource(LoadResource(host, rs)), "RESDATA", 7));

    WCHAR ev[128];
    CHECK(GetEnvironmentVariableW(W("systemroot"), ev, 128) == 10 && wstr_eq(ev, "C:\\Windows"));
    CHECK(GetEnvironmentVariableW(W("NoSuchVar"), ev, 128) == 0 && GetLastError() == ERROR_ENVVAR_NOT_FOUND);
    CHECK(SetEnvironmentVariableW(W("SHX_V"), W("abc")) && GetEnvironmentVariableW(W("shx_v"), ev, 128) == 3);
    CHECK(GetEnvironmentVariableW(W("SHX_V"), ev, 2) == 4);                                       /* 必要長 (NUL 含む) */
    CHECK(ExpandEnvironmentStringsW(W("%SystemRoot%\\x\\%SHX_V%\\%UNDEF%"), ev, 128) == 25 && wstr_eq(ev, "C:\\Windows\\x\\abc\\%UNDEF%"));
    CHECK(SetEnvironmentVariableW(W("SHX_V"), NULL) && GetEnvironmentVariableW(W("SHX_V"), ev, 128) == 0);
    LPWSTR es = GetEnvironmentStringsW(); int cnt = 0;
    for (LPWSTR q = es; *q; q += lstrlenW(q) + 1) cnt++;
    CHECK(cnt >= 20 && FreeEnvironmentStringsW(es));
    CHECK(wstr_eq(GetCommandLineW(), "\"C:\\Program Files\\Image-Line\\FL Studio 2026\\FL64.exe\""));
    shimx_set_command_line("FL64.exe /open x.flp");
    CHECK(wstr_eq(GetCommandLineW(), "FL64.exe /open x.flp") && !strcmp(GetCommandLineA(), "FL64.exe /open x.flp"));

    SYSTEM_INFO64 si; GetSystemInfo(&si);
    CHECK(sizeof si == 48 && si.wProcessorArchitecture == 9 && si.dwPageSize == 4096 && si.dwNumberOfProcessors >= 1 && si.dwAllocationGranularity == 65536);
    STARTUPINFOW64 su; GetStartupInfoW(&su);
    CHECK(sizeof su == 104 && su.cb == 104 && su.hStdOutput == (uint64_t)GetStdHandle(STD_OUTPUT_HANDLE));
    OSVERSIONINFOEXW vi; memset(&vi, 0, sizeof vi); vi.dwOSVersionInfoSize = sizeof vi;
    CHECK(sizeof vi == 284 && GetVersionExW(&vi) && vi.dwMajorVersion == 10 && vi.dwBuildNumber == 19045 && vi.dwPlatformId == 2);
    CHECK((GetVersion() & 0xFF) == 10);
    OSVERSIONINFOEXW want; memset(&want, 0, sizeof want); want.dwOSVersionInfoSize = sizeof want; want.dwMajorVersion = 6; want.dwMinorVersion = 1;
    ULONGLONG cond = VerSetConditionMask(VerSetConditionMask(0, 2, 3 /*GE*/), 1, 3);
    CHECK(VerifyVersionInfoW(&want, 3, cond));                                                   /* >= 6.1 (実 10.0) は真 */
    want.dwMajorVersion = 11;
    CHECK(VerifyVersionInfoW(&want, 3, cond) == FALSE);
    BOOL wow = TRUE; CHECK(IsWow64Process(GetCurrentProcess(), &wow) && !wow);
    CHECK(IsProcessorFeaturePresent(10) && !IsProcessorFeaturePresent(23) && !IsProcessorFeaturePresent(40));   /* SSE2 有 / FASTFAIL・AVX2 無 */
    WCHAR cn[32]; DWORD cnl = 32; CHECK(GetComputerNameW(cn, &cnl) && cnl == 9 && wstr_eq(cn, "WEBSTUDIO"));
    DWORD li = 0; CHECK(GetLogicalProcessorInformation(NULL, &li) == FALSE && li == si.dwNumberOfProcessors * 32);
    CHECK(GetSystemDirectoryW(path, 300) == 19 && GetWindowsDirectoryW(path, 300) == 10);
    CHECK(IsDebuggerPresent() == FALSE);
    PROCESS_INFORMATION64 pi;
    CHECK(CreateProcessW(W("C:\\x.exe"), NULL, NULL, NULL, FALSE, 0, NULL, NULL, NULL, &pi) == FALSE && GetLastError() == ERROR_FILE_NOT_FOUND);
    DWORD ec = 0; CHECK(GetExitCodeProcess(GetCurrentProcess(), &ec) && ec == STILL_ACTIVE && GetCurrentProcessId() != 0);
    HANDLE ph = OpenProcess(0x1F0FFF, FALSE, GetCurrentProcessId()); CHECK(ph && GetProcessId(ph) == GetCurrentProcessId()); CloseHandle(ph);

    ATOM at = AddAtomW(W("MyAtom")); CHECK(at >= 0xC000 && FindAtomW(W("MYATOM")) == at && AddAtomW(W("myatom")) == at);
    CHECK(DeleteAtom(at) == 0 && FindAtomW(W("MyAtom")) == at && DeleteAtom(at) == 0 && FindAtomW(W("MyAtom")) == 0);
    ATOM ga = GlobalAddAtomW(W("GA")); CHECK(ga >= 0xC000 && FindAtomW(W("GA")) == 0 && GlobalFindAtomW(W("ga")) == ga && GlobalDeleteAtom(ga) == 0);

    uint64_t rargs[2] = { 0x11, 0x22 };
    PVOID veh = AddVectoredExceptionHandler(1, my_veh);
    CHECK(veh);
    RaiseException(0xE0000001u, 0, 2, rargs);                    /* VEH が CONTINUE_EXECUTION → 復帰 */
    CHECK(g_veh_calls == 1);
    RaiseException(0x406D1388u, 0, 0, NULL);                      /* スレッド命名例外は無害 */
    CHECK(g_veh_calls == 1);
    CHECK(RemoveVectoredExceptionHandler(veh) == 1 && RemoveVectoredExceptionHandler(veh) == 0);
    CHECK(SetUnhandledExceptionFilter((LPTOP_LEVEL_EXCEPTION_FILTER)my_veh) == NULL);
    RaiseException(0xE0000001u, 0, 2, rargs);                    /* UEF 経由でも継続 */
    SetUnhandledExceptionFilter(NULL);
    uint8_t ctx[1232]; memset(ctx, 0xFF, sizeof ctx); RtlCaptureContext(ctx);
    CHECK(ctx[0] == 0 && ctx[1231] == 0);
    DWORD64 base = 123; CHECK(RtlLookupFunctionEntry(0x1000, &base, NULL) == NULL && base == 0);
    CHECK(RtlPcToFileHeader((PVOID)0x20010, (PVOID*)&mx) != NULL);
    EXCEPTION_RECORD64 er; memset(&er, 0, sizeof er); er.ExceptionCode = 0xC0000005; er.NumberParameters = 1;
    EXCEPTION_POINTERS64 ep = { (uint64_t)(uintptr_t)&er, (uint64_t)(uintptr_t)ctx };
    CHECK(UnhandledExceptionFilter(&ep) == EXCEPTION_EXECUTE_HANDLER);
    CHECK(sizeof(EXCEPTION_RECORD64) == 152);
    _lock(3); _lock(3); _unlock(3); _unlock(3); _lock_file(stdout); _unlock_file(stdout);

    DWORD cf2 = 77;
    CHECK(InternetGetConnectedState(&cf2, 0) == FALSE && cf2 == 0);
    CHECK(InternetOpenW(W("ua"), 0, NULL, NULL, 0) == NULL && GetLastError() == ERROR_INTERNET_DISCONNECTED);
    uint8_t wsad[400] = {0};
    CHECK(WSAStartup(0x0202, wsad) == 10091);
    CHECK(WinVerifyTrust(0, NULL, NULL) == (LONG)TRUST_E_NOSIGNATURE);
    shimx_set_trust_ok(1); CHECK(WinVerifyTrust(0, NULL, NULL) == 0); shimx_set_trust_ok(0);
    HANDLE en = 0; CHECK(WNetOpenEnumW(2, 1, 0, NULL, &en) == ERROR_NO_NETWORK);
    CHECK(midiInGetNumDevs() == 0 && midiOutGetNumDevs() == 0 && midiOutOpen(&en, 0, 0, 0, 0) == 2);
    DWORD acmc = 5;
    CHECK(acmMetrics(0, 1, &acmc) == 0 && acmDriverOpen(&en, 0, 0) == 6);
}

void run_sys_tests(void) {
    test_strings();
    test_registry();
    test_files();
    test_time();
    test_memory();
    test_process_module();
}
