/* probe.c — FL エンジン (Delphi TRegistry ラッパ) と同じ呼出パターンで vreg を叩く検証用ヘルパ。テスト/e2e 専用 (本番リンク不要)。
 * 呼出パターンの根拠: tools/startup/work/eng_reg1.c (FUN_005af120 Create / 005af3d0 SetRoot / 005af7c0 OpenKeyRO / 005b03a0 ReadStrCur)
 *   - ルート = 0xffffffff80000001(HKCU) / ...02(HKLM) を HKEY として設定。OpenKey は RegOpenKeyExW(root, path, 0, 0xf003f|WOW64bit)
 *   - ReadString: RegQueryValueExW(NULL data) で長さ取得 → 本取得。ReadInt/ReadBool: 値は REG_SZ 文字列 ("123"/"0"/"1") を数値化
 *     (startup REPORT §3: 「全て REG_SZ 文字列; 例外は OS の CurrentMajor/MinorVersionNumber DWORD」)。REG_DWORD も許容する。
 * 全 API は UTF-8 入出力。戻り値: Win32 エラーコード (0=成功)。
 */
#include "shimx_internal.h"
#include "vreg.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static HKEY root_of(const char* h) {
    if (!strcmp(h, "HKCU")) return HKEY_CURRENT_USER;
    if (!strcmp(h, "HKLM")) return HKEY_LOCAL_MACHINE;
    if (!strcmp(h, "HKCR")) return HKEY_CLASSES_ROOT;
    if (!strcmp(h, "HKU")) return (HKEY)0x80000003u;
    return NULL;
}
static WCHAR* w8(const char* s) { return shx_wcsdup_utf8(s); }
static LSTATUS open_key(const char* hive, const char* key, int create, REGSAM sam, HKEY* out) {
    HKEY r = root_of(hive);
    if (!r) return ERROR_INVALID_PARAMETER;
    WCHAR* wk = w8(key);
    LSTATUS st = create ? RegCreateKeyExW(r, wk, 0, NULL, 0, sam, NULL, out, NULL) : RegOpenKeyExW(r, wk, 0, sam, out);
    free(wk);
    return st;
}
#define SAM_RO 0x20019u
#define SAM_RW 0xF003Fu

int vreg_probe_key_exists(const char* hive, const char* key) {
    HKEY k; if (open_key(hive, key, 0, SAM_RO, &k)) return 0;
    RegCloseKey(k); return 1;
}
int vreg_probe_value_exists(const char* hive, const char* key, const char* name) {
    HKEY k; if (open_key(hive, key, 0, SAM_RO, &k)) return 0;
    WCHAR* wn = w8(name); DWORD cb = 0, ty = 0;
    LSTATUS st = RegQueryValueExW(k, wn, NULL, &ty, NULL, &cb);
    free(wn); RegCloseKey(k);
    return st == ERROR_SUCCESS;
}
/* ReadString: out に UTF-8。type は REG_DWORD なら 10 進文字列化 */
int vreg_probe_read_str(const char* hive, const char* key, const char* name, char* out, int cap, unsigned* type_out) {
    HKEY k; LSTATUS st = open_key(hive, key, 0, SAM_RO, &k);
    if (st) return (int)st;
    WCHAR* wn = w8(name); DWORD cb = 0, ty = 0;
    st = RegQueryValueExW(k, wn, NULL, &ty, NULL, &cb);
    if (st == ERROR_SUCCESS) {
        BYTE* buf = (BYTE*)calloc(cb + 4, 1); DWORD got = cb;
        st = RegQueryValueExW(k, wn, NULL, &ty, buf, &got);
        if (st == ERROR_SUCCESS) {
            if (type_out) *type_out = ty;
            if (ty == REG_DWORD && got == 4) snprintf(out, (size_t)cap, "%u", *(DWORD*)buf);
            else if (ty == REG_SZ || ty == REG_EXPAND_SZ) {
                ((WCHAR*)buf)[got / 2] = 0;
                if (shimx_utf16_to_utf8((WCHAR*)buf, -1, out, (size_t)cap) < 0) st = ERROR_MORE_DATA;
            } else st = 1630u;
        }
        free(buf);
    }
    free(wn); RegCloseKey(k);
    return (int)st;
}
long vreg_probe_read_int(const char* hive, const char* key, const char* name, long def) {
    char b[64]; unsigned ty = 0;
    if (vreg_probe_read_str(hive, key, name, b, sizeof b, &ty) != 0) return def;
    char* e; if (!*b) return def;
    long v = strtol(b, &e, 10);
    return (e == b) ? def : v;
}
int vreg_probe_read_bool(const char* hive, const char* key, const char* name, int def) {
    return vreg_probe_read_int(hive, key, name, def) != 0;
}
int vreg_probe_write_str(const char* hive, const char* key, const char* name, const char* val) {
    HKEY k; LSTATUS st = open_key(hive, key, 1, SAM_RW, &k);
    if (st) return (int)st;
    WCHAR* wn = w8(name); WCHAR* wv = w8(val);
    st = RegSetValueExW(k, wn, 0, REG_SZ, (const BYTE*)wv, (DWORD)(shx_wstr_len(wv) + 1) * 2);
    free(wn); free(wv); RegCloseKey(k);
    return (int)st;
}
int vreg_probe_write_int(const char* hive, const char* key, const char* name, long v) {
    char b[32]; snprintf(b, sizeof b, "%ld", v);
    return vreg_probe_write_str(hive, key, name, b);
}
int vreg_probe_write_dword(const char* hive, const char* key, const char* name, unsigned v) {
    HKEY k; LSTATUS st = open_key(hive, key, 1, SAM_RW, &k);
    if (st) return (int)st;
    WCHAR* wn = w8(name);
    st = RegSetValueExW(k, wn, 0, REG_DWORD, (const BYTE*)&v, 4);
    free(wn); RegCloseKey(k);
    return (int)st;
}
int vreg_probe_delete_value(const char* hive, const char* key, const char* name) {
    HKEY k; LSTATUS st = open_key(hive, key, 0, SAM_RW, &k);
    if (st) return (int)st;
    WCHAR* wn = w8(name); st = RegDeleteValueW(k, wn); free(wn); RegCloseKey(k);
    return (int)st;
}
int vreg_probe_create_key(const char* hive, const char* key) {
    HKEY k; LSTATUS st = open_key(hive, key, 1, SAM_RW, &k);
    if (!st) RegCloseKey(k);
    return (int)st;
}
int vreg_probe_delete_key(const char* hive, const char* key) {
    HKEY r = root_of(hive); if (!r) return ERROR_INVALID_PARAMETER;
    WCHAR* wk = w8(key); LSTATUS st = RegDeleteKeyW(r, wk); free(wk);
    return (int)st;
}
/* サブキー名 (kind=0) / 値名 (kind=1) を '\n' 区切りで列挙 */
int vreg_probe_enum(const char* hive, const char* key, int kind, char* out, int cap) {
    HKEY k; LSTATUS st = open_key(hive, key, 0, SAM_RO, &k);
    if (st) return (int)st;
    int n = 0; out[0] = 0;
    for (DWORD i = 0;; i++) {
        WCHAR nm[512]; DWORD cch = 512;
        st = kind ? RegEnumValueW(k, i, nm, &cch, NULL, NULL, NULL, NULL) : RegEnumKeyExW(k, i, nm, &cch, NULL, NULL, NULL, NULL);
        if (st == ERROR_NO_MORE_ITEMS) { st = 0; break; }
        if (st) break;
        char u[2048]; if (shimx_utf16_to_utf8(nm, -1, u, sizeof u) < 0) continue;
        int l = (int)strlen(u);
        if (n + l + 2 > cap) { st = ERROR_MORE_DATA; break; }
        memcpy(out + n, u, (size_t)l); n += l; out[n++] = '\n'; out[n] = 0;
    }
    RegCloseKey(k);
    return (int)st;
}
