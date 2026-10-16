/* watch_shim_5533.c: watch_ir_5533.py が IR に差し込む値の観測フック (診断専用・#5533)。
 * shim_*.o として link し genstubs の対象から外す (stage4.sh の規約)。
 * 値は linear memory に書かず、JS 側の配列 globalThis.__m11_wv に積む。
 * 前回 (固定アドレス 0x11FFF000 のリング) は boot 中の heap と衝突して値が消えたため、この方式に変えた。 */
#include <emscripten.h>

EM_JS(void, m11_wv_push, (unsigned long long id, unsigned long long value), {
    if (!globalThis.__m11_wv) globalThis.__m11_wv = [];
    if (globalThis.__m11_wv.length < 2000) globalThis.__m11_wv.push([id, value]);
});

void m11_wv(unsigned long long id, unsigned long long value) {
    m11_wv_push(id, value);
}
