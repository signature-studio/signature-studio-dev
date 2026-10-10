/* plugin_bal_entry.c — multi-load 試験用の 2 つ目の module: Fruity Balance の SIMD mix kernel (tools/plugins/lift/t0_balance, RetDec lift 済み IR)
 * を VST2 風 facade (hostbridge guest ABI: hb_plugin_init / hb_scratch / VSTPluginMain / hb_icall) で包んだ surrogate.
 * kernel 0x5dee90: mix(src, dst, n, &g[8]) — FL 内部形式 (L,R interleaved f32) の 2x2 matrix / scale / ramp.
 * 目的は「別 DLL / 別 lift 系統 / 別 base の module が OTT と同じ host・同じ bridge で同時に動く」ことの実証 (DSP 正当性の主張ではない).
 * アドレス敷設は一切不要 (kernel は image を読まない): 全作業領域は静的配列 = GLOBAL_BASE 以降.
 */
#include <stdint.h>
#include <string.h>
#include <emscripten.h>
#include "vst2_abi.h"

extern uint64_t function_5dee90(uint64_t src, uint64_t dst, uint64_t n, uint64_t g);
extern int32_t hb_host_call(uint32_t eff, int32_t op, int32_t idx, uint32_t vlo, uint32_t vhi, uint32_t ptr, float opt);

enum { HB_FN_DISPATCHER = 0x1000, HB_FN_PROCESS_LEGACY, HB_FN_SETPARAM, HB_FN_GETPARAM, HB_FN_PROCESS_REPLACING, HB_FN_PROCESS_DOUBLE };
#define MAXINST 8
#define MAXBLOCK 4096
typedef struct { HbAEffect e; float g[8]; uint32_t used; int32_t program; float sr; } BalInst;
static BalInst g_inst[MAXINST];
static uint8_t g_scratch[1 << 20] __attribute__((aligned(16)));
static float g_il[2 * MAXBLOCK + 8] __attribute__((aligned(16)));
static float g_ol[2 * MAXBLOCK + 16] __attribute__((aligned(16)));
static uint32_t g_audio_master, g_init;
static const char* const k_name[8] = { "G0 L>L", "G1 R>R", "G2 R>L", "G3 L>R", "R4", "R5", "R6", "R7" };

EMSCRIPTEN_KEEPALIVE int32_t hb_plugin_init(void) { g_init = 1; return 0; }
EMSCRIPTEN_KEEPALIVE uint32_t hb_scratch(void) { return (uint32_t)(uintptr_t)g_scratch; }

static inline float bits2f(uint64_t b) { uint32_t u = (uint32_t)b; float f; memcpy(&f, &u, 4); return f; }
static inline uint64_t f2bits(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }

EMSCRIPTEN_KEEPALIVE uint64_t VSTPluginMain(uint64_t audioMaster) {
  hb_plugin_init();
  g_audio_master = (uint32_t)audioMaster;
  if (g_audio_master && !hb_host_call(0, audioMasterVersion, 0, 0, 0, 0, 0.f)) return 0;
  for (int i = 0; i < MAXINST; i++) {
    if (g_inst[i].used) continue;
    BalInst* b = &g_inst[i]; memset(b, 0, sizeof *b); b->used = 1; b->sr = 44100.f;
    b->g[0] = 0.8f; b->g[1] = 0.5f;
    HbAEffect* e = &b->e;
    e->magic = HB_EFFECT_MAGIC; e->numPrograms = 1; e->numParams = 8; e->numInputs = 2; e->numOutputs = 2;
    e->flags = effFlagsCanReplacing; e->ioRatio = 1.0f; e->uniqueID = 0x42616c4b; /* 'BalK' */ e->version = 1;
    e->dispatcher = HB_FN_DISPATCHER; e->process = HB_FN_PROCESS_LEGACY; e->setParameter = HB_FN_SETPARAM; e->getParameter = HB_FN_GETPARAM;
    e->processReplacing = HB_FN_PROCESS_REPLACING; e->processDoubleReplacing = HB_FN_PROCESS_DOUBLE; e->object = (uint64_t)(uintptr_t)b;
    return (uint64_t)(uintptr_t)e;
  }
  return 0;
}

static void put_str(uint32_t ptr, const char* s) { if (ptr) strcpy((char*)(uintptr_t)ptr, s); }

static int64_t do_dispatch(BalInst* b, int32_t op, int32_t idx, int64_t val, uint32_t ptr, float opt) {
  switch (op) {
    case effOpen: return 0;
    case effClose: b->used = 0; return 1;
    case effSetProgram: b->program = (int32_t)val; return 0;
    case effGetProgram: return b->program;
    case effSetSampleRate: b->sr = opt; return 0;
    case effGetParamName: put_str(ptr, (idx >= 0 && idx < 8) ? k_name[idx] : ""); return 0;
    case effGetParamLabel: put_str(ptr, ""); return 0;
    case effGetParamDisplay: put_str(ptr, ""); return 0;
    case effCanBeAutomated: return 1;
    case effGetPlugCategory: return 1;
    case effGetEffectName: put_str(ptr, "Balance kernel"); return 1;
    case effGetProductString: put_str(ptr, "Fruity Balance (kernel)"); return 1;
    case effGetVendorString: put_str(ptr, "Image-Line"); return 1;
    case effGetVendorVersion: return 1;
    case effGetVstVersion: return 2400;
    default: return 0;
  }
}

EMSCRIPTEN_KEEPALIVE uint64_t hb_icall(uint64_t fn, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3, uint64_t a4, uint64_t a5) {
  HbAEffect* e = (HbAEffect*)(uintptr_t)a0; BalInst* b = e ? (BalInst*)(uintptr_t)e->object : 0;
  switch (fn) {
    case HB_FN_DISPATCHER: return (uint64_t)do_dispatch(b, (int32_t)a1, (int32_t)a2, (int64_t)a3, (uint32_t)a4, bits2f(a5));
    case HB_FN_SETPARAM: if ((int32_t)a1 >= 0 && (int32_t)a1 < 8) b->g[(int32_t)a1] = bits2f(a2); return 0;
    case HB_FN_GETPARAM: return ((int32_t)a1 >= 0 && (int32_t)a1 < 8) ? f2bits(b->g[(int32_t)a1]) : 0;
    case HB_FN_PROCESS_REPLACING: {
      int32_t n = (int32_t)a3; if (n < 0 || n > MAXBLOCK) return 0;
      const float** in = (const float**)(uintptr_t)a1; float** out = (float**)(uintptr_t)a2;
      /* 型は Win64 の 8B ポインタ (hb 規約): 下位 32bit のみ使用 */
      const float* l = (const float*)(uintptr_t)(((const uint64_t*)in)[0]); const float* r = (const float*)(uintptr_t)(((const uint64_t*)in)[1]);
      for (int i = 0; i < n; i++) { g_il[2 * i] = l[i]; g_il[2 * i + 1] = r[i]; }
      function_5dee90((uint64_t)(uintptr_t)g_il, (uint64_t)(uintptr_t)g_ol, (uint64_t)n, (uint64_t)(uintptr_t)b->g);
      float* ol = (float*)(uintptr_t)(((uint64_t*)out)[0]); float* orr = (float*)(uintptr_t)(((uint64_t*)out)[1]);
      for (int i = 0; i < n; i++) { ol[i] = g_ol[2 * i]; orr[i] = g_ol[2 * i + 1]; }
      return 0;
    }
    default: return 0;
  }
}
