/* モジュール表 / LoadLibrary / GetProcAddress / リソース / IMAGEHLP。
 *
 * 実体のロード (wasm モジュール連結) は tools/hostbridge の領分。ここは「口」だけを提供する:
 *   shimx_module_register()   — 既存モジュール (FLEngine 等) を名前+base で登録
 *   shimx_proc_register()     — モジュール内の関数を名前/序数で登録
 *   shimx_set_load_hook()     — LoadLibrary 時に未知名を解決する外部フック
 *   shimx_set_proc_resolver() — GetProcAddress の外部フック
 *   shimx_set_resource_provider() — FindResource/LoadResource の実体
 * 組込み: システム DLL 名 (kernel32 等) は擬似モジュール (最小 PE ヘッダ付き 4KB 画像) として扱い、
 *   GetProcAddress は shim が実装済みの API (生成表 proctable.c) を返す。
 */
#include "shimx_internal.h"
#include <strings.h>
#include <ctype.h>

typedef struct { const char* dll; const char* name; void* fn; } ShxProcEnt;
extern const ShxProcEnt shx_proctable[];
extern const int shx_proctable_n;

typedef struct ProcReg { char* name; DWORD ordinal; void* fn; struct ProcReg* next; } ProcReg;
typedef struct ShxMod {
    char* name; char* path; HMODULE base; size_t size; int refs; int builtin;
    ProcReg* procs; struct ShxMod* next;
} ShxMod;

static ShxMod* g_mods;
static ShxMod* g_exe;
static shx_mutex_t g_mod_lk;
static int g_strict;
static int g_pseudo_load;       /* R4: 未知 DLL を擬似モジュールとして登録するか */
static void* (*g_resolver)(HMODULE, const char*, DWORD);
static HMODULE (*g_load_hook)(const char*, DWORD);
static const void* (*g_res_provider)(HMODULE, const WCHAR*, const WCHAR*, DWORD*);

/* R3: 序数直指定 GetProcAddress の組込み表 (手書き)。名前表 (proctable.c, 自動生成) は序数を扱えないため別表。
 * 序数 → 名前の対応は Windows 10/11 の shell32.dll エクスポート表 (implib 定義 + wine shell32.spec と突合済み)。
 * SHX-T8 (#175): shell32 74 = SHCreateStdEnumFmtEtc / shlwapi 12 = SHCreateMemStream / 219 = QISearch も実装済み (src/shord.c)。
 * 根拠: tools/shimx/REPORT.md §15。 */
typedef struct { const char* dll; DWORD ord; void* fn; } ShxOrdEnt;
static const ShxOrdEnt shx_ordtable[] = {
    { "shell32.dll",  16, (void*)ILFindLastID },
    { "shell32.dll",  17, (void*)ILRemoveLastID },
    { "shell32.dll",  18, (void*)ILClone },
    { "shell32.dll",  19, (void*)ILCloneFirst },
    { "shell32.dll",  21, (void*)ILIsEqual },
    { "shell32.dll",  25, (void*)ILCombine },
    { "shell32.dll", 152, (void*)ILGetSize },
    { "shell32.dll", 153, (void*)ILGetNext },
    { "shell32.dll", 155, (void*)ILFree },
    { "shell32.dll", 190, (void*)ILCreateFromPathW },
    { "shell32.dll",  74, (void*)SHCreateStdEnumFmtEtc },
    { "shlwapi.dll",  12, (void*)SHCreateMemStream },
    { "shlwapi.dll", 219, (void*)QISearch },
};

void shimx_set_strict(int on) { g_strict = on; }
int shx_strict_mode(void) { return g_strict; }
void shimx_set_pseudo_load(int on) { g_pseudo_load = on; }
void shimx_set_proc_resolver(void* (*fn)(HMODULE, const char*, DWORD)) { g_resolver = fn; }
void shimx_set_load_hook(HMODULE (*fn)(const char*, DWORD)) { g_load_hook = fn; }
void shimx_set_resource_provider(const void* (*fn)(HMODULE, const WCHAR*, const WCHAR*, DWORD*)) { g_res_provider = fn; }

static void* fake_image(uint64_t imageBase, int isDll) {
    uint8_t* p = NULL;
    if (posix_memalign((void**)&p, 4096, 4096) != 0 || !p) return NULL;
    memset(p, 0, 4096);
    *(uint16_t*)p = 0x5A4D;                       /* MZ */
    *(uint32_t*)(p + 0x3C) = 0x80;                /* e_lfanew */
    uint8_t* nt = p + 0x80;
    *(uint32_t*)nt = 0x4550;                      /* PE\0\0 */
    uint8_t* fh = nt + 4;
    *(uint16_t*)(fh + 0) = 0x8664;                /* AMD64 */
    *(uint16_t*)(fh + 2) = 0;                     /* sections */
    *(uint16_t*)(fh + 16) = 0xF0;                 /* SizeOfOptionalHeader */
    *(uint16_t*)(fh + 18) = isDll ? 0x2022 : 0x0022;
    uint8_t* oh = fh + 20;
    *(uint16_t*)oh = 0x20B;                       /* PE32+ */
    *(uint64_t*)(oh + 24) = imageBase;
    *(uint32_t*)(oh + 32) = 0x1000;               /* SectionAlignment */
    *(uint32_t*)(oh + 36) = 0x200;                /* FileAlignment */
    *(uint32_t*)(oh + 56) = 0x1000;               /* SizeOfImage */
    *(uint32_t*)(oh + 60) = 0x400;                /* SizeOfHeaders */
    *(uint16_t*)(oh + 68) = isDll ? 3 : 2;        /* Subsystem */
    *(uint32_t*)(oh + 108) = 16;                  /* NumberOfRvaAndSizes */
    return p;
}

static void base_name(const char* in, char* out, size_t sz) {
    const char* b = in;
    for (const char* p = in; *p; p++) if (*p == '\\' || *p == '/') b = p + 1;
    size_t n = strlen(b);
    if (n >= sz - 5) n = sz - 6;
    for (size_t i = 0; i < n; i++) out[i] = (char)tolower((unsigned char)b[i]);
    out[n] = 0;
    if (!strchr(out, '.')) strcat(out, ".dll");
}

static int is_system_dll(const char* n) {
    static const char* const k[] = {
        "kernel32.dll","kernelbase.dll","ntdll.dll","user32.dll","gdi32.dll","advapi32.dll","ole32.dll","oleaut32.dll",
        "shell32.dll","shlwapi.dll","comctl32.dll","comdlg32.dll","winmm.dll","version.dll","ws2_32.dll","wininet.dll",
        "psapi.dll","dbghelp.dll","imagehlp.dll","winspool.drv","msacm32.dll","mpr.dll","crypt32.dll","wintrust.dll",
        "opengl32.dll","dsound.dll","dwmapi.dll","uxtheme.dll","imm32.dll","shcore.dll","rpcrt4.dll","propsys.dll",
        "windowscodecs.dll","wtsapi32.dll","msimg32.dll","setupapi.dll","netapi32.dll","iphlpapi.dll","ucrtbase.dll",
        "msvcrt.dll","oleacc.dll","shfolder.dll","gdiplus.dll","secur32.dll","bcrypt.dll","cfgmgr32.dll","d3d11.dll","d2d1.dll","dwrite.dll",
    };
    for (size_t i = 0; i < sizeof k / sizeof k[0]; i++) if (!strcmp(n, k[i])) return 1;
    return !strncmp(n, "api-ms-win-", 11) || !strncmp(n, "ext-ms-", 7);
}

static ShxMod* mod_find_locked(const char* bn) {
    for (ShxMod* m = g_mods; m; m = m->next) if (!strcmp(m->name, bn)) return m;
    return NULL;
}
static ShxMod* mod_by_base_locked(HMODULE h) {
    for (ShxMod* m = g_mods; m; m = m->next) if (m->base == h) return m;
    return NULL;
}
/* 内部: HMODULE → モジュール名 (見つからなければ NULL)。cbtrans の lifttab resolver が DLL 別判定に使う */
const char* shx_mod_name(HMODULE h) {
    if (!h) return NULL;
    shx_mutex_lock(&g_mod_lk);
    ShxMod* m = mod_by_base_locked(h);
    const char* r = m ? m->name : NULL;
    shx_mutex_unlock(&g_mod_lk);
    return r;
}
static ShxMod* mod_add_locked(const char* name, const char* path, HMODULE base, size_t size, int builtin) {
    ShxMod* m = (ShxMod*)calloc(1, sizeof(ShxMod));
    m->name = strdup(name); m->path = strdup(path); m->base = base; m->size = size; m->refs = 1; m->builtin = builtin;
    m->next = g_mods; g_mods = m;
    return m;
}

HMODULE shimx_module_register(const char* name, HMODULE base, const char* winPath) {
    shx_ensure_init();
    char bn[256]; base_name(name, bn, sizeof bn);
    shx_mutex_lock(&g_mod_lk);
    ShxMod* m = mod_find_locked(bn);
    if (!m) {
        if (!base) base = (HMODULE)fake_image(0x180000000ull, 1);
        m = mod_add_locked(bn, winPath ? winPath : bn, base, 0x1000, 0);
    } else {
        if (base) m->base = base;
        if (winPath) { free(m->path); m->path = strdup(winPath); }
    }
    HMODULE r = m->base;
    shx_mutex_unlock(&g_mod_lk);
    return r;
}
int shimx_proc_register(HMODULE h, const char* name, DWORD ordinal, void* fn) {
    shx_mutex_lock(&g_mod_lk);
    ShxMod* m = mod_by_base_locked(h);
    if (!m) { shx_mutex_unlock(&g_mod_lk); return -1; }
    ProcReg* p = (ProcReg*)calloc(1, sizeof(ProcReg));
    p->name = name ? strdup(name) : NULL; p->ordinal = ordinal; p->fn = fn;
    p->next = m->procs; m->procs = p;
    shx_mutex_unlock(&g_mod_lk);
    return 0;
}
void shimx_set_exe_path(const char* winPath) {
    shx_ensure_init();
    char bn[256]; base_name(winPath, bn, sizeof bn);
    shx_mutex_lock(&g_mod_lk);
    if (g_exe) { free(g_exe->name); free(g_exe->path); g_exe->name = strdup(bn); g_exe->path = strdup(winPath); }
    shx_mutex_unlock(&g_mod_lk);
}
void shx_init_modules(void) {
    shx_mutex_lock(&g_mod_lk);
    g_exe = mod_add_locked("fl64.exe", "C:\\Program Files\\Image-Line\\FL Studio 2026\\FL64.exe",
                           (HMODULE)fake_image(0x140000000ull, 0), 0x1000, 0);
    shx_mutex_unlock(&g_mod_lk);
}

/* name → ShxMod* (登録済みか、システム DLL なら擬似モジュールを作る)。lock 内で呼ぶ */
static ShxMod* mod_resolve_locked(const char* utf8name, int create) {
    char bn[256]; base_name(utf8name, bn, sizeof bn);
    ShxMod* m = mod_find_locked(bn);
    if (m || !create) return m;
    if (is_system_dll(bn)) {
        char path[300]; snprintf(path, sizeof path, "C:\\Windows\\System32\\%s", bn);
        return mod_add_locked(bn, path, (HMODULE)fake_image(0x7FFB00000000ull, 1), 0x1000, 1);
    }
    return NULL;
}

HMODULE GetModuleHandleW(LPCWSTR name) {
    shx_ensure_init();
    HMODULE r = 0;
    shx_mutex_lock(&g_mod_lk);
    if (!name) r = g_exe->base;
    else {
        char u[512];
        if (shimx_utf16_to_utf8(name, -1, u, sizeof u) >= 0) { ShxMod* m = mod_resolve_locked(u, 1); if (m) r = m->base; }
    }
    shx_mutex_unlock(&g_mod_lk);
    SetLastError(r ? ERROR_SUCCESS : ERROR_MOD_NOT_FOUND);
    return r;
}
HMODULE GetModuleHandleA(LPCSTR name) {
    shx_ensure_init();
    HMODULE r = 0;
    shx_mutex_lock(&g_mod_lk);
    if (!name) r = g_exe->base;
    else { ShxMod* m = mod_resolve_locked(name, 1); if (m) r = m->base; }
    shx_mutex_unlock(&g_mod_lk);
    SetLastError(r ? ERROR_SUCCESS : ERROR_MOD_NOT_FOUND);
    return r;
}
BOOL GetModuleHandleExW(DWORD flags, LPCWSTR name, HMODULE* out) {
    shx_ensure_init();
    HMODULE r = 0;
    shx_mutex_lock(&g_mod_lk);
    if (flags & 4u /* FROM_ADDRESS */) {
        uintptr_t a = (uintptr_t)name;
        for (ShxMod* m = g_mods; m; m = m->next)
            if (a >= (uintptr_t)m->base && a < (uintptr_t)m->base + (m->size ? m->size : 1)) { r = m->base; if (!(flags & 2u)) m->refs++; break; }
        if (!r) r = g_exe->base;      /* 呼び出し元アドレス不明 (lifted コード内の関数 VA) は主モジュール扱い */
    } else if (!name) r = g_exe->base;
    else {
        char u[512];
        if (shimx_utf16_to_utf8(name, -1, u, sizeof u) >= 0) {
            ShxMod* m = mod_resolve_locked(u, 1);
            if (m) { r = m->base; if (!(flags & 2u)) m->refs++; }
        }
    }
    shx_mutex_unlock(&g_mod_lk);
    if (!r) { SetLastError(ERROR_MOD_NOT_FOUND); if (out) *out = 0; return FALSE; }
    if (out) *out = r;
    return TRUE;
}

DWORD GetModuleFileNameW(HMODULE h, LPWSTR buf, DWORD n) {
    shx_ensure_init();
    char path[512] = "";
    shx_mutex_lock(&g_mod_lk);
    ShxMod* m = h ? mod_by_base_locked(h) : g_exe;
    if (m) snprintf(path, sizeof path, "%s", m->path);
    shx_mutex_unlock(&g_mod_lk);
    if (!m) { SetLastError(ERROR_MOD_NOT_FOUND); return 0; }
    WCHAR* w = shx_wcsdup_utf8(path);
    DWORD len = (DWORD)shx_wstr_len(w), r;
    if (n == 0) r = 0;
    else if (len < n) { memcpy(buf, w, ((size_t)len + 1) * 2); r = len; SetLastError(ERROR_SUCCESS); }
    else { memcpy(buf, w, ((size_t)n - 1) * 2); buf[n - 1] = 0; r = n; SetLastError(ERROR_INSUFFICIENT_BUFFER); }
    free(w);
    return r;
}
DWORD GetModuleFileNameA(HMODULE h, LPSTR buf, DWORD n) {
    WCHAR w[600];
    DWORD len = GetModuleFileNameW(h, w, 600);
    if (!len) return 0;
    int need = WideCharToMultiByte(CP_ACP, 0, w, -1, NULL, 0, NULL, NULL);
    if (n == 0) return 0;
    if ((DWORD)need <= n) { WideCharToMultiByte(CP_ACP, 0, w, -1, buf, (int)n, NULL, NULL); return (DWORD)need - 1; }
    char* t = (char*)malloc((size_t)need);
    WideCharToMultiByte(CP_ACP, 0, w, -1, t, need, NULL, NULL);
    memcpy(buf, t, n - 1); buf[n - 1] = 0; free(t);
    SetLastError(ERROR_INSUFFICIENT_BUFFER);
    return n;
}

static HMODULE load_utf8(const char* name, DWORD flags) {
    shx_ensure_init();
    HMODULE r = 0;
    shx_mutex_lock(&g_mod_lk);
    ShxMod* m = mod_resolve_locked(name, 1);
    if (m) { m->refs++; r = m->base; }
    shx_mutex_unlock(&g_mod_lk);
    if (!r && g_load_hook) {
        r = g_load_hook(name, flags);
        if (r) {
            char bn[256]; base_name(name, bn, sizeof bn);
            shx_mutex_lock(&g_mod_lk);
            if (!mod_find_locked(bn)) mod_add_locked(bn, name, r, 0x1000, 0);
            shx_mutex_unlock(&g_mod_lk);
        }
    }
    if (!r && g_pseudo_load) {                       /* R4: 未知 DLL を擬似モジュール (最小 PE ヘッダ画像) として登録 */
        char bn[256]; base_name(name, bn, sizeof bn);
        shx_mutex_lock(&g_mod_lk);
        ShxMod* pm = mod_find_locked(bn);
        if (!pm) pm = mod_add_locked(bn, name, (HMODULE)fake_image(0x7FFB00000000ull, 1), 0x1000, 1);
        pm->refs++;
        r = pm->base;
        shx_mutex_unlock(&g_mod_lk);
        SHX_TRACE("LoadLibrary 擬似登録: %s", name);
    }
    if (!r) { SHX_TRACE("LoadLibrary 失敗: %s", name); SetLastError(ERROR_MOD_NOT_FOUND); }
    else SetLastError(ERROR_SUCCESS);
    return r;
}
HMODULE LoadLibraryExW(LPCWSTR name, HANDLE file, DWORD flags) {
    (void)file;
    char u[512];
    if (!name || shimx_utf16_to_utf8(name, -1, u, sizeof u) < 0) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    return load_utf8(u, flags);
}
HMODULE LoadLibraryW(LPCWSTR name) { return LoadLibraryExW(name, 0, 0); }
HMODULE LoadLibraryA(LPCSTR name) {
    if (!name) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    return load_utf8(name, 0);
}
BOOL FreeLibrary(HMODULE h) {
    BOOL ok = FALSE;
    shx_mutex_lock(&g_mod_lk);
    ShxMod* m = mod_by_base_locked(h);
    if (m) { if (m->refs > 0) m->refs--; ok = TRUE; }
    shx_mutex_unlock(&g_mod_lk);
    if (!ok) SetLastError(ERROR_INVALID_HANDLE);
    return ok;
}
BOOL SetDllDirectoryW(LPCWSTR p) { (void)p; return TRUE; }

void* GetProcAddress(HMODULE h, LPCSTR name) {
    shx_ensure_init();
    if (!name) { SetLastError(ERROR_INVALID_PARAMETER); return NULL; }
    int byOrd = shx_is_iptr((uintptr_t)name);            /* R1: 閾値は shimx_set_intptr_limit で変更可 (既定 0x10000) */
    DWORD ord = byOrd ? (DWORD)(uintptr_t)name : 0;
    void* fn = NULL;
    char modname[256] = "?"; int builtin = 0;
    shx_mutex_lock(&g_mod_lk);
    ShxMod* m = h ? mod_by_base_locked(h) : NULL;
    if (m) {
        snprintf(modname, sizeof modname, "%s", m->name); builtin = m->builtin;
        for (ProcReg* p = m->procs; p && !fn; p = p->next)
            if (byOrd ? (p->ordinal == ord) : (p->name && !strcmp(p->name, name))) fn = p->fn;
    }
    shx_mutex_unlock(&g_mod_lk);
    if (!m) { SetLastError(ERROR_MOD_NOT_FOUND); return NULL; }
    if (!fn && g_resolver) fn = g_resolver(h, byOrd ? NULL : name, ord);
    if (!fn && !byOrd) {
        int any = !strcmp(modname, "kernelbase.dll") || !strncmp(modname, "api-ms-win-", 11) || !strncmp(modname, "ext-ms-", 7) ||
                  !strcmp(modname, "ucrtbase.dll") || !strcmp(modname, "kernel32.dll");
        for (int i = 0; i < shx_proctable_n && !fn; i++) {
            const ShxProcEnt* e = &shx_proctable[i];
            if (strcmp(e->name, name)) continue;
            if (!strcmp(e->dll, modname) || (any && (!strcmp(e->dll, "kernel32.dll") || !strcmp(e->dll, "advapi32.dll")))) fn = e->fn;
        }
    }
    if (!fn && byOrd) {                                  /* R3: 序数直指定の組込み表 (M11 の shell32 序数 import 分) */
        for (size_t i = 0; i < sizeof shx_ordtable / sizeof shx_ordtable[0] && !fn; i++) {
            const ShxOrdEnt* e = &shx_ordtable[i];
            if (e->ord == ord && !strcmp(e->dll, modname)) fn = e->fn;
        }
    }
    if (!fn && !byOrd && (!strcmp(name, "DWriteCreateFactory") || !strcmp(name, "DWriteCoreCreateFactory")))
        shim_unimplemented("DWriteCreateFactory (DirectWrite 未対応: Kilohearts Skia の動的ロード。KH-20 方針 = 明示 fail-fast)");
    if (!fn && !byOrd && (!strcmp(name, "SHBrowseForFolderA") || !strcmp(name, "SHBrowseForFolderW")))
        shim_unimplemented("SHBrowseForFolder");
    if (!fn) {
        char nb[64];
        if (byOrd) { snprintf(nb, sizeof nb, "#%u", ord); name = nb; }
        if (g_strict && builtin) {
            char msg[400]; snprintf(msg, sizeof msg, "GetProcAddress(%s!%s)", modname, name);
            shim_unimplemented(msg);
        }
        SHX_TRACE("GetProcAddress miss: %s!%s", modname, name);
        SetLastError(ERROR_PROC_NOT_FOUND);
        return NULL;
    }
    SetLastError(ERROR_SUCCESS);
    return fn;
}

/* ---------------------------------------------------------------
 * リソース: HRSRC = {data,size} への小構造体ポインタ
 * --------------------------------------------------------------- */
typedef struct { const void* data; DWORD size; } ResEnt;
HRSRC FindResourceW(HMODULE m, LPCWSTR name, LPCWSTR type) {
    DWORD sz = 0;
    const void* d = g_res_provider ? g_res_provider(m, name, type, &sz) : NULL;
    if (!d) { SetLastError(ERROR_RESOURCE_DATA_NOT_FOUND); return 0; }
    ResEnt* r = (ResEnt*)malloc(sizeof(ResEnt));
    r->data = d; r->size = sz;
    return (HRSRC)r;
}
HRSRC FindResourceA(HMODULE m, LPCSTR name, LPCSTR type) {
    WCHAR wn[256], wt[256]; const WCHAR* pn; const WCHAR* pt;
    if (shx_is_iptr((uintptr_t)name)) pn = (const WCHAR*)name; else { MultiByteToWideChar(CP_ACP, 0, name, -1, wn, 256); pn = wn; }
    if (shx_is_iptr((uintptr_t)type)) pt = (const WCHAR*)type; else { MultiByteToWideChar(CP_ACP, 0, type, -1, wt, 256); pt = wt; }
    return FindResourceW(m, pn, pt);
}
HGLOBAL LoadResource(HMODULE m, HRSRC r) { (void)m; return r ? (HGLOBAL)r : 0; }
LPVOID LockResource(HGLOBAL h) { return h ? (LPVOID)((ResEnt*)h)->data : NULL; }
DWORD SizeofResource(HMODULE m, HRSRC r) { (void)m; return r ? ((ResEnt*)r)->size : 0; }
BOOL FreeResource(HGLOBAL h) { (void)h; return FALSE; }

/* IMAGEHLP: 擬似/登録モジュールのメモリ上 PE ヘッダを辿る */
void* ImageNtHeader(PVOID base) {
    uint8_t* p = (uint8_t*)base;
    if (!p || *(uint16_t*)p != 0x5A4D) return NULL;
    uint32_t off = *(uint32_t*)(p + 0x3C);
    if (*(uint32_t*)(p + off) != 0x4550) return NULL;
    return p + off;
}
void* ImageRvaToVa(void* nt, PVOID base, ULONG rva, void** sect) {
    (void)nt; (void)sect;
    return (uint8_t*)base + rva;      /* メモリ上にマップ済み画像 (M11 の LVA=0 敷設) 前提: RVA をそのまま加算 */
}
void* ImageDirectoryEntryToData(PVOID base, BOOLEAN mapped, USHORT_T dir, ULONG* size) {
    (void)mapped;
    uint8_t* nt = (uint8_t*)ImageNtHeader(base);
    if (!nt || dir >= 16) { if (size) *size = 0; return NULL; }
    uint8_t* dd = nt + 4 + 20 + 112 + (size_t)dir * 8;
    uint32_t rva = *(uint32_t*)dd, sz = *(uint32_t*)(dd + 4);
    if (size) *size = sz;
    return rva ? (uint8_t*)base + rva : NULL;
}
