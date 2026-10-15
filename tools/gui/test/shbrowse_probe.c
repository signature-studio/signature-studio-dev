/* SHX-T34 (#2917): gui 側 node + mock 検査の probe。tools/gui/test/shbrowse_failfast.sh が gui + shimx の同一 wasm にリンクして使う。
 *   node x.cjs a   : GetProcAddress(shell32.dll, "SHBrowseForFolderA") → 未対応として名前を出して fail-fast (abort)
 *   node x.cjs w   : GetProcAddress(shell32.dll, "SHBrowseForFolderW") → 同上
 *   node x.cjs ok  : 対照。GetProcAddress(shell32.dll, "ShellExecuteW") は解決される (fail-fast にならない)
 * fail-fast が効かない構成では GetProcAddress が戻るので rc=0 になり、検査側が FAIL にする。 */
#include <stdio.h>
#include <string.h>
#include "shimx.h"

static WCHAR* wstr(const char* s) {
    static WCHAR buf[256];
    int n = shimx_utf8_to_utf16(s, -1, buf, 255);
    buf[n < 0 ? 0 : n] = 0;
    return buf;
}

int main(int argc, char** argv) {
    const char* mode = argc > 1 ? argv[1] : "";
    const char* name = !strcmp(mode, "a") ? "SHBrowseForFolderA"
                     : !strcmp(mode, "w") ? "SHBrowseForFolderW"
                     : "ShellExecuteW";
    HMODULE sh = GetModuleHandleW(wstr("shell32.dll"));
    void* fn = GetProcAddress(sh, name);
    fprintf(stderr, "[shbrowse-probe] %s %s\n", name, fn ? "resolved" : "NULL");
    return fn ? 0 : 3;
}
