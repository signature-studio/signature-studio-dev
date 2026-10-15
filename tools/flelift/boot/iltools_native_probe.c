/* iltools_native_probe.c — #4783 受入 2: ILTools_x64.dll の native 読込を実測する最小ホスト。
 * boot の分岐 (0x815e52〜0x815e8d) と同じ順で LoadLibraryW(L"ILTools") → GetProcAddress("CreateCursorFromFont") を呼び、
 * 戻り値を出力する。DLL 探索は実行ディレクトリ (ILTools_x64.dll を置いた場所)。
 * 検証: x86_64-w64-mingw32-gcc -O0 -o probe.exe iltools_native_probe.c && wine64 probe.exe
 */
#include <windows.h>
#include <stdio.h>

int main(void) {
    HMODULE h = LoadLibraryW(L"ILTools");
    printf("LoadLibraryW(ILTools) = %p err=%lu\n", (void *)h, GetLastError());
    if (!h) return 2;
    FARPROC p = GetProcAddress(h, "CreateCursorFromFont");
    printf("GetProcAddress(CreateCursorFromFont) = %p err=%lu\n", (void *)p, GetLastError());
    return p ? 0 : 3;
}
