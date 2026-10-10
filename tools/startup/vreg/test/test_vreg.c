/* vreg C 単体テスト。 node で実行し "ALL PASS" で exit 0。 */
#include "../../../shimx/test/test_common.h"
#include "../src/vreg.h"

static int g_notified; static uint32_t g_last_gen;
static void on_notify(uint32_t g) { g_notified++; g_last_gen = g; }

static void t_flstyle(void) {
    char b[256]; unsigned ty;
    /* FL(Delphi TRegistry)は Int/Bool も REG_SZ 文字列で保存 → ReadInt は文字列→数値変換 */
    CHECK(vreg_probe_write_str("HKCU", "Software\\Image-Line\\FL Studio 26\\General", "Run counter", "123") == 0);
    CHECK(vreg_probe_read_int("HKCU", "Software\\Image-Line\\FL Studio 26\\General", "Run counter", -1) == 123);
    CHECK(vreg_probe_read_str("HKCU", "Software\\Image-Line\\FL Studio 26\\General", "Run counter", b, sizeof b, &ty) == 0 && ty == REG_SZ && !strcmp(b, "123"));
    CHECK(vreg_probe_write_int("HKCU", "Software\\Image-Line\\FL Studio 26\\General", "Fullscreen", 1) == 0);
    CHECK(vreg_probe_read_bool("HKCU", "Software\\Image-Line\\FL Studio 26\\General", "Fullscreen", 0) == 1);
    CHECK(vreg_probe_read_int("HKCU", "Software\\Image-Line\\FL Studio 26\\General", "NoSuchValue", 44100) == 44100);   /* 既定 */
    CHECK(vreg_probe_write_str("HKCU", "Software\\Image-Line\\FL Studio 26\\General", "Empty", "") == 0);
    CHECK(vreg_probe_read_int("HKCU", "Software\\Image-Line\\FL Studio 26\\General", "Empty", 7) == 7);                 /* 空文字 → 既定 */
    CHECK(vreg_probe_write_str("HKCU", "Software\\Image-Line\\FL Studio 26\\General", "Junk", "abc") == 0);
    CHECK(vreg_probe_read_int("HKCU", "Software\\Image-Line\\FL Studio 26\\General", "Junk", 9) == 9);                  /* 非数 → 既定 */
    /* OS キーだけ DWORD */
    CHECK(vreg_probe_write_dword("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion", "CurrentMajorVersionNumber", 10) == 0);
    CHECK(vreg_probe_read_int("HKLM", "software\\microsoft\\windows nt\\currentversion", "CurrentMajorVersionNumber", 0) == 10);   /* 大小無視 */
    CHECK(vreg_probe_read_str("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion", "CurrentMajorVersionNumber", b, sizeof b, &ty) == 0 && ty == REG_DWORD && !strcmp(b, "10"));
    /* 日本語名 */
    CHECK(vreg_probe_write_str("HKCU", "Software\\テスト\\キー", "名前", "値あ") == 0);
    CHECK(vreg_probe_read_str("HKCU", "Software\\テスト\\キー", "名前", b, sizeof b, &ty) == 0 && !strcmp(b, "値あ"));
}

static void t_enum_morefit(void) {
    HKEY k; WCHAR nm[4]; DWORD n = 2;
    CHECK(RegCreateKeyExW(HKEY_CURRENT_USER, W("Software\\EnumT\\longname_key"), 0, NULL, 0, KEY_ALL_ACCESS, NULL, &k, NULL) == 0);
    RegCloseKey(k);
    CHECK(RegOpenKeyExW(HKEY_CURRENT_USER, W("Software\\EnumT"), 0, KEY_READ, &k) == 0);
    CHECK(RegEnumKeyExW(k, 0, nm, &n, NULL, NULL, NULL, NULL) == ERROR_MORE_DATA && n == 12);       /* 必要長 (NUL 除く) を返す */
    CHECK(RegEnumKeyW(k, 0, nm, 4) == ERROR_MORE_DATA);
    WCHAR big[64]; CHECK(RegEnumKeyW(k, 0, big, 64) == 0 && wstr_eq(big, "longname_key"));
    RegCloseKey(k);
}

static void t_generation(void) {
    vreg_set_notify(on_notify);
    uint32_t g0 = vreg_generation(); g_notified = 0;
    CHECK(vreg_probe_write_str("HKCU", "Software\\GenT", "a", "1") == 0);   /* key 作成 + 値設定 */
    CHECK(vreg_generation() > g0 && g_notified >= 1 && g_last_gen == vreg_generation());
    uint32_t g1 = vreg_generation(); int n1 = g_notified;
    char b[16]; unsigned ty;
    CHECK(vreg_probe_read_str("HKCU", "Software\\GenT", "a", b, sizeof b, &ty) == 0);          /* 読み取りは世代を進めない */
    CHECK(vreg_generation() == g1 && g_notified == n1);
    CHECK(vreg_probe_delete_value("HKCU", "Software\\GenT", "a") == 0 && vreg_generation() > g1);
    CHECK(vreg_probe_delete_value("HKCU", "Software\\GenT", "a") != 0);                         /* 失敗は通知しない */
    vreg_set_notify(NULL);
}

static void t_import_export(void) {
    /* UTF-8 BOM / 値削除 / キー削除 / hex(7) / @ */
    const char* txt =
        "\xEF\xBB\xBFWindows Registry Editor Version 5.00\r\n\r\n"
        "[HKEY_CURRENT_USER\\Software\\ImpT]\r\n"
        "@=\"default\"\r\n\"s\"=\"a\\\\b\\\"c\"\r\n\"d\"=dword:0000002a\r\n\"q\"=hex(b):01,00,00,00,00,00,00,00\r\n"
        "\"m\"=hex(7):61,00,00,00,62,00,00,00,00,00\r\n\"gone\"=\"x\"\r\n\r\n"
        "[HKEY_CURRENT_USER\\Software\\ImpT\\Sub]\r\n\"x\"=\"1\"\r\n\r\n"
        "[HKEY_CURRENT_USER\\Software\\ImpT]\r\n\"gone\"=-\r\n";
    CHECK(shimx_reg_import_text(txt) >= 6);
    char b[64]; unsigned ty;
    CHECK(vreg_probe_read_str("HKCU", "Software\\ImpT", "s", b, sizeof b, &ty) == 0 && !strcmp(b, "a\\b\"c"));
    CHECK(vreg_probe_read_int("HKCU", "Software\\ImpT", "d", 0) == 42);
    CHECK(vreg_probe_value_exists("HKCU", "Software\\ImpT", "gone") == 0);                     /* "name"=- */
    HKEY k; DWORD cb = 0;
    CHECK(RegOpenKeyExW(HKEY_CURRENT_USER, W("Software\\ImpT"), 0, KEY_READ, &k) == 0);
    CHECK(RegQueryValueExW(k, W("m"), NULL, &ty, NULL, &cb) == 0 && ty == REG_MULTI_SZ && cb == 10);
    CHECK(RegQueryValueExW(k, W("q"), NULL, &ty, NULL, &cb) == 0 && ty == REG_QWORD && cb == 8);
    CHECK(RegQueryValueExW(k, NULL, NULL, &ty, NULL, &cb) == 0 && cb == 16);                    /* 既定値 */
    RegCloseKey(k);
    /* export_root → clear → import で完全復元 */
    char* ex = vreg_export_root(1);
    CHECK(ex && strstr(ex, "[HKEY_CURRENT_USER\\Software\\ImpT\\Sub]") && !strstr(ex, "HKEY_LOCAL_MACHINE"));
    vreg_clear_root(1);
    CHECK(!vreg_probe_key_exists("HKCU", "Software\\ImpT"));
    CHECK(shimx_reg_import_text(ex) > 0);
    free(ex);
    CHECK(vreg_probe_read_str("HKCU", "Software\\ImpT\\Sub", "x", b, sizeof b, &ty) == 0 && !strcmp(b, "1"));
    CHECK(vreg_probe_read_str("HKCU", "Software\\ImpT", "s", b, sizeof b, &ty) == 0 && !strcmp(b, "a\\b\"c"));
    /* [-key] */
    CHECK(shimx_reg_import_text("[-HKEY_CURRENT_USER\\Software\\ImpT]\n") >= 1);
    CHECK(!vreg_probe_key_exists("HKCU", "Software\\ImpT") && !vreg_probe_key_exists("HKCU", "Software\\ImpT\\Sub"));
}

static void t_newapis(void) {
    HKEY k; DWORD ty, cb; char a[32]; DWORD d = 5;
    CHECK(RegSetKeyValueW(HKEY_CURRENT_USER, W("Software\\NewApi\\A"), W("n"), REG_DWORD, &d, 4) == 0);
    CHECK(RegSetKeyValueW(HKEY_CURRENT_USER, W("Software\\NewApi\\B"), W("s"), REG_SZ, W("zz"), 6) == 0);
    cb = sizeof a; CHECK(RegGetValueA(HKEY_CURRENT_USER, "Software\\NewApi\\B", "s", RRF_RT_REG_SZ, &ty, a, &cb) == 0 && !strcmp(a, "zz"));
    cb = 4; CHECK(RegGetValueA(HKEY_CURRENT_USER, "Software\\NewApi\\A", "n", RRF_RT_REG_SZ, &ty, a, &cb) == 1630);
    CHECK(RegDeleteKeyValueW(HKEY_CURRENT_USER, W("Software\\NewApi\\B"), W("s")) == 0);
    CHECK(vreg_probe_value_exists("HKCU", "Software\\NewApi\\B", "s") == 0);
    CHECK(RegOpenKeyExW(HKEY_CURRENT_USER, W("Software\\NewApi"), 0, KEY_ALL_ACCESS, &k) == 0);
    CHECK(RegDeleteKeyW(HKEY_CURRENT_USER, W("Software\\NewApi")) == ERROR_ACCESS_DENIED);       /* 子あり */
    CHECK(RegDeleteTreeW(HKEY_CURRENT_USER, W("Software\\NewApi\\A")) == 0);
    CHECK(!vreg_probe_key_exists("HKCU", "Software\\NewApi\\A"));
    CHECK(RegDeleteTreeW(k, NULL) == 0);                                                        /* 配下全消去 (k は残る) */
    DWORD ns = 9; CHECK(RegQueryInfoKeyW(k, NULL, NULL, NULL, &ns, NULL, NULL, NULL, NULL, NULL, NULL, NULL) == 0 && ns == 0);
    RegCloseKey(k);
    CHECK(RegDeleteTreeW(HKEY_CURRENT_USER, W("Software\\NewApi")) == 0 && !vreg_probe_key_exists("HKCU", "Software\\NewApi"));
    CHECK(RegDeleteTreeW(HKEY_CURRENT_USER, W("Software\\NewApi")) == ERROR_FILE_NOT_FOUND);
}

static void t_enum_probe(void) {
    char out[256];
    vreg_probe_write_str("HKCU", "Software\\Image-Line\\Registrations\\FL Studio 26.1", "ILRegKey", "x");
    vreg_probe_create_key("HKCU", "Software\\Image-Line\\Registrations\\Token");
    CHECK(vreg_probe_enum("HKCU", "Software\\Image-Line\\Registrations", 0, out, sizeof out) == 0);
    CHECK(!strcmp(out, "FL Studio 26.1\nToken\n"));            /* FUN_008e6150: "FL Studio " 前方一致サブキー列挙に使われる */
    CHECK(vreg_probe_enum("HKCU", "Software\\Image-Line\\Registrations\\FL Studio 26.1", 1, out, sizeof out) == 0 && !strcmp(out, "ILRegKey\n"));
}

int main(void) {
    shimx_init();
    t_flstyle(); fprintf(stderr, "[vreg-test] flstyle OK\n");
    t_enum_morefit(); fprintf(stderr, "[vreg-test] enum OK\n");
    t_generation(); fprintf(stderr, "[vreg-test] generation OK\n");
    t_import_export(); fprintf(stderr, "[vreg-test] import/export OK\n");
    t_newapis(); fprintf(stderr, "[vreg-test] newapis OK\n");
    t_enum_probe(); fprintf(stderr, "[vreg-test] enum-probe OK\n");
    printf("[vreg-test] ALL PASS\n");
    return 0;
}
