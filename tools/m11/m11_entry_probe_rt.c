/* #1894: entry probe の実体 (計測専用). m11_entry_probe.py が IR の対象関数入口に入れた
 * `store volatile i32 1, ptr @m11_fe_<hex>` の先の変数をここで定義し, survey から読み出す.
 * 呼出しを挟まない (global への store のみ) ので survey を変えない (#1847). */
#include <stdint.h>

#define FE(h) volatile int m11_fe_##h = 0;
FE(12a3ff0)
FE(417110)
FE(417b70)
FE(418030)
FE(418280)
FE(4183d0)
FE(418700)
FE(416750)

/* 0..6 の index で各 probe の値 (0/1) を返す. 順序は M11_FE_NAMES (survey 側と揃える) */
int m11_fe_get(int i) {
    switch (i) {
    case 0: return m11_fe_12a3ff0;
    case 1: return m11_fe_417110;
    case 2: return m11_fe_417b70;
    case 3: return m11_fe_418030;
    case 4: return m11_fe_418280;
    case 5: return m11_fe_4183d0;
    case 6: return m11_fe_418700;
    case 7: return m11_fe_416750;
    default: return -1;
    }
}

/* survey 直後に全 probe を 0 へ戻す (unit ごとの到達を分けるため) */
void m11_fe_clear(void) {
    m11_fe_12a3ff0 = 0; m11_fe_417110 = 0; m11_fe_417b70 = 0; m11_fe_418030 = 0;
    m11_fe_418280 = 0; m11_fe_4183d0 = 0; m11_fe_418700 = 0; m11_fe_416750 = 0;
}
