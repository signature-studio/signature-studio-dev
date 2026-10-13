/* uilang probe (ST-T19 / #591): shimx の GetUserPreferredUILanguages を FL (FLEngine_x64.dll 0x9df190) と同じ呼び方で叩き、
 * 戻り値と、そこから FL が導く言語コード / Program language 書込み有無 (0x9deaa0 の分岐モデル) を 1 行で出す。
 *   node probe.cjs default        … shimx 既定ロケール
 *   node probe.cjs lcid <hex>     … shimx_set_locale(<hex>) の後
 * FL 側の呼び方 (verify_uilang.py が DLL のバイト列で照合済み):
 *   flags=8 (MUI_LANGUAGE_NAME) / 1 回目 buf=NULL でサイズ取得 → cch*2 byte 確保 → 2 回目で取得 →
 *   先頭の NUL 終端文字列だけ使う → 引数 true なら最初の '-' の手前までに縮める。
 */
#include "shimx.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define MUI_LANGUAGE_NAME 0x8

static int w2a(const WCHAR* w, char* out, int cap) {
    int i = 0;
    for (; w[i] && i < cap - 1; i++) out[i] = (char)w[i];
    out[i] = 0;
    return i;
}

int main(int argc, char** argv) {
    const char* mode = argc > 1 ? argv[1] : "default";
    unsigned lcid = 0;
    if (!strcmp(mode, "lcid") && argc > 2) {
        lcid = (unsigned)strtoul(argv[2], NULL, 16);
        shimx_set_locale((LCID)lcid);
    }
    ULONG num = 0, cch = 0;
    BOOL r1 = GetUserPreferredUILanguages(MUI_LANGUAGE_NAME, &num, NULL, &cch);
    if (!(r1 && num >= 1)) { printf("RESULT mode=%s lcid=0x%04x r1=%d num=%lu cch=%lu -> FL は言語を取得できず (空文字)\n", mode, lcid, r1, (unsigned long)num, (unsigned long)cch); return 0; }
    WCHAR* buf = (WCHAR*)calloc(cch, 2);
    ULONG cch2 = cch;
    BOOL r2 = GetUserPreferredUILanguages(MUI_LANGUAGE_NAME, &num, buf, &cch2);
    char full[64] = "";
    if (r2) w2a(buf, full, sizeof full);
    char lang[64];
    strcpy(lang, full);
    char* dash = strchr(lang, '-');
    if (dash) *dash = 0;
    int is_zh = !strcmp(lang, "zh");
    printf("RESULT mode=%s lcid=0x%04x r1=%d num=%lu cch1=%lu r2=%d cch2=%lu tail_nul2=%d full=%s lang=%s fl_writes_program_language=%d\n",
           mode, lcid, r1, (unsigned long)num, (unsigned long)cch, r2, (unsigned long)cch2,
           (cch >= 2 && buf[cch - 1] == 0 && buf[cch - 2] == 0), full, lang, is_zh);
    free(buf);
    return 0;
}
