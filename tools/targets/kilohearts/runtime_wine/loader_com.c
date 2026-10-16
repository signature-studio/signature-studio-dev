#include <windows.h>
#include <stdio.h>

typedef int (*fn_ptr_int)(void *);

static long __stdcall qi_fail(void *self, void *iid, void **out) {
    if (out) *out = NULL;
    printf("QueryInterface called self=%p iid=%p\n", self, iid);
    fflush(stdout);
    return (long)0x80004002;
}

static unsigned long __stdcall ref_stub(void *self) { return 1; }

static void *vtbl[3] = { (void *)qi_fail, (void *)ref_stub, (void *)ref_stub };

int main(int argc, char **argv) {
    const char *path = argc > 1 ? argv[1] : "HeartCore.core_64";
    HMODULE h = LoadLibraryExA(path, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!h) {
        printf("LOAD FAIL err=%lu\n", GetLastError());
        return 2;
    }
    printf("LOAD OK handle=%p\n", (void *)h);
    FARPROC st = GetProcAddress(h, "ACFStartup");
    if (!st) {
        printf("ACFStartup missing\n");
        return 3;
    }
    void *obj[4] = { vtbl, NULL, NULL, NULL };
    printf("ACFStartup(fake IUnknown %p) ...\n", (void *)obj);
    fflush(stdout);
    int r = ((fn_ptr_int)st)((void *)obj);
    printf("ACFStartup() = %d (0x%x)\n", r, (unsigned)r);
    fflush(stdout);
    return 0;
}
