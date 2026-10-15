/* heap 相当 (§3 #7 の P0 最小面): Emscripten malloc ラッパ。
 * - GlobalAlloc/LocalAlloc/HeapAlloc はすべて「ブロック先頭にヘッダ (サイズ +
 *   magic + lock数) を付けて malloc、返り値はヘッダ直後のポインタ」で統一。
 *   GMEM_MOVEABLE は v1 では FIXED に写影する (wasm は単一アドレス空間で
 *   移動不要。inventory.md の制限事項)。
 * - VirtualAlloc/VirtualProtect は wasm 上で no-op (memory.grow) 相当のため、
 *   面としては別タスク。ここでは含めない。
 * - HeapCreate の戻り値はダミーの非 NULL ハンドル (実体を持たない)。
 */
#include "shim.h"

#define SHIM_HEAP_MAGIC 0x53484D34u /* "SHM4" */

typedef struct ShimMemHdr {
    uint32_t magic;
    uint32_t lockCount;
    size_t   size;
} ShimMemHdr;

static void* raw_of(void* user) {
    return (unsigned char*)user - sizeof(ShimMemHdr);
}

static void* user_of(void* raw) {
    return (unsigned char*)raw + sizeof(ShimMemHdr);
}

static void* alloc_with_header(size_t bytes, int zeroInit) {
    ShimMemHdr* hdr = (ShimMemHdr*)malloc(sizeof(ShimMemHdr) + bytes);
    if (!hdr) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return NULL; }
    hdr->magic = SHIM_HEAP_MAGIC;
    hdr->lockCount = 0;
    hdr->size = bytes;
    void* user = user_of(hdr);
    if (zeroInit) memset(user, 0, bytes);
    SetLastError(ERROR_SUCCESS);
    return user;
}

static int block_ok(void* user) {
    /* ヘッダ [user - sizeof(hdr), user) が wasm linear memory の内に収まるかを先に確かめる。
     * 範囲外の値 (例: u16 の文字列値) を読むと wasm が OOB trap する (LD-132 / #2802) */
    uint64_t u = (uintptr_t)user;
    uint64_t mem = (uint64_t)__builtin_wasm_memory_size(0) * 65536u;
    if (!user || u < sizeof(ShimMemHdr) || u > mem) return 0;
    ShimMemHdr* hdr = (ShimMemHdr*)raw_of(user);
    return hdr->magic == SHIM_HEAP_MAGIC;
}

/* ---------------------------------------------------------------
 * GlobalAlloc / GlobalLock / GlobalUnlock / GlobalFree  (§3 #7)
 * --------------------------------------------------------------- */
HGLOBAL GlobalAlloc(DWORD flags, SIZE_T bytes) {
    if (bytes == 0) bytes = 1; /* Win 仕様: 0 バイト確保は実質 1 バイト扱い */
    return (HGLOBAL)alloc_with_header(bytes, (flags & GMEM_ZEROINIT) != 0);
}

LPVOID GlobalLock(HGLOBAL h) {
    if (!block_ok((void*)h)) { SetLastError(ERROR_INVALID_FUNCTION); return NULL; }
    ShimMemHdr* hdr = (ShimMemHdr*)raw_of((void*)h);
    hdr->lockCount++;
    SetLastError(ERROR_SUCCESS);
    return (LPVOID)h; /* FIXED 写影なので handle と LPVOID が同じ値 */
}

BOOL GlobalUnlock(HGLOBAL h) {
    if (!block_ok((void*)h)) { SetLastError(ERROR_INVALID_FUNCTION); return FALSE; }
    ShimMemHdr* hdr = (ShimMemHdr*)raw_of((void*)h);
    if (hdr->lockCount == 0) { SetLastError(ERROR_INVALID_FUNCTION); return FALSE; }
    hdr->lockCount--;
    SetLastError(ERROR_SUCCESS);
    return TRUE; /* 常に「参照が残っていない」= 0 を返す Win 慣例は破棄 (v1) */
}

HGLOBAL GlobalFree(HGLOBAL h) {
    if (!block_ok((void*)h)) { SetLastError(ERROR_INVALID_FUNCTION); return h; }
    free(raw_of((void*)h));
    SetLastError(ERROR_SUCCESS);
    return NULL;
}

/* ---------------------------------------------------------------
 * LocalAlloc / LocalFree  (§3 #7)
 * --------------------------------------------------------------- */
HLOCAL LocalAlloc(DWORD flags, SIZE_T bytes) {
    return (HLOCAL)GlobalAlloc(flags, bytes); /* 16bit 世代の区別は意味を持たない */
}

HLOCAL LocalReAlloc(HLOCAL h, SIZE_T bytes, DWORD flags) {
    (void)flags;
    if (!block_ok((void*)h)) { SetLastError(ERROR_INVALID_FUNCTION); return NULL; }
    ShimMemHdr* hdr = (ShimMemHdr*)raw_of((void*)h);
    ShimMemHdr* nh = (ShimMemHdr*)realloc(hdr, sizeof(ShimMemHdr) + bytes);
    if (!nh) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return NULL; }
    nh->magic = SHIM_HEAP_MAGIC;
    nh->size = bytes;
    SetLastError(ERROR_SUCCESS);
    return (HLOCAL)user_of(nh);
}

HLOCAL LocalFree(HLOCAL h) {
    return (HLOCAL)GlobalFree((HGLOBAL)h);
}

/* ---------------------------------------------------------------
 * HeapCreate / HeapAlloc / HeapReAlloc / HeapFree  (§3 #7)
 * --------------------------------------------------------------- */
HEAP_HANDLE HeapCreate(DWORD flags, SIZE_T initial, SIZE_T maximum) {
    (void)flags; (void)initial; (void)maximum;
    /* 単一 malloc ヒープに束ねるので実体は持たない。非 NULL を返すだけ。 */
    SetLastError(ERROR_SUCCESS);
    return (HEAP_HANDLE)0x1u;
}

static int heap_ok(HEAP_HANDLE heap) {
    return heap != NULL && heap != INVALID_HANDLE_VALUE;
}

LPVOID HeapAlloc(HEAP_HANDLE heap, DWORD flags, SIZE_T bytes) {
    (void)heap_ok(heap);
    return alloc_with_header(bytes, (flags & HEAP_ZERO_MEMORY) != 0);
}

LPVOID HeapReAlloc(HEAP_HANDLE heap, DWORD flags, LPVOID p, SIZE_T bytes) {
    (void)heap;
    if (!block_ok(p)) { SetLastError(ERROR_INVALID_FUNCTION); return NULL; }
    ShimMemHdr* hdr = (ShimMemHdr*)raw_of(p);
    size_t oldSize = hdr->size;
    ShimMemHdr* nh = (ShimMemHdr*)realloc(hdr, sizeof(ShimMemHdr) + bytes);
    if (!nh) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return NULL; }
    nh->magic = SHIM_HEAP_MAGIC;
    nh->size = bytes;
    void* user = user_of(nh);
    if ((flags & HEAP_ZERO_MEMORY) && bytes > oldSize)
        memset((unsigned char*)user + oldSize, 0, bytes - oldSize);
    SetLastError(ERROR_SUCCESS);
    return user;
}

BOOL HeapFree(HEAP_HANDLE heap, DWORD flags, LPVOID p) {
    (void)heap; (void)flags;
    /* liftdiff の native 参照 (tools/liftdiff/rt/ld_core.h の HeapFree は引数を見ず 1) と同じ応答にする (#2821)。
     * 割当てのない p は解放せず TRUE を返す (block_ok で範囲外を読まない) */
    if (block_ok(p)) free(raw_of(p));
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}
