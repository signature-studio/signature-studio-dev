/* fail-fast stub: 未対応 Win32 import が呼ばれたら関数名を stderr に出して即 abort。
 * strategy.md M4 検証条件 3 「未対応の要求が来た場合に fail-fast で静かにハンドル」の
 * 実装部。ランタイム到達は異常系 (inventory.md の未対応一覧に載っている API) であり、
 * それを見逃さないことが目的。
 */
#include "shim.h"

void shim_unimplemented(const char* apiName) {
    fprintf(stderr, "[shim] FAIL-FAST: unimplemented Win32 API: %s\n",
            apiName ? apiName : "(unknown)");
    fflush(stderr);
    abort();
}
