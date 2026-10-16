/* fw_blk10_probe.c — #4143: BLK+0x10 への store の実行時ダンプ。
 * fw_blk10_probe.py が canon3 の各 store 直前に挿入する呼出し先。
 * 出力 (stderr): "[blk10] line=<IR 行> val=<値 (u64)> hex=<値 (16 進)>"
 * 値が 203 の store と 268436792 (0x10000538) の store の行を grep すれば書込み元が分かる。 */
#include <stdio.h>
#include <stdint.h>

void fw_dbg_blk10(uint64_t val, int32_t line) {
  static int n = 0;
  if (n++ < 200000)
    fprintf(stderr, "[blk10] line=%d val=%llu hex=0x%llx\n", (int)line,
            (unsigned long long)val, (unsigned long long)val);
}
