/* FL が LoadLibrary("Python312") 後に GetProcAddress/動的束縛する Py* 名 → 静的リンク済みシンボルの対応 (PY-2 #83)。
 * pybind_refs.inc は analysis/pybind_extract.py が FLEngine PE (0xc395a0) から生成する。Python.h は含めない (extern 宣言を自前で持つため)。
 * wasm では関数アドレス = indirect function table の index、データ = 線形メモリ上のアドレス。 */
#include <emscripten.h>
#include <stddef.h>
#include <string.h>
#include "pybind_refs.inc"

EMSCRIPTEN_KEEPALIVE const void *flpy_resolve(const char *name) {
    for (size_t i = 0; i < sizeof pybind_refs / sizeof pybind_refs[0]; i++)
        if (strcmp(pybind_refs[i].name, name) == 0) return pybind_refs[i].addr;
    return NULL;
}
EMSCRIPTEN_KEEPALIVE unsigned flpy_resolve_count(void) { return (unsigned)(sizeof pybind_refs / sizeof pybind_refs[0]); }
