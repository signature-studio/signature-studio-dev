/* shimx テストランナー。
 *   node x.cjs            : 全グループ (MT ビルドならスレッド系も)
 *   node x.cjs unimpl     : shim_unimplemented → 関数名を出して abort
 *   node x.cjs raise      : 未処理 RaiseException → fail-fast
 *   node x.cjs rtlunwind  : RtlUnwind (frame 未登録) → fail-fast
 *   node x.cjs sehnomatch : SEH frame はあるが捕捉 scope 無し → fail-fast (#171)
 *   node x.cjs sehbadtarget : RtlUnwindEx の targetFrame に一致 frame 無し → fail-fast (#171)
 *   node x.cjs strict     : strict モードで未知 GetProcAddress → fail-fast
 *   node x.cjs bstrfree   : strict モードで SysFreeString(管理外ポインタ) → fail-fast (R5)
 *   node x.cjs csnull     : 既定モードで EnterCriticalSection(NULL) → fail-fast (R7)
 *   node x.cjs exit       : ExitProcess(7) → exit hook + 終了コード 7
 *   node x.cjs deadlock   : ST ビルドで INFINITE 待ちが起こり得る場合 fail-fast
 *   node x.cjs shbrowse   : SHBrowseForFolderW の GetProcAddress → 未対応として fail-fast (SHX-T22 #1179)
 *   node x.cjs ifiledialog: CoCreateInstance(FileOpenDialog) → 未対応として fail-fast (SHX-T33 #2916)
 *   node x.cjs ifilesave  : CoCreateInstance(FileSaveDialog) → 未対応として fail-fast (SHX-T33 #2916)
 */
#include "test_common.h"

static void exit_hook(UINT code) { fprintf(stderr, "[shimx-test] exit hook code=%u\n", code); }

int main(int argc, char** argv) {
    const char* mode = argc > 1 ? argv[1] : "all";
    if (!strcmp(mode, "unimpl")) { shim_unimplemented("DestroyWindow_NonImplemented_Example"); return 0; }
    if (!strcmp(mode, "raise")) { uint64_t a[1] = { 0x1234 }; RaiseException(0xE06D7363u, EXCEPTION_NONCONTINUABLE, 1, a); return 0; }
    if (!strcmp(mode, "rtlunwind")) { RtlUnwind(NULL, NULL, NULL, NULL); return 0; }
    if (!strcmp(mode, "sehnomatch")) { seh_failfast_nomatch(); return 0; }
    if (!strcmp(mode, "sehbadtarget")) { seh_failfast_badtarget(); return 0; }
    if (!strcmp(mode, "strict")) {
        shimx_set_strict(1);
        GetProcAddress(GetModuleHandleW(W("kernel32.dll")), "NoSuchKernelApi");
        return 0;
    }
    if (!strcmp(mode, "bstrfree")) {                                       /* R5: strict では管理外 BSTR を fail-fast */
        shimx_set_strict(1);
        uint64_t dummy[2] = { 0, 0 };
        SysFreeString((BSTR)&dummy[1]);
        return 0;
    }
    if (!strcmp(mode, "csnull")) {                                         /* R7: 既定は fail-fast (Win32 AV 相当) */
        EnterCriticalSection(NULL);
        return 0;
    }
    if (!strcmp(mode, "dwrite")) {                                         /* KH-20: DirectWrite は未対応 = 名前を出して fail-fast */
        GetProcAddress(GetModuleHandleW(W("dwrite.dll")), "DWriteCreateFactory");
        return 0;
    }
    if (!strcmp(mode, "shbrowse")) {                                       /* SHX-T22 #1179: フォルダ選択は未対応 = 名前を出して fail-fast */
        GetProcAddress(GetModuleHandleW(W("shell32.dll")), "SHBrowseForFolderW");
        return 0;
    }
    if (!strcmp(mode, "ifiledialog") || !strcmp(mode, "ifilesave")) {      /* SHX-T33 #2916: IFileDialog の CoCreateInstance は未対応 = 名前を出して fail-fast */
        GUID clsid; LPVOID obj = NULL;
        CLSIDFromString(W(!strcmp(mode, "ifiledialog") ? "{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}" : "{C0B4E2F3-BA21-4773-8DBA-335EC946EB8B}"), &clsid);
        CoCreateInstance((uint64_t)(uintptr_t)&clsid, NULL, 1, &clsid, &obj);
        return 0;
    }
    if (!strcmp(mode, "exit")) { shimx_set_exit_hook(exit_hook); ExitProcess(7); return 0; }
    if (!strcmp(mode, "deadlock")) {
        HANDLE e = CreateEventW(NULL, TRUE, FALSE, NULL);
        WaitForSingleObject(e, INFINITE);
        return 0;
    }
#if defined(__EMSCRIPTEN_PTHREADS__)
    const int mt = 1;
    const char* build = "mt(pthreads)";
#else
    const int mt = 0;
    const char* build = "st";
#endif
    run_core_tests(mt);          fprintf(stderr, "[shimx-test] core OK\n");
    run_sys_tests();             fprintf(stderr, "[shimx-test] sys OK\n");
    run_ole_shell_tests();       fprintf(stderr, "[shimx-test] ole/shell OK\n");
    run_link_tests(mt);          fprintf(stderr, "[shimx-test] link OK\n");
    run_cbtrans_tests(mt);       fprintf(stderr, "[shimx-test] cbtrans OK\n");
    run_midi_tests(mt);          fprintf(stderr, "[shimx-test] midi OK\n");
    run_seh_tests();             fprintf(stderr, "[shimx-test] seh OK\n");
    run_absent_path_tests();     fprintf(stderr, "[shimx-test] absent-path OK\n");
    printf("[shimx-test] ALL PASS (build=%s)\n", build);
    return 0;
}
