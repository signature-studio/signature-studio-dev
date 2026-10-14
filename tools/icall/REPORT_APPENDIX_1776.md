> **正本**: `tools/icall/REPORT.md`。#1776 (ICALL-39) の節。前節は `REPORT_APPENDIX_1592.md` #1592 (ICALL-33)。

## #1776 (ICALL-39): 警告 10 件の段の帰属と、警告を出す edge 破棄の機構 (部分達成)

素材: `fl-win64` (`extracted/block00031_PE.bin`)・`toolchain-retdec` (RetDec v5.0 install bundle)。
測定 commit = `0b17ef9f` (origin/main 時点)。`tools/icall` のコードは変更していないため、差分は本文書の追加のみ。
差分証跡 (HEAD = 本節の commit):

```
git diff 0b17ef9f HEAD -- tools/icall    # 本文書の追加のみ
```

### (1) 再現 (run A、`--print-after-all` 付き、foreground・1 回)

`fn_boundary_repro.sh` の run A と同じ範囲 (`0x128c280-0x128c2e1,0x128c320-0x128dc44`) に `--print-after-all` を付けた。

- rc=0、所要 20.4 s。開始時 load 0.40。
- 警告 10 件 (`NonRecursiveCFGBuilder`)。`#1592` 節の (1) A の 10 件と一致。
- 内訳: `# empty statement` 3 件・`rax_1_reload = rax_1_reg2mem` 5 件・`var514 = *(IntToPtrCastExpr<ptr>((var441 - 8)))` 2 件。
- 警告文に関数名は出ない。全件が `function_128c320` の定義内 (`define i64 @function_128c320()`、dump 行 653214 以降) の段で出ることを確認。

### (2) 警告が出る段 (受入 1 の段の帰属)

`A.log` の段見出しと警告行を行番号で対応づけた (repo 外・未 commit)。

| 段 (直前の見出し) | 件数 | 直後の出力 |
|---|--:|---|
| `removing code that is not reachable in a CFG` | 2 | `# empty statement`・`rax_1_reload = rax_1_reg2mem` |
| `optimizations` → `-> running SimpleCopyPropagationOptimizer` (1 回目) | 2 | `# empty statement`・`rax_1_reload = rax_1_reg2mem` |
| `optimizations` → `-> running CopyPropagationOptimizer` (1 回目) | 2 | 同上 |
| `optimizations` → `-> running SimpleCopyPropagationOptimizer` (2 回目) | 2 | `var514 = *(...)`・`rax_1_reload = rax_1_reg2mem` |
| `optimizations` → `-> running CopyPropagationOptimizer` (2 回目) | 2 | 同上 |

- 警告の順序はログの出力順で、optimizer 名の直後の出力を、その optimizer の実行中の警告として帰属させた (推定)。
- CopyPropagationOptimizer は `runOnFunction()` の先頭で `cfgBuilder->getCFG(func)` を呼ぶ (upstream `src/llvmir2hll/optimizer/optimizers/copy_propagation_optimizer.cpp`、v5.0 で確認)。optimizer ごとに CFG 構築が走り、同じ edge 破棄が再出力されると読める (`getCFG` の内部の再構築有無は未確認)。SimpleCopyPropagationOptimizer も同型と推定 (未検証)。
- `#1456` の記述「BIR 変換 → CFG 構築」は、最初の 2 件 (`removing code that is not reachable`) と一致する。残り 8 件は copy-propagation 系の CFG 再構築で、`#1592` 節の観測と一致する。
- 結論: 10 件は「LLVM→HLL 段の最初の CFG 構築 (2 件)」と「copy-propagation 系の CFG 再構築 (8 件、同じ edge の再出力)」に分かれる。段の帰属は確定。

### (3) 警告の発生箇所と edge 破棄の機構 (upstream v5.0 ソース)

- 警告は `NonRecursiveCFGBuilder::addEdgeFromVector()` (`src/llvmir2hll/graphs/cfg/cfg_builders/non_recursive_cfg_builder.cpp`) の 2 分岐で出る。両分岐とも同じ文言。
  - (a) 後続 statement が `EmptyStmt`: `emptyStmtToNodeMap` に無い → 当該 build で一度も visit されていない空文。
  - (b) 後続 statement が非空: `cfg->getNodeForStmt(succStmt).first` が null → `stmtNodeMapping` に無い。
- ログは (a)/(b) を区別しない。このため「どちらの分岐か」は本節では未確定。
- upstream の同関数のコメントに、この現象が既知の TODO として書かれている: `addEdgeFromCurrNodeToSuccNode()` が親の successor へ edge を作るが、その target の job が作られない場合がある。upstream は原因を特定できていないと明記し、警告を出して edge を捨てる暫定処理にしている。
- 警告を出す統一処理: 該当 edge は追加されない。そのため target の node は到達不能になりうる。`purgeCFG()` の `removeUnreachableNodes()` で statement が消えるかどうかは本節では未確認。
- 結論: `RNC-edge-drop` の「edge 破棄」という機構は upstream の既知 TODO と一致する。ただし本 run では (a)/(b) の別と、捨てられた edge が最終出力の statement を落とすかは確定していない。

### (4) 受入 2 (`function_128c320` の BIR ノード欠落の機構) の状態

- 本 run では確定していない。警告文は statement 名のみで関数名を出さないため、A の 10 件が `#1592` の D で出る 5 件 (`function_128c320()` へ向かう edge) と同じものかは未確認。
- `--print-after-all` は BIR を dump しないため、`#851` の (2) と同じく段内部の対応は未特定。
- 上記 (3) の機構 (upstream の既知 TODO: parent successor への edge で job が無い) は、BIR ノード欠落の候補になりうるが、本 run ではこの候補を実測で結び付けていない。

### (5) DEFECTS 行案 (受入 3)

- `docs/DEFECTS.md` の D1a〜D22 のどれとも一致しない (D15 は「call 命令の IR ブロックが空」で、本件とは別)。
- 一方、本件の機構は upstream の既知 TODO と一致するため「完全に未知の類型」ではない。
- 最終出力への影響 (statement が落ちるか、miscompile になるか) が未確定のため、`RNC-edge-drop` は現時点で `docs/DEFECTS.md` に正本化しない。行案は保留 (`#1592` の保留を継続)。

### 未達 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 警告 (a) 空文 / (b) 非空 のどちらか、各 statement の BIR・AST 上の由来 (`--print-after-all` の段間差分) | 警告 10 件の statement 単位の出所が未確定 | #1861 `[ICALL-46]` |
| 捨てられた edge が最終出力の statement を落とすか (`removeUnreachableNodes` の前後の比較) | `DEFECTS.md` 行案 (`RNC-edge-drop`) の判断材料 | #1861 `[ICALL-46]` |
