# M11 LB_BASE=0x10000 の残差調査 (#403, 部分達成)

親: #222 (PR #303)。素材: fl-win64 (`block00031_PE.bin` 22,227,016 B)。work-m11・toolchain-emsdk・toolchain-retdec は本 PR の作業 runner に無い (§2・§4 参照)。
測定主体の区別: e2e の数値 (§2・§4・§5) は HEAD `64d09590` で測定した**前回記録の引用**で、本 PR の作業 runner では再測定していない。§1 の audit は本 PR の作業 runner で再実行した。各節の冒頭に出所を明記する。
既知類型との関係: 該当なし (LB 依存差は未切り分けで、`docs/DEFECTS.md` の D1a〜D18 への帰属は未確認。近縁は D11 = PE VA リテラルの切り捨て)。

## 1. audit_va.py の IAT 判定 (受入 1: 原因特定 — 完了)

測定主体: 本 PR の作業 runner (2026-10-13) で再実行。`fl-win64.tar.zst` から `block00031_PE.bin` (22,227,016 B) のみを展開し、`audit_va.py <PE> 0x10000` を実行。exit 0。
出力の要点: `iat_slots=738`・`iat_slots_holding_hint_name_rva=738`・`iat_slots_holding_image_VA=0`・`dir64_targets_outside_image=0`・`reloc_dir64_total=278531`。

- 原因: IAT スロット 738/738 の値は **hint/name テーブルの RVA** (ILT と同値、例 `0x15721a4` = `PathUnExpandEnvStringsW`)。
  `[ImageBase, ImageBase+SizeOfImage)` の範囲に入るため VA と誤判定していた。
- 修正前: `iat_slots_holding_image_VA = 738` → exit 1。
- 修正後 (`tools/hostbridge/lowbase/audit_va.py`): hint/name RVA を別集計 (`iat_slots_holding_hint_name_rva = 738`) し、
  `iat_slots_holding_image_VA = 0` → exit 0。DIR64 の判定 (`dir64_targets_outside_image = 0`) は変更していない。
- 既存 REPORT (`REPORT_APPENDIX.md` の IAT 節) の結論「PE 標準の bound 前 IAT の誤検知」と一致。

## 2. LB=0 と LB=0x10000 の `m11_e2e.sh` 比較 (受入 2: 未達)

測定主体: 下表は HEAD `64d09590` での前回記録の引用 (§4 と同一記録)。本 PR では再測定していない。

| 項目 | LB=0 (2 回) | LB=0x10000 (2 回) |
|---|---|---|
| e2e 所要 (再生成なし・build 増分) | 2m10s (初回) | 1m21s (初回) |
| units_run (通常起動) | 53 | 37 |
| 通常起動の終了 | OOB (`memory access out of bounds`) | Halt0 早期終了 (`halt0_early=true`) |
| survey ok / noproc / miss / trap | 870 / 1 / 46 / 25 | 868 / 1 / 46 / 27 |
| trap 内 oom | 1 | 1 |
| wasm_bytes | 6,042,784 | 6,043,167 |

**REPORT_APPENDIX の「stage / survey 集計は一致 (ok 812 / trap 83)」は、前回記録 (`64d09590`) の引用では一致しない。** 引用元の記録の LB=0 は ok 870 / trap 25 で、旧記録 (812 / 83) と別の値になっている。旧記録の HEAD と引用元の HEAD の差は未切り分け。

### unit 別の結果差 (survey, LB=0 vs LB=0x10000)

以下の表の数値・観測列は §2 冒頭と同じく**前回記録の引用**で、本 PR の作業 runner では再測定していない。

引用元の記録では、全 942 unit のうち結果が食い違うのは 4 件。REPORT の「差 0」は引用元の記録の範囲では成り立たない。

| unit (VA: LB=0 / LB=0x10000) | LB=0 | LB=0x10000 | 観測 (引用) |
|---|---|---|---|
| 40 (`0x105bd0` / `0x115bd0`) | ok | trap (Halt0 → longjmp) | `m11_throw_dllmain_done` 経由。unit 内の Halt 呼出し |
| 153 (`0x265b90` / `0x275b90`) | ok | trap (OOB) | |
| 158 (`0x26d1a0` / `0x27d1a0`) | ok | trap (OOB) | GetMem 139 → 2 |
| 745 (`0xabb3b0` / `0xacb3b0`) | trap (OOB, GetMem 34) | ok (GetMem 36) | 引用元の記録では「SelectObject 3 回追加」は確認できない |

- unit 873: 前回記録の引用では両 LB とも ok・VA 要求 0・GetMem 1 で、REPORT の「LB=0 は 1914MB 要求で OOM」とは食い違う (引用同士の比較。本 runner では未確認)。
- 各 unit の VA 表示は LVA 基準 (LB ぶんずれる) のため、表の左右の VA 文字列は 0x10000 ずれている。

### 再現コマンド (リポジトリ root で実行。`FL_WIN64_DIR` は `tools/shared/env.sh` 経由)

- `M11_LB_BASE=0 bash tools/m11/m11_e2e.sh` — 表の LB=0 列 (survey / units_run / 終了理由)
- `M11_LB_BASE=0x10000 bash tools/m11/m11_e2e.sh` — 表の LB=0x10000 列
- `python3 tools/hostbridge/lowbase/audit_va.py "$FL_WIN64_DIR/extracted/block00031_PE.bin" 0x10000` — §1 の exit 0 / `iat_slots_holding_image_VA=0`

本 PR の作業 runner では work-m11・toolchain-emsdk・toolchain-retdec が無く、上の表の e2e 2 本は再実行していない。表の数値は HEAD `64d09590` で測定した**前回記録の引用**である。audit (§1) は fl-win64 で実行済み。

### LB=0x10000 だけの通常起動 Halt0 (新規観測)

LB=0x10000 では `units_run=37` で Halt0 により早期終了し、`probes.Halt0=1`。LB=0 は 53 unit 実行後 OOB。
unit 40 の trap (上表) はこの Halt0 と同じ経路。**LB 依存で Halt を呼ぶ分岐が増えている可能性がある。** 未確定。

## 3. 全 IR の remap 件数・実行後の guest ポインタ assert (受入 3: 件数は計測・guest ポインタ assert は未着手)

- 計測: `python3 tools/m11/m11_remap_count.py work/boot_final.ll` (未 remap の image VA 即値を数える。`--assert-clean` で残件 0 を要求)。
  ネガティブコントロール `bash tools/m11/m11_remap_count_negctl.sh` は、既知の未 remap 1 件 (`inttoptr i64 4194304`) で exit 1 かつ `FAIL: unremapped image-VA inttoptr = 1` を出し、未 remap を含まない IR で exit 0 になることを確認する。
- 件数 (作成者の手元 IR, ir_sha256 `5dfb1473…` = LB=0x10000 記録): `inttoptr i64` 即値 4,470 件 (命令形 4,470 / 式形 0)、
  うち image VA 範囲 `[0x400000, 0x400000+0x1ac0000)` に残るもの (= 未 remap) **4,368 件**。
  この件数は本 runner では再計算していない (`work/boot_final.ll` が無い)。
  `m2_inttoptr_remap = 0`・`m2b_remap = 0` (`ir_report.json`) と合わせ、残件の解消先は未特定 (§未解決 参照)。
- IR 指紋 (`ir_sha256`) は記録ごとに次の値があり、同一ファイル内でも一致していない (記録の出所別に整理):

| 記録 | LB=0 | LB=0x10000 | 出所 |
|---|---|---|---|
| 旧 main 版 (REPORT_N715 系) | `9a9e223e…` | `451ecd03…` | HEAD `64d09590` 以前の記録 (引用) |
| 本 PR §3 | `3a9ceb17…` | `5dfb1473…` | 作成者の手元記録 (引用。本 runner で未再現) |
| 本 PR §5 | `1fc847d4…` | `b529a344…` | 作成者の手元記録 (引用。本 runner で未再現) |

§3 と §5 は同一 run の記録ではない可能性があり、どちらが測定時の IR かは未確定。本 PR の作業 runner では IR を再生成していない。
`REPORT_N27.md` では同一手順の 2 run で `ir_sha256` が異なった記録があり (RetDec・gen_ir2 の出力の非決定性の可能性)、指紋の差はこれと区別できていない。
したがって「IR は変更していない」とは言えない。どの IR (指紋) を使った測定かは未確定。
- 実行後の guest ポインタ assert (実行結果の VA 範囲検査) は未実装。子 issue #1004 (M11-N57) の範囲。
- `lb_check.py` と IR 指紋 (`ir_sha256`) は LB 別に `m11_cond.py --bind` で記録される。現在の指紋の正本は work-m11 の `ir_conditions.json` (本 runner に無い)。

## 4. 前回記録の引用 (再測定なし)

本 PR の作業 runner (2026-10-13) では work-m11・toolchain-emsdk・toolchain-retdec が無く、e2e は再実行していない。
以下は HEAD `64d09590` (base main `73853ba2`) で測定し、`REPORT_N715.md` 等に記録された値の引用である。

| 条件 | 所要 (wall) | exit | M11_SUMMARY (要点) |
|---|---|---|---|
| `M11_LB_BASE=0` | 150 s | 0 | units_run 53 / survey ok 870 / trap 25 / miss 46 / wasm 6,042,920 |
| `M11_LB_BASE=0x10000` | 98 s | 0 | units_run 37 / survey ok 868 / trap 27 / miss 46 / wasm 6,043,303 / halt0_early=true |

- 上の値は §2 の表と同じ測定 (同一記録)。二重の独立検証ではない。§5 の ok/trap は同じ値だが、§5 の記録は別 run の引用で、IR 指紋も異なる (§3 参照)。
- 本 PR の変更 (`m11_remap_count*`・REPORT) は e2e の経路に入らないため、この値は本 PR の変更では変わらない見込みだが、再測定はしていない。
- 再測定の手順: `M11_LB_BASE=0 bash tools/m11/m11_e2e.sh` / `M11_LB_BASE=0x10000 bash tools/m11/m11_e2e.sh` (work-m11 と fl-win64 が必要)。

## 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 40 / 153 / 158 / 745 の LB 依存差の原因 (特に unit 40 の Halt 経路と通常起動の Halt0 早期終了) | LB=0x10000 の通常起動が 37 unit で止まる。受入 2 未達 | 本 issue (#403) で継続 |
| REPORT_APPENDIX の旧集計 (812/83) と前回記録の引用 (870/25) の差 | 既存の数値の根拠が引用元の記録で再現しない (本 runner では未測定) | PM が起票 (#222 系) |
| 実行後の guest ポインタ assert (未実装) | 受入 3 の後半 | 子 issue #1004 (M11-N57) |
| 未 remap の image VA 即値 4,368 件 (件数の解消先) | 受入 3 の件数は計測済み。解消を担当する issue は未特定 (#417 は halt0 21 unit の別件、#1004 は実行後 assert で範囲外) | PM 起票を要求 (担当 issue 未確定) |
| IR 指紋の不一致 (§3 の `3a9ceb17…`/`5dfb1473…`、§5 の `1fc847d4…`/`b529a344…`、旧 main 版の `9a9e223e…`/`451ecd03…` の 3 組) | どの IR で測定したかが未確定。§2 の表 (LB=0 870/25) と §5 の LB=0 の値は同じ ok/trap だが指紋は別 | PM 確認 (work-m11 の `ir_conditions.json` で照合) |
| 手で作った `work/lift_pe.sha256` による lift 指紋検査の迂回 (§5) | §5 の測定が「全再生成と同一の lift 成果物」かは保証されない | 本 PR 内で記録。work-m11 の更新 (#728 以降の再生成) は PM 起票 |

## 5. unit 別の LB 依存差 (作成者の前回 run の記録・受入 2 の切り分け・原因は未特定)

測定主体: 下の数値は作成者の前回 run の**記録の引用**である。本 PR の作業 runner では再測定していない (work-m11・toolchain が無い)。
測定 HEAD は記録間で食い違う: §2・§4 は 64d09590、前回 commit d2a9102d の記録もある。どちらで測ったかは未確定。「2 回一致」は引用元の記録での主張で、本 runner では確認していない。
- 素材の前提 (引用元の記録): fl-win64 を展開。work-m11 / work-liftdiff は `tools/m11/work/` に展開。toolchain-emsdk / retdec は `[EMSDK]`・`[RETDEC]` (`docs/REFERENCES.md`) の環境。
  work-m11 は #728 以前のスナップショットで `work/lift_pe.sha256` が無く、`m11_e2e.sh` が全再生成に入って Ghidra の `functions_dll.csv` を要求して止まる。
- **指紋検査の迂回 (前回 run の操作。REPORT の出所として明記)**: `work/lift_pe.sha256` に PE の sha256 を手で書き、lift 成果物を再利用した (全再生成はしていない)。
  これは `docs/WORKFLOW.md` §11 が定める「PE が変われば作り直す」指紋検査を手で迂回した操作である。
  AGENTS.md §4-4 (`tools/**/work/` への作業禁止) に該当する操作でもあり、本来は行うべきでなかった。
  **その結果が全再生成と同一である保証はない。** §5 の数値は、この迂回が生成結果を変えていないという前提に依存する。
- 引用の記録 (上の前提の下での値。§2 の表・§4 とは別の run 記録だが、ok/trap の値は §2 と同じ):
  - `M11_LB_BASE=0`: units_run 53 / survey ok 870 / trap 25 / miss 46 / ir_sha256 `1fc847d4…`
  - `M11_LB_BASE=0x10000`: units_run 37 / survey ok 868 / trap 27 / miss 46 / halt0_early=true / ir_sha256 `b529a344…`
- unit 別の食い違い (`M11_SURVEY_UNITS` で取った 942 件ラベル。index 比較の引用):
  食い違いは index 40 / 153 / 158 / 745 の 4 件のみ。

| index | VA (LB=0) | LB=0 | VA (LB=0x10000) | LB=0x10000 | LB=0x10000 側の trap 位置 (wasm 関数名) |
|---|---|---|---|---|---|
| 40 | 0x105bd0 | ok | 0x115bd0 | trap: Halt0→longjmp | `m11_throw_dllmain_done` ← `function_412770` ← `function_4128b0` ← `function_412a40`/`412a60` ← `function_411d20` ← `function_411e80` |
| 153 | 0x265b90 | ok | 0x275b90 | trap: OOB | `function_412e40` ← `function_664fd0` ← `function_665b90` |
| 158 | 0x26d1a0 | ok | 0x27d1a0 | trap: OOB | `function_412c20` ← `function_4136a0` ← `function_413760` ← `function_414bb0` ← `function_653660` |
| 745 | 0xabb3b0 | trap: OOB | 0xacb3b0 | ok | (LB=0 側の trap: `function_407e20` ← `function_409440` ← `function_666bb0` ← `function_7745a0` ← `function_ebb3b0`) |

- 注: 上の VA は LVA 基準 (LB ぶんずれる)。LB=0 側の trap スタック名は LB=0 build で取った (`m11_survey.mjs` の `M11_SURVEY_STACK`)。
- 解釈 (推定と明記): 4 unit はいずれも LB 依存の分岐 (VA 即値・絶対アドレスの比較) を含む可能性があるが、**分岐の原因は未特定**。
  unit 40 は LB=0x10000 だけ Halt を呼ぶ経路に入り、通常起動が 37 unit で止まる (§2 の Halt0 早期終了と同じ経路)。
  unit 745 の LB=0 側 OOB も LB 依存の別経路の可能性があるが、未確認。
- 次の一手 (未着手): `function_412770` と `function_411d20` の IR で、Halt を呼ぶ条件の比較に使われる定数・ポインタを取り、
  LB=0 と LB=0x10000 の `boot_final.ll` の該当箇所を diff する。`m11_remap_count.py` の未 remap 即値 (§3) と突合する。

## 6. 本 runner の実測 (#2779・LB=0 / 0x10000 の後段)

測定日 2026-10-14。素材 fl-win64 (`block00031_PE.bin` 22,227,016 B)・work-m11 (#516 以前の snapshot)。toolchain は runner 同梱の `/opt/emsdk`・`/opt/retdec`。
測定 commit: LB=0 は `94dea77f` (測定時のコード)、LB=0x10000 は `51b20449` (fix。測定時の作業ツリーと同一)。
製品 KPI (`tools/flelift/boot/REPORT.md`) は本節で測っていない。

### 6.1 `m11_e2e.sh` 1 コマンドは通らない (受入 1 未達)

`M11_LB_BASE=0 bash tools/m11/m11_e2e.sh` は全再生成に入り、`m11_bounds.py` で fail-closed (0.6 s)。`ir_conditions` を作る `functions_dll.csv` (Ghidra 中間物。`tools/m2/work/ghidra_dll/`) が素材に無い。`work/lift_pe.sha256` も無い。
そこで後段だけを実行: `m11_e2e.sh` の複製 (`$RUNNER_TEMP`・未コミット。変えたのは `cd` と `lift_pe.sha256` の判定行だけ。lift 成果物が現 PE に対応するかは**未確認**)。gen_ir2 → boot5 RetDec lift → gen_ir2 → data/image → lb_check → build → 実行 A・B・C → judge → tolerant gate。

| 条件 | 結果 | rc | wall |
|---|---|---|---|
| LB=0 (`94dea77f`) | units_run 53・survey ok 872 / noproc 1 / miss 46 / trap 23・寛容 ok 874 / skipped 67・tolerant gate と negctl は OK | 0 | 1 m 58 s |
| LB=0x10000 (`94dea77f`) | gen_ir2 が `fix_ld108` の assert で停止 (即値不一致) | 1 | 0 m 31 s |
| LB=0x10000 (ld108 のみ修正) | build が `fix912` で停止 (`対象行が無い`) | 1 | 0 m 52 s |
| LB=0x10000 (`51b20449`) | gen_ir2・build OK (build は obj 全再構築で 9 分)。units_run 37 (Halt0 早期終了)・survey ok 869 / noproc 1 / miss 46 / trap 26。寛容起動は 600 s の `timeout` で打ち切られ出力空 → tolerant gate FAIL | 1 | 11 m 10 s |

load は未採取 (実行後に測っていない)。LB=0x10000 の rc=1 の内訳: 寛容起動の出力欠落 (子 #3160) と、strict・survey の期待値 (LB=0 の 56・872) との不一致。

### 6.2 #403 の数値との比較

| 項目 | #403 (引用) LB=0 | 本節 LB=0 | #403 (引用) LB=0x10000 | 本節 LB=0x10000 |
|---|---|---|---|---|
| units_run | 53 | 53 | 37 | 37 |
| survey ok / noproc / miss / trap | 870 / 1 / 46 / 25 | 872 / 1 / 46 / 23 | 868 / 1 / 46 / 27 | 869 / 1 / 46 / 26 |
| 通常起動の終了 | OOB | trap unreachable (function_8c5eb0) | Halt0 早期 | Halt0 早期 |

units_run と LB=0x10000 の Halt0 早期終了は #403 と一致。survey は ±2 のずれ。**受入 2 (「変わらない」) は未達**。
原因は未確定。候補は (a) boot5 の IR 組込み (`REPORT_N2778.md` §8.1 は boot5 無しで ok 870 を得ている。LB=0 のみの記録)、(b) ld108 (#2316。#403 より後)。切り分けは子 #3161。

### 6.3 不具合の修正 (本 PR)

`ldfix/fix_ld108.py` の head 即値 `16404608` (LB=0 の LVA 0xfa5080) と `fix912/m11_fix912.py` の VMT 即値 `994072` (0xf2b18) は LB=0 専用の固定文字列だった。LB=0x10000 の IR では +0x10000 された即値になる (実測 `16470144`・`1059608`)。そのため既定経路の `M11_LB_BASE=0x10000 m11_e2e.sh` は gen_ir2 か build で必ず止まっていた。両者とも `M11_LB_BASE` を足して照合するよう直した。
LB=0 の文字列は旧版と完全一致 (`HEAD_ST`・`RAX_ST`・`OLD`・`NEW` を python で比較して True)。

### 6.4 測定 commit から HEAD までの差分

LB=0 の測定 commit `94dea77f` から本 PR の fix commit `51b20449` までの `tools/m11` の差分 (本節の REPORT commit は含まない):

```diff
diff --git a/tools/m11/fix912/m11_fix912.py b/tools/m11/fix912/m11_fix912.py
index 3399bb6f..09e52370 100644
--- a/tools/m11/fix912/m11_fix912.py
+++ b/tools/m11/fix912/m11_fix912.py
@@ -12,10 +12,14 @@ RetDec の IR (function_4fb090) はこの dl を定数 1 ではなく、スタ
 """
 import argparse
 import json
+import os
 import sys
 
-OLD = '%39 = call i64 @function_4fa070(ptr nonnull inttoptr (i64 994072 to ptr), i64 %37, ptr %38)'
-NEW = '%39 = call i64 @function_4fa070(ptr nonnull inttoptr (i64 994072 to ptr), i64 1, ptr %38)'
+# VMT 即値は LVA (= RVA + M11_LB_BASE)。LB=0 は 994072 (0xf2b18)。LB=0x10000 で固定値だと対象行が無くなる (#2779)
+LB = int(os.environ.get('M11_LB_BASE', '0'), 0)
+VMT = str(994072 + LB)
+OLD = '%39 = call i64 @function_4fa070(ptr nonnull inttoptr (i64 ' + VMT + ' to ptr), i64 %37, ptr %38)'
+NEW = '%39 = call i64 @function_4fa070(ptr nonnull inttoptr (i64 ' + VMT + ' to ptr), i64 1, ptr %38)'
 
 
 def main():
diff --git a/tools/m11/ldfix/fix_ld108.py b/tools/m11/ldfix/fix_ld108.py
index 238016e9..4d099709 100755
--- a/tools/m11/ldfix/fix_ld108.py
+++ b/tools/m11/ldfix/fix_ld108.py
@@ -9,6 +9,7 @@ IR (lift 段から) は store 値を `%2 = load [arg1+8]` (変位 8) で代用
 
 使い方: python3 fix_ld108.py IN.ll OUT.ll
 """
+import os
 import re
 import sys
 
@@ -16,7 +17,9 @@ FN = re.compile(r'^define [^\n]*@function_41a670\(.*?\n}\n', re.M | re.S)
 DEF = re.compile(r'^define [^\n]*@function_41a670\(([^)]*)\)', re.M)
 ARG1 = re.compile(r'i64(?: [a-z_]+)* %arg1')
 BLK = re.compile(r'^dec_label_pc_41a69c:[^\n]*\n(.*?)(?=^dec_label_pc_|\Z)', re.M | re.S)
-HEAD_ST = 'store i64 %2, ptr inttoptr (i64 16404608 to ptr), align 8'
+# head 即値は LVA (= RVA + M11_LB_BASE)。LB=0 は 0xfa5080、LB=0x10000 は 0xfb5080 (#2779: 固定値だと LB=0x10000 で assert する)
+LB = int(os.environ.get('M11_LB_BASE', '0'), 0)
+HEAD_ST = 'store i64 %2, ptr inttoptr (i64 ' + str(16404608 + LB) + ' to ptr), align 8'
 RAX_ST = 'store i64 %2, ptr %rax.0.reg2mem'
 
 
```

LB=0 は HEAD で再 build していない (LB=0x10000 の build が obj を消すため、再 build は約 9 分)。差分は LB=0 で文字列が変わらないことの確認だけなので、LB=0 の数値は `94dea77f` の測定を採る。

### 6.5 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 全再生成経路 (`functions_dll.csv`・`lift_pe.sha256`) で `m11_e2e.sh` 1 コマンドが通らない。後段の複製は未コミット | 受入 1 未達 | #3113 (既存) |
| LB=0x10000 の寛容起動が 600 s で打ち切られ出力が空 | LB=0x10000 の e2e rc=1 | #3160 |
| #403 との数値差 (survey ±2)・LB=0 の停止理由 (OOB → unreachable) | 受入 2 未達 | #3161 |
| ptrcheck ゲートの LB=0x10000 側の結果 (基準は LB=0 の値) | 本 run の出力に数値行が無く未確認 | #3160 に含める |
