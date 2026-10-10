/* host_vst2.c — hostbridge PoC: 最小 VST2 ホスト ("FL 側" の代役).
 *
 * freestanding wasm32 (libc 無し)。Fruity Wrapper (TVSTPlugin.Create 0x7a9db0) の手順をそのまま再現する:
 *   LoadLibraryW → GetProcAddress 26 名試行 (0x7a8f90 の名前表) → main(audioMaster) → magic 検査 →
 *   resvd1 = host this → effOpen → effSetSampleRate/BlockSize → effMainsChanged(1) →
 *   effGetEffectName/VendorString/ProductString/VstVersion/PlugCategory/ParamName
 * ABI は x64 lift 済みコードと同形にするため、AEffect は Win64 配置 (8B ポインタ), 関数ポインタ/引数は u64.
 * 外界との接点は 4 つの import (module "hb") のみ: LoadLibraryW / GetProcAddress / FreeLibrary / icall.
 */
#include <stdint.h>
#include <stddef.h>
#include "vst2_abi.h"

#define HB_IMPORT(n) __attribute__((import_module("hb"), import_name(n)))
HB_IMPORT("LoadLibraryW") extern uint64_t hb_LoadLibraryW(const uint16_t* path);
HB_IMPORT("GetProcAddress") extern uint64_t hb_GetProcAddress(uint64_t h, const char* name);
HB_IMPORT("FreeLibrary") extern int32_t hb_FreeLibrary(uint64_t h);
HB_IMPORT("icall") extern uint64_t hb_icall(uint64_t fn, uint64_t a0, uint64_t a1, uint64_t a2,
                                            uint64_t a3, uint64_t a4, uint64_t a5);

#define EXPORT __attribute__((visibility("default"), used))

static uint8_t g_arena[1 << 20] __attribute__((aligned(16)));
static uint32_t g_arena_top;
EXPORT void* host_alloc(uint32_t n) {
  n = (n + 15u) & ~15u;
  if (g_arena_top + n > sizeof g_arena) return 0;
  void* p = &g_arena[g_arena_top];
  g_arena_top += n;
  return p;
}

typedef struct {
  char name[64], vendor[64], product[64];
  int32_t vstVersion, category, vendorVersion;
  int32_t numPrograms, numParams, numInputs, numOutputs, flags, uniqueID, version;
  int32_t getProcTries;           /* GetProcAddress を何回試したか (Fruity Wrapper 名前表 26 種) */
  int32_t magicOk;
  int32_t am_calls[64];           /* audioMaster 受信 opcode 別カウンタ */
  int32_t hostSampleRate, hostBlock;
  uint64_t hmodule;
} HostInfo;
static HostInfo g_info;
EXPORT HostInfo* host_info(void) { return &g_info; }

static int hstrlen(const char* s) { int n = 0; while (s[n]) n++; return n; }
static int hstreq(const char* a, const char* b) { while (*a && *a == *b) { a++; b++; } return *a == *b; }
static void hcpy(char* d, const char* s, int cap) { int i = 0; for (; s[i] && i < cap - 1; i++) d[i] = s[i]; d[i] = 0; }
static uint64_t f2b(float f) { union { float f; uint32_t u; } x; x.f = f; return x.u; }
static float b2f(uint64_t b) { union { float f; uint32_t u; } x; x.u = (uint32_t)b; return x.f; }

static struct { double samplePos, sampleRate, nanoSeconds, ppqPos, tempo, barStartPos, cycleStartPos, cycleEndPos;
                int32_t timeSigNum, timeSigDen, smpteOffset, smpteFrameRate, samplesToNextClock, flags; } g_time =
    {12345.0, 44100.0, 0.0, 0.0, 130.0, 0.0, 0.0, 0.0, 4, 4, 0, 0, 0, 0x2000};

/* Fruity Wrapper audioMaster (0x7a87c0) の再現: version=0x960, vendor="Image-Line", product="Fruity Wrapper",
 * vendorVersion=0x271a, canDo 表. それ以外は汎用 (FUN_007abca0) 側 = ここでは sampleRate/blockSize/updateDisplay のみ. */
EXPORT int64_t host_audio_master(uint64_t eff, int32_t op, int32_t idx, int64_t val, uint64_t ptr, float opt) {
  (void)eff; (void)idx; (void)val; (void)opt;
  if (op >= 0 && op < 64) g_info.am_calls[op]++;
  switch (op) {
    case audioMasterVersion: return 0x960;
    case audioMasterCurrentId: return 0;
    case audioMasterGetVendorString: hcpy((char*)(uintptr_t)ptr, "Image-Line", 64); return 1;
    case audioMasterGetProductString: hcpy((char*)(uintptr_t)ptr, "Fruity Wrapper", 64); return 1;
    case audioMasterGetVendorVersion: return 0x271a;
    case audioMasterGetSampleRate: return g_info.hostSampleRate;
    case audioMasterGetBlockSize: return g_info.hostBlock;
    case audioMasterUpdateDisplay: return 0;
    case audioMasterGetTime: return (int64_t)(uintptr_t)&g_time; /* VstTimeInfo* (0x58 bytes) */
    case audioMasterProcessEvents: { const int32_t* ev = (const int32_t*)(uintptr_t)ptr; return ev ? ev[0] * 10 + 1 : -1; }
    case audioMasterCanDo: {
      const char* s = (const char*)(uintptr_t)ptr;
      static const char* const yes[] = {"sendVstEvents", "sendVstMidiEvent", "supportShell", "sendVstTimeInfo",
                                        "supplyIdle", "acceptIOChanges", "receiveVstMidiEvent", "shellCategory",
                                        "sizeWindow", 0};
      static const char* const no1[] = {"receiveVstEvents", "receiveVstTimeInfo", "reportConnectionChanges",
                                        "asyncProcessing", "offline", 0};
      for (int i = 0; yes[i]; i++) if (hstreq(s, yes[i])) return 1;
      for (int i = 0; no1[i]; i++) if (hstreq(s, no1[i])) return -1;
      return 0;
    }
    default: return 0;
  }
}

/* 0x8e5d08 の名前表 (UTF-16 → ASCII) 26 種, 順序そのまま */
static const char* const k_main_names[26] = {
  "VstPluginMain", "VSTPluginMain", "main", "maiN", "maIn", "maIN", "mAin", "mAiN", "mAIn", "mAIN",
  "Main", "MaiN", "MaIn", "MaIN", "MAin", "MAiN", "MAIn", "MAIN",
  "vstpluginmain", "VSTPluginMain", "VSTPluginmain", "VSTpluginmain", "VSTpluginMain",
  "vstPluginMain", "vstPluginmain", "vstpluginMain",
};

static uint64_t disp(HbAEffect* e, int32_t op, int32_t idx, int64_t val, void* ptr, float opt) {
  return hb_icall(e->dispatcher, (uint64_t)(uintptr_t)e, (uint64_t)(int64_t)op, (uint64_t)(int64_t)idx,
                  (uint64_t)val, (uint64_t)(uintptr_t)ptr, f2b(opt));
}

/* 戻り: AEffect* (host 側 proxy) or 0 */
EXPORT HbAEffect* host_load_plugin(const uint16_t* wpath, int32_t sampleRate, int32_t block) {
  g_info.hostSampleRate = sampleRate;
  g_info.hostBlock = block;
  uint64_t h = hb_LoadLibraryW(wpath);
  g_info.hmodule = h;
  if (!h) return 0;
  uint64_t fn = 0;
  int tries = 0;
  for (int i = 0; i < 26 && !fn; i++) { fn = hb_GetProcAddress(h, k_main_names[i]); tries++; }
  g_info.getProcTries = tries;
  if (!fn) { hb_FreeLibrary(h); return 0; }
  /* (*main)(FUN_007a87c0) 相当. audioMaster = host 関数ポインタ(= wasm table index) */
  uint64_t r = hb_icall(fn, (uint64_t)(uintptr_t)&host_audio_master, 0, 0, 0, 0, 0);
  HbAEffect* e = (HbAEffect*)(uintptr_t)r;
  if (!e || e->magic != (int32_t)HB_EFFECT_MAGIC) { g_info.magicOk = 0; hb_FreeLibrary(h); return 0; }
  g_info.magicOk = 1;
  e->resvd1 = (uint64_t)(uintptr_t)&g_info; /* Fruity Wrapper: effect+0x40 = TVSTPlugin this */
  disp(e, effOpen, 0, 0, 0, 0.f);
  disp(e, effSetSampleRate, 0, 0, 0, (float)sampleRate);
  disp(e, effSetBlockSize, 0, block, 0, 0.f);
  disp(e, effMainsChanged, 0, 1, 0, 0.f);
  disp(e, effGetEffectName, 0, 0, g_info.name, 0.f);
  disp(e, effGetVendorString, 0, 0, g_info.vendor, 0.f);
  disp(e, effGetProductString, 0, 0, g_info.product, 0.f);
  g_info.vendorVersion = (int32_t)disp(e, effGetVendorVersion, 0, 0, 0, 0.f);
  g_info.vstVersion = (int32_t)disp(e, effGetVstVersion, 0, 0, 0, 0.f);
  g_info.category = (int32_t)disp(e, effGetPlugCategory, 0, 0, 0, 0.f);
  g_info.numPrograms = e->numPrograms;
  g_info.numParams = e->numParams;
  g_info.numInputs = e->numInputs;
  g_info.numOutputs = e->numOutputs;
  g_info.flags = e->flags;
  g_info.uniqueID = e->uniqueID;
  g_info.version = e->version;
  return e;
}

EXPORT int32_t host_param_name(HbAEffect* e, int32_t idx, char* buf) {
  buf[0] = 0;
  disp(e, effGetParamName, idx, 0, buf, 0.f);
  return hstrlen(buf);
}
EXPORT int32_t host_param_display(HbAEffect* e, int32_t idx, char* buf) {
  buf[0] = 0;
  disp(e, effGetParamDisplay, idx, 0, buf, 0.f);
  return hstrlen(buf);
}
EXPORT void host_set_param(HbAEffect* e, int32_t idx, float v) {
  hb_icall(e->setParameter, (uint64_t)(uintptr_t)e, (uint64_t)(int64_t)idx, f2b(v), 0, 0, 0);
}
EXPORT float host_get_param(HbAEffect* e, int32_t idx) {
  return b2f(hb_icall(e->getParameter, (uint64_t)(uintptr_t)e, (uint64_t)(int64_t)idx, 0, 0, 0, 0));
}
/* Fruity Wrapper の FUN_007ad040: flags が canReplacing なら +0x78, でなければ +0x10 */
EXPORT void host_process(HbAEffect* e, float** in, float** out, int32_t n) {
  uint64_t fn = (e->flags & effFlagsCanReplacing) ? e->processReplacing : e->process;
  hb_icall(fn, (uint64_t)(uintptr_t)e, (uint64_t)(uintptr_t)in, (uint64_t)(uintptr_t)out, (uint64_t)(int64_t)n, 0, 0);
}
EXPORT int32_t host_dispatch(HbAEffect* e, int32_t op, int32_t idx, int64_t val, void* ptr, float opt) {
  return (int32_t)disp(e, op, idx, val, ptr, opt);
}
EXPORT void host_close(HbAEffect* e) {
  disp(e, effMainsChanged, 0, 0, 0, 0.f);
  disp(e, effClose, 0, 0, 0, 0.f);
  hb_FreeLibrary(g_info.hmodule);
}
