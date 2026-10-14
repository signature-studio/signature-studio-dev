/* shimx 単体テスト (ole/shell): GUID / BSTR / VARIANT / SAFEARRAY / IStream / IMalloc / shell32 / version。 */
#include "test_common.h"

typedef struct { uint16_t vt, r1, r2, r3; union { int64_t i8; double r8; uint64_t ptr; uint8_t raw[16]; } u; } Var;

static int g_unk_released;
static uint64_t g_unk_vtbl[3];
static ULONG unk_qi(void* s, const GUID* i, void** o) { (void)i; *o = s; return 0; }
static ULONG unk_add(void* s) { (void)s; return 2; }
static ULONG unk_rel(void* s) { (void)s; g_unk_released++; return 1; }

static void test_guid_bstr(void) {
    GUID g;
    CHECK(CLSIDFromString(W("{3EB685DB-65F9-4CF6-A03A-E3EF65729F3D}"), &g) == S_OK);
    CHECK(g.Data1 == 0x3EB685DB && g.Data2 == 0x65F9 && g.Data3 == 0x4CF6 && g.Data4[0] == 0xA0 && g.Data4[7] == 0x3D);
    WCHAR s[64];
    CHECK(StringFromGUID2(&g, s, 64) == 39 && wstr_eq(s, "{3EB685DB-65F9-4CF6-A03A-E3EF65729F3D}"));
    CHECK(StringFromGUID2(&g, s, 10) == 0);
    LPWSTR cs = NULL; CHECK(StringFromCLSID(&g, &cs) == S_OK && wstr_eq(cs, "{3EB685DB-65F9-4CF6-A03A-E3EF65729F3D}")); CoTaskMemFree(cs);
    CHECK(CLSIDFromString(W("NotAGuid"), &g) == (HRESULT)0x800401F3);
    GUID a, b; CoCreateGuid(&a); CoCreateGuid(&b);
    CHECK(!IsEqualGUID(&a, &b) && IsEqualGUID(&a, &a) && (a.Data3 >> 12) == 4);
    LPVOID obj = (LPVOID)1;
    CHECK(CoCreateInstance((uint64_t)(uintptr_t)&a, NULL, 1, &b, &obj) == REGDB_E_CLASSNOTREG && obj == NULL);
    GUID shelllink;                                                       /* IFileDialog 以外の CLSID は従来どおり REGDB_E_CLASSNOTREG (SHX-T33) */
    CHECK(CLSIDFromString(W("{00021401-0000-0000-C000-000000000046}"), &shelllink) == S_OK);
    obj = (LPVOID)1;
    CHECK(CoCreateInstance((uint64_t)(uintptr_t)&shelllink, NULL, 1, &b, &obj) == REGDB_E_CLASSNOTREG && obj == NULL);
    CHECK(CoCreateInstance(0, NULL, 1, &b, &obj) == REGDB_E_CLASSNOTREG && obj == NULL);
    CHECK(CoInitialize(NULL) == S_OK && CoInitialize(NULL) == S_FALSE); CoUninitialize(); CoUninitialize();

    BSTR bs = SysAllocString(W("hello"));
    CHECK(bs && SysStringLen(bs) == 5 && SysStringByteLen(bs) == 10 && wstr_eq(bs, "hello") && bs[5] == 0);
    CHECK(SysReAllocStringLen(&bs, W("hello world"), 11) && SysStringLen(bs) == 11 && wstr_eq(bs, "hello world"));
    CHECK(SysReAllocStringLen(&bs, NULL, 3) && SysStringLen(bs) == 3 && bs[0] == 'h');          /* NULL: 先頭を保持して縮小 */
    SysFreeString(bs);
    BSTR e = SysAllocStringLen(NULL, 4); CHECK(e && SysStringLen(e) == 4 && e[0] == 0 && e[3] == 0); SysFreeString(e);
    CHECK(SysAllocString(NULL) == NULL && SysStringLen(NULL) == 0);
    SysFreeString(NULL);
}

static void test_variant_safearray(void) {
    Var v, w; VariantInit(&v); VariantInit(&w);
    CHECK(sizeof(Var) == 24 && v.vt == 0);
    v.vt = 8; v.u.ptr = (uint64_t)(uintptr_t)SysAllocString(W("abc"));
    CHECK(VariantCopy(&w, &v) == S_OK && w.vt == 8 && w.u.ptr != v.u.ptr && wstr_eq((BSTR)(uintptr_t)w.u.ptr, "abc"));
    CHECK(VariantClear(&v) == S_OK && v.vt == 0 && VariantClear(&w) == S_OK);

    v.vt = 3; *(int32_t*)v.u.raw = 42;                         /* VT_I4 → R8 / BSTR / BOOL */
    CHECK(VariantChangeType(&w, &v, 0, 5) == S_OK && w.vt == 5 && w.u.r8 == 42.0);
    CHECK(VariantChangeType(&w, &v, 0, 8) == S_OK && w.vt == 8 && wstr_eq((BSTR)(uintptr_t)w.u.ptr, "42")); VariantClear(&w);
    v.vt = 5; v.u.r8 = 3.7;
    CHECK(VariantChangeType(&w, &v, 0, 3) == S_OK && *(int32_t*)w.u.raw == 4);                   /* 四捨五入 */
    Var s; VariantInit(&s); s.vt = 8; s.u.ptr = (uint64_t)(uintptr_t)SysAllocString(W("2.5"));
    CHECK(VariantChangeType(&w, &s, 0, 5) == S_OK && w.u.r8 == 2.5); VariantClear(&s);
    s.vt = 11; *(int16_t*)s.u.raw = -1;
    CHECK(VariantChangeType(&w, &s, 0, 8) == S_OK && wstr_eq((BSTR)(uintptr_t)w.u.ptr, "True")); VariantClear(&w);
    s.vt = 1; CHECK(VariantChangeType(&w, &s, 0, 3) == DISP_E_TYPEMISMATCH);                      /* VT_NULL */
    /* BYREF 解除 */
    int32_t target = 77; Var r; VariantInit(&r); r.vt = 3 | 0x4000; r.u.ptr = (uint64_t)(uintptr_t)&target;
    CHECK(VariantCopyInd(&w, &r) == S_OK && w.vt == 3 && *(int32_t*)w.u.raw == 77);
    /* IUnknown の AddRef/Release が呼ばれる */
    g_unk_vtbl[0] = (uint64_t)(uintptr_t)unk_qi; g_unk_vtbl[1] = (uint64_t)(uintptr_t)unk_add; g_unk_vtbl[2] = (uint64_t)(uintptr_t)unk_rel;
    uint64_t obj = (uint64_t)(uintptr_t)g_unk_vtbl;
    VariantInit(&s); s.vt = 13; s.u.ptr = (uint64_t)(uintptr_t)&obj;
    CHECK(VariantCopy(&w, &s) == S_OK && VariantClear(&w) == S_OK && g_unk_released == 1);
    s.vt = 0;

    /* SAFEARRAY: 1 次元 [2..4] の I4 / BSTR */
    uint32_t bnd[2] = { 3, 2 };                                  /* cElements=3, lLbound=2 */
    uint8_t* sa = (uint8_t*)SafeArrayCreate(3, 1, bnd);
    CHECK(sa && *(uint16_t*)sa == 1 && *(uint32_t*)(sa + 4) == 4);          /* cDims, cbElements */
    LONG lb, ub; CHECK(SafeArrayGetLBound(sa, 1, &lb) == S_OK && SafeArrayGetUBound(sa, 1, &ub) == S_OK && lb == 2 && ub == 4);
    CHECK(SafeArrayGetElemsize(sa) == 4);
    for (LONG i = 2; i <= 4; i++) { int32_t val = (int32_t)i * 100; CHECK(SafeArrayPutElement(sa, &i, &val) == S_OK); }
    LONG idx = 3; int32_t got = 0; CHECK(SafeArrayGetElement(sa, &idx, &got) == S_OK && got == 300);
    idx = 5; CHECK(SafeArrayGetElement(sa, &idx, &got) == (HRESULT)0x8002000B);
    int32_t* data; CHECK(SafeArrayAccessData(sa, (void**)&data) == S_OK && data[0] == 200 && data[2] == 400);
    CHECK(SafeArrayDestroy(sa) == (HRESULT)0x8002000D);          /* ロック中は破棄不可 */
    CHECK(SafeArrayUnaccessData(sa) == S_OK && SafeArrayDestroy(sa) == S_OK);
    sa = (uint8_t*)SafeArrayCreate(8, 1, (uint32_t[]){ 2, 0 });
    CHECK(sa && SafeArrayGetElemsize(sa) == 8);                  /* BSTR は 8B スロット (Win64) */
    idx = 1; BSTR be = SysAllocString(W("elem")); CHECK(SafeArrayPutElement(sa, &idx, be) == S_OK); SysFreeString(be);       /* 要素は複製を保持 */
    BSTR out = NULL; CHECK(SafeArrayGetElement(sa, &idx, &out) == S_OK && wstr_eq(out, "elem")); SysFreeString(out);
    void* pp; CHECK(SafeArrayPtrOfIndex(sa, &idx, &pp) == S_OK && pp == (void*)(uintptr_t)(*(uint64_t*)(sa + 16) + 8));
    CHECK(SafeArrayDestroy(sa) == S_OK);
    /* 2 次元: [0..1]x[0..2] */
    uint32_t b2[4] = { 3, 0, 2, 0 };                              /* bounds[0] = 右端(3 要素), bounds[1] = 左端(2 要素) */
    sa = (uint8_t*)SafeArrayCreate(3, 2, b2);
    LONG ix[2] = { 1, 2 }; int32_t pv = 99; CHECK(SafeArrayPutElement(sa, ix, &pv) == S_OK);
    int32_t* d2; SafeArrayAccessData(sa, (void**)&d2); CHECK(d2[1 * 3 + 2] == 99); SafeArrayUnaccessData(sa);
    SafeArrayDestroy(sa);
    CHECK(SafeArrayCreate(99, 1, bnd) == NULL);
    /* VARIANT 配列の VariantClear / Copy */
    Var va; VariantInit(&va); va.vt = 3 | 0x2000; va.u.ptr = (uint64_t)(uintptr_t)SafeArrayCreate(3, 1, bnd);
    CHECK(VariantCopy(&w, &va) == S_OK && w.vt == (3 | 0x2000) && w.u.ptr != va.u.ptr);
    VariantClear(&w); VariantClear(&va);
}

#include "test_shord.inc"
static void test_stream_malloc(void) {
    LPVOID stm = NULL;
    CHECK(CreateStreamOnHGlobal(0, TRUE, &stm) == S_OK && stm);
    uint64_t* vt = (uint64_t*)(uintptr_t)*(uint64_t*)stm;                    /* Win64 vtable: 8B スロット */
    HRESULT (*write)(void*, const void*, ULONG, ULONG*) = (HRESULT (*)(void*, const void*, ULONG, ULONG*))(uintptr_t)vt[4];
    HRESULT (*read)(void*, void*, ULONG, ULONG*) = (HRESULT (*)(void*, void*, ULONG, ULONG*))(uintptr_t)vt[3];
    HRESULT (*seek)(void*, int64_t, DWORD, uint64_t*) = (HRESULT (*)(void*, int64_t, DWORD, uint64_t*))(uintptr_t)vt[5];
    ULONG (*rel)(void*) = (ULONG (*)(void*))(uintptr_t)vt[2];
    ULONG n = 0; char buf[32];
    CHECK(write(stm, "0123456789", 10, &n) == S_OK && n == 10);
    uint64_t np = 0; CHECK(seek(stm, 2, 0, &np) == S_OK && np == 2);
    CHECK(read(stm, buf, 5, &n) == S_OK && n == 5 && !memcmp(buf, "23456", 5));
    CHECK(seek(stm, -2, 2, &np) == S_OK && np == 8 && read(stm, buf, 10, &n) == S_FALSE && n == 2);   /* 末尾: 部分読み */
    HGLOBAL hg = 0; CHECK(GetHGlobalFromStream(stm, &hg) == S_OK && hg && !memcmp((void*)hg, "0123456789", 10));
    char big[5000]; memset(big, 7, sizeof big);
    seek(stm, 0, 2, &np); CHECK(write(stm, big, sizeof big, &n) == S_OK && n == sizeof big);        /* 自動拡張 */
    CHECK(rel(stm) == 0);
    /* 呼び出し側所有の HGLOBAL (del=FALSE) は破棄されない */
    HGLOBAL own = GlobalAlloc(GMEM_MOVEABLE, 8); memcpy((void*)own, "ABCDEFGH", 8);
    CHECK(CreateStreamOnHGlobal(own, FALSE, &stm) == S_OK);
    vt = (uint64_t*)(uintptr_t)*(uint64_t*)stm; read = (HRESULT (*)(void*, void*, ULONG, ULONG*))(uintptr_t)vt[3]; rel = (ULONG (*)(void*))(uintptr_t)vt[2];
    CHECK(read(stm, buf, 8, &n) == S_OK && !memcmp(buf, "ABCDEFGH", 8));
    rel(stm);
    CHECK(GlobalSize(own) == 8); GlobalFree(own);

    LPVOID m = NULL;
    CHECK(SHGetMalloc(&m) == S_OK && m);
    vt = (uint64_t*)(uintptr_t)*(uint64_t*)m;
    void* (*alloc)(void*, SIZE_T) = (void* (*)(void*, SIZE_T))(uintptr_t)vt[3];
    void (*mfree)(void*, void*) = (void (*)(void*, void*))(uintptr_t)vt[5];
    void* p = alloc(m, 64); CHECK(p); memset(p, 0, 64); mfree(m, p);
    /* Drop target 登録 */
    CHECK(RegisterDragDrop(0x1234, (LPVOID)0x99) == S_OK && shimx_get_drop_target(0x1234) == (LPVOID)0x99);
    CHECK(RegisterDragDrop(0x1234, (LPVOID)0x98) == (HRESULT)0x80040101 && RevokeDragDrop(0x1234) == S_OK && RevokeDragDrop(0x1234) == (HRESULT)0x80040100);
    CHECK(OleGetClipboard(&m) == (HRESULT)0x800401D0 && m == NULL);
    CHECK(StgCreateDocfileOnILockBytes(NULL, 0, 0, &m) == E_NOTIMPL);
}

static int g_shexec_calls;
static int shexec_hook(const char* verb, const char* file, const char* params) { (void)params; g_shexec_calls++; return !strcmp(verb, "open") && strstr(file, "https://") == file; }

static void test_shell_version(void) {
    WCHAR p[MAX_PATH];
    CHECK(SHGetFolderPathW(0, 0x1a, 0, 0, p) == S_OK && wstr_eq(p, "C:\\Users\\webstudio\\AppData\\Roaming"));
    CHECK(SHGetFolderPathW(0, 0x1c | 0x8000, 0, 0, p) == S_OK && GetFileAttributesW(p) & FILE_ATTRIBUTE_DIRECTORY);       /* CSIDL_FLAG_CREATE */
    CHECK(SHGetFolderPathW(0, 0xFE, 0, 0, p) == E_INVALIDARG);
    CHECK(SHGetSpecialFolderPathW(0, p, 0x23, FALSE) && wstr_eq(p, "C:\\ProgramData"));
    LPWSTR kp = NULL;
    GUID roaming = { 0x3EB685DB, 0x65F9, 0x4CF6, { 0xA0, 0x3A, 0xE3, 0xEF, 0x65, 0x72, 0x9F, 0x3D } };
    CHECK(SHGetKnownFolderPath(&roaming, 0, 0, &kp) == S_OK && wstr_eq(kp, "C:\\Users\\webstudio\\AppData\\Roaming")); CoTaskMemFree(kp);
    GUID bogus = {1, 2, 3, {4, 5, 6, 7, 8, 9, 10, 11}};
    CHECK(SHGetKnownFolderPath(&bogus, 0, 0, &kp) == (HRESULT)0x80070002 && kp == NULL);
    LPVOID pidl = ILCreateFromPathW(W("C:\\foo\\bar"));
    WCHAR back[MAX_PATH];
    CHECK(pidl && SHGetPathFromIDListW(pidl, back) && wstr_eq(back, "C:\\foo\\bar")); ILFree(pidl);
    CHECK(SHGetSpecialFolderLocation(0, 5, &pidl) == S_OK && SHGetPathFromIDListW(pidl, back) && wstr_eq(back, "C:\\Users\\webstudio\\Documents")); ILFree(pidl);
    CHECK(SHCreateDirectoryExW(0, W("C:\\shx_dir\\a\\b"), NULL) == 0 && SHCreateDirectoryExW(0, W("C:\\shx_dir\\a\\b"), NULL) == (int)ERROR_ALREADY_EXISTS);
    CHECK(GetFileAttributesW(W("C:\\shx_dir\\a\\b")) & FILE_ATTRIBUTE_DIRECTORY);
    WCHAR src[64]; memset(src, 0, sizeof src); lstrcpyW(src, W("C:\\shx_dir\\a"));
    WCHAR dst[64]; memset(dst, 0, sizeof dst); lstrcpyW(dst, W("C:\\shx_dir\\copy"));
    uint8_t op[56]; memset(op, 0, sizeof op);
    *(uint32_t*)(op + 8) = 2; *(uint64_t*)(op + 16) = (uint64_t)(uintptr_t)src; *(uint64_t*)(op + 24) = (uint64_t)(uintptr_t)dst;
    CHECK(SHFileOperationW(op) == 0 && (GetFileAttributesW(W("C:\\shx_dir\\copy\\b")) & FILE_ATTRIBUTE_DIRECTORY));      /* 再帰コピー */
    *(uint32_t*)(op + 8) = 3; *(uint64_t*)(op + 24) = 0; memset(src, 0, sizeof src); lstrcpyW(src, W("C:\\shx_dir"));
    CHECK(SHFileOperationW(op) == 0 && GetFileAttributesW(W("C:\\shx_dir")) == INVALID_FILE_ATTRIBUTES);
    WCHAR cleanup[] = { 'a', ':', 'b', '*', '.', 't', 'x', 't', 0 };
    CHECK(PathCleanupSpec(NULL, cleanup) == 1 && wstr_eq(cleanup, "a-b-.txt"));

    /* ShellExecute: フックで URL だけ許可 */
    CHECK((uintptr_t)ShellExecuteW(0, W("open"), W("https://example.com"), NULL, NULL, 1) == 2);   /* フック未設定 → FNF */
    shimx_set_shell_execute_hook(shexec_hook);
    CHECK((uintptr_t)ShellExecuteW(0, W("open"), W("https://example.com"), NULL, NULL, 1) == 33 && g_shexec_calls == 1);
    CHECK((uintptr_t)ShellExecuteW(0, W("open"), W("C:\\x.exe"), NULL, NULL, 1) == 2);
    uint8_t sei[112]; memset(sei, 0, sizeof sei);
    *(uint32_t*)sei = 112; *(uint64_t*)(sei + 16) = (uint64_t)(uintptr_t)W("open"); *(uint64_t*)(sei + 24) = (uint64_t)(uintptr_t)W("https://x.y");
    CHECK(ShellExecuteExW(sei) && *(uint64_t*)(sei + 56) == 33);

    /* version.dll: FL のファイル版 (shimx_set_version で変更可) */
    HANDLE h = CreateFileW(W("C:\\fl.exe"), GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, 0); CloseHandle(h);
    DWORD hnd = 1, sz = GetFileVersionInfoSizeW(W("C:\\fl.exe"), &hnd);
    CHECK(sz > 64 && hnd == 0);
    CHECK(GetFileVersionInfoSizeW(W("C:\\none.exe"), &hnd) == 0 && GetLastError() == ERROR_FILE_NOT_FOUND);
    void* blk = malloc(sz);
    CHECK(GetFileVersionInfoW(W("C:\\fl.exe"), 0, sz, blk));
    struct VFI { DWORD sig, sv, fvms, fvls, pvms, pvls, fm, fl, os, ft, fst, dms, dls; } *ffi = NULL;
    UINT len = 0;
    CHECK(VerQueryValueW(blk, W("\\"), (LPVOID*)&ffi, &len) && len == 52 && ffi->sig == 0xFEEF04BD && ffi->fvms == ((26u << 16) | 1) && ffi->fvls == ((7u << 16) | 5653));
    DWORD* tr = NULL; CHECK(VerQueryValueW(blk, W("\\VarFileInfo\\Translation"), (LPVOID*)&tr, &len) && len == 4 && *tr == 0x04B00409);
    WCHAR* sv = NULL;
    CHECK(VerQueryValueW(blk, W("\\StringFileInfo\\040904B0\\ProductVersion"), (LPVOID*)&sv, &len) && wstr_eq(sv, "26.1.7.5653") && len == 12);
    CHECK(VerQueryValueW(blk, W("\\StringFileInfo\\040904b0\\companyname"), (LPVOID*)&sv, &len) && wstr_eq(sv, "Image-Line"));
    CHECK(VerQueryValueW(blk, W("\\StringFileInfo\\040904B0\\Nope"), (LPVOID*)&sv, &len) == FALSE);
    free(blk);
    DeleteFileW(W("C:\\fl.exe"));
    CHECK(GetOpenFileNameW(NULL) == FALSE && CommDlgExtendedError() == 0);                   /* ファイル選択 UI 未接続 = キャンセル */
    HANDLE pr = (HANDLE)5; CHECK(OpenPrinterW(NULL, &pr, NULL) == FALSE && GetLastError() == 1801);
    DWORD need = 9, ret = 9; CHECK(EnumPrintersW(2, NULL, 2, NULL, 0, &need, &ret) && need == 0 && ret == 0);
    CHECK(SHGetFileInfoW(W("C:\\"), 0, NULL, 0, 0) == 0 && Shell_NotifyIconW(0, NULL) == FALSE);
}

void run_ole_shell_tests(void) {
    test_guid_bstr();
    test_variant_safearray();
    test_stream_malloc();
    test_shord();
    test_cp932();
    test_crypt();
    test_shell_version();
}
