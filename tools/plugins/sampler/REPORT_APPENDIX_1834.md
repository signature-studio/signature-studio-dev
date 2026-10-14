# sampler REPORT 付録 (#1834 [PLG-F3-17])

> 正本: `tools/plugins/sampler/REPORT.md` §5。 #1774 の残り (`engine_lift.sh 19048` の `emcc -c` rc 1)。

## 1. 切り分け (型推論元)

- 対象: `function_18004f7f8` (block19048)。 RetDec の出力は `define i64 @function_18004f7f8(i64 %arg1, i32 %arg2)`。
- 実機 (block19048_PE.bin @0x18004f7f8) の逆アセンブル: 第 2 引数は `rdx` (64 bit)。 `test rdx, rdx` → `movups xmm0, [rdx]` と 64 bit のポインタとして読む。 `i32` は誤り。 (根拠の逆アセンブルは PR 作成時の記述で、#1915 の review では独立に再確認していない。 emcc -c rc 0 は到達性の確認で、この型の正しさの確認ではない)
- 呼び出し側 24 件のうち、i64 の値を `trunc i64 W to i32` で切り落として渡す箇所と、`i32 0` で渡す箇所がある (`e.final.ll` の 130641・130706・135676・156187 等)。 定義だけを直すと call site の型が合わないため、定義と call site を揃える必要がある。
- 型推論の元は RetDec の引数復元 (確定)。 本体には `icmp eq i32 %arg2, 0` (`test rdx, rdx` を 32 bit 比較として復元したと推定) と `inttoptr i64 %arg2` が同時にあり、RetDec はその一方の i32 を採った。 この推定の裏付けは未取得。 RetDec 側は直さず、engine-local の pass で揃えた。

## 2. 修正

- `tools/plugins/sampler/fix_arg_width.py` (新規): `i32 %argN` 仮引数のうち、本体の使用が `icmp ... i32 %argN` と `inttoptr i64 %argN to ptr` だけのものを i64 に揃える。 他の使用があれば何もしない (fail-closed)。 定義・本体の icmp・call site (`trunc i64 W` は W を直接渡す / `0` は `i64 0` / それ以外は zext) を書き換える。
  - 3 段目 (ptr 仮引数へ i64 値を渡す call と、本体の `ptr %X` で X が i64 の値の `inttoptr` 揃え) は 19048 で**発火している**。 `function_180051a20(i64 %penv)` の本体 `ptr %penv` が `inttoptr i64 %penv to ptr` に揃う (`ptr_uses = 1`)。 3 段目を外すと `emcc -c` が `'%penv' defined with type 'i64' but expected 'ptr'` で落ちる (実測・`first_errors.txt`)。 カウンタ `ptr_args` は call site しか数えず 0 と出るため、 `ptr_uses` を別に出すようにした。
- `tools/plugins/sampler/test_fix_arg_width.py` (回帰テスト 7 件): 定義・icmp の i64 化 / 他の使用がある時の skip (fail-closed) / call site の `trunc` 剥がし / `0` → `i64 0` / それ以外の `zext` / 3 段目の 2 分岐 (本体の `ptr %X` と ptr 仮引数への call)。
- `tools/plugins/sampler/engine_lift.sh`: fixcmp の前に `fix_arg_width.py` を挟む (`e.final.ll` → `e.argw.ll` → `e.fixcmp.ll`)。

## 3. 測定 (engine_lift.sh)

| block | 修正前 (HEAD 486eab5d) summary 列 7 / 列 9 | 修正後 (本 PR) 列 7 / 列 9 | 備考 |
|---|---|---|---|
| 19048 | 1 / 1 (`'%arg2' ... i32`) | **0 / 0** | 最終 HEAD `81be9e49` の summary: `19048,1658,0,1712,0,5,0,0,0,63,2,97,0,54,1710,0`。 `fix_arg_width: defs = 1 callsites = 24 ptr_args = 0 ptr_uses = 1` (`%penv` の 3 段目が発火)。 66.5 s (load 0.24) |
| 19252 | 1 / 1 (REPORT §5 と一致) | 1 / 1 (変化なし) | 最終 HEAD の summary: `19252,522,0,551,1,5,1,0,1,16,2,165,0,29,549,0`。 `fix_arg_width: defs = 0 callsites = 0 ptr_args = 0 ptr_uses = 0`。 `e.argw.ll` = `e.final.ll` (cmp 一致)。 17.9 s (load 0.68)。 f80 段 (列 16) は 0 のまま |

- 列 7 (`emcc_c_rc`) は、本 PR で pass を最初の emcc の前に移したため、「素の `e.final.ll`」から「引数幅修正後の `e.argw.ll`」の判定に変わった。 19252 では pass が何も変えないので値は不変。
- 19048 の残り: `unimpl 5` (vcomisd / vucomisd / vucomiss / movntps) は #1582 の子 (PLG-F3-14) の範囲で、本 issue では触らない。
- 23677 の `emcc_c_rc` 1 (`do not know how to soften fp_extend`) は REPORT §5 行 6 (x86_fp80) と §7 の追跡先 (#197 の `f80_lower.py`・#540 [PLG-G3-2]) に対応する。 本 PR の pass は 23677 の `.ll` を変えない (`e.argw.ll` = `e.final.ll`) ため、emcc 入力は本 PR 前と同じ。 REPORT §5/§6 の旧値 (4c3ae00 時点の 0) との差の原因は未切り分け (§7 に記載済み)。

## 4. 実行環境

- `engine_lift.sh 19048`: 1 m 5 s (修正後)。 `engine_lift.sh 19252`: 17.9 s。 runner: 4 core / load 0.75–0.83。
- 素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`)・`toolchain-retdec`・`toolchain-emsdk`・`work-liftlib`・`work-fw-stage1`・`plugins-ott`。
