# M11 LB_BASE=0x10000 の残差調査 (#403, 部分達成)

親: #222 (PR #303)。素材: fl-win64 (`block00031_PE.bin` 22,227,016 B)。work-m11・toolchain-emsdk・toolchain-retdec は本 PR の作業 runner に無い (§2・§4 参照)。
e2e の測定は HEAD `64d09590` で実施。c8b9ad75 との差は `audit_va.py` のみで e2e 結果に影響しない (§1 の audit 実測は c8b9ad75 で実施)。
実行は各 1 回ずつ直列 (ただし同一条件の再実行 2 回で結果が一致したものを記す)。
既知類型との関係: 該当なし (LB 依存差は未切り分けで、`docs/DEFECTS.md` の D1a〜D18 への帰属は未確認。近縁は D11 = PE VA リテラルの切り捨て)。

## 1. audit_va.py の IAT 判定 (受入 1: 原因特定 — 完了)

- 原因: IAT スロット 738/738 の値は **hint/name テーブルの RVA** (ILT と同値、例 `0x15721a4` = `PathUnExpandEnvStringsW`)。
  `[ImageBase, ImageBase+SizeOfImage)` の範囲に入るため VA と誤判定していた。
- 修正前: `iat_slots_holding_image_VA = 738` → exit 1。
- 修正後 (`tools/hostbridge/lowbase/audit_va.py`): hint/name RVA を別集計 (`iat_slots_holding_hint_name_rva = 738`) し、
  `iat_slots_holding_image_VA = 0` → exit 0。DIR64 の判定 (`dir64_targets_outside_image = 0`) は変更していない。
- 既存 REPORT (`REPORT_APPENDIX.md` の IAT 節) の結論「PE 標準の bound 前 IAT の誤検知」と一致。

## 2. LB=0 と LB=0x10000 の `m11_e2e.sh` 比較 (受入 2: 未達)

| 項目 | LB=0 (2 回) | LB=0x10000 (2 回) |
|---|---|---|
| e2e 所要 (再生成なし・build 増分) | 2m10s (初回) | 1m21s (初回) |
| units_run (通常起動) | 53 | 37 |
| 通常起動の終了 | OOB (`memory access out of bounds`) | Halt0 早期終了 (`halt0_early=true`) |
| survey ok / noproc / miss / trap | 870 / 1 / 46 / 25 | 868 / 1 / 46 / 27 |
| trap 内 oom | 1 | 1 |
| wasm_bytes | 6,042,784 | 6,043,167 |

**REPORT_APPENDIX の「stage / survey 集計は一致 (ok 812 / trap 83)」は本 HEAD (`64d09590`) では再現しない。**
LB=0 でも ok 870 / trap 25 で、旧記録 (812 / 83) と別の値になっている。旧記録の HEAD と現 HEAD の差は未切り分け。

### unit 別の結果差 (survey, LB=0 vs LB=0x10000)

全 942 unit のうち結果が食い違うのは 4 件。REPORT の「差 0」は成り立たない。

| unit (VA: LB=0 / LB=0x10000) | LB=0 | LB=0x10000 | 観測 |
|---|---|---|---|
| 40 (`0x105bd0` / `0x115bd0`) | ok | trap (Halt0 → longjmp) | `m11_throw_dllmain_done` 経由。unit 内の Halt 呼出し |
| 153 (`0x265b90` / `0x275b90`) | ok | trap (OOB) | |
| 158 (`0x26d1a0` / `0x27d1a0`) | ok | trap (OOB) | GetMem 139 → 2 |
| 745 (`0xabb3b0` / `0xacb3b0`) | trap (OOB, GetMem 34) | ok (GetMem 36) | REPORT の「SelectObject 3 回追加」は本実行の出力で確認できず |

- unit 873: 両 LB とも ok・VA 要求 0・GetMem 1 で、REPORT の「LB=0 は 1914MB 要求で OOM」は再現しなかった。
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
- 指紋の不一致 (未切り分け): 旧記録 (main 版 §3) は LB=0 `9a9e223e…`・LB=0x10000 `451ecd03…`。本 PR の記録は LB=0 `3a9ceb17…`・LB=0x10000 `5dfb1473…`。
  本 PR は IR 生成・build の経路 (`m11_gen_ir2.sh`・`m11_build.sh`・`m11_lift.sh`) を変更しておらず、本 runner では IR を再生成していない。
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

- 上の値は §2 の表と同じ測定 (同一記録)。二重の独立検証ではない。
- 本 PR の変更 (`m11_remap_count*`・REPORT) は e2e の経路に入らないため、この値は本 PR の変更では変わらない見込みだが、再測定はしていない。
- 再測定の手順: `M11_LB_BASE=0 bash tools/m11/m11_e2e.sh` / `M11_LB_BASE=0x10000 bash tools/m11/m11_e2e.sh` (work-m11 と fl-win64 が必要)。

## 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 40 / 153 / 158 / 745 の LB 依存差の原因 (特に unit 40 の Halt 経路と通常起動の Halt0 早期終了) | LB=0x10000 の通常起動が 37 unit で止まる。受入 2 未達 | 本 issue (#403) で継続 |
| REPORT_APPENDIX の旧 HEAD 集計 (812/83) と現 HEAD (870/25) の差 | 既存の数値の根拠が現 HEAD で再現しない | PM が起票 (#222 系) |
| 実行後の guest ポインタ assert (未実装) | 受入 3 の後半 | 子 issue #1004 (M11-N57) |
| 未 remap の image VA 即値 4,368 件 (件数の解消先) | 受入 3 の件数は計測済み。解消を担当する issue は未特定 (#417 は halt0 21 unit の別件、#1004 は実行後 assert で範囲外) | PM 起票を要求 (担当 issue 未確定) |
| IR 指紋の不一致 (旧 `9a9e223e…`/`451ecd03…` と本記録 `3a9ceb17…`/`5dfb1473…`) | どの IR で測定したかが未確定 | PM 確認 (work-m11 の `ir_conditions.json` で照合) |

## 5. unit 別の LB 依存差の実測 (2026-10-13 run・受入 2 の切り分け・原因は未特定)

- 素材: fl-win64 → `$HOME/analysis/win64`、work-m11 / work-liftdiff → `tools/m11/work/`、toolchain-emsdk / retdec → `/opt/`。
  work-m11 は #728 以前のスナップショットで `work/lift_pe.sha256` が無く、`m11_e2e.sh` が全再生成に入って Ghidra の `functions_dll.csv` を要求して止まる。
  そのため `work/lift_pe.sha256` に現 PE の sha256 (`b2c64da4…`) を手で書き、lift 成果物を再利用した (全再生成はしていない)。
- e2e 実測 (同一 worktree・同一 work/・各条件 2 回以上):
  - `M11_LB_BASE=0`: units_run 53 / survey ok 870 / trap 25 / miss 46 / ir_sha256 `1fc847d4…`
  - `M11_LB_BASE=0x10000`: units_run 37 / survey ok 868 / trap 27 / miss 46 / halt0_early=true / ir_sha256 `b529a344…`
  - LB=0 の 2 回目 (`e2e_lb0c`) も 870/25 で一致。前回 PR #1006 の記録とも一致。
- unit 別の食い違い (`M11_SURVEY_UNITS` で取った 942 件ラベル。index 比較):
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
