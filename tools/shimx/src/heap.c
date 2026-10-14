/* heap / Global / Local / Virtual / メモリ状態。
 *
 * M4 差分:
 *   - ブロックヘッダを 16B にして *ユーザポインタを 16B アラインに* (Win64 の HeapAlloc は 16B 整列)
 *   - GetProcessHeap / HeapDestroy / HeapSize / HeapValidate / GlobalSize / GlobalReAlloc / LocalSize ... を追加
 *   - VirtualAlloc 系 (領域表付き) / VirtualQuery(Win64 MBI) / GlobalMemoryStatus(Ex) / IsBad*Ptr
 *   - GlobalUnlock は M4 互換 (ロック済みなら TRUE)。Win32 実仕様 (残ロック数) とは異なる (inventory 記載)
 *   - Virtual* は weak 定義: tools/m11 の m11_rt.c (強定義) があればそちらが優先される
 */
#include "shimx_internal.h"

#define HEAP_MAGIC  0x53485835u   /* "SHX5" */
#define HEAP_FREED  0xDEADF5EEu
#define HEAP_HDR    16

/* ヘッダは 16B 固定 (wasm32 の size_t=4B でも整列を保つため独自レイアウト) */
typedef struct { uint32_t magic, lockCount, size, flags; } Hdr16;

static void* raw_of(void* user) { return (unsigned char*)user - HEAP_HDR; }

static void* alloc_blk(size_t bytes, int zero) {
    void* raw = NULL;
    if (bytes > 0x7FFFFFF0u - HEAP_HDR || posix_memalign(&raw, 16, HEAP_HDR + bytes) != 0 || !raw) {
        SetLastError(ERROR_NOT_ENOUGH_MEMORY);
        return NULL;
    }
    Hdr16* h = (Hdr16*)raw;
    h->magic = HEAP_MAGIC; h->lockCount = 0; h->size = (uint32_t)bytes; h->flags = 0;
    void* user = (unsigned char*)raw + HEAP_HDR;
    if (zero) memset(user, 0, bytes);
    SetLastError(ERROR_SUCCESS);
    return user;
}
static int blk_ok(void* user) {
    /* ヘッダ 16B が wasm linear memory の内に収まるかを先に確かめる (範囲外は読まない / LD-132 #2802) */
    uint64_t u = (uintptr_t)user;
    uint64_t mem = (uint64_t)__builtin_wasm_memory_size(0) * 65536u;
    if (!user || ((uintptr_t)user & 15u) || u < HEAP_HDR || u > mem) return 0;
    return ((Hdr16*)raw_of(user))->magic == HEAP_MAGIC;
}

/* ---- 標準ヒープ ---- */
typedef struct { uint32_t magic; } HeapObj;
static HeapObj g_default_heap = { 0x48454150u };
HEAP_HANDLE GetProcessHeap(void) { return (HEAP_HANDLE)&g_default_heap; }
HEAP_HANDLE HeapCreate(DWORD flags, SIZE_T initial, SIZE_T maximum) {
    (void)flags; (void)initial; (void)maximum;
    HeapObj* h = (HeapObj*)malloc(sizeof(HeapObj));
    if (!h) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return 0; }
    h->magic = 0x48454150u;
    SetLastError(ERROR_SUCCESS);
    return (HEAP_HANDLE)h;
}
BOOL HeapDestroy(HEAP_HANDLE heap) {
    if (!heap || heap == INVALID_HANDLE_VALUE || heap == (HEAP_HANDLE)&g_default_heap) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    ((HeapObj*)heap)->magic = 0;
    free((void*)heap);     /* 配下ブロックは追跡していないため解放されない (inventory 制限) */
    return TRUE;
}
LPVOID HeapAlloc(HEAP_HANDLE heap, DWORD flags, SIZE_T bytes) {
    (void)heap;
    return alloc_blk(bytes ? bytes : 1, (flags & HEAP_ZERO_MEMORY) != 0);
}
LPVOID HeapReAlloc(HEAP_HANDLE heap, DWORD flags, LPVOID p, SIZE_T bytes) {
    (void)heap;
    if (!blk_ok(p)) { SetLastError(ERROR_INVALID_PARAMETER); return NULL; }
    Hdr16* h = (Hdr16*)raw_of(p);
    size_t old = h->size;
    if (!bytes) bytes = 1;
    void* nu = alloc_blk(bytes, 0);
    if (!nu) return NULL;
    memcpy(nu, p, old < bytes ? old : bytes);
    if ((flags & HEAP_ZERO_MEMORY) && bytes > old) memset((unsigned char*)nu + old, 0, bytes - old);
    h->magic = HEAP_FREED;
    free(h);
    SetLastError(ERROR_SUCCESS);
    return nu;
}
BOOL HeapFree(HEAP_HANDLE heap, DWORD flags, LPVOID p) {
    (void)heap; (void)flags;
    if (!p) return TRUE;
    /* 割当てのない p (範囲外 / magic 不一致) は解放せず TRUE。tools/shim/src/heap.c と同じ応答 (native 参照 #2821 / #3049) */
    if (!blk_ok(p)) { SetLastError(ERROR_SUCCESS); return TRUE; }
    Hdr16* h = (Hdr16*)raw_of(p);
    h->magic = HEAP_FREED;
    free(h);
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}
SIZE_T HeapSize(HEAP_HANDLE heap, DWORD flags, LPCVOID p) {
    (void)heap; (void)flags;
    if (!blk_ok((void*)p)) { SetLastError(ERROR_INVALID_PARAMETER); return (SIZE_T)-1; }
    return ((Hdr16*)raw_of((void*)p))->size;
}
BOOL HeapValidate(HEAP_HANDLE heap, DWORD flags, LPCVOID p) { (void)heap; (void)flags; return p ? blk_ok((void*)p) : TRUE; }
SIZE_T HeapCompact(HEAP_HANDLE heap, DWORD flags) { (void)heap; (void)flags; return 65536; }
BOOL HeapLock(HEAP_HANDLE heap) { (void)heap; return TRUE; }
BOOL HeapUnlock(HEAP_HANDLE heap) { (void)heap; return TRUE; }
BOOL HeapSetInformation(HEAP_HANDLE heap, int cls, PVOID info, SIZE_T n) { (void)heap; (void)cls; (void)info; (void)n; return TRUE; }

/* ---- Global / Local (MOVEABLE も FIXED 写像: ハンドル=ポインタ) ---- */
HGLOBAL GlobalAlloc(DWORD flags, SIZE_T bytes) { return (HGLOBAL)alloc_blk(bytes ? bytes : 1, (flags & GMEM_ZEROINIT) != 0); }
HGLOBAL GlobalReAlloc(HGLOBAL h, SIZE_T bytes, DWORD flags) {
    if (flags & 0x80u /* GMEM_MODIFY */) return h;
    void* n = HeapReAlloc(0, (flags & GMEM_ZEROINIT) ? HEAP_ZERO_MEMORY : 0, (void*)h, bytes);
    return (HGLOBAL)n;
}
LPVOID GlobalLock(HGLOBAL h) {
    if (!blk_ok((void*)h)) { SetLastError(ERROR_INVALID_HANDLE); return NULL; }
    ((Hdr16*)raw_of((void*)h))->lockCount++;
    SetLastError(ERROR_SUCCESS);
    return (LPVOID)h;
}
BOOL GlobalUnlock(HGLOBAL h) {
    if (!blk_ok((void*)h)) { SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
    Hdr16* hd = (Hdr16*)raw_of((void*)h);
    if (hd->lockCount == 0) { SetLastError(158 /* ERROR_NOT_LOCKED */); return FALSE; }
    hd->lockCount--;
    SetLastError(ERROR_SUCCESS);
    return TRUE;   /* M4 互換 */
}
HGLOBAL GlobalFree(HGLOBAL h) {
    if (!h) return 0;
    if (!blk_ok((void*)h)) { SetLastError(ERROR_INVALID_HANDLE); return h; }
    HeapFree(0, 0, (void*)h);
    return 0;
}
SIZE_T GlobalSize(HGLOBAL h) { return blk_ok((void*)h) ? ((Hdr16*)raw_of((void*)h))->size : 0; }
UINT GlobalFlags(HGLOBAL h) { return blk_ok((void*)h) ? (((Hdr16*)raw_of((void*)h))->lockCount & 0xFF) : 0x8000u /* GMEM_INVALID_HANDLE */; }
HGLOBAL GlobalHandle(LPCVOID p) { return blk_ok((void*)p) ? (HGLOBAL)p : 0; }
HLOCAL LocalAlloc(DWORD flags, SIZE_T bytes) { return (HLOCAL)GlobalAlloc(flags, bytes); }
HLOCAL LocalReAlloc(HLOCAL h, SIZE_T bytes, DWORD flags) { return (HLOCAL)GlobalReAlloc((HGLOBAL)h, bytes, flags); }
HLOCAL LocalFree(HLOCAL h) { return (HLOCAL)GlobalFree((HGLOBAL)h); }
SIZE_T LocalSize(HLOCAL h) { return GlobalSize((HGLOBAL)h); }
LPVOID LocalLock(HLOCAL h) { return GlobalLock((HGLOBAL)h); }
BOOL LocalUnlock(HLOCAL h) { return GlobalUnlock((HGLOBAL)h); }

/* ---- メモリ状態 ---- */
static uint64_t mem_bytes(void) { return (uint64_t)__builtin_wasm_memory_size(0) * 65536ull; }
void GlobalMemoryStatus(MEMORYSTATUS64* ms) {
    if (!ms) return;
    memset(ms, 0, sizeof(*ms));
    ms->dwLength = sizeof(*ms);
    ms->dwMemoryLoad = 50;
    ms->dwTotalPhys = 0x80000000ull; ms->dwAvailPhys = 0x40000000ull;
    ms->dwTotalPageFile = 0x100000000ull; ms->dwAvailPageFile = 0x80000000ull;
    ms->dwTotalVirtual = 0x7FFE0000ull; ms->dwAvailVirtual = 0x7FFE0000ull - mem_bytes();
}
BOOL GlobalMemoryStatusEx(MEMORYSTATUSEX* ms) {
    if (!ms || ms->dwLength < sizeof(*ms)) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    memset((char*)ms + 8, 0, sizeof(*ms) - 8);
    ms->dwLength = sizeof(*ms);
    ms->dwMemoryLoad = 50;
    ms->ullTotalPhys = 0x200000000ull; ms->ullAvailPhys = 0x100000000ull;
    ms->ullTotalPageFile = 0x400000000ull; ms->ullAvailPageFile = 0x200000000ull;
    ms->ullTotalVirtual = 0x7FFE0000ull; ms->ullAvailVirtual = 0x7FFE0000ull - mem_bytes();
    return TRUE;
}

/* ---- Virtual* (weak) ---- */
typedef struct { void* base; size_t size; int used; } VRegion;
#define VR_MAX 1024
static VRegion g_vr[VR_MAX];
static shx_mutex_t g_vr_lk;
#define VR_CAP (512u * 1024u * 1024u)

SHIMX_WEAK LPVOID VirtualAlloc(LPVOID addr, SIZE_T size, DWORD type, DWORD prot) {
    (void)prot;
    if (!size) { SetLastError(ERROR_INVALID_PARAMETER); return NULL; }
    size_t sz = (size + 4095u) & ~(size_t)4095u;
    if (addr) {
        shx_mutex_lock(&g_vr_lk);
        for (int i = 0; i < VR_MAX; i++) {
            if (g_vr[i].used && (char*)addr >= (char*)g_vr[i].base && (char*)addr + sz <= (char*)g_vr[i].base + g_vr[i].size) {
                shx_mutex_unlock(&g_vr_lk);
                if (type & MEM_COMMIT) { /* 既に零初期化済み領域の commit: 内容は保持 */ }
                return addr;
            }
        }
        shx_mutex_unlock(&g_vr_lk);
        SetLastError(487 /* ERROR_INVALID_ADDRESS */);
        return NULL;
    }
    if (sz > VR_CAP) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return NULL; }
    void* p = NULL;
    if (posix_memalign(&p, 65536, sz) != 0 || !p) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return NULL; }
    memset(p, 0, sz);
    shx_mutex_lock(&g_vr_lk);
    int slot = -1;
    for (int i = 0; i < VR_MAX; i++) if (!g_vr[i].used) { slot = i; break; }
    if (slot >= 0) { g_vr[slot].base = p; g_vr[slot].size = sz; g_vr[slot].used = 1; }
    shx_mutex_unlock(&g_vr_lk);
    if (slot < 0) { free(p); SetLastError(ERROR_NOT_ENOUGH_MEMORY); return NULL; }
    SetLastError(ERROR_SUCCESS);
    return p;
}
SHIMX_WEAK BOOL VirtualFree(LPVOID addr, SIZE_T size, DWORD type) {
    shx_mutex_lock(&g_vr_lk);
    for (int i = 0; i < VR_MAX; i++) {
        if (!g_vr[i].used) continue;
        char* b = (char*)g_vr[i].base;
        if (type & MEM_RELEASE) {
            if (b == (char*)addr && size == 0) {
                g_vr[i].used = 0;
                shx_mutex_unlock(&g_vr_lk);
                free(b);
                return TRUE;
            }
        } else if ((type & MEM_DECOMMIT) && (char*)addr >= b && (char*)addr + size <= b + g_vr[i].size) {
            shx_mutex_unlock(&g_vr_lk);
            memset(addr, 0, size);
            return TRUE;
        }
    }
    shx_mutex_unlock(&g_vr_lk);
    SetLastError(ERROR_INVALID_PARAMETER);
    return FALSE;
}
SHIMX_WEAK BOOL VirtualProtect(LPVOID addr, SIZE_T size, DWORD prot, LPDWORD old) {
    (void)addr; (void)size; (void)prot;
    if (old) *old = PAGE_READWRITE;
    return TRUE;
}
SHIMX_WEAK SIZE_T VirtualQuery(LPCVOID addr, MEMORY_BASIC_INFORMATION64* mbi, SIZE_T len) {
    if (!mbi || len < sizeof(*mbi)) { SetLastError(24 /* ERROR_BAD_LENGTH */); return 0; }
    memset(mbi, 0, sizeof(*mbi));
    uintptr_t a = (uintptr_t)addr, pg = a & ~(uintptr_t)4095u;
    uintptr_t allocBase = 0, end = 0;
    shx_mutex_lock(&g_vr_lk);
    for (int i = 0; i < VR_MAX; i++) {
        if (g_vr[i].used && a >= (uintptr_t)g_vr[i].base && a < (uintptr_t)g_vr[i].base + g_vr[i].size) {
            allocBase = (uintptr_t)g_vr[i].base; end = allocBase + g_vr[i].size; break;
        }
    }
    shx_mutex_unlock(&g_vr_lk);
    mbi->BaseAddress = pg;
    if (!allocBase && a >= 1024 && a < mem_bytes()) { allocBase = pg; end = (uintptr_t)mem_bytes(); }
    if (allocBase) {
        mbi->AllocationBase = allocBase; mbi->AllocationProtect = PAGE_READWRITE;
        mbi->RegionSize = end - pg; mbi->State = MEM_COMMIT; mbi->Protect = PAGE_READWRITE; mbi->Type = MEM_PRIVATE;
    } else {
        mbi->RegionSize = 0x10000 - pg;
        if (a >= 1024) mbi->RegionSize = 0x80000000u - pg;
        mbi->State = MEM_FREE; mbi->Protect = PAGE_NOACCESS;
    }
    return sizeof(*mbi);
}
SHIMX_WEAK SIZE_T VirtualQueryEx(HANDLE proc, LPCVOID addr, MEMORY_BASIC_INFORMATION64* mbi, SIZE_T len) {
    if (proc != (HANDLE)-1) { ShxObj* o = shx_ref(proc, OBJ_PROCESS); if (!o) { SetLastError(ERROR_INVALID_HANDLE); return 0; } shx_unref(o); }
    return VirtualQuery(addr, mbi, len);
}
BOOL IsBadReadPtr(LPCVOID p, SIZE_T n) {
    if (!n) return FALSE;
    uintptr_t a = (uintptr_t)p;
    return (a < 1024 || a + n < a || a + n > mem_bytes()) ? TRUE : FALSE;
}
BOOL IsBadWritePtr(LPVOID p, SIZE_T n) { return IsBadReadPtr(p, n); }
