/* #5715 (CI-238): function_439f90 の入口計数 probe の実体 (計測専用・M11_ENTRY_PROBE=1 の build でだけ使う).
 * - m11_fe_439f90: m11_439f90_probe_insert.py が function_439f90 の入口に入れた store の先 (呼出しを挟まない・#1847).
 * - m11_fe_417b70: m11_ov.c の M11_ENTRY_PROBE 分岐が参照する変数 (未定義だと link が落ちるため定義だけする・計数には使わない).
 * - m11_fe_get / m11_fe_clear: M11_ENTRY_PROBE=1 の link で export される関数 (index 0 = function_439f90). */
volatile int m11_fe_439f90 = 0;
volatile int m11_fe_417b70 = 0;

/* index 0 = function_439f90 (計測対象), index 1 = function_417b70 (陽性対照: m11_ov.c が常に立てる probe) */
int m11_fe_get(int i) { return i == 0 ? m11_fe_439f90 : i == 1 ? m11_fe_417b70 : -1; }

void m11_fe_clear(void) { m11_fe_439f90 = 0; m11_fe_417b70 = 0; }
