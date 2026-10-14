> **正本**: `tools/icall/REPORT.md`。#1592 (ICALL-33) の節。前節は `REPORT_APPENDIX_851.md` #1456 (ICALL-30)。

## #1592 (ICALL-33): 警告 10 件の出所 (関数本体の CFG 段) と 366 site 落ちの独立性 (部分達成)

素材: `fl-win64` (`block00031_PE.bin`)・`toolchain-retdec` (RetDec v5.0)・`work-icall` (`rt_flengine/sites_after.json` の既存監査)。
測定 commit = `5f0a8ce9` (origin/main 時点)。`tools/icall` のコードは変更していないため、差分は本文書の追加のみ。
差分証跡 (HEAD = 本節の commit):

```
git diff 5f0a8ce9 HEAD -- tools/icall                                            # 本文書の追加のみ
git diff 5f0a8ce9 HEAD -- tools/icall ':!tools/icall/REPORT_APPENDIX_1592.md'    # 0 行
```

### (1) 再現 (A〜D、`fn_boundary_repro.sh`、foreground・1 回)

開始時 load 0.25〜0.55。

| run | rc | sec | 警告 | `function_128c320` ラベル |
|---|--:|--:|--:|---|
| A | 0 | 13 | 10 | `0x128c320--0x128dc44` |
| B | 0 | 13 | 10 | `0x128c320--0x128dc44` |
| C | 0 | 9 | 5 | `0x128c320--0x128c321` (1 B) |
| D | 0 | 14 | 15 | `0x128c320--0x128dc44` |

全体 49.4 s (`real`)。#1456 の表と一致。

### (2) 警告を出す段と statement (受入 1)

`dump/A.full.log` (`fn_boundary_repro.sh` の run A で `--print-after-all --select-ranges A` を付けて生成。repo 外・未 commit。682 段 / 約 68 万行) で、警告 10 件の位置を段に対応づけた。

- 段の帰属: 既存 `REPORT_APPENDIX_851.md` (#1456) は警告を「BIR 変換 → CFG 構築 (`removing code that is not reachable`)」と記録している。本節の dump 観測では警告行が `LLVM IR -> HLL` の直前 (`Generate the current bitcode` の後) に出るとした。両者の差は本節の dump を再確認していないため**未検証**。段の名前は #1456 の記述を正とし、HLL 段への帰属は確定扱いしない。
- 警告 10 件の観測内訳 (dump 上の位置):
  - `removing code that is not reachable in a CFG` で 2 件 (`# empty statement`・`rax_1_reload = rax_1_reg2mem`)。
  - `SimpleCopyPropagationOptimizer` / `CopyPropagationOptimizer` で残り 8 件 (同じ edge 群の再警告)。
- `rax_1_reload = rax_1_reg2mem` の 5 件は、関数本体の `%rax.1.reg2mem` / `%rax.1.reload` の alloca・store・load の組 (`A.full.log` 673644・673987〜674002 行) と名前が一致する。ただし、警告文の statement が IR の命令と 1 対 1 で対応することは確認していない (生成段は未確定)。
- `var514 = *(...)`・`var512 = *(...)` の 2 件 (系 2 件) は、IR dump 内に同名の命令が無い。出所は未特定。
- `# empty statement` の 3 件も、IR dump に直接対応する命令が無い。
- 結論: 警告の出る pass は `removing code that is not reachable in a CFG` と copy-propagation 系まで観測。段の帰属は #1456 (BIR 段 CFG 構築) と未突合。statement の対応は `rax.1` の組のみ推定 (未確定)。

### (3) 183 site 突合 (受入 2): `roundtrip.sh` 条件 (書換え後)

`tools/icall/roundtrip.sh` を、RetDec のパスを素材 (`[RETDEC]`) に差し替えた一時コピーで実行 (リポジトリ内のスクリプトは変更していない。測定に使ったコピーは runner の一時領域 (リポジトリ外) に置き、commit していない)。

| 集合 | 全 call site | 書換え後 dropped | kept_indirect | 所要 |
|---|--:|--:|--:|--:|
| C (`0xc589b0` + `0x128f9e0`) | 374 | **366** | 8 | 42 s |
| D (C + `0x128c320` 本体) | 388 | **366** | 22 | 42 s |

site の内訳 (C・D 共通、`sites_after.json`):
- `0xc589b0`: 183 件すべて dropped。
- `0x128f9e0`: 191 件中 183 件 dropped、8 件 kept_indirect。
- `0x128c320` 本体 (D のみ): 14 件、すべて kept_indirect (dropped 0)。

結論: **本体 `0x128c320` を足しても dropped は 366 のまま変わらず、本体 14 site は落ちない。** 366 落ちは本体の edge 破棄 (警告 10〜15 件) と独立。よって「edge 破棄 → call 消失 → 366 落ち」とは本件の範囲では独立と観測された (因果の確定は未了)。
既存の before 側監査 (#1285 節 (3)、`status change C->D: []`) とも整合する。

### (4) DEFECTS 行案 (受入 3)

- `docs/DEFECTS.md` の既存類型 (D1a〜D22) とは一致しない (D15 は「call 命令の IR ブロックが空」だが、本件は call が残る)。
- ただし、警告の発生箇所 (HLL の CFG 段) と、落ちる edge の原因 (`function_128c320` の BIR ノードの欠落) が未確定。
- 366 落ちとの因果は本件の範囲で独立と観測されたため、`RNC-edge-drop` を現時点で類型として正本化しない。**行案は保留** (本節では「該当なし・保留」と明記)。

### 未達 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `var514`/`var512`/`# empty statement` の 5 件の HLL 段での出所 (RetDec 内部の名前の追跡) | 警告の全件の出所が未確定 | #1776 `[ICALL-39]` (本 run で起票) |
| `function_128c320` の BIR ノードが欠落する原因 (RetDec ソース追跡) | edge 破棄の機構が未確定。`DEFECTS.md` 行案の判断材料 | #1776 `[ICALL-39]` (本 run で起票) |
