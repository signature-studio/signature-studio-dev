# #683: function_414ad0 の `[arg1]` deref 復元 — 4 unit (149/158/280/659) と #307 の 68 関数への波及

**判定: 受入条件 1 は未達** (4 unit はいずれも ok にならない)。受入条件 2 は部分 (68 関数で「最初の trap が 414ad0 の OOB」は消えるが、verdict は全件 mismatch のまま)。受入条件 3 (ok→非 ok の退行 0) は survey 942 unit と 68 関数では達成、closure 7421 関数では未達 (match→非 match 7 件、§5)。**Closes しない (Refs #683)**。
**既定は OFF** (`M11_OV_414AD0=0`)。既定 OFF では main と同じ LStrSetLength 版が build され、main の build の挙動は変わらない。
既知類型との関係 (`docs/DEFECTS.md`): **D4** (disp=0 の 1 段 deref 脱落) の再発。新規類型なし。
検証起点 = `8d883c3` (main)。実装 commit = `309fb3c` (`m11_ov.c` / `m11_build.sh`)、検証スクリプト・IR 版 = `0113c86`、本 REPORT の再測定 = `956d2ed` の後続 commit (本文の HEAD 欄を参照)。

## 1. 機械語と lift 後 IR の突合 (function_414ad0, VA 0x414ad0..0x414ba9)

- 機械語の `[rbx]` (rbx = 入口 rcx = `var s` のアドレス) の 1 段 deref は **4 箇所** (414af3 / 414b49 / 414b64 / 414b78)。
- 作業 IR (`work-m11` の `boot_final3.ll`) では `%arg1` を ptr とする load が **0 件**。`%arg1` を値のまま `icmp eq i64 %arg1, 0` / `add i64 %arg1, -N` に使い、`%arg2-4` を ptr として読む (414b6c の `load i32, ptr (%37-4)` がトラップ位置 0xbc575 = unit 149/158/280/659 の入口)。
- IR はさらに機械語と違う点がある: 414b49 の `call 0x414850` の引数が `[rbx]` の新しい値ではなく **スタック slot のアドレス**、414b01 の早期 return の戻り値が機械語の rax (= `[rbx]` の値) ではなく arg1。転記では機械語どおりに写した。

## 2. 転記 (C 版) と IR 版

- **C 版**: `tools/m11/m11_ov.c` の `function_414ad0`。gate は `-DM11_OV_414AD0` (既定 **0**)。
  - `M11_OV_414AD0=1`: UStrSetLength 版 (`#if` 側。機械語 414ad0..414ba9 の分岐を写した転記。deref 復元あり)。
  - `M11_OV_414AD0=0` (既定): LStrSetLength 版 (`#else` 側。main の #134 版と同じ本体)。
  - **注意**: 両版とも C で `function_414ad0` を定義するため、gate の切替は「C 転記 (UStr 版) ↔ main と同じ C 版 (LStr 版)」の切替であり、「転記あり ↔ IR 版」の切替ではない。IR 版 (`ir414_fix.py`) は liftdiff の A/B (§4・§5) でのみ使う。
  - `m11_build.sh` は `work/ov_414ad0.stamp` で `ov.o` だけ切り替える (`emcc -c` に `-DM11_OV_414AD0` を渡す。`ov.o` の内容が gate で変わることを確認済み)。
- **IR 版** (`trap_triage/ir414_fix.py`): C 版と同じ分岐・同じ deref 復元を LLVM IR で書いたもの。liftdiff は C 上書きを取り込まないため、68 関数の batch はこちらを使う。`--none` は無変更の複写 (A 側・ネガコン)。

## 3. m11 survey (942 unit): gate OFF (既定) / ON

`bash trap_triage/neg_683.sh` (ON/OFF を順に build + `survey_units.mjs` + `survey_diff.py`)。素材 `work-m11` は #516/#680 以前の生成物で `ir_conditions.json` が無く、そのままでは build が fail-closed で止まる。そこで `m11_gen_ir2.sh` で同じ `boot*.lift.ll` から IR を作り直した (ldfix=applied、20 s)。以下はその再生成 IR の実測。

- 実行: commit `956d2ed` の worktree (`/home/runner/work/ws-713`) で、`m11_gen_ir2.sh` による IR 再生成後に 3 回実行 (測定 1・2・3)。各回で ON build → survey → OFF build → survey の順。C 側・build スクリプトは `956d2ed` から変更していない (本 fix の commit は REPORT・スクリプトの文言と cp 修正のみ)。
- 所要 (実測、測定 3): 全体 72 s (ON build 18.4 s / survey 17.5 s (load 0.50) / OFF build 18.4 s / survey 17.0 s (load 0.72))。

| 構成 | ok | oob | halt0 | miss | noproc | trap | 計 |
|---|--:|--:|--:|--:|--:|--:|--:|
| OFF (既定, gate=0) n=3 | 828 | 11 | 55 | 47 | 1 | 66 | 942 |
| ON (gate=1) n=3 | 828 | 11 | 55 | 47 | 1 | 66 | 942 |

- **決定的**: 測定 1〜3 は全件一致 (min = max)。OFF と ON も一致 (差 0)。
- **遷移 (OFF → ON)**: 942 unit 全件で kind 不変 (ok→ok 828 / oob→oob 11 / halt0→halt0 55 / miss→miss 47 / noproc→noproc 1)。frames の深さの変化も 0。icall sites / targets の [ok, miss] 差も 0。
- **PR 旧記述 (ON で ok 818→827、ok +9、副作用 58-63・307/311/917・56) は再生成 IR の実測で再現しない**。58-63 / 307 / 311 / 917 は OFF の段階で既に ok、56 は OFF・ON とも oob。
- **対象 4 unit**: 149 は OFF = ON = oob (最上位 frame `653660 ← 6539e0 ← 664190`)。158/280/659 は OFF = ON = halt0 (`412770 ← 4128b0__lifted ← 4128b0`)。**4 unit とも ok にならない → 受入条件 1 は未達。**
- **旧 818/21 の出所**: REPORT.md §8.2 の (a)「スナップショット (旧生成物)」。(c)「再生成 IR」を採用基準とする (REPORT.md §8.2 (e))。本 REPORT は (c) を基準とする。

ネガコン: 上記 gate OFF/ON の切替で結果は変わらない。したがって本 gate は survey 上では効果を持たない (C 版 UStr 版と LStr 版が survey で同一の結果)。

## 4. liftdiff: #307 の 68 関数への波及 (A/B、同一ハーネス)

- **定義** (`tests/oob_414ad0.py` と同じ): batch の関数のうち「最初の `wasm_trap` case の wasm_detail が `memory access out of bounds @ ld_wasm.wasm.function_414ad0` で始まる」関数。基準 jsonl `tools/liftdiff/work/m11/batch_closure.jsonl` (7421 行) で **68**。
- **A** = IR 無変更の複写 (`m11_414base`)、**B** = `ir414_fix.py` で修復した IR (`m11_414fix`)。68 関数を `--set file:` で指定、`--shards 4 --state auto`。
- **実行手順**: `liftdiff68_683.sh` を end-to-end で実行 (rc=0、41 s、`956d2ed` + 本 commit の cp 修正)。途中で `cp` の同一ファイル問題 (修正済み) と numpy 不足 (`liftdiff.py` の依存) に当たったため、venv に numpy / capstone / pefile を入れて実行。

| 指標 (68 関数) | A (IR 無変更) | B (414ad0 修復) |
|---|--:|--:|
| 最初の wasm_trap が 414ad0 の OOB | **67** | **0** |
| verdict = match | 0 | 0 |
| verdict = mismatch | 68 | 68 |

- 遷移 (cmp68_683.py): oob414→other・verdict mismatch→mismatch が 67、other→other・verdict mismatch→mismatch が 1。**match → 非 match の退行は 0** (A で match は 0 件のため自明)。
- B (68 関数) の最初の trap の内訳 (`/tmp/ld68.log` の関数別表の集計、計 68): `4133f0` の OOB 13 件 (経路 `4133f0 < 414c70`)、`412e40` の OOB 9 件 (経路 `412e40 < 652750`)、`4128b0__lifted` の unreachable 3 件、その他の OOB 2 件 (`8e6e30`・`__asm_rep_movsq_memcpy` 各 1)、trap なし 41 件。
- **414ad0 の修復で消えた OOB は、別の関数の OOB (`412e40` 経由、`4133f0 < 414c70` 等) に置き換わった**。その原因 (deref 脱落の有無) は未確認。68 関数はいずれも verdict が mismatch のまま。
- **A (今回 67) と既存 closure jsonl の 68 の差**: 1 関数 (最初の trap の関数が変わる)。shard・実行順 (memory 状態の持ち越し) による差と推定 (**未確認**)。このため A/B の比較は同一ハーネス内に限って読む。

## 5. closure 全体 (7421 関数) の A/B (14 shard、同一ハーネス)

A = IR 無変更 (`m11_414base`、`batch_414base_closure.jsonl`)、B = 修復 IR (`m11_414fix`、`batch_414fix_closure.jsonl`)。両方 `--set closure --shards 14 --state auto`。所要 A 779 s / B 796 s (B は A と非並行、A は m11 survey と並行していた時間を含む)。突合 = `cmp68_683.py` (全 VA)。

| 指標 (7421 関数) | A (IR 無変更) | B (414ad0 修復) |
|---|--:|--:|
| 最初の wasm_trap が 414ad0 の OOB | 63 | **0** |
| verdict = match | 3125 | 3127 (+2) |
| verdict = mismatch | 2135 | 2133 |
| verdict = unexec | 2161 | 2161 |

- 遷移 (A → B): match→match 3118 / **match→mismatch 7** / mismatch→match 9 / mismatch→mismatch 2063 / unexec→unexec 2161 / OOB414→other 63。
- **match → 非 match の 7 件**: 0x5af280 (ret_only)、0x50d920 (ret_only)、0x44b090 (callee_divergence、heap 書込み差)、0x79d920 (spill_slot_deref + callee_divergence)、0x663d80 (memory_semantics)、0x699ca0 (simd_helper + wasm_trap)、0x4447d0 (wasm_trap)。いずれも 414ad0 を直接呼ぶ関数ではない。heap 配置の変化など間接経路と推定 (**未確認**)。
- **受入条件 3 (退行 0) は closure 全体では未達** (7 件)。68 関数の subset では 0。
- 注意: 既存の `batch_closure.jsonl` (別の実行時) を基準にすると match→非 match が 106 件と出る。同一 harness の A (上表) では 7 件。差 99 件は harness 状態 (§4 と同根と推定) であり、退行の数え方は同一 harness の A を基準にする。
- **本 REPORT の再測定の範囲外**: §5 の closure は本 run で再実行していない (14 shard で約 13 分超のため、本 run の上限に収まらない)。§5 は `683-m11-414ad0-restore` 時点 (`0113c86`) の測定値。

## 5.1 kind 以外の差分 unit

survey 942 unit の kind は ON/OFF で全件一致 (§3)。`survey_diff.py` の「kind 以外も含めた差分」も 0 件。

## 6. 再現手順 (1 コマンド)

```sh
# m11 survey (ON/OFF。work-m11 展開済み、IR は m11_gen_ir2.sh で再生成、emsdk は m11_build.sh が source)
bash tools/m11/trap_triage/neg_683.sh
# liftdiff 68 関数 A/B (work-m11 + work-liftdiff 展開済み、PY は capstone + pefile + numpy 入り python)
FL_WIN64_DIR=... PY=... bash tools/m11/trap_triage/liftdiff68_683.sh
```
ネガコン: `liftdiff68_683.sh` の A (`--none`、IR 無変更)。survey の 0/1 比較は gate の両版比較であり、IR 版の無変更比較ではない (§2)。

## 7. 検証範囲 / 範囲外

- 範囲内: m11 survey 942 unit (ON/OFF 各 2 回)、liftdiff 68 関数 (A/B 各 1 回、end-to-end 実行)。
- 範囲外: closure 7421 関数の再測定 (§5 は旧測定値)、`m11_e2e.sh` 全体 (stage4 / bit-exact) への影響 (未実施)、C 版と IR 版の相互検算 (未実施)、副作用の原因 (旧 PR 記述の再現が無いため対象外)。
- 既存 REPORT の数値 (`818 / 21` 等) は旧生成物 (a) の値で、本 gate の有無とは無関係。他 REPORT の書換えは行わない。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 149 の最上位 frame (`653660 ← 6539e0 ← 664190`) の原因 | 4 対象 unit のうち 149 が oob のまま | #307 の次候補 (起票は PM) |
| 158/280/659 の halt0 (`412770 ← 4128b0__lifted`) の原因 | 4 unit が ok にならない | #683 の継続 (本 PR は Refs) |
| liftdiff 68 の次の trap (`412e40` 経由の OOB 等) | 68 関数が verdict match に届かない | #307 |
| closure の match→非 match 7 件 (0x5af280 / 0x50d920 / 0x44b090 / 0x79d920 / 0x663d80 / 0x699ca0 / 0x4447d0) の原因 | 受入条件 3 (退行 0) が closure 全体で未達 | #307 |
| liftdiff batch の再現性 (A 67 と closure 68 の差) | A/B の読み方 | #307 (harness 件) |
| C 版 (m11_ov.c) と IR 版 (ir414_fix.py) の相互検算 | 転記の正しさ (独立検算) | PM 判断 (検収 subagent) |
| gate ON が survey で効果を持たない理由 (C 版の 2 版が同じ結果) | 本 gate の存在意義 | PM 判断 |
| `work-m11` が #516/#680 以前の生成物で `ir_conditions.json` 無し (そのままでは build 不可) | 素材の更新 | PM 判断 (素材の再生成) |
