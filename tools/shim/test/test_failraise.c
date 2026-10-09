/* fail-fast 動作確認用: 未対応 API 呼び出しが即 abort することを
 * node 上 (非 0 exit + stderr に関数名) で確認する。test.sh 専用。
 */
#include "../src/shim.h"

int main(void) {
    /* 未対応面の代表として存在しない Win32 呼び出しを shim_unimplemented に
     * 直接送る (将来 M5 で lifter 側から未対応 import が来たときと同じ経路) */
    shim_unimplemented("DestroyWindow_NonImplemented_Example");
    return 0; /* 到達しない (abort 済み) */
}
