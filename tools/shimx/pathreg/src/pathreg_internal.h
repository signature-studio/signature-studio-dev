/* pathreg 内部共通 (CAB-168)。外部からは include/pathreg.h を使う */
#ifndef PATHREG_INTERNAL_H
#define PATHREG_INTERNAL_H

#include <stdio.h>

/* shimx の遅延初期化 (shimx_internal.h の実物と同一宣言。ここでは呼ぶだけ) */
void shx_ensure_init(void);

#endif /* PATHREG_INTERNAL_H */
