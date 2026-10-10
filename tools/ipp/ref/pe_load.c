#define _GNU_SOURCE
#include "pe_load.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <malloc.h>
#include <sys/mman.h>

#pragma pack(push,1)
typedef struct { uint16_t Machine, NumberOfSections; uint32_t TimeDateStamp, PtrSym, NumSym; uint16_t SizeOfOptionalHeader, Characteristics; } FILEHDR;
typedef struct { uint32_t VA, Size; } DDIR;
typedef struct { uint16_t Magic; uint8_t mj, mn; uint32_t SizeCode, SizeInit, SizeUninit, Entry, BaseCode; uint64_t ImageBase; uint32_t SecAlign, FileAlign;
  uint16_t a,b,c,d,e,f; uint32_t Win32Ver, SizeOfImage, SizeOfHeaders, Checksum; uint16_t Subsys, DllChar; uint64_t SR, SC, HR, HC; uint32_t LoaderFlags, NumDD; DDIR dd[16]; } OPT64;
typedef struct { char Name[8]; uint32_t VSize, VA, RawSize, RawPtr, r1, r2; uint16_t n1, n2; uint32_t Chars; } SEC;
typedef struct { uint32_t OFT, TDS, Fwd, Name, FT; } IMPDESC;
typedef struct { uint32_t Chars, TDS; uint16_t Maj, Min; uint32_t Name, Base, NumFuncs, NumNames, AddrFuncs, AddrNames, AddrOrd; } EXPDIR;
#pragma pack(pop)

/* ---- KERNEL32 の最小実装 (CRT 初期化は走らせないので dispatch 初期化経路で触られるものだけ) ---- */
static __thread uint32_t g_lasterr;
static MS void *k_GetProcessHeap(void) { return (void *)1; }
static MS void *k_HeapAlloc(void *h, uint32_t fl, size_t sz) { void *p = malloc(sz); if (p && (fl & 8)) memset(p, 0, sz); return p; }
static MS int   k_HeapFree(void *h, uint32_t fl, void *p) { free(p); return 1; }
static MS void *k_HeapReAlloc(void *h, uint32_t fl, void *p, size_t sz) { return realloc(p, sz); }
static MS size_t k_HeapSize(void *h, uint32_t fl, void *p) { return malloc_usable_size(p); }
static MS uint32_t k_GetLastError(void) { return g_lasterr; }
static MS void  k_SetLastError(uint32_t e) { g_lasterr = e; }
static MS int   k_ret1(void) { return 1; }
static MS int   k_ret0(void) { return 0; }
static MS void  k_nop(void) {}
static MS int   k_QPC(int64_t *p) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); *p = t.tv_sec * 1000000000LL + t.tv_nsec; return 1; }
static MS uint32_t k_GetCurrentThreadId(void) { return 1; }
static MS void *k_Encode(void *p) { return p; }
static void *g_tls[1088];
static MS uint32_t k_TlsAlloc(void) { static uint32_t n = 1; return n++; }
static MS void *k_TlsGetValue(uint32_t i) { return g_tls[i & 1023]; }
static MS int   k_TlsSetValue(uint32_t i, void *v) { g_tls[i & 1023] = v; return 1; }
static const struct { const char *n; void *f; } K32[] = {
  {"GetProcessHeap", k_GetProcessHeap}, {"HeapAlloc", k_HeapAlloc}, {"HeapFree", k_HeapFree}, {"HeapReAlloc", k_HeapReAlloc}, {"HeapSize", k_HeapSize},
  {"GetLastError", k_GetLastError}, {"SetLastError", k_SetLastError}, {"IsProcessorFeaturePresent", k_ret1}, {"QueryPerformanceCounter", k_QPC},
  {"GetCurrentThreadId", k_GetCurrentThreadId}, {"GetCurrentProcessId", k_GetCurrentThreadId}, {"EncodePointer", k_Encode},
  {"EnterCriticalSection", k_nop}, {"LeaveCriticalSection", k_nop}, {"DeleteCriticalSection", k_nop}, {"InitializeCriticalSectionAndSpinCount", k_ret1},
  {"IsDebuggerPresent", k_ret0}, {"TlsAlloc", k_TlsAlloc}, {"TlsGetValue", k_TlsGetValue}, {"TlsSetValue", k_TlsSetValue}, {"TlsFree", k_ret1},
  {"FlsAlloc", k_TlsAlloc}, {"FlsGetValue", k_TlsGetValue}, {"FlsSetValue", k_TlsSetValue}, {"FlsFree", k_ret1}, {"GetCurrentProcess", k_ret1},
};
static void trap_c(const char *name) { fprintf(stderr, "[pe_load] UNIMPLEMENTED KERNEL32 import called: %s\n", name); _exit(97); }
static uint8_t *g_tramp; static size_t g_tramp_n;
static void *make_trap(const char *name) {
  if (!g_tramp) { g_tramp = mmap(NULL, 1 << 16, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0); }
  uint8_t *p = g_tramp + g_tramp_n * 32; g_tramp_n++;
  uint64_t a = (uint64_t)strdup(name), h = (uint64_t)trap_c;
  p[0] = 0x48; p[1] = 0xBF; memcpy(p + 2, &a, 8);       /* mov rdi, name */
  p[10] = 0x49; p[11] = 0xBB; memcpy(p + 12, &h, 8);    /* mov r11, handler */
  p[20] = 0x41; p[21] = 0xFF; p[22] = 0xE3;             /* jmp r11 */
  return p;
}

int pe_load(const char *path, PE *pe) {
  FILE *f = fopen(path, "rb"); if (!f) { perror(path); return -1; }
  fseek(f, 0, SEEK_END); long fs = ftell(f); fseek(f, 0, SEEK_SET);
  uint8_t *fd = malloc(fs); if (fread(fd, 1, fs, f) != (size_t)fs) return -2; fclose(f);
  uint32_t pe_off = *(uint32_t *)(fd + 0x3c);
  FILEHDR *fh = (FILEHDR *)(fd + pe_off + 4); OPT64 *oh = (OPT64 *)(fd + pe_off + 4 + sizeof(FILEHDR));
  SEC *sec = (SEC *)((uint8_t *)oh + fh->SizeOfOptionalHeader);
  void *want = (void *)oh->ImageBase;
  uint8_t *base = mmap(want, oh->SizeOfImage, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
  if (base != want) { fprintf(stderr, "[pe_load] cannot map at preferred base %p (got %p)\n", want, base); return -3; }
  memcpy(base, fd, oh->SizeOfHeaders);
  for (int i = 0; i < fh->NumberOfSections; i++) memcpy(base + sec[i].VA, fd + sec[i].RawPtr, sec[i].RawSize < sec[i].VSize ? sec[i].RawSize : sec[i].VSize);
  /* imports */
  DDIR imp = oh->dd[1];
  for (IMPDESC *d = (IMPDESC *)(base + imp.VA); imp.VA && d->Name; d++) {
    uint64_t *oft = (uint64_t *)(base + (d->OFT ? d->OFT : d->FT)), *ft = (uint64_t *)(base + d->FT);
    for (; *oft; oft++, ft++) {
      const char *nm = (const char *)(base + (*oft & 0x7fffffffffffffffULL) + 2); void *fp = NULL;
      for (size_t k = 0; k < sizeof K32 / sizeof *K32; k++) if (!strcmp(K32[k].n, nm)) fp = K32[k].f;
      *ft = (uint64_t)(fp ? fp : make_trap(nm));
    }
  }
  pe->base = base; pe->image_base = oh->ImageBase; pe->size = oh->SizeOfImage;
  free(fd); return 0;
}

void *pe_export(const PE *pe, const char *name) {
  uint32_t pe_off = *(uint32_t *)(pe->base + 0x3c);
  OPT64 *oh = (OPT64 *)(pe->base + pe_off + 4 + sizeof(FILEHDR));
  EXPDIR *ed = (EXPDIR *)(pe->base + oh->dd[0].VA);
  uint32_t *names = (uint32_t *)(pe->base + ed->AddrNames), *funcs = (uint32_t *)(pe->base + ed->AddrFuncs); uint16_t *ords = (uint16_t *)(pe->base + ed->AddrOrd);
  int lo = 0, hi = ed->NumNames - 1;
  while (lo <= hi) { int mid = (lo + hi) / 2; int c = strcmp(name, (const char *)(pe->base + names[mid]));
    if (!c) return pe->base + funcs[ords[mid]]; if (c < 0) hi = mid - 1; else lo = mid + 1; }
  return NULL;
}
