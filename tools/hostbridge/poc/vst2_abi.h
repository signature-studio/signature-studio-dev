/* vst2_abi.h — hostbridge PoC: VST2 ABI の自前定義 (Steinberg SDK ヘッダは使わない)。
 *
 * レイアウトの根拠 (2 系統の独立証拠):
 *   (1) OTT_vst2_win64.dll の AudioEffect::AudioEffect (0x180126920) の store 列
 *       (cEffect = obj+0x30; +0x00 magic 'VstP' / +0x08 dispatcher / +0x10 process /
 *        +0x18 setParameter / +0x20 getParameter / +0x28 numPrograms / +0x2c numParams /
 *        +0x30 numInputs / +0x34 numOutputs / +0x38 flags|=0x10 / +0x5c ioRatio=1.0f /
 *        +0x60 object / +0x70 uniqueID / +0x74 version / +0x78 processReplacing /
 *        +0x80 processDoubleReplacing)  → HOSTBRIDGE.md §1.4
 *   (2) Fruity Wrapper (TVSTPlugin.Create, 0x7a9db0) のホスト側アクセス
 *       (+0x08 dispatcher 呼出, +0x38 flags, +0x40 resvd1 へ host this 格納, +0x70 uniqueID,
 *        +0x78 processReplacing, +0x18 setParameter, +0x20 getParameter)。
 *
 * ポインタは Win64 ABI に合わせ 8 byte (hb_ptr = uint64_t)。lift 済み x64 コード (FL / プラグイン) は
 * この配置を前提とするため、wasm32 のホスト側 C も同一配置を明示的に採用する。
 */
#ifndef HB_VST2_ABI_H
#define HB_VST2_ABI_H
#include <stdint.h>
#include <stddef.h>

typedef uint64_t hb_ptr;

#define HB_EFFECT_MAGIC 0x56737450u /* 'VstP' */

typedef struct HbAEffect {
  int32_t magic;            /* 0x00 */
  int32_t _pad0;
  hb_ptr dispatcher;        /* 0x08 */
  hb_ptr process;           /* 0x10 (deprecated, accumulating) */
  hb_ptr setParameter;      /* 0x18 */
  hb_ptr getParameter;      /* 0x20 */
  int32_t numPrograms;      /* 0x28 */
  int32_t numParams;        /* 0x2c */
  int32_t numInputs;        /* 0x30 */
  int32_t numOutputs;       /* 0x34 */
  int32_t flags;            /* 0x38 */
  int32_t _pad1;
  hb_ptr resvd1;            /* 0x40 host-owned (Fruity Wrapper stores its TVSTPlugin* here) */
  hb_ptr resvd2;            /* 0x48 */
  int32_t initialDelay;     /* 0x50 */
  int32_t realQualities;    /* 0x54 */
  int32_t offQualities;     /* 0x58 */
  float ioRatio;            /* 0x5c */
  hb_ptr object;            /* 0x60 plugin-owned (opaque to host) */
  hb_ptr user;              /* 0x68 host-owned */
  int32_t uniqueID;         /* 0x70 */
  int32_t version;          /* 0x74 */
  hb_ptr processReplacing;  /* 0x78 */
  hb_ptr processDoubleReplacing; /* 0x80 */
  char future[56];          /* 0x88 */
} HbAEffect;                /* sizeof == 0xc0 */

_Static_assert(offsetof(HbAEffect, dispatcher) == 0x08, "dispatcher");
_Static_assert(offsetof(HbAEffect, numPrograms) == 0x28, "numPrograms");
_Static_assert(offsetof(HbAEffect, flags) == 0x38, "flags");
_Static_assert(offsetof(HbAEffect, resvd1) == 0x40, "resvd1");
_Static_assert(offsetof(HbAEffect, ioRatio) == 0x5c, "ioRatio");
_Static_assert(offsetof(HbAEffect, object) == 0x60, "object");
_Static_assert(offsetof(HbAEffect, uniqueID) == 0x70, "uniqueID");
_Static_assert(offsetof(HbAEffect, processReplacing) == 0x78, "processReplacing");
_Static_assert(sizeof(HbAEffect) == 0xc0, "sizeof AEffect");

/* flags */
enum {
  effFlagsHasEditor = 1 << 0,
  effFlagsCanReplacing = 1 << 4,
  effFlagsProgramChunks = 1 << 5,
  effFlagsIsSynth = 1 << 8,
  effFlagsCanDoubleReplacing = 1 << 12,
};

/* dispatcher opcodes (host → plugin). Fruity Wrapper が実際に発行する値は HOSTBRIDGE.md §1.3 */
enum {
  effOpen = 0, effClose = 1, effSetProgram = 2, effGetProgram = 3, effSetProgramName = 4,
  effGetProgramName = 5, effGetParamLabel = 6, effGetParamDisplay = 7, effGetParamName = 8,
  effSetSampleRate = 10, effSetBlockSize = 11, effMainsChanged = 12,
  effEditGetRect = 13, effEditOpen = 14, effEditClose = 15, effEditIdle = 19,
  effGetChunk = 23, effSetChunk = 24, effProcessEvents = 25, effCanBeAutomated = 26,
  effString2Parameter = 27, effGetProgramNameIndexed = 29,
  effGetInputProperties = 33, effGetOutputProperties = 34, effGetPlugCategory = 35,
  effSetSpeakerArrangement = 42, effSetBypass = 44,
  effGetEffectName = 45, effGetVendorString = 47, effGetProductString = 48,
  effGetVendorVersion = 49, effVendorSpecific = 50, effCanDo = 51, effGetTailSize = 52,
  effIdle = 53, effGetParameterProperties = 56, effGetVstVersion = 58,
  effSetEditKnobMode = 61, effBeginSetProgram = 67, effEndSetProgram = 68,
  effShellGetNextPlugin = 70, effStartProcess = 71, effStopProcess = 72,
  effSetProcessPrecision = 77, effGetNumMidiInputChannels = 78, effGetNumMidiOutputChannels = 79,
};

/* audioMaster opcodes (plugin → host) */
enum {
  audioMasterAutomate = 0, audioMasterVersion = 1, audioMasterCurrentId = 2, audioMasterIdle = 3,
  audioMasterGetTime = 7, audioMasterProcessEvents = 8, audioMasterIOChanged = 13,
  audioMasterSizeWindow = 15, audioMasterGetSampleRate = 16, audioMasterGetBlockSize = 17,
  audioMasterGetVendorString = 32, audioMasterGetProductString = 33,
  audioMasterGetVendorVersion = 34, audioMasterCanDo = 37, audioMasterGetLanguage = 38,
  audioMasterUpdateDisplay = 42,
};

/* 全 guest 関数ポインタ呼出の共通形 (lift 済み x64 の i64×N と同形): 引数は u64 に正規化。
 * float 引数は下位 32bit に f32 ビット (M7〜M10 の ir7_argpass / m10_e2e の f32b() と同じ規約)。 */
#define HB_ICALL_MAXARGS 6

#endif
