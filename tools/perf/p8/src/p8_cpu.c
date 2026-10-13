/* lift の ott_cpu.c 相当: CPU 状態 (R/X/flag) は別 TU のグローバル。PIC では default visibility だと GOT 経由になる */
#include "p8.h"
uint64_t R[16];
X128 X[16];
uint8_t fZF, fSF, fCF, fOF, fPF;
