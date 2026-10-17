#include <windows.h>
#include <stdio.h>

typedef int (*fn_ptr_int)(void *);

#define STUB(n) static long __stdcall s##n(void *self, void *a, void *b, void *c) { \
    printf("slot[%d] self=%p a=%p b=%p c=%p\n", n, self, a, b, c); fflush(stdout); return 0; }
STUB(0) STUB(1) STUB(2) STUB(3) STUB(4) STUB(5) STUB(6) STUB(7)
STUB(8) STUB(9) STUB(10) STUB(11) STUB(12) STUB(13) STUB(14) STUB(15)

static void *vtbl2[16] = {
    (void *)s0, (void *)s1, (void *)s2, (void *)s3, (void *)s4, (void *)s5, (void *)s6, (void *)s7,
    (void *)s8, (void *)s9, (void *)s10, (void *)s11, (void *)s12, (void *)s13, (void *)s14, (void *)s15
};
static void *obj2[4] = { vtbl2, NULL, NULL, NULL };

static long __stdcall qi_ok(void *self, void *iid, void **out) {
    printf("QI self=%p iid=%p -> S_OK\n", self, iid);
    fflush(stdout);
    if (out) *out = (void *)obj2;
    return 0;
}
static unsigned long __stdcall ref_stub(void *self) { return 1; }
static void *vtbl[3] = { (void *)qi_ok, (void *)ref_stub, (void *)ref_stub };

int main(int argc, char **argv) {
    const char *path = argc > 1 ? argv[1] : "HeartCore.core_64";
    HMODULE h = LoadLibraryExA(path, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!h) { printf("LOAD FAIL err=%lu\n", GetLastError()); return 2; }
    printf("LOAD OK handle=%p\n", (void *)h);
    FARPROC st = GetProcAddress(h, "ACFStartup");
    if (!st) { printf("ACFStartup missing\n"); return 3; }
    void *obj[4] = { vtbl, NULL, NULL, NULL };
    fflush(stdout);
    int r = ((fn_ptr_int)st)((void *)obj);
    printf("ACFStartup() = %d (0x%x)\n", r, (unsigned)r);
    fflush(stdout);
    return 0;
}
