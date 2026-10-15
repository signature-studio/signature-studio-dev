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

## 6. #3160 の再測定: LB=0x10000 の寛容起動は 600 s で打ち切られず、LB 依存の unit 差は 8 件

既知類型との関係: 該当なし (新しい候補: LB 直書きの定数を持つ IR 修復 pass が LB≠0 で不適用になる。類型 ID は未付与)。
測定主体: 本 PR の作業 runner (2026-10-14)。素材は work-m11 (#516 以前の snapshot)・fl-win64・toolchain-emsdk (`[EMSDK]`)。
`m11_e2e.sh` の全再生成は使わず、lift 成果物 (boot0〜4.lift.ll) から後段 (gen_ir2 → 画像 → lb_check → build → 寛容起動) を実行する (`tools/m11/m11_lb_tolerant_repro.sh`)。
測定 commit: `17b078a1` (コードを変えた最後の commit。直前の `9a00a57c` で測った値も同じ)。`git diff 17b078a1 HEAD -- tools/m11 ':(exclude)tools/m11/REPORT*'` の出力は空 (差分 0)。

### 6-1 LB 別の結果 (`bash tools/m11/m11_lb_tolerant_repro.sh 0 work/repro_lb0` / `... 0x10000 work/repro_lb10000`)

| 項目 | LB=0 | LB=0x10000 |
|---|---|---|
| 寛容起動 wall (timeout 600) | 16.8–17.0 s (n=3) | 20.2–20.5 s (n=4) |
| attempted / ok / noproc / miss / skipped | 942 / 867 / 1 / 47 / 74 | 942 / 867 / 1 / 47 / 74 |
| skipped の内訳 | oob 19・halt0 7・unreachable 1 | oob 16・halt0 8・abort 2・unreachable 1 |
| hook_ran (InitUnits 本体の呼出し) | true (1 回) | true (1 回) |
| lb_check (静的検査) | PASS | PASS |

LB=0: `17b078a1` の repro (17.0 s)・`9a00a57c` の repro (16.9 s)・`var_C` (16.8 s)。LB=0x10000: `17b078a1` の repro (20.25 s)・`9a00a57c` の repro (20.2 s)・`var_A` (20.5 s)・`fixed` (20.5 s)。
再実行は unit 別の記録 (942 件) が一致した (`m11_lb_unit_diff.py` の差 0)。

### 6-2 LB=0 と LB=0x10000 の unit 結果差 (`python3 tools/m11/m11_lb_unit_diff.py tools/m11/work/repro_lb0/tolerant_units.json tools/m11/work/repro_lb10000/tolerant_units.json`・kind 差 8)

| index | VA (LB=0 側) | LB=0 | LB=0x10000 | §2 の表 (引用) |
|---|---|---|---|---|
| 40 | 0x105bd0 | ok | halt0 | 一致 |
| 153 | 0x265b90 | ok | oob | 一致 |
| 158 | 0x26d1a0 | ok | oob | 一致 |
| 745 | 0xabb3b0 | oob | ok | 一致 |
| 291 | 0x432660 | oob | ok | §2 に無し (新規) |
| 296 | 0x446130 | oob | ok | §2 に無し (新規) |
| 304 | 0x483140 | oob | abort | §2 に無し (新規) |
| 555 | 0x7f2500 | oob | abort | §2 に無し (新規) |

- §2 の 4 件は再現した。§5 の「食い違いは 4 件のみ」は引用元の記録での値で、本測定では 8 件。
- 陽性対照 (差が出ること) は LB=0 と LB=0x10000 の比較 (差 8)。陰性対照 (同一 LB の再実行) は差 0。

### 6-3 候補の切り分け (寛容起動の打ち切り)

- ハング・無限ループ: 再現せず。942 試行が全て 20 s 以内に完了 (`attempted` = `units_total` = 942)。
- InitUnits の再入: 再現せず。`hook_ran` は 1 回。`attempted` は 942 で、二重起動の痕跡なし。Halt0 (dllmain 経由) は 8 件を skip として処理。
- 未 remap の image VA 即値 (§3): 件数は LB 間で同じ (`m11_remap_count.py`: LB=0 IR も LB=0x10000 IR も `unremapped` 4,364)。件数の差は 6-2 の原因ではない。
- 元の報告 (`M11_LB_BASE=0x10000` で 600 s 打ち切り) は、この snapshot とこの commit では再現しなかった。元の打ち切りの原因は未特定。

### 6-4 e2e 経路を止めていた LB 直書き (本 PR で修正)

- `ldfix/fix_ld108.py` (#2402): 照合文字列が LB=0 の LVA `0xFA5080` (16404608) を直書きしていた。LB=0x10000 の IR では head が 16470144 に remap されており、修正前は `m11_gen_ir2.sh` が `store 行が想定と違う` の assert で止まった (gen_ir2 rc=1 を実測)。
- `fix912/m11_fix912.py` (#912): VMT 定数 `994072` (0xF2D18) も同じ。LB=0x10000 の IR では `1059608`。修正前は `m11_build.sh` が `[fix912] FAIL: 対象行が無い (before=0 after=0)` で止まった (実測)。
- 修正: どちらも `M11_LB_BASE` を加算して照合する。LB=0 の照合文字列は旧値と一致 (`HEAD_ST`・`OLD`・`NEW` を LB=0 で確認)。
- ld108 を外した版 (`M11_FIX_LD108=0 M11_ALLOW_LD108_DISABLED=1`) の寛容起動も、unit 結果は fixed 版と差 0。この unit 集合では ld108 の適用は結果を変えない。

### 6-5 未確認・限界

- lift 成果物 (boot0〜4.lift.ll) が fl-win64 の PE から作られたことは未確認。work-m11 に `work/lift_pe.sha256` が無く、§5 のような手書きの指紋は使っていない。
- LB=0 の寛容起動は ok 867 / skipped 74 で、`m11_tolerant_gate.py` の pin (ok 874 / skipped 67) と一致しない。snapshot の IR と pin の基準 (`--full` 再生成) が違うと推定 (未確認)。
- `m11_e2e.sh` の全経路 (`M11_LB_BASE=0x10000 bash m11_e2e.sh`) は未実行 (全再生成に入るため)。
- 寛容起動の `ptrcheck` はゲート未設定 (`M11_PTRCHECK_MAX_NEW` 無し)。`image_va_words_new` は LB=0x10000 で 71987、LB=0 で 72042。
- 再現手順: `bash tools/m11/m11_lb_tolerant_repro.sh <LB> <出力>` (要 `FL_WIN64_DIR`・work-m11)。ネガティブ対照の具体例: 修正前の commit `e9881327` で LB=0x10000 の gen_ir2 は止まる (6-4)。

### 6-6 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| LB=0 と LB=0x10000 の unit 結果差 8 件 (特に unit 40 の Halt0・unit 745 の oob) の原因 | LB 依存の寛容起動の結果が変わる。silent 誤りの可能性 | 子 issue (本 PR の Closes #3160 の後に起票) |
| 元の 600 s 打ち切りの原因 (本 snapshot では再現せず) | 報告の根拠が再現しない | 本 issue の §6-3 に記録。再現には lift_pe.sha256 付きの完全な成果物が要る |
| LB=0 寛容起動の pin (874/67) と snapshot の値 (867/74) の差 | gate 数値の基準が snapshot と不一致 | PM 確認 (`--full` 再生成での再測定が要る) |

## 7. #3296: function_412770 の rep movsq 源 `ptr null` の修正 (受入 1 達成・受入 2 未達)

測定主体: 本 PR の作業 runner (2026-10-15)。素材: fl-win64 (`block00031_PE.bin`)・work-m11 (`tools/m11/work`)・emsdk (`/opt/emsdk`)。
測定 commit: `3b6651de` (コードを変えた最後の commit)。`git diff 3b6651de HEAD -- tools/m11 ':(exclude)tools/m11/REPORT*'` の出力は空 (差分 0)。

### 7-1 機械語と lift IR

- 機械語 (VA 0x412790〜0x41279b): `mov rsi,[rax]` (rax = arg1) → `mov rdi,rax; mov ecx,0x25; rep movsq` (37 qword)。源は `[arg1+0]` の**値** (1 段 deref)。
- lift 段 (`tools/m11/work/boot0.lift.ll`) から既に `call @__asm_rep_movsq_memcpy(ptr %4, ptr null, i64 37)`。`ptr null` の源は boot_final.ll でも lift でもこの 1 箇所だけ。
- 修正: `tools/m11/ldfix/fix_src412770.py` (gen_ir2 で ldfix の後に適用。対象行が 1 件でない・二重適用・第 1 仮引数が `ptr %arg1` でない場合は assert で停止)。`load i64 [arg1+0]` → `inttoptr` → 源に置換。

### 7-2 LB 別の再現 (`bash tools/m11/m11_lb_tolerant_repro.sh <LB> <出力>`)

| 条件 | wall | ok / miss / oob / halt0 / abort / noproc |
|---|---|---|
| LB=0 修正前 (`repro_lb0`) | 16.7 s | 868 / 47 / 19 / 7 / 0 / 1 |
| LB=0 修正後 (`fix_lb0`) | 16.6 s | 868 / 47 / 19 / 7 / 0 / 1 |
| LB=0x10000 修正前 (`repro_lb10000`) | 20.1 s | 868 / 47 / 16 / 8 / 2 / 1 |
| LB=0x10000 修正後 (`fix_lb10000`) | 19.7 s | 868 / 47 / 16 / 8 / 2 / 1 |

- `m11_lb_unit_diff.py` の kind 差は、修正前 (`repro_lb0` vs `repro_lb10000`) も修正後 (`fix_lb0` vs `fix_lb10000`) も **8 件** (unit 40・153・158・291・296・304・555・745。§6-2 と同じ)。
- 修正前後の unit 結果差は **0** (`fix_lb0` vs `repro_lb0`、`fix_lb10000` vs `repro_lb10000`)。修正は unit 結果を 1 件も変えなかった。
- 解釈 (推定・未確認): 源が `[arg1+0]` の値で、その値が 0 なら修正後も address 0 を読むので LB 依存は残る。寛容起動の harness で arg1 先の値が 0 である可能性が高い。機械語どおりの読みは正しいが、LB 依存の直接原因ではない。
- 受入 1 (機械語どおりの load に戻す lift 修正) は達成。受入 2 (kind 差 0) は未達。

### 7-3 新類型の行案 (`docs/DEFECTS.md` 用・ID 未付与・PM が登録)

`NULL 源の rep movsq`: lift 段が機械語 `mov rsi,[rax]` (1 段 deref の load) を脱落させ、rep movsq の源を `ptr null` にする。NULL 源は wasm の address 0 を読むため、address 0 の中身 (LB=0 は PE ヘッダ・LB=0x10000 は 0 埋め) で結果が LB 依存になる。検出: boot_final.ll に `__asm_rep_movsq_memcpy(ptr ..., ptr null, ...)` (本件 1 件)。修正: `ldfix/fix_src412770.py` (本件のみ・一般化は未実施)。

### 7-4 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| LB 依存 unit 差 8 件 (40・153・158・291・296・304・555・745) の原因。修正後も不変。arg1 先の値・unit 40 の Halt 経路・unit 153/158 の OOB の発生箇所は未特定 | 寛容起動の LB 別の結果が違う (silent 誤り)。受入 2 未達 | 子 issue [M11-N181] |
| issue 本文の `tools/m11/m11_lb_ir_fn_diff.py` は repo に存在しない | 関数単位の IR diff (`function_412770`) の再現コマンドが使えない | 本 PR では未対応。issue 本文の修正は PM |
