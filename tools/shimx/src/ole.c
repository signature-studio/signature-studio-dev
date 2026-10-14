/* ole32 / oleaut32: COM 初期化 (スタブ), GUID, BSTR, VARIANT, SAFEARRAY (Win64 レイアウト), IStream(HGLOBAL), IMalloc。
 * - VARIANT は 24B (vt@0, 値@8)。SAFEARRAY は Win64 の {cDims,fFeatures,cbElements,cLocks,pad,pvData(8B),bounds[]}。
 *   ポインタ要素 (BSTR/IUnknown) は 8B スロットに低位 32bit でポインタを格納する (lifted Win64 コードと整合)。
 * - COM オブジェクトの vtable も 8B スロット。C 側関数は wasm32 の自然な署名を持つため、lifted コードからの
 *   間接呼出しは hostbridge 側の呼出規約ブリッジを要する (inventory 参照)。
 */
#include "shimx_internal.h"

#define VT_EMPTY 0
#define VT_NULL 1
#define VT_I2 2
#define VT_I4 3
#define VT_R4 4
#define VT_R8 5
#define VT_CY 6
#define VT_DATE 7
#define VT_BSTR 8
#define VT_DISPATCH 9
#define VT_ERROR 10
#define VT_BOOL 11
#define VT_VARIANT 12
#define VT_UNKNOWN 13
#define VT_I1 16
#define VT_UI1 17
#define VT_UI2 18
#define VT_UI4 19
#define VT_I8 20
#define VT_UI8 21
#define VT_INT 22
#define VT_UINT 23
#define VT_ARRAY 0x2000
#define VT_BYREF 0x4000
#define VT_LPWSTR 31

typedef struct { uint16_t vt, r1, r2, r3; union { int64_t i8; double r8; uint64_t ptr; uint8_t raw[16]; } u; } Variant64;  /* 24B */

/* ---------------- COM 初期化 ---------------- */
static _Thread_local int t_com;
HRESULT CoInitializeEx(LPVOID rsv, DWORD flags) { (void)rsv; (void)flags; return (t_com++ == 0) ? S_OK : S_FALSE; }
HRESULT CoInitialize(LPVOID rsv) { return CoInitializeEx(rsv, 0); }
void CoUninitialize(void) { if (t_com > 0) t_com--; }
HRESULT OleInitialize(LPVOID rsv) { return CoInitializeEx(rsv, 0); }
void OleUninitialize(void) { CoUninitialize(); }

LPVOID CoTaskMemAlloc(SIZE_T n) { return malloc(n ? n : 1); }
LPVOID CoTaskMemRealloc(LPVOID p, SIZE_T n) { return realloc(p, n ? n : 1); }
void CoTaskMemFree(LPVOID p) { free(p); }
static const GUID clsid_FileOpenDialog = { 0xDC1C5A9C, 0xE88A, 0x4DDE, { 0xA5, 0xA1, 0x60, 0xF8, 0x2A, 0x20, 0xAE, 0xF7 } };
static const GUID clsid_FileSaveDialog = { 0xC0B4E2F3, 0xBA21, 0x4773, { 0x8D, 0xBA, 0x33, 0x5E, 0xC9, 0x46, 0xEB, 0x8B } };
HRESULT CoCreateInstance(uint64_t clsid, LPVOID outer, DWORD ctx, const GUID* iid, LPVOID* out) {   /* 第1引数は RetDec 署名 (i64) に合わせる */
    (void)outer; (void)ctx; (void)iid;
    const GUID* g = (const GUID*)(uintptr_t)clsid;   /* guest の CLSID へのポインタ */
    if (g && IsEqualGUID(g, &clsid_FileOpenDialog)) shim_unimplemented("CoCreateInstance(FileOpenDialog)");   /* SHX-T33 #2916: IFileDialog 未対応 = 明示 fail-fast */
    if (g && IsEqualGUID(g, &clsid_FileSaveDialog)) shim_unimplemented("CoCreateInstance(FileSaveDialog)");
    if (out) *out = NULL;
    return REGDB_E_CLASSNOTREG;
}
HRESULT CoGetClassObject(const GUID* clsid, DWORD ctx, LPVOID srv, const GUID* iid, LPVOID* out) {
    (void)clsid; (void)ctx; (void)srv; (void)iid;
    if (out) *out = NULL;
    return REGDB_E_CLASSNOTREG;
}
HRESULT GetActiveObject(const GUID* clsid, LPVOID rsv, LPVOID* unk) {
    (void)clsid; (void)rsv; if (unk) *unk = NULL; return (HRESULT)0x800401E3;  /* MK_E_UNAVAILABLE */
}
HRESULT GetErrorInfo(DWORD rsv, LPVOID* info) { (void)rsv; if (info) *info = NULL; return S_FALSE; }

/* ---------------- GUID ---------------- */
BOOL IsEqualGUID(const GUID* a, const GUID* b) { return a && b && memcmp(a, b, sizeof(GUID)) == 0; }
HRESULT CoCreateGuid(GUID* g) {
    if (!g) return E_POINTER;
    static uint64_t s;
    if (!s) s = (uint64_t)(shx_now_ms() * 1000.0) ^ 0x9E3779B97F4A7C15ull;
    uint8_t* b = (uint8_t*)g;
    for (int i = 0; i < 16; i++) { s ^= s << 13; s ^= s >> 7; s ^= s << 17; b[i] = (uint8_t)(s >> 24); }
    g->Data3 = (WORD)((g->Data3 & 0x0FFF) | 0x4000);
    g->Data4[0] = (BYTE)((g->Data4[0] & 0x3F) | 0x80);
    return S_OK;
}
HRESULT UuidCreate(GUID* g) { return CoCreateGuid(g); }
int StringFromGUID2(const GUID* g, LPWSTR out, int cch) {
    if (cch < 39) return 0;
    char t[48];
    snprintf(t, sizeof t, "{%08X-%04X-%04X-%02X%02X-%02X%02X%02X%02X%02X%02X}", g->Data1, g->Data2, g->Data3,
             g->Data4[0], g->Data4[1], g->Data4[2], g->Data4[3], g->Data4[4], g->Data4[5], g->Data4[6], g->Data4[7]);
    for (int i = 0; i < 39; i++) out[i] = (WCHAR)t[i];
    return 39;
}
HRESULT StringFromCLSID(const GUID* g, LPWSTR* out) {
    WCHAR* p = (WCHAR*)CoTaskMemAlloc(39 * 2);
    if (!p) return E_OUTOFMEMORY;
    StringFromGUID2(g, p, 39);
    *out = p;
    return S_OK;
}
HRESULT CLSIDFromString(LPCWSTR s, GUID* g) {
    if (!s) { memset(g, 0, sizeof *g); return S_OK; }
    char t[48]; int n = 0;
    while (s[n] && n < 46) { t[n] = (char)s[n]; n++; }
    t[n] = 0;
    unsigned a, b, c, d[8];
    if (n != 38 || t[0] != '{' || sscanf(t, "{%8x-%4x-%4x-%2x%2x-%2x%2x%2x%2x%2x%2x}", &a, &b, &c, &d[0], &d[1], &d[2], &d[3], &d[4], &d[5], &d[6], &d[7]) != 11)
        return (HRESULT)0x800401F3;   /* CO_E_CLASSSTRING (ProgID 解決は非対応) */
    g->Data1 = a; g->Data2 = (WORD)b; g->Data3 = (WORD)c;
    for (int i = 0; i < 8; i++) g->Data4[i] = (BYTE)d[i];
    return S_OK;
}
HRESULT ProgIDFromCLSID(const GUID* g, LPWSTR* out) { (void)g; if (out) *out = NULL; return REGDB_E_CLASSNOTREG; }

/* ---------------- BSTR ----------------
 * R5: SysFreeString が shimx 管理外ポインタ (lift 側 FastMM/スタック等) を受けたときの扱い。
 * SysAlloc* が確保したベースポインタ (user - 4) を所有表に記録し、解放時に入口で判定する:
 *   所有済み  → unregister して free (従来どおり)
 *   管理外    → strict=1: fail-fast (「SysFreeString (管理外ポインタ)」) / strict=0: 無視 + trace
 *               (M11 の lift 誤り `_WStrClr` がスタック番地を渡して abort した実測 (REPORT §3-#1) を
 *                shimx 側で無害化する。二重 free も同一経路で無害化)
 */
#define BSTR_SET_INIT_CAP 1024
typedef struct { uintptr_t* v; size_t cap, n; } ShxPtrSet;
static ShxPtrSet g_bstr_set;
static shx_mutex_t g_bstr_lk;

static uintptr_t bstr_hash(uintptr_t x) { x ^= x >> 16; x *= 0x45d9f3bull; x ^= x >> 16; x *= 0x45d9f3bull; x ^= x >> 16; return x; }
static int bstr_set_has_locked(uintptr_t key) {
    ShxPtrSet* s = &g_bstr_set;
    if (!s->cap) return 0;
    size_t i = (size_t)bstr_hash(key) & (s->cap - 1);
    for (size_t probe = 0; probe < s->cap; probe++, i = (i + 1) & (s->cap - 1)) {
        if (!s->v[i]) return 0;
        if (s->v[i] == key) return 1;
    }
    return 0;
}
static int bstr_set_add_locked(uintptr_t key) {
    ShxPtrSet* s = &g_bstr_set;
    if (s->n * 2 >= s->cap) {                     /* 負荷率 < 0.5 で再ハッシュ */
        size_t nc = s->cap ? s->cap * 2 : BSTR_SET_INIT_CAP;
        uintptr_t* nv = (uintptr_t*)calloc(nc, sizeof(uintptr_t));
        if (!nv) return 0;
        for (size_t i = 0; s->cap && i < s->cap; i++) {
            if (!s->v[i]) continue;
            size_t j = (size_t)bstr_hash(s->v[i]) & (nc - 1);
            while (nv[j]) j = (j + 1) & (nc - 1);
            nv[j] = s->v[i];
        }
        free(s->v);
        s->v = nv; s->cap = nc;
    }
    size_t i = (size_t)bstr_hash(key) & (s->cap - 1);
    while (s->v[i]) {
        if (s->v[i] == key) return 1;
        i = (i + 1) & (s->cap - 1);
    }
    s->v[i] = key; s->n++;
    return 1;
}
static void bstr_set_del_locked(uintptr_t key) {
    ShxPtrSet* s = &g_bstr_set;
    if (!s->cap) return;
    size_t i = (size_t)bstr_hash(key) & (s->cap - 1);
    for (size_t probe = 0; probe < s->cap; probe++, i = (i + 1) & (s->cap - 1)) {
        if (!s->v[i]) return;
        if (s->v[i] == key) { s->v[i] = 0; s->n--; return; }
    }
}

BSTR SysAllocStringByteLen(LPCSTR s, UINT bytes) {
    uint8_t* p = (uint8_t*)malloc(4 + (size_t)bytes + 4);
    if (!p) return NULL;
    *(uint32_t*)p = bytes;
    if (s) memcpy(p + 4, s, bytes); else memset(p + 4, 0, bytes);
    memset(p + 4 + bytes, 0, 4);
    shx_mutex_lock(&g_bstr_lk);
    bstr_set_add_locked((uintptr_t)p);
    shx_mutex_unlock(&g_bstr_lk);
    return (BSTR)(p + 4);
}
BSTR SysAllocStringLen(const WCHAR* s, UINT len) { return SysAllocStringByteLen((LPCSTR)s, len * 2); }
BSTR SysAllocString(const WCHAR* s) { return s ? SysAllocStringLen(s, (UINT)shx_wstr_len(s)) : NULL; }
BOOL SysReAllocStringLen(BSTR* b, const WCHAR* s, UINT len) {
    if (!b) return FALSE;
    BSTR n = SysAllocStringLen(NULL, len);
    if (!n) return FALSE;
    if (s) memcpy(n, s, (size_t)len * 2);
    else if (*b) memcpy(n, *b, (size_t)(SysStringLen(*b) < len ? SysStringLen(*b) : len) * 2);
    SysFreeString(*b);
    *b = n;
    return TRUE;
}
void SysFreeString(BSTR b) {
    if (!b) return;
    uintptr_t base = (uintptr_t)b - 4;
    shx_mutex_lock(&g_bstr_lk);
    int owned = bstr_set_has_locked(base);
    if (owned) bstr_set_del_locked(base);
    shx_mutex_unlock(&g_bstr_lk);
    if (!owned) {
        if (shx_strict_mode()) shim_unimplemented("SysFreeString (管理外ポインタ)");
        SHX_TRACE("SysFreeString: 管理外ポインタ %p を無視 (strict=0)", b);
        return;
    }
    free((void*)base);
}
UINT SysStringLen(BSTR b) { return b ? *(uint32_t*)((uint8_t*)b - 4) / 2 : 0; }
UINT SysStringByteLen(BSTR b) { return b ? *(uint32_t*)((uint8_t*)b - 4) : 0; }

/* ---------------- COM 呼出ヘルパ (8B スロット vtable) ---------------- */
static uint32_t com_release(void* obj) {
    if (!obj) return 0;
    uint64_t* vtbl = (uint64_t*)(uintptr_t)*(uint64_t*)obj;
    uint32_t (*fn)(void*) = (uint32_t (*)(void*))(uintptr_t)vtbl[2];
    return fn(obj);
}
static uint32_t com_addref(void* obj) {
    if (!obj) return 0;
    uint64_t* vtbl = (uint64_t*)(uintptr_t)*(uint64_t*)obj;
    uint32_t (*fn)(void*) = (uint32_t (*)(void*))(uintptr_t)vtbl[1];
    return fn(obj);
}

/* ---------------- SAFEARRAY ---------------- */
typedef struct { uint16_t cDims, fFeatures; uint32_t cbElements, cLocks, pad; uint64_t pvData; struct { uint32_t cElements; int32_t lLbound; } b[1]; } SafeArr64;
#define SA_PREFIX 8

static uint32_t vt_size(uint16_t vt) {
    switch (vt) {
        case VT_I1: case VT_UI1: return 1;
        case VT_I2: case VT_UI2: case VT_BOOL: return 2;
        case VT_I4: case VT_UI4: case VT_R4: case VT_INT: case VT_UINT: case VT_ERROR: return 4;
        case VT_I8: case VT_UI8: case VT_R8: case VT_DATE: case VT_CY: return 8;
        case VT_BSTR: case VT_DISPATCH: case VT_UNKNOWN: return 8;
        case VT_VARIANT: return 24;
        default: return 0;
    }
}
static uint16_t sa_feat(uint16_t vt) {
    uint16_t f = 0x80;   /* FADF_HAVEVARTYPE */
    if (vt == VT_BSTR) f |= 0x100; else if (vt == VT_UNKNOWN) f |= 0x200; else if (vt == VT_DISPATCH) f |= 0x400; else if (vt == VT_VARIANT) f |= 0x800;
    return f;
}
static uint16_t sa_vt(const SafeArr64* sa) { return *(uint16_t*)((const uint8_t*)sa - SA_PREFIX); }

void* SafeArrayCreate(WORD vt, UINT dims, const void* bounds) {
    uint32_t es = vt_size(vt);
    if (!es || dims == 0 || dims > 32 || !bounds) return NULL;
    size_t hdr = sizeof(SafeArr64) + (dims - 1) * 8;
    uint8_t* base = (uint8_t*)calloc(1, SA_PREFIX + hdr);
    if (!base) return NULL;
    SafeArr64* sa = (SafeArr64*)(base + SA_PREFIX);
    *(uint16_t*)base = vt;
    sa->cDims = (uint16_t)dims; sa->fFeatures = sa_feat(vt); sa->cbElements = es;
    uint64_t total = 1;
    const uint32_t* bp = (const uint32_t*)bounds;
    for (UINT i = 0; i < dims; i++) { sa->b[i].cElements = bp[i * 2]; sa->b[i].lLbound = (int32_t)bp[i * 2 + 1]; total *= bp[i * 2]; }
    void* data = calloc(1, (size_t)(total * es) + 1);
    if (!data) { free(base); return NULL; }
    sa->pvData = (uint64_t)(uintptr_t)data;
    return sa;
}
HRESULT SafeArrayDestroy(void* p) {
    SafeArr64* sa = (SafeArr64*)p;
    if (!sa) return S_OK;
    if (sa->cLocks) return (HRESULT)0x8002000D;    /* DISP_E_ARRAYISLOCKED */
    uint64_t total = 1;
    for (int i = 0; i < sa->cDims; i++) total *= sa->b[i].cElements;
    uint8_t* d = (uint8_t*)(uintptr_t)sa->pvData;
    if (d) {
        uint16_t vt = sa_vt(sa);
        for (uint64_t i = 0; i < total; i++) {
            if (vt == VT_BSTR) SysFreeString((BSTR)(uintptr_t)*(uint64_t*)(d + i * 8));
            else if (vt == VT_UNKNOWN || vt == VT_DISPATCH) com_release((void*)(uintptr_t)*(uint64_t*)(d + i * 8));
            else if (vt == VT_VARIANT) VariantClear(d + i * 24);
        }
        free(d);
    }
    free((uint8_t*)sa - SA_PREFIX);
    return S_OK;
}
HRESULT SafeArrayAccessData(void* p, void** pp) {
    SafeArr64* sa = (SafeArr64*)p;
    if (!sa || !pp) return E_INVALIDARG;
    sa->cLocks++; *pp = (void*)(uintptr_t)sa->pvData; return S_OK;
}
HRESULT SafeArrayUnaccessData(void* p) { SafeArr64* sa = (SafeArr64*)p; if (!sa) return E_INVALIDARG; if (sa->cLocks) sa->cLocks--; return S_OK; }
UINT SafeArrayGetElemsize(void* p) { return p ? ((SafeArr64*)p)->cbElements : 0; }
HRESULT SafeArrayGetLBound(void* p, UINT dim, LONG* out) {
    SafeArr64* sa = (SafeArr64*)p;
    if (!sa || dim < 1 || dim > sa->cDims || !out) return (HRESULT)0x8002000B;   /* DISP_E_BADINDEX */
    *out = sa->b[sa->cDims - dim].lLbound; return S_OK;
}
HRESULT SafeArrayGetUBound(void* p, UINT dim, LONG* out) {
    SafeArr64* sa = (SafeArr64*)p;
    if (!sa || dim < 1 || dim > sa->cDims || !out) return (HRESULT)0x8002000B;
    *out = sa->b[sa->cDims - dim].lLbound + (LONG)sa->b[sa->cDims - dim].cElements - 1; return S_OK;
}
HRESULT SafeArrayPtrOfIndex(void* p, const LONG* idx, void** pp) {
    SafeArr64* sa = (SafeArr64*)p;
    if (!sa || !idx || !pp) return E_INVALIDARG;
    uint64_t lin = 0;
    for (int k = 0; k < sa->cDims; k++) {
        int d = sa->cDims - 1 - k;     /* idx[0] = 最左次元 = rgsabound[cDims-1] */
        int64_t off = (int64_t)idx[k] - sa->b[d].lLbound;
        if (off < 0 || (uint64_t)off >= sa->b[d].cElements) return (HRESULT)0x8002000B;
        lin = lin * sa->b[d].cElements + (uint64_t)off;
    }
    *pp = (void*)((uint8_t*)(uintptr_t)sa->pvData + lin * sa->cbElements);
    return S_OK;
}
HRESULT SafeArrayGetElement(void* p, const LONG* idx, void* out) {
    void* src; HRESULT hr = SafeArrayPtrOfIndex(p, idx, &src);
    if (FAILED(hr)) return hr;
    SafeArr64* sa = (SafeArr64*)p;
    uint16_t vt = sa_vt(sa);
    if (vt == VT_BSTR) {
        BSTR s = (BSTR)(uintptr_t)*(uint64_t*)src;
        BSTR c = s ? SysAllocStringByteLen((LPCSTR)s, SysStringByteLen(s)) : NULL;
        *(uint64_t*)out = (uint64_t)(uintptr_t)c;
    } else if (vt == VT_UNKNOWN || vt == VT_DISPATCH) {
        void* o = (void*)(uintptr_t)*(uint64_t*)src; com_addref(o); *(uint64_t*)out = (uint64_t)(uintptr_t)o;
    } else if (vt == VT_VARIANT) VariantCopy(out, src);
    else memcpy(out, src, sa->cbElements);
    return S_OK;
}
HRESULT SafeArrayPutElement(void* p, const LONG* idx, void* in) {
    void* dst; HRESULT hr = SafeArrayPtrOfIndex(p, idx, &dst);
    if (FAILED(hr)) return hr;
    SafeArr64* sa = (SafeArr64*)p;
    uint16_t vt = sa_vt(sa);
    if (vt == VT_BSTR) {
        SysFreeString((BSTR)(uintptr_t)*(uint64_t*)dst);
        BSTR s = (BSTR)in;
        *(uint64_t*)dst = (uint64_t)(uintptr_t)(s ? SysAllocStringByteLen((LPCSTR)s, SysStringByteLen(s)) : NULL);
    } else if (vt == VT_UNKNOWN || vt == VT_DISPATCH) {
        com_release((void*)(uintptr_t)*(uint64_t*)dst);
        com_addref(in);
        *(uint64_t*)dst = (uint64_t)(uintptr_t)in;
    } else if (vt == VT_VARIANT) { VariantClear(dst); VariantCopy(dst, in); }
    else memcpy(dst, in, sa->cbElements);
    return S_OK;
}

/* ---------------- VARIANT ---------------- */
void VariantInit(void* v) { memset(v, 0, sizeof(Variant64)); }
HRESULT VariantClear(void* pv) {
    Variant64* v = (Variant64*)pv;
    if (!(v->vt & VT_BYREF)) {
        if (v->vt == VT_BSTR) SysFreeString((BSTR)(uintptr_t)v->u.ptr);
        else if (v->vt == VT_UNKNOWN || v->vt == VT_DISPATCH) com_release((void*)(uintptr_t)v->u.ptr);
        else if (v->vt & VT_ARRAY) SafeArrayDestroy((void*)(uintptr_t)v->u.ptr);
        else if (v->vt == VT_VARIANT) {}
    }
    memset(v, 0, sizeof *v);
    return S_OK;
}
HRESULT VariantCopy(void* dst, const void* src) {
    if (dst == src) return S_OK;
    Variant64 tmp = *(const Variant64*)src;
    VariantClear(dst);
    if (!(tmp.vt & VT_BYREF)) {
        if (tmp.vt == VT_BSTR) { BSTR s = (BSTR)(uintptr_t)tmp.u.ptr; tmp.u.ptr = (uint64_t)(uintptr_t)(s ? SysAllocStringByteLen((LPCSTR)s, SysStringByteLen(s)) : NULL); }
        else if (tmp.vt == VT_UNKNOWN || tmp.vt == VT_DISPATCH) com_addref((void*)(uintptr_t)tmp.u.ptr);
        else if (tmp.vt & VT_ARRAY) {
            SafeArr64* sa = (SafeArr64*)(uintptr_t)tmp.u.ptr;
            if (sa) {
                SafeArr64* n = (SafeArr64*)SafeArrayCreate(sa_vt(sa), sa->cDims, NULL);   /* bounds 配列形式が異なるため手動複製 */
                (void)n;
                size_t hdr = sizeof(SafeArr64) + (sa->cDims - 1) * 8;
                uint8_t* base = (uint8_t*)calloc(1, SA_PREFIX + hdr);
                memcpy(base, (uint8_t*)sa - SA_PREFIX, SA_PREFIX + hdr);
                SafeArr64* c = (SafeArr64*)(base + SA_PREFIX);
                uint64_t total = 1; for (int i = 0; i < c->cDims; i++) total *= c->b[i].cElements;
                uint8_t* d = (uint8_t*)calloc(1, (size_t)(total * c->cbElements) + 1);
                memcpy(d, (void*)(uintptr_t)sa->pvData, (size_t)(total * c->cbElements));
                c->pvData = (uint64_t)(uintptr_t)d; c->cLocks = 0;
                uint16_t vt = sa_vt(c);
                for (uint64_t i = 0; i < total; i++) {
                    if (vt == VT_BSTR) { BSTR s = (BSTR)(uintptr_t)*(uint64_t*)(d + i * 8); *(uint64_t*)(d + i * 8) = (uint64_t)(uintptr_t)(s ? SysAllocStringByteLen((LPCSTR)s, SysStringByteLen(s)) : NULL); }
                    else if (vt == VT_UNKNOWN || vt == VT_DISPATCH) com_addref((void*)(uintptr_t)*(uint64_t*)(d + i * 8));
                    else if (vt == VT_VARIANT) { Variant64 t2 = *(Variant64*)(d + i * 24); VariantInit(d + i * 24); VariantCopy(d + i * 24, &t2); }
                }
                tmp.u.ptr = (uint64_t)(uintptr_t)c;
            }
        }
    }
    *(Variant64*)dst = tmp;
    return S_OK;
}
HRESULT VariantCopyInd(void* dst, const void* src) {
    const Variant64* s = (const Variant64*)src;
    if (!(s->vt & VT_BYREF)) return VariantCopy(dst, src);
    uint16_t base = s->vt & ~VT_BYREF;
    void* p = (void*)(uintptr_t)s->u.ptr;
    if (!p) return E_INVALIDARG;
    if (base == VT_VARIANT) return VariantCopyInd(dst, p);
    Variant64 t; memset(&t, 0, sizeof t); t.vt = base;
    uint32_t es = vt_size(base & ~VT_ARRAY);
    if (base & VT_ARRAY) { t.u.ptr = *(uint64_t*)p; }
    else if (base == VT_BSTR || base == VT_UNKNOWN || base == VT_DISPATCH) t.u.ptr = (uint64_t)(uintptr_t)*(void**)p;
    else if (es) memcpy(t.u.raw, p, es);
    else return DISP_E_BADVARTYPE;
    return VariantCopy(dst, &t);
}

static int variant_to_f64(const Variant64* v, double* d, int64_t* i, int* isInt) {
    *isInt = 1;
    switch (v->vt) {
        case VT_EMPTY: *i = 0; *d = 0; return 0;
        case VT_I1: *i = (int8_t)v->u.raw[0]; break;
        case VT_UI1: *i = v->u.raw[0]; break;
        case VT_I2: *i = *(int16_t*)v->u.raw; break;
        case VT_UI2: *i = *(uint16_t*)v->u.raw; break;
        case VT_BOOL: *i = *(int16_t*)v->u.raw ? -1 : 0; break;
        case VT_I4: case VT_INT: case VT_ERROR: *i = *(int32_t*)v->u.raw; break;
        case VT_UI4: case VT_UINT: *i = *(uint32_t*)v->u.raw; break;
        case VT_I8: *i = v->u.i8; break;
        case VT_UI8: *i = (int64_t)v->u.i8; break;
        case VT_R4: *d = *(float*)v->u.raw; *isInt = 0; return 0;
        case VT_R8: case VT_DATE: *d = v->u.r8; *isInt = 0; return 0;
        default: return -1;
    }
    *d = (double)*i;
    return 0;
}
HRESULT VariantChangeType(void* pdst, const void* psrc, WORD flags, WORD vt) {
    (void)flags;
    const Variant64* src = (const Variant64*)psrc;
    Variant64 out; memset(&out, 0, sizeof out); out.vt = vt;
    if (src->vt & (VT_BYREF | VT_ARRAY)) { Variant64 t; VariantInit(&t); HRESULT hr = VariantCopyInd(&t, src); if (FAILED(hr)) return hr; hr = VariantChangeType(pdst, &t, flags, vt); VariantClear(&t); return hr; }
    if (src->vt == vt) return VariantCopy(pdst, psrc);
    if (src->vt == VT_NULL) return DISP_E_TYPEMISMATCH;
    double d = 0; int64_t i = 0; int isInt = 1;
    if (vt == VT_BSTR) {
        char t[64];
        if (src->vt == VT_BOOL) snprintf(t, sizeof t, "%s", *(int16_t*)src->u.raw ? "True" : "False");
        else if (variant_to_f64(src, &d, &i, &isInt) < 0) return DISP_E_TYPEMISMATCH;
        else if (isInt) snprintf(t, sizeof t, "%lld", (long long)i);
        else snprintf(t, sizeof t, "%.15g", d);
        WCHAR w[64]; int n = 0; for (; t[n]; n++) w[n] = (WCHAR)t[n];
        out.u.ptr = (uint64_t)(uintptr_t)SysAllocStringLen(w, (UINT)n);
    } else {
        if (src->vt == VT_BSTR) {
            BSTR s = (BSTR)(uintptr_t)src->u.ptr; char t[64]; UINT n = SysStringLen(s);
            if (n > 63) n = 63;
            for (UINT k = 0; k < n; k++) t[k] = (char)s[k];
            t[n] = 0;
            char* e; d = strtod(t, &e);
            if (e == t && vt != VT_BOOL) return DISP_E_TYPEMISMATCH;
            if (vt == VT_BOOL) { int b = (!strcasecmp(t, "true")) || (e != t && d != 0); out.u.raw[0] = b ? 0xFF : 0; out.u.raw[1] = b ? 0xFF : 0; goto done; }
            i = (int64_t)d; isInt = (strchr(t, '.') == NULL);
        } else if (variant_to_f64(src, &d, &i, &isInt) < 0) return DISP_E_TYPEMISMATCH;
        if (!isInt) i = (int64_t)(d < 0 ? d - 0.5 : d + 0.5);
        switch (vt) {
            case VT_I1: out.u.raw[0] = (uint8_t)(int8_t)i; break;
            case VT_UI1: out.u.raw[0] = (uint8_t)i; break;
            case VT_I2: *(int16_t*)out.u.raw = (int16_t)i; break;
            case VT_UI2: *(uint16_t*)out.u.raw = (uint16_t)i; break;
            case VT_BOOL: *(int16_t*)out.u.raw = (d != 0 || i != 0) ? -1 : 0; break;
            case VT_I4: case VT_INT: case VT_ERROR: *(int32_t*)out.u.raw = (int32_t)i; break;
            case VT_UI4: case VT_UINT: *(uint32_t*)out.u.raw = (uint32_t)i; break;
            case VT_I8: case VT_UI8: out.u.i8 = i; break;
            case VT_R4: *(float*)out.u.raw = (float)(isInt ? (double)i : d); break;
            case VT_R8: case VT_DATE: out.u.r8 = isInt ? (double)i : d; break;
            default: return DISP_E_BADVARTYPE;
        }
    }
done:
    VariantClear(pdst);
    *(Variant64*)pdst = out;
    return S_OK;
}

/* ---------------- IStream on HGLOBAL (Win64 vtable: 8B スロット) ---------------- */
typedef struct ShxStream {
    uint64_t vtbl;              /* +0: vtable ポインタ (8B スロット) */
    LONG refs; HGLOBAL h; uint32_t size, pos; int del;
} ShxStream;
static uint64_t g_stm_vtbl[14];
static HRESULT stm_qi(ShxStream* s, const GUID* iid, void** out) { (void)iid; *out = s; InterlockedIncrement(&s->refs); return S_OK; }
static ULONG stm_addref(ShxStream* s) { return (ULONG)InterlockedIncrement(&s->refs); }
static ULONG stm_release(ShxStream* s) {
    LONG r = InterlockedDecrement(&s->refs);
    if (r == 0) { if (s->del && s->h) GlobalFree(s->h); free(s); }
    return (ULONG)r;
}
static HRESULT stm_read(ShxStream* s, void* buf, ULONG cb, ULONG* got) {
    ULONG n = s->pos < s->size ? (s->size - s->pos < cb ? s->size - s->pos : cb) : 0;
    if (n) memcpy(buf, (uint8_t*)s->h + s->pos, n);
    s->pos += n; if (got) *got = n;
    return n == cb ? S_OK : S_FALSE;
}
static HRESULT stm_grow(ShxStream* s, uint32_t need) {
    SIZE_T cap = GlobalSize(s->h);
    if (need <= cap) return S_OK;
    SIZE_T nc = cap * 2 > need ? cap * 2 : need;
    HGLOBAL n = GlobalReAlloc(s->h, nc, GMEM_ZEROINIT);
    if (!n) return E_OUTOFMEMORY;
    s->h = n; return S_OK;
}
static HRESULT stm_write(ShxStream* s, const void* buf, ULONG cb, ULONG* wr) {
    if (stm_grow(s, s->pos + cb) != S_OK) return E_OUTOFMEMORY;
    memcpy((uint8_t*)s->h + s->pos, buf, cb);
    s->pos += cb; if (s->pos > s->size) s->size = s->pos;
    if (wr) *wr = cb;
    return S_OK;
}
static HRESULT stm_seek(ShxStream* s, int64_t mv, DWORD org, uint64_t* np) {
    int64_t base = org == 0 ? 0 : org == 1 ? (int64_t)s->pos : (int64_t)s->size;
    int64_t p = base + mv;
    if (p < 0) return (HRESULT)0x80030005;   /* STG_E_ACCESSDENIED 近似 */
    s->pos = (uint32_t)p; if (np) *np = (uint64_t)p;
    return S_OK;
}
static HRESULT stm_setsize(ShxStream* s, uint64_t n) {
    if (stm_grow(s, (uint32_t)n) != S_OK) return E_OUTOFMEMORY;
    if (n < s->size) memset((uint8_t*)s->h + n, 0, s->size - n);
    s->size = (uint32_t)n; return S_OK;
}
static HRESULT stm_stat(ShxStream* s, void* st, DWORD flags) {
    (void)flags; memset(st, 0, 80);
    *(uint32_t*)((uint8_t*)st + 8) = 2;                 /* STGTY_STREAM */
    *(uint64_t*)((uint8_t*)st + 16) = s->size;
    return S_OK;
}
static HRESULT stm_notimpl(void) { return E_NOTIMPL; }
static HRESULT stm_ok(void) { return S_OK; }
static void stm_vtbl_init(void) {
    if (g_stm_vtbl[0]) return;
    void* f[14] = { (void*)stm_qi, (void*)stm_addref, (void*)stm_release, (void*)stm_read, (void*)stm_write,
                    (void*)stm_seek, (void*)stm_setsize, (void*)stm_notimpl /*CopyTo*/, (void*)stm_ok /*Commit*/,
                    (void*)stm_ok /*Revert*/, (void*)stm_notimpl, (void*)stm_notimpl, (void*)stm_stat, (void*)stm_notimpl /*Clone*/ };
    for (int i = 0; i < 14; i++) g_stm_vtbl[i] = (uint64_t)(uintptr_t)f[i];
}
HRESULT CreateStreamOnHGlobal(HGLOBAL h, BOOL del, LPVOID* out) {
    if (!out) return E_POINTER;
    stm_vtbl_init();
    ShxStream* s = (ShxStream*)calloc(1, sizeof *s);
    if (!s) return E_OUTOFMEMORY;
    if (!h) { h = GlobalAlloc(GMEM_MOVEABLE, 0); del = TRUE; }
    s->vtbl = (uint64_t)(uintptr_t)g_stm_vtbl; s->refs = 1; s->h = h; s->del = del;
    s->size = (uint32_t)GlobalSize(h);
    *out = s;
    return S_OK;
}
HRESULT GetHGlobalFromStream(LPVOID stm, HGLOBAL* h) {
    ShxStream* s = (ShxStream*)stm;
    if (!s || s->vtbl != (uint64_t)(uintptr_t)g_stm_vtbl || !h) return E_INVALIDARG;
    *h = s->h; return S_OK;
}
HRESULT CoMarshalInterThreadInterfaceInStream(const GUID* iid, LPVOID unk, LPVOID* stm) {
    (void)iid;
    LPVOID s; HRESULT hr = CreateStreamOnHGlobal(0, TRUE, &s);
    if (FAILED(hr)) return hr;
    uint64_t p = (uint64_t)(uintptr_t)unk; ULONG w;
    stm_write((ShxStream*)s, &p, 8, &w);
    ((ShxStream*)s)->pos = 0;
    *stm = s; return S_OK;
}
HRESULT CoGetInterfaceAndReleaseStream(LPVOID stm, const GUID* iid, LPVOID* out) {
    (void)iid;
    ShxStream* s = (ShxStream*)stm; uint64_t p = 0; ULONG got;
    if (!s || !out) return E_INVALIDARG;
    stm_read(s, &p, 8, &got);
    stm_release(s);
    *out = (LPVOID)(uintptr_t)p;
    return got == 8 ? S_OK : E_FAIL;
}

/* ---------------- IMalloc (SHGetMalloc 用) ---------------- */
typedef struct { uint64_t vtbl; } ShxMalloc;
static uint64_t g_malloc_vtbl[9];
static ShxMalloc g_malloc_obj;
static HRESULT mal_qi(void* s, const GUID* i, void** o) { (void)i; *o = s; return S_OK; }
static ULONG mal_ref(void* s) { (void)s; return 1; }
static void* mal_alloc(void* s, SIZE_T n) { (void)s; return CoTaskMemAlloc(n); }
static void* mal_realloc(void* s, void* p, SIZE_T n) { (void)s; return CoTaskMemRealloc(p, n); }
static void mal_free(void* s, void* p) { (void)s; CoTaskMemFree(p); }
static SIZE_T mal_size(void* s, void* p) { (void)s; (void)p; return (SIZE_T)-1; }
static int mal_did(void* s, void* p) { (void)s; (void)p; return -1; }
static void mal_min(void* s) { (void)s; }
HRESULT SHGetMalloc(LPVOID* out) {
    if (!out) return E_POINTER;
    if (!g_malloc_vtbl[0]) {
        void* f[9] = { (void*)mal_qi, (void*)mal_ref, (void*)mal_ref, (void*)mal_alloc, (void*)mal_realloc, (void*)mal_free, (void*)mal_size, (void*)mal_did, (void*)mal_min };
        for (int i = 0; i < 9; i++) g_malloc_vtbl[i] = (uint64_t)(uintptr_t)f[i];
        g_malloc_obj.vtbl = (uint64_t)(uintptr_t)g_malloc_vtbl;
    }
    *out = &g_malloc_obj;
    return S_OK;
}

/* ---------------- ドラッグ&ドロップ / クリップボード (OLE) ---------------- */
#define DD_MAX 64
static struct { HWND w; LPVOID t; } g_dd[DD_MAX];
HRESULT RegisterDragDrop(HWND w, LPVOID target) {
    shx_lock();
    int free_i = -1;
    for (int i = 0; i < DD_MAX; i++) {
        if (g_dd[i].w == w && w) { shx_unlock(); return (HRESULT)0x80040101; }   /* DRAGDROP_E_ALREADYREGISTERED */
        if (!g_dd[i].w && free_i < 0) free_i = i;
    }
    if (free_i >= 0) { g_dd[free_i].w = w; g_dd[free_i].t = target; }
    shx_unlock();
    return free_i >= 0 ? S_OK : E_OUTOFMEMORY;
}
HRESULT RevokeDragDrop(HWND w) {
    HRESULT hr = (HRESULT)0x80040100;   /* DRAGDROP_E_NOTREGISTERED */
    shx_lock();
    for (int i = 0; i < DD_MAX; i++) if (g_dd[i].w == w) { g_dd[i].w = 0; g_dd[i].t = NULL; hr = S_OK; break; }
    shx_unlock();
    return hr;
}
LPVOID shimx_get_drop_target(HWND w) {      /* gui 担当向け: 登録済み IDropTarget を取得 */
    LPVOID t = NULL;
    shx_lock();
    for (int i = 0; i < DD_MAX; i++) if (g_dd[i].w == w) { t = g_dd[i].t; break; }
    shx_unlock();
    return t;
}
HRESULT DoDragDrop(LPVOID obj, LPVOID src, DWORD effects, DWORD* eff) { (void)obj; (void)src; (void)effects; if (eff) *eff = 0; return (HRESULT)0x00040101; /* DRAGDROP_S_CANCEL */ }
HRESULT OleGetClipboard(LPVOID* obj) { if (obj) *obj = NULL; return (HRESULT)0x800401D0; /* CLIPBRD_E_CANT_OPEN */ }
HRESULT OleSetClipboard(LPVOID obj) { (void)obj; return S_OK; }
HRESULT OleFlushClipboard(void) { return S_OK; }
HRESULT OleIsCurrentClipboard(LPVOID obj) { (void)obj; return S_FALSE; }
void ReleaseStgMedium(LPVOID m) {
    if (!m) return;
    uint32_t tymed = *(uint32_t*)m;
    uint64_t h = *(uint64_t*)((uint8_t*)m + 8);
    if (tymed == 1 /* TYMED_HGLOBAL */ && h) GlobalFree((HGLOBAL)(uintptr_t)h);
    memset(m, 0, 24);
}
HRESULT PropVariantClear(LPVOID pv) {
    if (!pv) return E_INVALIDARG;
    uint16_t vt = *(uint16_t*)pv;
    uint64_t p = *(uint64_t*)((uint8_t*)pv + 8);
    if (vt == VT_BSTR) SysFreeString((BSTR)(uintptr_t)p);
    else if (vt == VT_LPWSTR || vt == 30 /* VT_LPSTR */) CoTaskMemFree((void*)(uintptr_t)p);
    memset(pv, 0, 24);
    return S_OK;
}

/* ---------------- 構造化ストレージ / OLE UI: 非対応 (E_NOTIMPL) ---------------- */
HRESULT CreateILockBytesOnHGlobal(HGLOBAL h, BOOL del, LPVOID* out) { (void)h; (void)del; if (out) *out = NULL; return E_NOTIMPL; }
HRESULT StgCreateDocfileOnILockBytes(LPVOID lb, DWORD mode, DWORD rsv, LPVOID* out) { (void)lb; (void)mode; (void)rsv; if (out) *out = NULL; return E_NOTIMPL; }
HRESULT CreateDataAdviseHolder(LPVOID* out) { if (out) *out = NULL; return E_NOTIMPL; }
HRESULT OleDraw(LPVOID unk, DWORD aspect, HANDLE dc, LPVOID rc) { (void)unk; (void)aspect; (void)dc; (void)rc; return E_NOTIMPL; }
BOOL IsAccelerator(HANDLE haccel, int n, LPVOID msg, WORD* cmd) { (void)haccel; (void)n; (void)msg; (void)cmd; return FALSE; }
HRESULT OleSetMenuDescriptor(HANDLE h, HWND frame, HWND obj, LPVOID f, LPVOID o) { (void)h; (void)frame; (void)obj; (void)f; (void)o; return E_NOTIMPL; }

/* ---------------- SHX-T23 (#1388): RegisterDragDrop 経路の guest 呼出し橋 ----------------
 * 方式 (tools/gui/shimx_coexist/REPORT.md §10):
 *   C→guest: guest の IDropTarget vtable (8B スロット) の各 VA を shimx_cbtrans_get_invoke() (= lift 側 m11_icall) で呼ぶ。
 *   guest→C: 渡す IDataObject の vtable スロットは lifttab トークン (cbtrans.c の "IDataObject.*" 行) にする。
 *            guest が間接呼出しすると __wrap_m11_icall → shimx_lifttab_trampoline → shimx_ido_* に落ちる。
 * 検証は node + mock (C 側の偽 guest)。実 FL guest の vtable 呼出しの正しさは実機でのみ検証可能 (#177 と同じ制約)。 */
#define SHX_CF_HDROP 15
#define SHX_DVASPECT_CONTENT 1
#define SHX_TYMED_HGLOBAL 1
#define SHX_DV_E_FORMATETC 0x80040064
#define SHX_DV_E_LINDEX 0x80040068
#define SHX_DV_E_TYMED 0x80040069
#define SHX_DV_E_DVASPECT 0x8004006B
#define SHX_E_UNEXPECTED 0x8000FFFF
#define SHX_IDT_FAILED(r) ((int32_t)(uint32_t)(r) < 0)
typedef struct { uint64_t vtbl; LONG refs; HANDLE hd; } ShxDataObj;
static uint64_t g_ido_vt[12];
static const char* const g_ido_names[12] = {
    "IDataObject.QueryInterface", "IDataObject.AddRef", "IDataObject.Release", "IDataObject.GetData",
    "IDataObject.NotImpl", "IDataObject.QueryGetData", "IDataObject.NotImpl", "IDataObject.NotImpl",
    "IDataObject.NotImpl", "IDataObject.NotImpl", "IDataObject.NotImpl", "IDataObject.NotImpl",
};
static void ido_vt_init(void) {
    if (g_ido_vt[0]) return;
    for (int i = 0; i < 12; i++) g_ido_vt[i] = shimx_lifttab_token(g_ido_names[i], 0);
}
static HRESULT ido_fmt_check(const void* fe) {
    if (!fe) return E_INVALIDARG;
    const uint8_t* f = (const uint8_t*)fe;
    if (*(const uint16_t*)f != SHX_CF_HDROP) return SHX_DV_E_FORMATETC;
    if (*(const uint32_t*)(f + 16) != SHX_DVASPECT_CONTENT) return SHX_DV_E_DVASPECT;
    if (*(const int32_t*)(f + 20) != -1) return SHX_DV_E_LINDEX;
    if (!(*(const uint32_t*)(f + 24) & SHX_TYMED_HGLOBAL)) return SHX_DV_E_TYMED;
    return S_OK;
}
HRESULT shimx_ido_QueryInterface(void* self, const GUID* iid, void** out) {
    static const GUID iid_unk = { 0, 0, 0, { 0xC0, 0, 0, 0, 0, 0, 0, 0x46 } };
    static const GUID iid_ido = { 0x0000010E, 0, 0, { 0xC0, 0, 0, 0, 0, 0, 0, 0x46 } };
    if (!out) return E_POINTER;
    *out = NULL;
    if (!iid || (!IsEqualGUID(iid, &iid_unk) && !IsEqualGUID(iid, &iid_ido))) return E_NOINTERFACE;
    *out = self;
    shimx_ido_AddRef(self);
    return S_OK;
}
ULONG shimx_ido_AddRef(void* self) { return (ULONG)InterlockedIncrement(&((ShxDataObj*)self)->refs); }
ULONG shimx_ido_Release(void* self) {
    LONG r = InterlockedDecrement(&((ShxDataObj*)self)->refs);
    if (r == 0) free(self);
    return (ULONG)r;
}
HRESULT shimx_ido_GetData(void* self, const void* fe, void* sm) {
    ShxDataObj* o = (ShxDataObj*)self;
    HRESULT hr = ido_fmt_check(fe);
    if (FAILED(hr)) return hr;
    if (!sm) return E_POINTER;
    size_t sz = 0;
    const uint8_t* src = shimx_hdrop_bytes(o->hd, &sz);
    if (!src) return SHX_E_UNEXPECTED;
    HGLOBAL g = GlobalAlloc(GMEM_MOVEABLE, sz);
    if (!g) return E_OUTOFMEMORY;
    memcpy(GlobalLock(g), src, sz);
    GlobalUnlock(g);
    memset(sm, 0, 24);
    *(uint32_t*)sm = SHX_TYMED_HGLOBAL;
    *(uint64_t*)((uint8_t*)sm + 8) = (uint64_t)(uintptr_t)g;
    return S_OK;
}
HRESULT shimx_ido_QueryGetData(void* self, const void* fe) { (void)self; return ido_fmt_check(fe); }
HRESULT shimx_ido_NotImpl(void) { return E_NOTIMPL; }

int shimx_drop_invoke(void* target, uint64_t hwnd, size_t hdrop, int x, int y) {
    (void)hwnd;
    shimx_cb_invoke_fn f = shimx_cbtrans_get_invoke();
    if (!f || !target || !hdrop) return 0;
    ido_vt_init();
    ShxDataObj* o = (ShxDataObj*)calloc(1, sizeof *o);
    if (!o) return 0;
    o->vtbl = (uint64_t)(uintptr_t)g_ido_vt; o->refs = 1; o->hd = (HANDLE)hdrop;
    uint64_t* vt = (uint64_t*)(uintptr_t)*(uint64_t*)target;
    uint64_t self = (uint64_t)(uintptr_t)target, ido = (uint64_t)(uintptr_t)o;
    uint64_t pt = (uint64_t)(uint32_t)x | ((uint64_t)(uint32_t)y << 32);
    uint32_t eff = 1;
    uint64_t ea = (uint64_t)(uintptr_t)&eff;
    int entered = 0, handled = 0;
    if (!SHX_IDT_FAILED(f(vt[3], self, ido, 0, pt, ea, 0, 0, 0))) {
        entered = 1;
        if (!SHX_IDT_FAILED(f(vt[4], self, 0, pt, ea, 0, 0, 0, 0)) && eff)
            handled = !SHX_IDT_FAILED(f(vt[6], self, ido, 0, pt, ea, 0, 0, 0));
    }
    if (entered && !handled) f(vt[5], self, 0, 0, 0, 0, 0, 0, 0);
    shimx_ido_Release(o);
    return handled;
}
