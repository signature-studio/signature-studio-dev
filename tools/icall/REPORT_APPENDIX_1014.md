# 付録: icall #1014 (ICALL-15) — FLEngine 2 関数の落ち 366 site のブロック単位 before / after 分類

> 親: #847 (ICALL-9)。受入条件 1 (SCCP の機構特定) は PR #1250 で達成済み (`REPORT_APPENDIX.md` §12.3)。本付録は受入条件 2 (ブロック単位の before / after 分類) の結果と、その検証。受入条件 3 (修正と kept の実測) は未達 (§5)。
> 既知類型との関係 (`docs/DEFECTS.md`): **未判定** (D15 と症状が同型、D1b と機構が近い。§6)。

## 1. 結論

- 落ちた 366 site は**全て消失**。別関数の段に現れた落ち site は 0 (`moved 0`)。
- 段の流れ (段番号は `--print-after-all` の dump 全体での段番号):
  1. GVN 段: `function_1cc0000` は段 401 (`Global Value Numbering`)、`function_1cc9b70` は段 402。stub 呼出しを含むブロックは 114 / 121。
  2. SCCP 段: 段 405 / 406 (`Sparse Conditional Constant Propagation`)。stub 呼出しはこの段で減る (段ごとの数の正本は `REPORT_APPENDIX.md` §12.1。本付録 §2 の再実行で一致)。ブロック数はこの段では変わらない。
  3. 最初にブロック数が減る段 (Jump Threading): 段 413 / 414。ブロック数は 303 → 29、316 → 42。落ちた site のブロック 114 + 114 がここで消える。
- `function_1cc9b70` の kept 8 site (6 ブロック) は SCCP 段と Jump Threading 段の後も残る。SCCP 段の stub 9 本は、kept 8 本と comis 1 本の内訳 (§3)。

## 2. 測定

- 測定 commit: `f15f25b4` (分類スクリプト `tools/icall/sites_block_classify.py` の最終版。段番号・ブロック数・1 対 1 検証・ネガティブコントロールを script が出す)。
- 入力: `measure_flengine_split.sh` の出力 (測定経路は HEAD `1d363e63`)。素材 `fl-win64` (`block00031_PE.bin`、22,227,016 B、`$RUNNER_TEMP/fl-win64/extracted`)。
- RetDec: 上流 release v5.0 (`RetDec-v5.0-Linux-Release.tar.xz`、sha256 `e5a7dd82…8ab1a5`) を `$RUNNER_TEMP/retdec` に展開し、`[RETDEC]` の位置 (`docs/REFERENCES.md` §4) に symlink した。素材 bundle `toolchain-retdec` は本 run に無かったため、上流配布物で測定した。bundle 版での独立再実行は PR 本文の `oc_artifacts` 行で行う。
- 所要 (各 1 回。min–max レンジは未取得):
  - `measure_flengine_split.sh`: real 132.9 s (user 133.1 s、sys 55.9 s、終了時の 1 分 load 1.53、4 core)。base 366 / c2 366 (基準どおり)。site 374 (0xc589b0 側 183 / 0x128f9e0 側 191)。段 dump 709 段。
  - `sites_block_classify.py` (`RETDEC_BIN` 指定、段 dump を RetDec で取り直す): real 68.2 s (user 21.0 s、sys 47.2 s、終了時の 1 分 load 0.67)。
- fix round 2 の再実行 (コードは `f15f25b4` と同じ。作業ツリーは md のみ変更): `measure_flengine_split.sh` real 117.3 s (base 366 / c2 366、段 709)、`sites_block_classify.py` (RetDec 取り直し) real 60.7 s。`summary.txt` の全数値は本節・§3・§4 と一致 (タグ段候補の段 81〜87 は各段とも 12)。
- 段 dump を再利用する実行 (引数 `DUMP`) の `summary.txt` と `site_block.tsv` は、RetDec を取り直した実行と `cmp` で一致。
- 段ごとの stub 呼出し数 (GVN 段・SCCP 段の値) は、この再実行の `summary.txt` が `REPORT_APPENDIX.md` §12.1 の値と一致することを確認した。

## 3. 結果 (`summary.txt` の出力)

| 関数 (lift 名) | 元 VA | site | 落ち | kept | GVN 段 | SCCP 段 | JT 段 | stub を含むブロック (GVN) | ブロック数 (GVN → JT) |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `function_1cc0000` | 0xc589b0 | 183 | 183 | 0 | 401 | 405 | 413 | 114 | 303 → 29 |
| `function_1cc9b70` | 0x128f9e0 | 191 | 183 | 8 | 402 | 406 | 414 | 121 (site 120 + comis 1) | 316 → 42 |

- stub 呼出し数 (段ごと、SCCP 段で減る値) は本表に書かない。正本は `REPORT_APPENDIX.md` §12.1 (一致は §2)。
- site ブロック: 234 (114 + 120)。落ち 228 (114 + 114)、kept 6 (`function_1cc9b70`)。
- 1 対 1 検証: GVN 段の stub 合計 375 = site ブロックの stub 合計 374 + 非 site 1 (comis)。234 ブロックで「ブロックの site 数 = GVN 段の stub 数」の不一致は 0。
- 消失: 落ちた 366 site は全て Jump Threading 段で label が消える (`label_gone_at=413` 183 件、`label_gone_at=414` 183 件)。
- VA の対応: stub の `!insn.addr` と `sites[].new` の差は +78 が 367 件、+81 が 7 件。対応 374、未対応 1 (VA `0x1cca430`、`function_1cc9b70` の comis stub)、同一 site への重複 0。
- タグ段の基準は段 100 (`Global Variable Optimizer`、stub VA 375)。段 81〜87 の各段をタグ段にすると、基準と所属 label が違う site は各段とも 12 (`summary.txt` のタグ段候補の列)。段 445 以降は stub VA が 9 件のみで、基準と 366 site の所属が変わるため使えない。

## 4. ネガティブコントロール (WORKFLOW §5)

同じ段 dump を壊して、検出器が反応することを数値で確かめた (script の `negctl` 行)。

| 対象 | 壊し方 | 結果 |
|---|---|---|
| 基準 (段を固定して再解析) | なし | 1 対 1 不一致 0 / moved 0 (本番と一致) |
| N1 (別関数への移動) | 段 402 の `function_1cc9b70` に、落ち site の label `dec_label_pc_1cc0a5e` を 1 つ注入 | moved 0 → 1 |
| N2 (1 対 1) | 段 401 の `function_1cc0000` の `dec_label_pc_1cc0a5e` から stub 呼出し 1 本を削除 | 1 対 1 不一致 0 → 1 |

- 注意: N2 は落ちの段を**固定して**検査する。固定しないと、stub を消した段が stub 総数の減少として「落ちの段」に自動判定され、比較対象が 1 つ前の段に移る。そのため不一致が 0 → 0 になり、検出器が盲目になる。script は `analyze(..., fixed)` で段を固定する。本番の自動判定は固定段と一致することを `negctl 基準` 行で確認した。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入条件 3: 畳み込まれた switch 枝の動的検証 (native で `g22 > 1` を通す入力) と、修正後の kept 実測 | 366 site が真の死コードか lift 欠陥かが未決。修正方針を決められない | #1014 (継続) |
| 既知類型: 366 site が D15 型 (vtable 呼出しの欠落) か D1b 型 (分岐先の dead code 化) か | `DEFECTS.md` への登録は未判定。§6 | #1014 (継続。受入条件 3 の動的検証で決める) |

## 6. 既知類型との関係: 未判定

- 落ちた 366 site は全て `call qword ptr [reg+disp]` (vtable 呼出し) で、#1014 の 2026-10-13 21:43 のコメント (PR #1393 の run) と一致する。
- 症状 (メモリ間接 call が最終 IR から消える) は `docs/DEFECTS.md` D15 と同型。機構 (LLVM の畳み込みで分岐先が dead code になる) は D1b に近い。
- 真の死コードか lift 欠陥かは、受入条件 3 の動的検証まで決まらない。よって「該当なし」とはしない。
- `docs/DEFECTS.md` への行案 (直接編集せず PM が反映する。番号は PM が割り当てる。列は DEFECTS.md の表に合わせた):

```
| D-1014 (番号は仮) | fe→opt | **新規** (#1014 / PR #2836) | vtable 呼出し (`call qword ptr [reg+N]`) が最終 IR から消える。症状は D15 と同型 | 未確定。SCCP (段 405) で stub が消え、Jump Threading (段 413) で分岐先ブロックが dead code になる。D1b と機構が近い | FLEngine 0xc589b0 / 0x128f9e0 の落ち 366 site (本付録 §3) | 段 dump の stub 数が SCCP 段で 0 になる (本付録 §3) | 未修復 (動的検証待ち) |
```

## 7. 検証

- 再現 (段 dump を取り直す。`RETDEC_BIN` に `retdec-decompiler` を指定する):
  1. `FL_WIN64_DIR=<fl-win64 展開先>/extracted bash tools/icall/measure_flengine_split.sh <outdir>`
  2. `RETDEC_BIN=<retdec-decompiler> python3 tools/icall/sites_block_classify.py <outdir>/base/rw.dll <outdir>/base/after.ranges <outdir>/base/map.json <outdir>/base/sites_after.json <outdir2>`
  3. 段 dump を再利用する場合は、2 の後ろに段 dump のパス `<outdir2>/print_after_all.txt` を付ける (RetDec を呼ばない)。
- 測定経路の差分: `git diff --stat 26f90ada f15f25b4 -- tools/icall/measure_flengine_split.sh tools/icall/roundtrip.sh tools/icall/audit_icall.py tools/icall/icall_rewrite.py tools/icall/ir_icall_restore.py tools/icall/passes_stub_count.py tools/icall/sccp_stub_drop.py` は 0 行。
- 測定 commit 以降のコード差分 (WORKFLOW §6): `git diff f15f25b4 HEAD -- tools/icall ':!*.md'` の出力は 0 行 (`c4b6506d` 時点で確認。以後の commit は md のみ)。
- 範囲外: native での動的検証 (受入条件 3) は未実施。段 dump は RetDec v5.0 の出力に依存する。

## 8. 前版の履歴 (`REPORT_APPENDIX.md` §12.4.1・§12.4.2 から分割移動)

### 8.1 (旧 §12.4.1) 本 run (HEAD `12586095`) の実測と、分類で判明した点

測定経路のコード差分は `711b58ca` → `12586095` で 0 行。§12.1 / §12.3 の数値は本 run で再確認した。

- `measure_flengine_split.sh`: 132.7 s (real, 4 core) は HEAD `12586095` で新規取得した実測。
- 段 dump の `!N` 番号は最終 `.ll` の `!N` と一致しない (例: 最終 `.ll` の `!392` は `30189433`)。`map.json` の `sites[].new` と最終 `.ll` の META 値の共通は 0 件。site → 段 dump ブロックの突合は現成果物では組めず、段単位で `!N` を保存する修正が要る。
- `__icall_dispatch(i64 <site VA>)` は restored IR に 8 件あり、§12.3 の kept 集合と一致する。dropped の VA は現れない。

受入条件 2・3 は未達。次 run の入力: `oc_artifacts: fl-win64 toolchain-retdec`。

### 8.2 (旧 §12.4.2) 段 dump の構造の確定 (HEAD `1017f349`、測定は `measure_flengine_split.sh` を再実行)

測定値: `measure_flengine_split.sh` 119.9 s (real, 4 core, load 1.70)。base 366 / c2 366 (基準どおり)。`passes_stub.txt` 709 段。`passes_stub_count.py` の段 dump は 2,692,856 行 (119 MB)。

段 dump (`retdec-decompiler --print-after-all` の stderr) について、次を実物で確認した。突合 (受入条件 2) の前提になる構造である。

- **ヘッダ 1 個 = 段 1 本ではない**。同じ段名 (例 `Global Value Numbering`) のヘッダが段内で複数回出る。`function_1cc0000` の `define` は段 `GVN` の 3 本のヘッダのうち 1 本 (2476420 側の後ろ) にしか出ず、先頭の 2460095 側の本文は `__decompiler_undefined_function_*` の宣言だけの空関数だった。段の単位をヘッダで切ると関数と段の対応がずれる。
- **`!N` の META 定義はヘッダの直前の段に属する**。例: `!8632` の定義は 1468692 行にあり、その直前のヘッダは `Assembly mapping instruction removal` (1430666)。META は次のヘッダ (`C++ class hierarchy optimization` 1470748) の直前にまとめて出る。したがって `!N → VA` は段本文ではなく、META が並ぶ位置で解決する。
- 同じ `!8632` が段ごとに別の値を持つ (1468692 では `30212733`、1627480 では `30213838`)。`!N` を最終 `.ll` の番号と照合してはならない (前回の不一致の原因)。
- `block_map.py` (作業用・PR 外) で段ヘッダ単位に切ると、`function_1cc0000` の基本ブロックが 1 個にしか見えず、stub 呼出しを含むブロックの VA 集合が取れなかった。上の構造 (同名ヘッダの複数化) を反映して切り直すのが次の作業。

受入条件 2・3 は引き続き未達 (受入条件 2 は `REPORT_APPENDIX_1014.md` で達成)。同名ヘッダを束ねる規則は作っておらず、同付録は「関数の `define` がある段だけを使う」方式で回避している。修正 (受入条件 3) は未着手。
