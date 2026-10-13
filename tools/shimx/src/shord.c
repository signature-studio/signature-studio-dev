/* 序数 import でしか参照されない shell32 / shlwapi API (SHX-T8, #175)。
 *   shell32  #74  = SHCreateStdEnumFmtEtc(UINT cfmt, const FORMATETC* afmt, IEnumFORMATETC** out)   (OTT vst2/vst3)
 *   shlwapi  #12  = SHCreateMemStream(const BYTE* data, UINT len) → IStream*                         (Serum2)
 *   shlwapi  #219 = QISearch(void* that, const QITAB* tab, REFIID riid, void** out)                  (Serum2)
 * 序数 → 名前の根拠は tools/shimx/REPORT.md §14 (Wine shell32.spec / shlwapi.spec = Windows の序数表と突合)。
 * GetProcAddress(序数) 解決は module.c の shx_ordtable、lift ABI トークンは cbtrans.c の g_lifttab。
 *
 * COM オブジェクトは shimx 既存 (ole.c の IStream/IMalloc) と同じ Win64 vtable 規約: 先頭 8B = vtable ポインタ、
 * vtable は 8B スロット。FORMATETC は Win64 レイアウト 32B (cfFormat@0 WORD / ptd@8 / dwAspect@16 / lindex@20 / tymed@24)。
 */
#include "shimx_internal.h"

#define FE_SIZE 32u

typedef struct ShxEnumFmt {
    uint64_t vtbl;
    LONG refs;
    uint32_t n, pos;
    uint8_t* fe;                 /* n × FE_SIZE。ptd は CoTaskMemAlloc の深いコピーを所有 */
} ShxEnumFmt;

static uint64_t g_enum_vtbl[7];
static const GUID IID_IUnknown_ = { 0x00000000, 0x0000, 0x0000, { 0xC0, 0, 0, 0, 0, 0, 0, 0x46 } };
static const GUID IID_IEnumFORMATETC_ = { 0x00000103, 0x0000, 0x0000, { 0xC0, 0, 0, 0, 0, 0, 0, 0x46 } };

static uint64_t ptd_dup(uint64_t p) {
    if (!p) return 0;
    uint32_t sz = *(const uint32_t*)(uintptr_t)p;           /* DVTARGETDEVICE.tdSize */
    void* q = CoTaskMemAlloc(sz);
    if (!q) return 0;
    memcpy(q, (const void*)(uintptr_t)p, sz);
    return (uint64_t)(uintptr_t)q;
}
static void fe_free_ptds(uint8_t* fe, uint32_t n) {
    for (uint32_t i = 0; i < n; i++) {
        uint64_t p = *(uint64_t*)(fe + i * FE_SIZE + 8);
        if (p) CoTaskMemFree((void*)(uintptr_t)p);
    }
}
static HRESULT enum_new(const uint8_t* src, uint32_t n, uint32_t pos, ShxEnumFmt** out);

static HRESULT en_qi(ShxEnumFmt* e, const GUID* iid, void** out) {
    if (!out) return E_POINTER;
    if (iid && (IsEqualGUID(iid, &IID_IUnknown_) || IsEqualGUID(iid, &IID_IEnumFORMATETC_))) {
        *out = e; InterlockedIncrement(&e->refs); return S_OK;
    }
    *out = NULL; return E_NOINTERFACE;
}
static ULONG en_addref(ShxEnumFmt* e) { return (ULONG)InterlockedIncrement(&e->refs); }
static ULONG en_release(ShxEnumFmt* e) {
    LONG r = InterlockedDecrement(&e->refs);
    if (r == 0) { fe_free_ptds(e->fe, e->n); free(e->fe); free(e); }
    return (ULONG)r;
}
static HRESULT en_next(ShxEnumFmt* e, ULONG celt, uint8_t* out, ULONG* fetched) {
    if (!out || (celt != 1 && !fetched)) return E_INVALIDARG;
    ULONG n = 0;
    while (n < celt && e->pos < e->n) {
        uint8_t* d = out + (size_t)n * FE_SIZE;
        memcpy(d, e->fe + (size_t)e->pos * FE_SIZE, FE_SIZE);
        *(uint64_t*)(d + 8) = ptd_dup(*(uint64_t*)(d + 8));
        n++; e->pos++;
    }
    if (fetched) *fetched = n;
    return n == celt ? S_OK : S_FALSE;
}
static HRESULT en_skip(ShxEnumFmt* e, ULONG celt) {
    uint64_t np = (uint64_t)e->pos + celt;
    if (np > e->n) { e->pos = e->n; return S_FALSE; }
    e->pos = (uint32_t)np; return S_OK;
}
static HRESULT en_reset(ShxEnumFmt* e) { e->pos = 0; return S_OK; }
static HRESULT en_clone(ShxEnumFmt* e, void** out) {
    if (!out) return E_POINTER;
    ShxEnumFmt* c = NULL;
    HRESULT hr = enum_new(e->fe, e->n, e->pos, &c);
    *out = FAILED(hr) ? NULL : c;
    return hr;
}

static HRESULT enum_new(const uint8_t* src, uint32_t n, uint32_t pos, ShxEnumFmt** out) {
    if (!g_enum_vtbl[0]) {
        void* f[7] = { (void*)en_qi, (void*)en_addref, (void*)en_release, (void*)en_next, (void*)en_skip, (void*)en_reset, (void*)en_clone };
        for (int i = 0; i < 7; i++) g_enum_vtbl[i] = (uint64_t)(uintptr_t)f[i];
    }
    ShxEnumFmt* e = (ShxEnumFmt*)calloc(1, sizeof *e);
    if (!e) return E_OUTOFMEMORY;
    e->fe = (uint8_t*)calloc(n ? n : 1, FE_SIZE);
    if (!e->fe) { free(e); return E_OUTOFMEMORY; }
    if (n) memcpy(e->fe, src, (size_t)n * FE_SIZE);
    for (uint32_t i = 0; i < n; i++) *(uint64_t*)(e->fe + i * FE_SIZE + 8) = ptd_dup(*(uint64_t*)(e->fe + i * FE_SIZE + 8));
    e->vtbl = (uint64_t)(uintptr_t)g_enum_vtbl; e->refs = 1; e->n = n; e->pos = pos;
    *out = e;
    return S_OK;
}

HRESULT SHCreateStdEnumFmtEtc(UINT cfmt, const void* afmt, LPVOID* out) {
    if (!out) return E_POINTER;
    *out = NULL;
    if (cfmt && !afmt) return E_INVALIDARG;
    ShxEnumFmt* e = NULL;
    HRESULT hr = enum_new((const uint8_t*)afmt, cfmt, 0, &e);
    if (FAILED(hr)) return hr;
    *out = e;
    return S_OK;
}

LPVOID SHCreateMemStream(const BYTE* data, UINT len) {
    HGLOBAL h = GlobalAlloc(GMEM_MOVEABLE, data ? len : 0);       /* data==NULL: 空ストリーム (cbInit 無視) */
    if (!h) return NULL;
    if (data && len) memcpy((void*)h, data, len);
    LPVOID s = NULL;
    if (FAILED(CreateStreamOnHGlobal(h, TRUE, &s))) { GlobalFree(h); return NULL; }
    if (!data || !len) {                       /* GlobalAlloc(0) は 1B に切り上がり、ストリーム長が 1 になるので 0 に確定 */
        const uint64_t* vt = (const uint64_t*)(uintptr_t)*(const uint64_t*)s;
        ((HRESULT (*)(void*, uint64_t))(uintptr_t)vt[6])(s, 0);      /* IStream::SetSize(0) */
    }
    return s;
}

/* QITAB (Win64): { const IID* piid @0 (8B スロット); DWORD dwOffset @8 } = 16B。piid==NULL で終端 */
static void unk_addref(void* unk) {
    uint64_t vt = *(const uint64_t*)unk;
    ULONG (*fn)(void*) = (ULONG (*)(void*))(uintptr_t)((const uint64_t*)(uintptr_t)vt)[1];
    fn(unk);
}
HRESULT QISearch(void* that, const void* tab, const GUID* riid, LPVOID* out) {
    if (!out) return E_POINTER;
    const uint8_t* t = (const uint8_t*)tab;
    for (const uint8_t* p = t; *(const uint64_t*)p; p += 16) {
        if (IsEqualGUID(riid, (const GUID*)(uintptr_t)*(const uint64_t*)p)) {
            void* u = (uint8_t*)that + *(const uint32_t*)(p + 8);
            unk_addref(u); *out = u; return S_OK;
        }
    }
    const uint64_t first = *(const uint64_t*)t;
    if (IsEqualGUID(riid, &IID_IUnknown_) && first && !IsEqualGUID(riid, (const GUID*)(uintptr_t)first)) {
        void* u = (uint8_t*)that + *(const uint32_t*)(t + 8);
        unk_addref(u); *out = u; return S_OK;
    }
    *out = NULL;
    return E_NOINTERFACE;
}
