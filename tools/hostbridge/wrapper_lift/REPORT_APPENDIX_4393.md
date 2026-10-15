# REPORT 付録 — #4393 (HB-H54): `statement not in loop` 27 件の飛び先注釈欠落の原因切り分け

> **正本**: `tools/hostbridge/wrapper_lift/REPORT.md` §15。本付録は計測の全文。

測定 commit: `093bed7c1` (本 PR の測定コードを入れた最初の commit。`notloop_probe.py` の追加のみ)。検証 HEAD は同じ commit。
素材: `fl-win64` (`extracted/block19091_PE.bin`)・`toolchain-retdec` (RetDec v5.0)・`toolchain-emsdk` (emcc 6.0.12)。`$RUNNER_TEMP` に展開。load average (1 分値) 0.26–0.72。
起点: origin/main `8635f4546` から `4393-retdec-statement-not-in-loop` を切った worktree。

## 1. 再現 (受入条件 1 の前提)

- `retdec_batch.py` (BATCH=500・直列・`KEEP_DIR` 指定): 19,816 / 19,816 ok・RetDec 呼び出し 41 回・fail 0・所要 `retdec_seconds_all` 191.52 s (wall 191.69 s)。出力 C は 41 ファイル。
- 生の emcc (`-fsyntax-only -w -ferror-limit=0`) の `'break' statement not in loop` は **78 行**。#1679 の報告 (78) と一致。

## 2. 切り分け (受入条件 1)

`notloop_probe.py` の判定。78 行を、飛び先 `// break -> 0x<VA>` の注釈の位置で分類する。

| 分類 | 行数 | 組 (関数・飛び先) 数 |
|---|---|---|
| 飛び先の注釈 `// 0x<VA>` が同じ関数内にある (`gotofix` が直せる) | 51 | — |
| 飛び先の注釈が同じ関数内に無い (`skip_no_addr_in_func` の 27 件) | 27 | 19 |

27 件は 19 組 (同じ関数の同じ飛び先を複数の `break` が指すため)。

### 2.1 飛び先の機械語上の位置

19 組すべてについて、飛び先 VA は当該関数の線形 decode (capstone、`Image.read`) の命令境界。
- 19 組すべて命令境界 (boundary)。decode 範囲の欠落や、飛び先が命令の途中に当たる、という原因ではない。
- 19 組中 16 組は同じ関数内に飛び先への直接 jump がある。残り 3 組は無い (`0x44ac34`・`0x7c3322`・`0x487f31`)。直接 jump が無い組も命令境界上にあり、RetDec が fall-through で到達する位置と推定する (未検証)。

### 2.2 原因: RetDec の backend 最適化段で注釈付きブロックが落ちる

同じ関数を `--backend-no-opts` で再 lift すると、19 組すべてで飛び先の注釈 `// 0x<VA>` が出力 C に現れる (`noopt_annotated` 19/19)。既定 (最適化あり) では 0 件。

代表例 `function_732ae0` (`0x732ae0-0x732b95`、飛び先 `0x732b75`):

- 飛び先 `0x732b75` は `mov al, 1; jmp 0x732b88` (戻り値 1 の経路)。
- `--backend-no-opts` で出た `.ll` には `dec_label_pc_732b75` のブロックが存在する (`br label %dec_label_pc_732b88`)。backend の最適化を切らない限り IR は残る。
- `--backend-no-opts` の C では `// 0x732b75` が出力 (`result = v7; return result` の直前)。
- 既定の C では、飛び先のブロックは `// break -> 0x732b75` の `break` の先で `v7 = v4 & -256 | 1` に統合され、注釈 `// 0x732b75` が消える。戻り値の式は残る (値は落ちていない)。よって `gotofix` の「同じ関数内に注釈が無い → 直さない」は正しい判定だが、原因はバックエンドの統合で、C 上の制御フロー欠落ではない。

**確定していること**: 27 件 (19 組) は、RetDec の既定 backend 最適化段で飛び先の注釈付きブロックが他のブロックに統合され、注釈が消えたもの。機械語上の飛び先は命令境界で、IR に存在する。
**未確定**: どの最適化パスで統合されるか (`--backend-disabled-opts` による特定は未実施)。統合後の C が実行時に同じ値を返すかは、wasm の bit 一致検証が無いため未検証 (DEFECTS の類型との照合も未実施)。

## 3. 採らなかった方式

- `--backend-no-opts` で全体を lift し直す: 制御構造が既定と変わるため、既定の出力に対する 27 件の修復にはならない。別の出力を作るので、本 issue の範囲外 (#1954 の範囲で比較が必要)。
- `break` を機械的に `goto` へ書き換える: 飛び先の注釈が無い以上、飛び先を C 上で確定できない (`gotofix` の既存の判定を変えない)。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 統合を行う backend 最適化パスの特定 (`--backend-disabled-opts` の二分探索) | 27 件の直し方が決まらない | #1954 (HB-H41) |
| `--backend-no-opts` の出力での wasm 実行 (bit 一致) | 27 件の制御構造の正しさ未検証 | #829 (HB-H20) 系 |
