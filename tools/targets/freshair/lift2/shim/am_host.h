/* am_host.h — FA-2c: audioMaster (host callback) 応答表。native 参照 (ms_abi C 関数) と
 * wasm (fa_host_icall 経由の host 実装) が **同一ソース** を共有する (OTT の am_host.h と同型)。
 * opcode 別の呼出回数まで一致させることで、host 境界の差を検出する。
 * VST2 audioMasterCallback: (AEffect* effect, VstInt32 opcode, VstInt32 index, VstIntPtr value, void* ptr, float opt)
 *   MS x64: rcx=effect edx=opcode r8d=index r9=value / [rsp+0x20]=ptr / [rsp+0x28]=opt (callee 入口基準)。 */
#ifndef AM_HOST_H
#define AM_HOST_H
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define AM_OP_MAX 64
static unsigned long long am_counts[AM_OP_MAX];
static int am_trace;

static void am_reset(void) { memset(am_counts, 0, sizeof am_counts); }
static unsigned long long am_count(void) { unsigned long long t = 0; for (int i = 0; i < AM_OP_MAX; i++) t += am_counts[i]; return t; }
static void am_dump(int verbose) {
    for (int i = 0; i < AM_OP_MAX; i++)
        if (am_counts[i] || verbose) fprintf(stderr, "am op %d x %llu\n", i, am_counts[i]);
}

/* host 応答表 (定数: native/wasm 同一) */
static long long am_handle(void* effect, int opcode, int index, long long value, void* ptr, float opt) {
    if (opcode >= 0 && opcode < AM_OP_MAX) am_counts[opcode]++;
    else am_counts[AM_OP_MAX - 1]++;
    switch (opcode) {
    case 0:  return 2400;             /* audioMasterVersion */
    case 1:  return 1;                /* audioMasterAutomate (0 を返すと VSTPluginMain が生成中止する) */
    case 2:  return 0;                /* currentId */
    case 3:  return 0;                /* idle */
    case 4:  return 1;                /* pinConnected: 接続済み */
    case 5:  return 0;                /* wantMidi */
    case 7:  return 0;                /* getTime (未提供) */
    case 8:  return 0;                /* processEvents */
    case 9:  return 0;                /* setTime */
    case 10: return 0;                /* tempoAt */
    case 11: return 0;                /* getNumAutomatableParameters (0 = 不明) */
    case 12: return 0;                /* getParameterQuantization */
    case 13: return 0;                /* IOChanged */
    case 14: return 0;                /* needIdle */
    case 16: return 48000;            /* getSampleRate */
    case 17: return 512;              /* getBlockSize */
    case 18: return 0;                /* getInputLatency */
    case 19: return 0;                /* getOutputLatency */
    case 23: return 2;                /* getCurrentProcessLevel (2 = 非リアルタイム) */
    case 24: return 0;                /* getAutomationState */
    case 25: case 26: case 27: case 28: case 29: return 0;  /* offline */
    case 30: return 0;                /* setOutputSampleRate */
    case 42: return (long long)0x80000003LL; /* getSpeakerConfiguration: kSpeakerArrEmpty|kSpeakerL|kSpeakerR */
    case 45: return 0;                /* getDirectory (未提供) */
    case 46: return 0;                /* updateDisplay */
    case 47: case 48: return 0;       /* beginEdit/endEdit */
    case 51: case 52: return 0;       /* getVendorString/getProductString (ptr は書かない) */
    case 53: return 1;                /* getVendorVersion */
    case 56: return 0;                /* canDo (全て非対応) */
    default: return 0;
    }
}

#ifndef __wasm__
/* native 側: guest 機械語が直接 call できる ms_abi 関数ポインタ */
#include "fa_win_shim.h"
static long long __attribute__((ms_abi)) am_callback(void* effect, int opcode, int index, long long value, void* ptr, float opt) {
    return am_handle(effect, opcode, index, value, ptr, opt);
}
#endif

#endif
