#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

typedef int (*fn_ptr_int)(void *);

int main(int argc, char **argv) {
    const char *path = argc > 1 ? argv[1] : "HeartCore.core_64";
    unsigned long long arg = argc > 2 ? strtoull(argv[2], NULL, 16) : 0;
    HMODULE h = LoadLibraryExA(path, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!h) {
        printf("LOAD FAIL err=%lu\n", GetLastError());
        return 2;
    }
    printf("LOAD OK handle=%p\n", (void *)h);
    FARPROC st = GetProcAddress(h, "ACFStartup");
    printf("ACFStartup arg=%llx\n", arg);
    fflush(stdout);
    if (st) printf("ACFStartup() = %d\n", ((fn_ptr_int)st)((void *)arg));
    else printf("ACFStartup missing\n");
    fflush(stdout);
    return 0;
}
