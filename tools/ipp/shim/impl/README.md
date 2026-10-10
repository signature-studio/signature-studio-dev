# shim/impl — 追加実装の置き場 (CAB-136 以降)

ここに `*.c` を置くと `gen_shim.py` が `nm` で `ipp*` 定義を検出し、**該当名は fail-soft stub から型付き thunk に自動で切り替わる**
(`../src/ipp_*.c` に置いても同じ。どちらも build_native.sh / build_wasm.sh が自動で拾う)。

契約:
1. 関数の C 宣言は `../gen/ipp_proto.h` のプロトタイプと一致させる (`#include "../gen/ipp_proto.h"` するか、同一型で宣言。食い違いは `test/proto_check.c` のコンパイルエラーになる)。
   プロトタイプの確度が `B+`/`B-` の関数は **実装前に呼出側 (win FLEngine 逆アセンブル) で引数順を確認**し、違っていれば `../sigs.py` を直す (`data/ipp_sigs.json` の `conf` 参照)。
2. 実装したら `bash ../shim_e2e.sh` が緑のままであること。実 IPP をオラクルにした差分テストは `../test/shim_ref.c` の FN 表 (ipp_ref.c の複製; thunk 経路も同時検査) に追加する。
