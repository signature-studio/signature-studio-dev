/* am_host.h — VSTPluginMain / dispatcher が呼ぶ host 側 audioMaster callback の共有実装。
 *
 * native 参照 (entry_native.c, 実機械語呼出の相手) と wasm lift 側 (rt_entry.c の ott_am 仮想入口
 * override body) の **同一ソースを 2 回コンパイル** して使う。両者の観測差 (応答値 / 呼出回数) は
 * entry 比較 matrix の突合対象になるため、ロジックを 1 箇所に置く。
 *
 * メモリアクセスは tools/ott/rt/ott_cpu.h の LD8/ST8 マクロに統一:
 *   native 側 = guest VA がそのままホスト仮想アドレス (PE を 0x180000000 に敷設済み) → A_() は恒等
 *   wasm 側   = guest VA は linear address (0x30000000+RVA) → A_() も恒等
 * ゆえ同一コードで両方の意味になる。
 *
 * 応答表は FL (Fruity Wrapper audioMaster 0x7a87c0) の観測値に合わせた最小集合:
 *   audioMasterVersion=0x960 / GetSampleRate=44100 / GetBlockSize=512 /
 *   GetVendorString="Image-Line" / GetProductString="Fruity Wrapper" / GetVendorVersion=0x271a /
 *   CanDo("sendVstTimeInfo","sendVstEvents","sendVstMidiEvent","supplyIdle")=1, ("offline")=-1, 他=0 /
 *   CurrentId=0 / GetLanguage=1 (kVstLangEnglish) / UpdateDisplay=0 / GetTime=0 (非対応の意)。
 * 呼出回数を am_counts[op] に計上し、native/wasm で突合する。
 */
#ifndef OTT_AM_HOST_H
#define OTT_AM_HOST_H
#include <stdint.h>
#include "ott_cpu.h"

static uint32_t am_counts[64];

static int64_t am_logic(int32_t op, int32_t idx, int64_t val, uint64_t ptr, float opt) {
    (void)idx; (void)val; (void)opt;
    if (0 <= op && op < 64) am_counts[op]++;
    switch (op) {
    case 1:  /* audioMasterVersion */ return 0x960;
    case 2:  /* audioMasterCurrentId */ return 0;
    case 16: /* audioMasterGetSampleRate */ return 44100;
    case 17: /* audioMasterGetBlockSize */ return 512;
    case 32: /* audioMasterGetVendorString */
        if (ptr) { const char* s = "Image-Line"; for (int i = 0; i < 12; i++) ST8(ptr + i, s[i]); }
        return 1;
    case 33: /* audioMasterGetProductString */
        if (ptr) { const char* s = "Fruity Wrapper"; for (int i = 0; i < 16; i++) ST8(ptr + i, s[i]); }
        return 1;
    case 34: /* audioMasterGetVendorVersion */ return 0x271a;
    case 37: /* audioMasterCanDo: 文字列を読んで応答 */
        if (ptr) {
            char b[32]; int n = 0;
            for (; n < 31; n++) { b[n] = (char)LD8(ptr + n); if (!b[n]) break; }
            b[n] = 0;
            static const char* const yes[] = {"sendVstEvents", "sendVstMidiEvent", "sendVstTimeInfo", "supplyIdle", 0};
            static const char* const no[] = {"offline", 0};
            for (int i = 0; yes[i]; i++) {
                int j = 0; while (yes[i][j] && yes[i][j] == b[j]) j++;
                if (!yes[i][j] && !b[j]) return 1;
            }
            for (int i = 0; no[i]; i++) {
                int j = 0; while (no[i][j] && no[i][j] == b[j]) j++;
                if (!no[i][j] && !b[j]) return -1;
            }
        }
        return 0;
    case 38: /* audioMasterGetLanguage */ return 1; /* kVstLangEnglish */
    case 42: /* audioMasterUpdateDisplay */ return 0;
    default: return 0;
    }
}

/* 呼出回数表 (native: entry_native.c がポインタを公開 / wasm: rt_entry.c が export) */
static uint32_t* am_counts_ptr(void) { return am_counts; }

#endif
