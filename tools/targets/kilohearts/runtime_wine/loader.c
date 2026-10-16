#include <string.h>
#include <windows.h>
#include <stdio.h>

typedef int (*fn_void_int)(void);

int main(int argc, char **argv) {
    const char *path = argc > 1 ? argv[1] : "HeartCore.core_64";
    const char *list = argc > 2 ? argv[2] : "exports.txt";
    HMODULE h = LoadLibraryExA(path, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!h) {
        printf("LOAD FAIL err=%lu\n", GetLastError());
        return 2;
    }
    printf("LOAD OK handle=%p\n", (void *)h);

    FILE *f = fopen(list, "r");
    if (!f) {
        printf("no export list %s\n", list);
        return 3;
    }
    char name[256];
    int total = 0, found = 0;
    while (fgets(name, sizeof name, f)) {
        name[strcspn(name, "\r\n")] = 0;
        if (!name[0]) continue;
        total++;
        if (GetProcAddress(h, name)) found++;
        else printf("MISSING %s\n", name);
    }
    fclose(f);
    printf("exports resolved %d/%d\n", found, total);

    FARPROC sdk = GetProcAddress(h, "ACFGetSDKVersion");
    if (sdk) printf("ACFGetSDKVersion() = %d\n", ((fn_void_int)sdk)());
    fflush(stdout);

    FARPROC st = GetProcAddress(h, "ACFStartup");
    if (st) printf("ACFStartup() = %d\n", ((fn_void_int)st)());
    else printf("ACFStartup missing\n");
    fflush(stdout);

    FARPROC sd = GetProcAddress(h, "ACFShutdown");
    if (sd) printf("ACFShutdown() = %d\n", ((fn_void_int)sd)());
    fflush(stdout);
    return 0;
}
