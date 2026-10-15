/* SHX-T37 (#3070): HeapReAlloc / GlobalLock / GlobalUnlock / GlobalFree の不正入力に対する
 * 戻り値と GetLastError を実測する単体 probe。tools/shimx/test/ の外に置く (test.sh は test/*.c を全部コンパイルするため)。
 * 使い方: node probe.cjs <fn> <value-hex>   (1 ケース = 1 プロセス。wasm trap は呼び出し側で TRAP と記録する)
 * 出力: fn value ret errcode   (ret は戻り値の hex、errcode は呼び出し前に 0 へ戻した GetLastError の値。0 = 呼び出しが設定しなかった)
 */
#include "../src/shimx.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void show(const char* fn, uintptr_t v, uintptr_t ret) {
    printf("%s\t0x%llx\t0x%llx\t%lu\n", fn, (unsigned long long)v, (unsigned long long)ret, (unsigned long)GetLastError());
}

int main(int argc, char** argv) {
    if (argc < 3) { fprintf(stderr, "usage: probe <fn> <value-hex>\n"); return 2; }
    const char* fn = argv[1];
    uintptr_t v = (uintptr_t)strtoull(argv[2], NULL, 16);
    HEAP_HANDLE heap = GetProcessHeap();

    if (!strcmp(fn, "HeapReAlloc")) {
        SetLastError(0);
        uintptr_t r = (uintptr_t)HeapReAlloc(heap, 0, (LPVOID)v, 64);
        show(fn, v, r);
    } else if (!strcmp(fn, "GlobalLock")) {
        SetLastError(0);
        uintptr_t r = (uintptr_t)GlobalLock((HGLOBAL)v);
        show(fn, v, r);
    } else if (!strcmp(fn, "GlobalUnlock")) {
        SetLastError(0);
        uintptr_t r = (uintptr_t)GlobalUnlock((HGLOBAL)v);
        show(fn, v, r);
    } else if (!strcmp(fn, "GlobalFree")) {
        SetLastError(0);
        uintptr_t r = (uintptr_t)GlobalFree((HGLOBAL)v);
        show(fn, v, r);
    } else if (!strcmp(fn, "freed")) {
        /* 解放済みブロックへの 4 関数 (v は無視)。GlobalFree 後のポインタを使う */
        HGLOBAL g = GlobalAlloc(GMEM_ZEROINIT, 64);
        GlobalFree(g);
        uintptr_t gv = (uintptr_t)g;
        SetLastError(0); uintptr_t r1 = (uintptr_t)HeapReAlloc(heap, 0, (LPVOID)gv, 64); show("HeapReAlloc", gv, r1);
        SetLastError(0); uintptr_t r2 = (uintptr_t)GlobalLock((HGLOBAL)gv); show("GlobalLock", gv, r2);
        SetLastError(0); uintptr_t r3 = (uintptr_t)GlobalUnlock((HGLOBAL)gv); show("GlobalUnlock", gv, r3);
        SetLastError(0); uintptr_t r4 = (uintptr_t)GlobalFree((HGLOBAL)gv); show("GlobalFree", gv, r4);
    } else if (!strcmp(fn, "unlocked")) {
        /* 正常入力の参考: 確保直後 (ロックなし) の GlobalUnlock と、Lock→Unlock の戻り値 */
        HGLOBAL g = GlobalAlloc(GMEM_ZEROINIT, 64);
        SetLastError(0); uintptr_t r1 = (uintptr_t)GlobalUnlock(g); show("GlobalUnlock(never-locked)", (uintptr_t)g, r1);
        GlobalLock(g);
        SetLastError(0); uintptr_t r2 = (uintptr_t)GlobalUnlock(g); show("GlobalUnlock(locked-once)", (uintptr_t)g, r2);
        GlobalFree(g);
    } else {
        fprintf(stderr, "unknown fn %s\n", fn);
        return 2;
    }
    return 0;
}
