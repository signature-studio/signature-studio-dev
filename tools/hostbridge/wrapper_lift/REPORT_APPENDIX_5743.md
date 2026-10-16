# REPORT 付録 — #5743 (HB-H59): `statement not in loop` 27 件の既定 backend 最適化段の特定

> **正本**: `tools/hostbridge/wrapper_lift/REPORT.md` §12。本付録は計測の全文。

測定 commit: §1〜§4 は `67c85ae87` (`notloop_passes.sh` の commit)。§4b は `112cdcf32` (main 取り込み済みの測定 commit。`notloop_minset.sh`・`notloop_vardef.sh` と測定値を同 commit に含む)。§4c は本 PR のコード commit `a34f768e7` (`notloop_minset_err.sh` の旧版)。`notloop_minset_err.sh` はその後に修正しており、修正版の実測は未実施 (下記 §4c)。
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

- 19 行 (関数 18 個。0x7c76b0 は飛び先 2 つ) すべてで noopt は注釈が出る (19/19)。
- 表の内訳: 0x5e5d60 (既定で注釈有り) を除く 18 行が probe の未解決組に当たる。その内訳は、特定 5 行 (単独 disable で戻る 2 行: 0x487c30 は dis_wtwc、0x6a0ae0 は dis_empty / 両 disable で戻る 3 行: 0x732ae0・0x732c50・0x7c32c0) と未特定 13 行 (どの変種でも戻らない)。5 + 13 = 18。
- 0x5e5d60 は default で既に 1 (注釈あり) のため、「段の特定」には数えない。ただし、単一 range の再 lift (本表) と probe の判定 (関数全体の注釈) は同じ条件ではない。0x5e5d60 が probe の未解決 19 組に入るかは、以下の理由で確認していない。
- **未確認**: probe の未解決 19 組と表の 19 行の 1 対 1 対応は示せていない。表は関数 18 個・飛び先 19 個 (0x7c76b0 は 2 飛び先) で、0x5e5d60 を含む。probe の出力 (`pairs.txt` 相当) は本 PR に無く、この run の環境にも無い。RetDec (`toolchain-retdec`) と emsdk (`toolchain-emsdk`) も無いため、probe を再実行できなかった。したがって「表の 18 行が probe の 19 組のうち 18 組である」とは言えず、未測定の 1 組は特定できていない。

## 3. 代表 1 組 (0x732ae0 → 0x732b75) の絞り込み

- 単独の disable: 既定の optimizer を 1 つずつ disable し、どれ 1 つでも注釈は戻らなかったと記録している。ただし測定の母集団 (48 個か、§4b と同じ 32 種か) を示す測定ログは本 PR に無く、再確認できていない。母集団は未確定として扱う。
- 単独の enable (`--backend-enabled-opts`): EmptyStmtOptimizer・WhileTrueToWhileCondOptimizer・BreakContinueReturnOptimizer・GotoStmtOptimizer・IfStructureOptimizer・DeadCodeOptimizer・CopyPropagationOptimizer の各 1 件のみでは、いずれも注釈は有り (1)。`EmptyStmtOptimizer` のように既定で有効な optimizer を列挙しても結果が既定 (0) から変わる (1) のは、このオプションが「列挙したものだけを有効にする」指定だからと推定する (RetDec の仕様は未確認。列挙外の既定 optimizer が無効になる前提)。
- 両方の disable のみ戻る。よって注釈の消失は、この 2 つの組み合わせ (相互作用) による。単独の原因は特定できない。

## 4. 判定

- **測定済み**: 19 組すべて notloop の飛び先は命令境界、`--backend-no-opts` で注釈が出る (19/19)。
- **測定済み**: 表の 18 行 (0x5e5d60 を除く) のうち、`EmptyStmtOptimizer` と `WhileTrueToWhileCondOptimizer` のどちらか単独の disable で注釈が戻る 2 行 (0x487c30 は dis_wtwc、0x6a0ae0 は dis_empty)、両方 disable で戻る 3 行 (0x732ae0・0x732c50・0x7c32c0) の計 5 行。
- **既定で注釈有り**: 0x5e5d60 は default で注釈が出るため段の特定の対象外 (probe の未解決に入らない)。
- **未特定**: 残り 13 行は、どの単独 disable・両方 disable でも戻らない。段は特定できていない。
- **未確認**: probe の未解決 19 組と表の行の 1 対 1 対応。表から数えた未測定組は 1 組 (上記 §2 の未確認を参照)。
- **未検証**: 注釈の消失が「統合」によるかは確認していない (#4393 の推定のまま)。戻した C の wasm 実行による bit 一致は未実施。

## 4b. 12 組の全 disable と VarDefStmtOptimizer 単独 (本 run)

- 測定 commit: `112cdcf32` (main 取り込み済み。`notloop_minset.sh`・`notloop_vardef.sh` と測定値を同 commit に含む)。素材・RetDec・emcc は §1 と同じ。
- **母集団**: §4b の全 disable と 1-minimal は、`--backend-disabled-opts` に渡した **ヘッダ名 32 種** の範囲でのみ成り立つ。ヘッダ名は本 run に展開した RetDec の `optimizers/*.h` のファイル名から `.h` を除いたもの (32 件)。§3 の「既定の 48 個」との差 16 種は、§4b では探索していない。差の 16 種が RetDec の名前として渡せるかは未確認 (本 run に RetDec が無く、ヘッダ名一覧もリポジトリに無い)。したがって下記の結論は「32 種の中での最小」であり、全 optimizer の中での最小ではない。件数 32 は再計数していない (素材が無い)。
- 全 disable (32 種): 表の未特定 13 行のうち、関数範囲を取れた 12 行で注釈が戻る (12/12)。0x683120 は当時 `NORANGE` で未測定だったが、§4c で範囲を取得して測定済み (注釈は戻る)。
- 1 組の最小集合 (`notloop_minset.sh`): 0x732ae0 は `EmptyStmtOptimizer,WhileTrueToWhileCondOptimizer` (§3 と一致)。

| 関数 | 飛び先 | 全 disable (32 種) で戻る | 32 種の中での 1-minimal |
|---|---|---|---|
| 0x408770 | 0x4087ba | 戻る | VarDefStmtOptimizer |
| 0x412db0 | 0x412e10 | 戻る | VarDefStmtOptimizer |
| 0x4166b0 | 0x4168ba | 戻る | VarDefStmtOptimizer |
| 0x44abe0 | 0x44ac34 | 戻る | VarDefStmtOptimizer,WhileTrueToWhileCondOptimizer |
| 0x52ef40 | 0x52eff1 | 戻る | VarDefStmtOptimizer |
| 0x575480 | 0x575627 | 戻る | VarDefStmtOptimizer |
| 0x59a1c0 | 0x59a260 | 戻る | VarDefStmtOptimizer |
| 0x717600 | 0x7176ba | 戻る | VarDefStmtOptimizer |
| 0x741340 | 0x7414ec | 戻る | VarDefStmtOptimizer |
| 0x7c0570 | 0x7c062e | 戻る | VarDefStmtOptimizer |
| 0x7c76b0 | 0x7c773b | 戻る | VarDefStmtOptimizer |
| 0x7c76b0 | 0x7c7796 | 戻る | VarDefStmtOptimizer |
| 0x683120 | 0x6835cb | 戻る (§4c で測定。当時の表は `NORANGE`) | VarDefStmtOptimizer (§4c) |

- 上表の範囲 (`lo-hi`) は本 run の `targets.txt` にあり、リポジトリに収録していない。`notloop_vardef.sh` の入力として再現するには、関数の範囲を取り直す必要がある (未収録)。
- **VarDef 単独の disable で件数は減らない**: `notloop_vardef.sh` で、VarDefStmtOptimizer のみ disable した C の `emcc -fsyntax-only` の `not in loop` 件数は、既定 C と全 12 組で同じ (0x4166b0・0x575480・0x7c76b0 系は 4 件、0x717600 は 2 件、他は 1 件)。注釈の復帰は、この件数を変えなかった。
- 判定 (測定の範囲に留める): 注釈の消失は VarDefStmtOptimizer 単独 (11 組) と、VarDefStmtOptimizer + WhileTrueToWhileCondOptimizer (0x44abe0) の disable で戻る。VarDef 単独の disable では `not in loop` の件数は減らない。これ以上の結論 (VarDef が原因ではない等) は、件数を減らす別の段・組み合わせを測っていないので言えない。
- 未検証: 最小集合の C を wasm 実行して bit 一致を確認すること (未実施)。全 disable 32 種は `--backend-disabled-opts` に全名を渡しており、名前の全件が有効であることは未確認 (存在しない名前は無視される)。

## 4c. 0x683120 (`0x6835cb`) の測定 (本 run。測定 commit は本 PR のコード commit)

- 素材: `toolchain-retdec` (RetDec v5.0)・`toolchain-emsdk` (6.0.12)・`fl-win64` (`extracted/block19091_PE.bin`)。`$RUNNER_TEMP` に展開。emcc は `PATH` に通した (通さないと `emcc` が見つからず、`not in loop` が 0 と誤読される)。
- 範囲: `0x683120-0x6835ff` (lift 可能。前 run の `NORANGE` の解消。`--backend-no-opts` で注釈 1 件)。
- 全 32 種 disable: 注釈 0 → 1 (戻る)、`not in loop` 1 → 0。
- VarDefStmtOptimizer 単独: 注釈 0 → 1 (戻る)、`not in loop` は 1 のまま (`notloop_vardef.sh`)。
- 注釈を戻す最小集合 (`notloop_minset.sh`・所要 88.7 s): `VarDefStmtOptimizer` 単独。
- `not in loop` を 0 にする最小集合 (`notloop_minset_err.sh`・所要 93.0 s。本 run 新規): `WhileTrueToWhileCondOptimizer` 単独。**この結果は旧版スクリプト (測定 commit `a34f768e7`) によるもの。** 旧版は RetDec 失敗時に前候補の `e.c` が残る・emcc の終了コードを見ない、という偽陽性の余地があったため、この値は検証されていない。
- 修正版 (本 PR の HEAD): 候補ごとに `e.c` を消し、RetDec の終了コード・`e.c` の存在・emcc の終了コードを確認する。既定 C で `not in loop` が 0 なら中止する (正対照)。この修正版での再測定は素材 (`toolchain-retdec`・`toolchain-emsdk`) が無く未実施。修正版の分岐は偽の RetDec / emcc で確認済み (正常系・RetDec 失敗で中止・emcc 無しで中止)。
- 判定 (旧版の結果を前提にした場合): この組では、注釈を戻す段 (VarDef) と `not in loop` を消す段 (WhileTrueToWhileCond) が**一致しない**。前 run までの「注釈の段 = エラーの段」という前提は、この組では成り立たない。ただし上記のとおり、この結論は修正版で再測定するまで確定ではない。
- 未測定: 0x683120 の C を wasm 実行して bit 一致を見ること (未実施)。残り 12 組の `not in loop` の最小集合 (範囲の確定が要るため未実施。0x408770 は範囲を推定で `0x4087ff` と置いて測ったが、範囲の根拠が無いため結果は採らない)。

## 5. 採らなかった方式

- 両方 disable した C を既定に採用する: 制御構造が既定と変わる。13 組は戻らないため、採用しても 27 件は解消しない。
- `break` を機械的に `goto` へ書き換える: 飛び先の注釈が無いので、飛び先を C 上で確定できない (#4393 §3)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残り 13 組の注釈消失の段 (単独・組み合わせの disable では戻らない) | 27 件のうち 13 組の直し方が決まらない | #1954 (HB-H41) |
| 全 optimizer 48 個のうち 32 種の外 (16 種) の探索 | 最小集合が 32 種の中でのみ成り立つ | #1954 (HB-H41) |
| 12 組の入力範囲 (`targets.txt`) が未収録 | §4b の再現手段 | #1954 (HB-H41) |
| VarDef 単独 disable で件数が減らない段の特定 | 27 件の直し方が決まらない | #1954 (HB-H41) |
| 両方 disable (5 組) の C の wasm 実行 (bit 一致) | 戻した C の正しさ未検証 | #1954 (HB-H41) |
| probe の範囲と grep の範囲の差 (0x5e5d60) | 未解決 19 組の数え方 | #1954 (HB-H41) |
| probe の未解決 19 組 (`pairs.txt`) と表 19 行の 1 対 1 対応。未測定の 1 組の特定 | 測定の網羅性 | #1954 (HB-H41) |
| `--backend-enabled-opts` の意味 (「列挙したものだけ有効」) は推定。RetDec の仕様は未確認 | §3 の単独 enable の解釈 | #1954 (HB-H41) |
