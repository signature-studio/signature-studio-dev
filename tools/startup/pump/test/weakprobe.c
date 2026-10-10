/* weakprobe.c — 置換前対照: pump TU をリンクせず winstubs weak のまま GetMessageW を呼ぶと
 * weak stub の戻り値 0 (= WM_QUIT → メインループ即終了) が返る。
 * pump 強定義リンクでは HOSTED モードの -1 になる。この差が「弱→強の置換」の行動面の証拠。
 * 出力: "weakprobe\tGetMessageW_empty_ret=<r>"
 */
#include "../../winstubs/src/winstubs.h"

/* winstubs.h はポンプ API を宣言しない (ws_cases.c と同様にここで宣言)。シグネチャは ws_ui.c と同一 */
LONG GetMessageW(LPVOID msg, HWND h, UINT lo, UINT hi);

int main(void) {
    winstubs_init(0);
    unsigned char buf[64];
    LONG r = GetMessageW(buf, 0, 0, 0);
    printf("weakprobe\tGetMessageW_empty_ret=%d\n", (int)r);
    return 0;
}
