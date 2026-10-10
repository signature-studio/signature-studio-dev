/* regpersist.c — レジストリ永続化の C 側口 (pathreg.h「ホストブリッジ (JS) フック契約」参照)。
 *
 * 変更検出: shimx_reg_export_text() (全ハイブの .reg テキスト, malloc 文字列) を FNV-1a 64bit で
 * ハッシュし、pathreg_reg_mark_saved() 時点の値と比較する。export+hash なので flush 点でのみ呼ぶ。
 * 永続化の実体 (IndexedDB への保存) は JS 側 js/regbridge.mjs が行う (Vreg 互換レコード)。
 */
#include "pathreg.h"
#include "pathreg_internal.h"
#include <stdlib.h>
#include <string.h>

static uint64_t g_saved_hash;
static int g_saved_valid;

/* FNV-1a 64bit */
uint64_t pathreg_fnv1a64(const char* s, size_t n) {
    uint64_t h = 0xcbf29ce484222325ull;
    for (size_t i = 0; i < n; i++) { h ^= (uint8_t)s[i]; h *= 0x100000001b3ull; }
    return h;
}

int pathreg_reg_hash(uint64_t* outHash) {
    char* text = shimx_reg_export_text();
    if (!text) return -1;
    uint64_t h = pathreg_fnv1a64(text, strlen(text));
    free(text);
    if (outHash) *outHash = h;
    return 0;
}

int pathreg_reg_changed(void) {
    uint64_t h = 0;
    if (pathreg_reg_hash(&h) != 0) return -1;
    if (!g_saved_valid) return 1;        /* 基準が無ければ「変化あり」扱い (保存を促す) */
    return h != g_saved_hash;
}

void pathreg_reg_mark_saved(void) {
    uint64_t h = 0;
    if (pathreg_reg_hash(&h) == 0) { g_saved_hash = h; g_saved_valid = 1; }
}

uint64_t pathreg_reg_saved_hash(void) { return g_saved_hash; }

int pathreg_reg_seed_text(const char* regTextUtf8) {
    if (!regTextUtf8) return -1;
    return shimx_reg_import_text(regTextUtf8);
}
