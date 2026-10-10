# OTT 固有 recipe (vendored)

`tools/m6..m10` の OTT 固有 IR pass (関数名・VA・dsm 位置に依存する再構成) を **無改変でコピー**したもの。
汎用化できる部分 (base 正規化 / P1 / VA remap / gdata / SIMD helper) は `liftlib/passes/`・`liftlib/simd/` に統合済みで,
ここに残るのは OTT バイナリの個別事情に依存する recipe のみ。

| ファイル | 元 | 内容 (入力依存) |
|---|---|---|
| m6_memfix.py | m6 | CRT memmove/memset define を C 実装へ置換 (関数名固定: function_1801a2a20/1801a30d0) |
| m6_full_extract.py | m6 | closure で declare-only の 3 関数を full lift から splice (HELPER_RENAME は RetDec 接尾番号依存) |
| ir7_argpass_fixed.py | m8 | setParameter の f32 引数接続 + jump table 本体再生成 (dsm 依存) |
| ir8_valueflow.py | m8 | accessor 誤訳再生成 + SVF xmm1 2-arg 化 16 callsite (insn.addr/dsm 依存) |
| ir9_bootstraps.py | m9 | resume/gate box/exp,log,tan の C port 置換 (F3〜F6) |
| ir9_outcopy.py | m9 | 出力 copy の deref 復元 — **汎用 F7 (passes/f7.py) が同型を機械検出** |
| m10_coefref.py / m10_coefdump.mjs | m10 | band 係数 dsm register-exact 突合 |

e2e_check.mjs / e2e_trap10.mjs は m10_e2e.sh のヒアドキュメント (E1/E3/E4/E5/E6 と E7) を取り出したもの。
モジュールパスだけ環境変数 `OTT_CJS` で受ける形に変更 (判定ロジックは無改変)。
