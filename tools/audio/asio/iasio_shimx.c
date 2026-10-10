/* iasio_shimx.c — shimx 結合 (tools/shimx のメモリレジストリ + Reg* API を使用)。
 * 有効化: ビルドに shimx の実装 (src の .c または work/obj_MT の .o) を含め -DFLASIO_COM_SHIMX=1 とし、
 * 実行時に iasio_shimx_register() を 1 度呼ぶ。以後 iasio_enum_asio_drivers() は shimx のレジストリ
 * (lifted FLEngine が advapi32 Reg* 経由で読むものと同一実体) を読む。
 *
 * 注意: shimx.h は include しない (tools/shimx は本タスクでは読取専用で、作業中のツリー変更に
 * 影響されないよう必要最小限の宣言をここに置く — コミット済 shimx.h の typedef/値と同一)。
 * CoCreateInstance のフォワード入口は iasio_co_create_instance() (shimx ole.c 側の 1 行改変は
 * shimx 担当 — 入口提供のみ)。 */
#include "iasio.h"

#ifdef FLASIO_COM_SHIMX

#include <stdio.h>
#include <string.h>

/* ---- 最小 Win32 型 (shimx.h コミット済定義と同一のサイズ/値) ---- */
typedef uint32_t shx_ulong_ptr;          /* ULONG_PTR (wasm32 = 4B) */
typedef shx_ulong_ptr shx_handle;
typedef shx_handle shx_hkey;
typedef uint32_t shx_dword;
typedef int32_t  shx_long;
typedef shx_long shx_lstatus;
typedef shx_dword shx_regsam;
typedef unsigned char shx_byte;
typedef char *shx_lpstr;
typedef const char *shx_lpcstr;
typedef shx_dword *shx_lpdword;
typedef struct { shx_dword lo, hi; } shx_filetime;

#define SHX_ERROR_SUCCESS     0u
#define SHX_REG_SZ            1u
#define SHX_KEY_READ          0x20019u
#define SHX_HKEY_LOCAL_MACHINE ((shx_hkey)0x80000002u)

extern shx_lstatus RegOpenKeyExA(shx_hkey k, shx_lpcstr sub, shx_dword opt, shx_regsam sam, shx_hkey *out);
extern shx_lstatus RegEnumKeyExA(shx_hkey k, shx_dword idx, shx_lpstr name, shx_lpdword cch, shx_lpdword rsv,
                                 shx_lpstr cls, shx_lpdword cchCls, shx_filetime *lastWrite);
extern shx_lstatus RegQueryValueExA(shx_hkey k, shx_lpcstr name, shx_lpdword rsv, shx_lpdword type,
                                    shx_byte *data, shx_lpdword cb);
extern shx_lstatus RegCloseKey(shx_hkey k);
extern shx_lstatus RegDeleteKeyA(shx_hkey k, shx_lpcstr sub);
extern int shimx_reg_set_sz(const char *path, const char *name, const char *utf8);

static int sx_open(const char *path, uint32_t *hkey) {
    /* iasio パス形式 "HKLM\software\asio\..." → RegOpenKeyExA(ルート, 副パス)。
     * shimx は大小無視なので実測どおり小文字 "software\asio" のまま渡す。 */
    static const struct { const char *root; shx_hkey k; } roots[] = {
        { "HKEY_CLASSES_ROOT", (shx_hkey)0x80000000u }, { "HKCR", (shx_hkey)0x80000000u },
        { "HKEY_CURRENT_USER", (shx_hkey)0x80000001u }, { "HKCU", (shx_hkey)0x80000001u },
        { "HKEY_LOCAL_MACHINE", (shx_hkey)0x80000002u }, { "HKLM", (shx_hkey)0x80000002u },
    };
    char sub[160];
    for (unsigned i = 0; i < sizeof roots / sizeof roots[0]; i++) {
        size_t rl = strlen(roots[i].root);
        if (strncasecmp(path, roots[i].root, rl) == 0 && (path[rl] == '\\' || !path[rl])) {
            const char *rest = path + rl;
            while (*rest == '\\') rest++;
            snprintf(sub, sizeof sub, "%s", rest);
            for (char *q = sub; *q; q++) if (*q == '/') *q = '\\';
            shx_hkey hk = 0;
            if (RegOpenKeyExA(roots[i].k, sub[0] ? sub : "\\", 0, SHX_KEY_READ, &hk) != (shx_lstatus)SHX_ERROR_SUCCESS) return -1;
            if (hkey) *hkey = (uint32_t)hk;
            return 0;
        }
    }
    return -1;
}

static int sx_enum(uint32_t hk, uint32_t idx, char *name, uint32_t cap) {
    char buf[64]; shx_dword cch = sizeof buf;
    shx_lstatus r = RegEnumKeyExA((shx_hkey)hk, idx, buf, &cch, NULL, NULL, NULL, NULL);
    if (r != (shx_lstatus)SHX_ERROR_SUCCESS) return -1;
    snprintf(name, cap, "%.*s", (int)cch, buf);
    return 0;
}

static int sx_query(uint32_t hk, const char *name, char *out, uint32_t cap) {
    shx_dword type = 0, cb = cap;
    shx_lstatus r = RegQueryValueExA((shx_hkey)hk, name, NULL, &type, (shx_byte *)out, &cb);
    if (r != (shx_lstatus)SHX_ERROR_SUCCESS || type != SHX_REG_SZ) return -1;
    out[cap - 1] = 0;
    return 0;
}

static void sx_close(uint32_t hk) { if (hk) RegCloseKey((shx_hkey)hk); }

/* shimx レジストリへの登録 (ILWASAPI2ASIO DllRegisterServer 相当の実体)。 */
int iasio_shimx_register(void) {
    static const iasio_reg_backend_t b = { sx_open, sx_enum, sx_query, sx_close };
    if (shimx_reg_set_sz("HKLM\\software\\asio\\FL Studio ASIO", "clsid", "{188135E1-7171-3434-854F-01A3C71F3DF9}") != 0 ||
        shimx_reg_set_sz("HKLM\\software\\asio\\FL Studio ASIO", "", "FL Studio ASIO") != 0 ||
        shimx_reg_set_sz("HKLM\\SOFTWARE\\Classes\\CLSID\\{188135E1-7171-3434-854F-01A3C71F3DF9}", "", "FL Studio ASIO") != 0 ||
        shimx_reg_set_sz("HKLM\\SOFTWARE\\Classes\\CLSID\\{188135E1-7171-3434-854F-01A3C71F3DF9}\\InprocServer32", "", "ILWASAPI2ASIO_x64.dll") != 0)
        return -1;
    iasio_reg_set_backend(&b);
    return 0;
}

void iasio_shimx_unregister(void) {
    RegDeleteKeyA(SHX_HKEY_LOCAL_MACHINE, "software\\asio\\FL Studio ASIO");
    RegDeleteKeyA(SHX_HKEY_LOCAL_MACHINE, "SOFTWARE\\Classes\\CLSID\\{188135E1-7171-3434-854F-01A3C71F3DF9}\\InprocServer32");
    RegDeleteKeyA(SHX_HKEY_LOCAL_MACHINE, "SOFTWARE\\Classes\\CLSID\\{188135E1-7171-3434-854F-01A3C71F3DF9}");
    iasio_reg_set_backend(NULL);
}

#endif /* FLASIO_COM_SHIMX */
