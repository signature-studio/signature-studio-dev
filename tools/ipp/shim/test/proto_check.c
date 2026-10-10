/* 署名検査: 実装側ヘッダ (src/ipp_min.h) と生成プロトタイプ (gen/ipp_proto.h) を同一 TU で include。型が食い違えば conflicting types でコンパイルエラー。 */
#include "../../src/ipp_min.h"
#include "../gen/ipp_proto.h"
int main(void) { return 0; }
