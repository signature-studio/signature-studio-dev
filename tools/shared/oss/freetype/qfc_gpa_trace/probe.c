#include <windows.h>
#include <stdio.h>
int main(void) {
    HMODULE k = GetModuleHandleA("kernel32.dll");
    printf("ctrl GetLastError=%p\n", (void *)GetProcAddress(k, "GetLastError"));
    fflush(stdout);
    HMODULE h = LoadLibraryA("QuickFontCache_x64.dll");
    printf("LoadLibrary=%p err=%lu\n", (void *)h, GetLastError());
    fflush(stdout);
    if (h) {
        printf("InitDll=%p\n", (void *)GetProcAddress(h, "InitDll"));
        printf("CreateVST3Instance=%p\n", (void *)GetProcAddress(h, "CreateVST3Instance"));
        fflush(stdout);
    }
    return 0;
}
