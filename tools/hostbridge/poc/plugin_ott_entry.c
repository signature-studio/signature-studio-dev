/* plugin_ott_entry.c — hostbridge PoC: OTT (lift 済み DSP closure) 用の VST2 入口 surrogate.
 *
 * 位置づけ: M6〜M10 の lift closure (166 関数) は OTTProcessor の DSP 部 (ctor / setParameter /
 * resume / processReplacing) のみで、VSTPluginMain / createEffectInstance / dispatcher
 * (AudioEffectX::dispatcher の巨大 switch) / AEffect の static thunk 群は closure 外。
 * 本ファイルはその「closure 外 SDK glue」を、ネイティブ DLL の逆アセンブル (HOSTBRIDGE.md §1.4) で
 * 確認した動作の最小再現として持つ。closure を VSTPluginMain まで拡張できた時点で不要になる
 * (= 差し替え点は hb_icall() 1 箇所のみ)。
 *
 * ネイティブ VSTPluginMain (0x180128ba0) の動作:
 *   if (!audioMaster(NULL, audioMasterVersion, 0,0,NULL,0.f)) return NULL;
 *   obj = createEffectInstance(audioMaster);  // 0x180125b40: new(0x328) → OTTProcessor ctor (0x18011d400)
 *                                             //   → vftable=OTTVST, uniqueID='XfTT', OTTEditor(0x248) 生成,
 *                                             //   → 0x180120800(obj) 呼出
 *   return obj->getAeffect();                 // vtable+0xf0
 *
 * guest ABI 契約 (全 plugin module 共通 / HOSTBRIDGE.md §2.3):
 *   hb_plugin_init(), hb_scratch(), VSTPluginMain(u64), hb_icall(u64 fn, u64 a0..a5)
 *   + import hb_host_call() (plugin→host upcall)
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <emscripten.h>
#include "vst2_abi.h"

/* --- lift 済み closure (tools/m10 の ott_m10.ll 由来; i64 ABI) --- */
extern uint64_t function_18011d400(uint64_t obj, uint64_t audioMaster);               /* OTTProcessor::OTTProcessor */
extern uint64_t function_180120af0(uint64_t obj, uint64_t idx, uint64_t f32bits);     /* OTTProcessor::setParameter */
extern uint64_t function_180120800(uint64_t obj);                                     /* resume 相当 */
extern uint64_t function_18011ec20(uint64_t obj, uint64_t in, uint64_t out, uint64_t n); /* processReplacing */
extern void m6_data_install(void);

extern int32_t hb_host_call(uint32_t eff, int32_t op, int32_t idx, uint32_t vlo, uint32_t vhi,
                            uint32_t ptr, float opt);

/* --- メモリ配置: PE image (0x30000000..0x30300800) の後ろ. lift 側 malloc (emscripten dlmalloc) は
 *     __heap_base(≈0x10xxxxxx) から伸びるので 0x30400000 以降は 500MB 割当までは衝突しない. --- */
#define HB_ARENA 0x30400000u
#define HB_SCRATCH_BASE (HB_ARENA)
#define HB_SCRATCH_SIZE 0x00100000u /* 1MB: in/out ch×8 × 4096 frames + 文字列 + 構造体 */
#define HB_INST_BASE (HB_ARENA + HB_SCRATCH_SIZE)
#define HB_INST_STRIDE 0x1000u
#define HB_INST_MAX 8
#define OTT_OBJ_SIZE 0x328u /* createEffectInstance の operator new(0x328) */

/* AEffect の関数ポインタ欄に入れる guest 側 fn id */
enum {
  HB_FN_DISPATCHER = 0x1000, HB_FN_PROCESS_LEGACY, HB_FN_SETPARAM, HB_FN_GETPARAM,
  HB_FN_PROCESS_REPLACING, HB_FN_PROCESS_DOUBLE,
};

typedef struct {
  uint32_t used;
  float params[32];
  float sampleRate;
  int32_t blockSize;
  int32_t program;
} OttShadow; /* obj の後ろ (obj+0x400) */

#define INST(i) ((uint8_t*)(uintptr_t)(HB_INST_BASE + (uint32_t)(i) * HB_INST_STRIDE))
#define SHADOW(obj) ((OttShadow*)((uint8_t*)(uintptr_t)(obj) + 0x400))

static const char* const k_param_name[19] = {
  "Depth", "Time", "In Gain", "Out Gain", "Clean XOV", "Thresh L", "Thresh M", "Thresh H",
  "Gain L", "Gain M", "Gain H", "Byp Upwd L", "Byp Upwd M", "Byp Upwd H",
  "Byp Dnwd L", "Byp Dnwd M", "Byp Dnwd H", "Upwd Strgth", "Dnwd Strgth",
};

static uint32_t g_audio_master; /* host の audioMaster (guest 側から見える slot) */
static uint32_t g_initialised;

static inline float bits2f(uint64_t b) { uint32_t u = (uint32_t)b; float f; memcpy(&f, &u, 4); return f; }
static inline uint64_t f2bits(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }

EMSCRIPTEN_KEEPALIVE int32_t hb_plugin_init(void) {
  if (g_initialised) return 0;
  m6_data_install();
  memset((void*)(uintptr_t)HB_ARENA, 0, HB_SCRATCH_SIZE + HB_INST_MAX * HB_INST_STRIDE);
  g_initialised = 1;
  return 0;
}

EMSCRIPTEN_KEEPALIVE uint32_t hb_scratch(void) { return HB_SCRATCH_BASE; }

static int32_t audio_master(uint32_t eff, int32_t op, int32_t idx, int64_t val, uint32_t ptr, float opt) {
  if (!g_audio_master) return 0;
  return hb_host_call(eff, op, idx, (uint32_t)val, (uint32_t)((uint64_t)val >> 32), ptr, opt);
}

EMSCRIPTEN_KEEPALIVE uint64_t VSTPluginMain(uint64_t audioMaster) {
  hb_plugin_init();
  g_audio_master = (uint32_t)audioMaster;
  /* ネイティブ同様: host version check (audioMaster(NULL, audioMasterVersion, 0,0,NULL,0)) */
  if (g_audio_master && !audio_master(0, audioMasterVersion, 0, 0, 0, 0.f)) return 0;
  int slot = -1;
  for (int i = 0; i < HB_INST_MAX; i++) {
    if (!SHADOW(INST(i))->used) { slot = i; break; }
  }
  if (slot < 0) return 0;
  uint8_t* obj = INST(slot);
  memset(obj, 0, HB_INST_STRIDE);
  function_18011d400((uint64_t)(uintptr_t)obj, 0 /* M10 harness と同じ: lift 済 ctor は audioMaster=0 で通す */);
  function_180120800((uint64_t)(uintptr_t)obj);
  OttShadow* sh = SHADOW(obj);
  sh->used = 1;
  sh->sampleRate = 44100.f;
  sh->blockSize = 1024;
  HbAEffect* e = (HbAEffect*)(obj + 0x30); /* cEffect = obj+0x30 (HOSTBRIDGE.md §1.4) */
  /* lift した AudioEffect ctor は r8d/r9d (numPrograms=1, numParams=0x14) を落とす → ネイティブ値で補正 */
  e->numPrograms = 1;
  e->numParams = 20;
  e->flags &= ~effFlagsHasEditor; /* GUI 未 lift: FL の generic editor を使わせる */
  e->dispatcher = HB_FN_DISPATCHER;
  e->process = HB_FN_PROCESS_LEGACY;
  e->setParameter = HB_FN_SETPARAM;
  e->getParameter = HB_FN_GETPARAM;
  e->processReplacing = HB_FN_PROCESS_REPLACING;
  e->processDoubleReplacing = HB_FN_PROCESS_DOUBLE;
  e->object = (uint64_t)(uintptr_t)obj;
  return (uint64_t)(uintptr_t)e;
}

static void put_str(uint32_t ptr, const char* s) { if (ptr) { strcpy((char*)(uintptr_t)ptr, s); } }

static int64_t do_dispatch(HbAEffect* e, int32_t op, int32_t idx, int64_t val, uint32_t ptr, float opt) {
  uint8_t* obj = (uint8_t*)(uintptr_t)e->object;
  OttShadow* sh = SHADOW(obj);
  switch (op) {
    case effOpen:
      if (g_audio_master) { /* SDK AudioEffect::open 相当ではなく Fruity Wrapper との往復確認用 */
        int32_t sr = audio_master((uint32_t)(uintptr_t)e, audioMasterGetSampleRate, 0, 0, 0, 0.f);
        (void)sr;
      }
      return 0;
    case effClose: sh->used = 0; return 1;
    case effSetProgram: sh->program = (int32_t)val; return 0;
    case effGetProgram: return sh->program;
    case effSetSampleRate: sh->sampleRate = opt; memcpy(obj + 0x18, &opt, 4); return 0;
    case effSetBlockSize: sh->blockSize = (int32_t)val; memcpy(obj + 0x1c, &sh->blockSize, 4); return 0;
    case effMainsChanged: if (val) function_180120800((uint64_t)(uintptr_t)obj); return 0;
    case effGetParamName: if (idx >= 0 && idx < 19) { put_str(ptr, k_param_name[idx]); } else { put_str(ptr, ""); } return 0;
    case effGetParamLabel: put_str(ptr, ""); return 0;
    case effGetParamDisplay:
      if (idx >= 0 && idx < 32 && ptr) snprintf((char*)(uintptr_t)ptr, 24, "%.2f", (double)sh->params[idx]);
      return 0;
    case effCanBeAutomated: return 1;
    case effGetPlugCategory: return 1; /* kPlugCategEffect */
    case effGetEffectName: put_str(ptr, "OTT"); return 1;
    case effGetProductString: put_str(ptr, "OTT"); return 1;
    case effGetVendorString: put_str(ptr, "Xfer Records"); return 1;
    case effGetVendorVersion: return 1037;
    case effGetVstVersion: return 2400;
    case effGetTailSize: return 0;
    case effGetNumMidiInputChannels: case effGetNumMidiOutputChannels: return 0;
    case effProcessEvents: return 0; /* OTT は MIDI 不要 */
    case effEditGetRect: case effEditOpen: case effEditClose: case effEditIdle: return 0; /* GUI 未 lift */
    case effCanDo: return 0;
    default: return 0; /* VST2 規約: 未対応 opcode は 0 */
  }
}

EMSCRIPTEN_KEEPALIVE uint64_t hb_icall(uint64_t fn, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3,
                                       uint64_t a4, uint64_t a5) {
  HbAEffect* e = (HbAEffect*)(uintptr_t)a0;
  uint8_t* obj = e ? (uint8_t*)(uintptr_t)e->object : 0;
  switch (fn) {
    case HB_FN_DISPATCHER:
      return (uint64_t)do_dispatch(e, (int32_t)a1, (int32_t)a2, (int64_t)a3, (uint32_t)a4, bits2f(a5));
    case HB_FN_SETPARAM: {
      int32_t idx = (int32_t)a1;
      if (idx >= 0 && idx < 32) SHADOW(obj)->params[idx] = bits2f(a2);
      function_180120af0((uint64_t)(uintptr_t)obj, (uint64_t)(uint32_t)idx, a2 & 0xffffffffu);
      return 0;
    }
    case HB_FN_GETPARAM: {
      int32_t idx = (int32_t)a1;
      return (idx >= 0 && idx < 32) ? f2bits(SHADOW(obj)->params[idx]) : 0;
    }
    case HB_FN_PROCESS_REPLACING:
      function_18011ec20((uint64_t)(uintptr_t)obj, a1, a2, (uint64_t)(uint32_t)a3);
      return 0;
    case HB_FN_PROCESS_LEGACY: case HB_FN_PROCESS_DOUBLE:
      return 0; /* flags で advertise していない */
    default: return 0;
  }
}
