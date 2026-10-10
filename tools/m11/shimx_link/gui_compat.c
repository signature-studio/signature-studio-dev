/* --soft 用: M11 の m11_win.c が user32 API として実装していた 3 本の挙動を再現する (M11 e2e の到達点を後退させないため)。
 * 元実装: tools/m11/m11_win.c (LoadStringW / MessageBoxA / MessageBoxW)。shimx の対象外 (user32 = tools/gui 担当) ゆえ shim の独自追加ではなく
 * 「GUI 側が本実装を持つまでの暫定互換スタブ」。LoadStringW が buf[0]=0 を書かないと Delphi の LoadResString が未初期化バッファを読んで Halt に至る (実測)。 */
#include <stdio.h>

unsigned LoadStringW(void* h, unsigned id, unsigned short* buf, unsigned n) { (void)h; (void)id; if (buf && n) buf[0] = 0; return 0; }
unsigned MessageBoxA(void* h, const char* text, const char* cap, unsigned type) {
    fprintf(stderr, "[m11][MessageBoxA] caption='%s' text='%s' type=0x%x (自動 IDOK)\n", cap ? cap : "", text ? text : "", type);
    (void)h; return 1;
}
unsigned MessageBoxW(void* h, const unsigned short* text, const unsigned short* cap, unsigned type) {
    char t[256], c[128]; int i;
    for (i = 0; text && text[i] && i < 255; i++) t[i] = text[i] < 128 ? (char)text[i] : '?'; t[i] = 0;
    for (i = 0; cap && cap[i] && i < 127; i++) c[i] = cap[i] < 128 ? (char)cap[i] : '?'; c[i] = 0;
    fprintf(stderr, "[m11][MessageBoxW] caption='%s' text='%s' type=0x%x (自動 IDOK)\n", c, t, type);
    (void)h; return 1;
}
