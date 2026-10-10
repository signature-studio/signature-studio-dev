/* 署名突合: 本実装の宣言 (../ipp_fft_pffft.h) と生成プロトタイプ (../gen/ipp_proto.h) を
   同一 TU で include する。28 関数のどれかで型が食い違えば conflicting types でコンパイルエラー。
   (shim/test/proto_check.c が担う ipp_min.h 突合の FFT 拡張分。fft_e2e.sh がコンパイルする) */
#include "../ipp_fft_pffft.h"
#include "../../gen/ipp_proto.h"
int main(void) { return 0; }
