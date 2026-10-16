# REPORT 付録 — #5743 (HB-H59): `statement not in loop` 27 件の既定 backend 最適化段の特定

> **正本**: `tools/hostbridge/wrapper_lift/REPORT.md` §12。本付録は計測の全文。

測定 commit: 本 PR の `notloop_passes.sh` を入れた commit (HEAD 時点の commit は PR 本文に併記)。
素材: `fl-win64` (`extracted/block19091_PE.bin`)・`toolchain-retdec` (RetDec v5.0)・`toolchain-emsdk`。`$RUNNER_TEMP` に展開。load average (1 分値) 1.08 (測定中)。
起点: origin/main `912bba735` から `5743-retdec-stmt-not-in-loop` を切った worktree `ws-5743`。

## 1. 再現

- `retdec_batch.py` (BATCH=500・直列・`KEEP_DIR` 指定): 19,816 / 19,816 ok・RetDec 呼び出し 41 回・fail 0・所要 `retdec_seconds_all` 281.42 s。
- `notloop_probe.py`: `{"notloop": 78, "resolvable": 51, "unresolved_pairs": 19, "boundary": 19, "noopt_annotated": 19}`。#4393 の付録と一致。

## 2. 19 組の変種別の注釈の有無

各組を単一 range (関数範囲) で再 lift し、飛び先の注釈 `// <飛び先>` の行数を数えた (1 = 有り・0 = 無し)。
- default: 既定の backend
- noopt: `--backend-no-opts`
- dis_empty: `--backend-disabled-opts EmptyStmtOptimizer`
- dis_wtwc: `--backend-disabled-opts WhileTrueToWhileCondOptimizer`
- dis_both: 両方を disable

| 関数 | 飛び先 | default | noopt | dis_empty | dis_wtwc | dis_both |
|---|---|---|---|---|---|---|
| 0x408770 | 0x4087ba | 0 | 1 | 0 | 0 | 0 |
| 0x412db0 | 0x412e10 | 0 | 1 | 0 | 0 | 0 |
| 0x4166b0 | 0x4168ba | 0 | 1 | 0 | 0 | 0 |
| 0x44abe0 | 0x44ac34 | 0 | 1 | 0 | 0 | 0 |
| 0x487c30 | 0x487f31 | 0 | 1 | 0 | 1 | 1 |
| 0x52ef40 | 0x52eff1 | 0 | 1 | 0 | 0 | 0 |
| 0x575480 | 0x575627 | 0 | 1 | 0 | 0 | 0 |
| 0x59a1c0 | 0x59a260 | 0 | 1 | 0 | 0 | 0 |
| 0x5e5d60 | 0x5e60b9 | 1 | 1 | 1 | 1 | 1 |
| 0x683120 | 0x6835cb | 0 | 1 | 0 | 0 | 0 |
| 0x6a0ae0 | 0x6a0d79 | 0 | 1 | 1 | 0 | 1 |
| 0x717600 | 0x7176ba | 0 | 1 | 0 | 0 | 0 |
| 0x732ae0 | 0x732b75 | 0 | 1 | 0 | 0 | 1 |
| 0x732c50 | 0x732cf4 | 0 | 1 | 0 | 0 | 1 |
| 0x741340 | 0x7414ec | 0 | 1 | 0 | 0 | 0 |
| 0x7c0570 | 0x7c062e | 0 | 1 | 0 | 0 | 0 |
| 0x7c32c0 | 0x7c3322 | 0 | 1 | 0 | 0 | 1 |
| 0x7c76b0 | 0x7c773b | 0 | 1 | 0 | 0 | 0 |
| 0x7c76b0 | 0x7c7796 | 0 | 1 | 0 | 0 | 0 |

- 19 組すべてで noopt は注釈が出る (19/19)。
- `dis_both` で戻るのは 5 組 (0x487c30・0x6a0ae0・0x732ae0・0x732c50・0x7c32c0)。
- 0x5e5d60 は default で既に 1 (注釈あり)。probe は関数範囲の内側だけを見るため、probe の未解決 19 組に入っている値と一致しない。範囲の扱いの違いは未確認。
- 残り 13 組は、どの変種でも注釈が戻らない。

## 3. 代表 1 組 (0x732ae0 → 0x732b75) の絞り込み

- 単独の disable: 既定の 48 個の optimizer を 1 つずつ disable した。どれ 1 つでも注釈は戻らない (48 件とも 0)。
- 単独の enable (`--backend-enabled-opts`): EmptyStmtOptimizer・WhileTrueToWhileCondOptimizer・BreakContinueReturnOptimizer・GotoStmtOptimizer・IfStructureOptimizer・DeadCodeOptimizer・CopyPropagationOptimizer の各 1 件のみでは、いずれも注釈は有り (1)。
- 両方の disable のみ戻る。よって注釈の消失は、この 2 つの組み合わせ (相互作用) による。単独の原因は特定できない。

## 4. 判定

- **測定済み**: 19 組すべて notloop の飛び先は命令境界、`--backend-no-opts` で注釈が出る (19/19)。
- **測定済み**: 19 組中 5 組 (+ 既定で注釈有りの 1 組) は `EmptyStmtOptimizer` と `WhileTrueToWhileCondOptimizer` のどちらか・両方の disable で注釈が戻る。
- **未特定**: 残り 13 組は、どの単独 disable・両方 disable でも戻らない。段は特定できていない。
- **未検証**: 注釈の消失が「統合」によるかは確認していない (#4393 の推定のまま)。戻した C の wasm 実行による bit 一致は未実施。

## 5. 採らなかった方式

- 両方 disable した C を既定に採用する: 制御構造が既定と変わる。13 組は戻らないため、採用しても 27 件は解消しない。
- `break` を機械的に `goto` へ書き換える: 飛び先の注釈が無いので、飛び先を C 上で確定できない (#4393 §3)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残り 13 組の注釈消失の段 (単独・組み合わせの disable では戻らない) | 27 件のうち 13 組の直し方が決まらない | #1954 (HB-H41) |
| 両方 disable (5 組) の C の wasm 実行 (bit 一致) | 戻した C の正しさ未検証 | #1954 (HB-H41) |
| probe の範囲と grep の範囲の差 (0x5e5d60) | 未解決 19 組の数え方 | #1954 (HB-H41) |
