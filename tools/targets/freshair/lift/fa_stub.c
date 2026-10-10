/* std::vector<float>::_Emplace_reallocate 相当 (0x1803ded20): 本検証ではシナリオが capacity を
 * 確保するため到達しない。到達時は fail-fast。 */
#include <emscripten.h>
EMSCRIPTEN_KEEPALIVE long long function_1803ded20(long long a, long long b, void* c) { __builtin_trap(); }
