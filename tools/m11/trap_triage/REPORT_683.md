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

- 実行: HEAD `50fed21d` の worktree で、`m11_gen_ir2.sh` による IR 再生成 (20.7 s、`ldfix=applied`、`ir_sha256` 7497b4d8…) の後に `neg_683.sh` を 3 回実行 (測定 1・2・3)。各回で ON build → survey → OFF build → survey の順。`50fed21d` と `44bf3e9` の差分は本 REPORT のみ (コード・スクリプト同一)。C 側 (`m11_ov.c`) と build スクリプトは `956d2ed` から変更していない。
- 所要 (実測、`neg_683.sh` の各段階。load は各段階終了時の 1 分値): 測定 1 = 全体 76.8 s (ON build 24.5 s / survey 17.2 s (load 1.03) / OFF build 18.4 s / survey 16.5 s (load 1.02))、測定 2 = ON build 18.6 s / survey 16.9 s (load 1.08) / OFF build 18.6 s / survey 16.8 s (load 1.11)、測定 3 = ON build 18.4 s / survey 17.2 s (load 1.06) / OFF build 18.6 s / survey 17.2 s (load 1.03)。

| 構成 | ok | oob | halt0 | miss | noproc | trap | 計 |
|---|--:|--:|--:|--:|--:|--:|--:|
| OFF (既定, gate=0) n=3 | 828 | 11 | 55 | 47 | 1 | 66 | 942 |
| ON (gate=1) n=3 | 828 | 11 | 55 | 47 | 1 | 66 | 942 |

- **決定的**: 測定 1〜3 は全件一致 (min = max = n=3)。OFF と ON も一致 (差 0)。
- **`survey_diff.py` の全出力** (`bash trap_triage/neg_683.sh` の出力そのもの。測定 1〜3 とも 1 行ずつ完全に同一。`off` / `on` の 2 行は同スクリプト末尾の unit 149/158/280/659 表示):

```
A: {'halt0': 55, 'miss': 47, 'noproc': 1, 'ok': 828, 'oob': 11}  trap=66
B: {'halt0': 55, 'miss': 47, 'noproc': 1, 'ok': 828, 'oob': 11}  trap=66
遷移 (A -> B):
  halt0   -> halt0   55
  miss    -> miss    47
  noproc  -> noproc  1
  ok      -> ok      828
  oob     -> oob     11
ok 退行 unit: 0 []
kind 以外も含めた差分 unit (frames は深さのみ比較): 0 []
icall sites の総数 [ok, miss] 差 (A -> B): 0 件 
icall targets の総数 [ok, miss] 差 (A -> B): 0 件 
off  units 149/158/280/659: [(149, 'oob'), (158, 'halt0'), (280, 'halt0'), (659, 'halt0')]
on   units 149/158/280/659: [(149, 'oob'), (158, 'halt0'), (280, 'halt0'), (659, 'halt0')]
```

  kind 以外の差分は 3 回とも 0 件。ok 退行 0。
- **遷移 (OFF → ON)**: 942 unit 全件で kind 不変 (ok→ok 828 / oob→oob 11 / halt0→halt0 55 / miss→miss 47 / noproc→noproc 1)。frames の深さの変化も 0。icall sites / targets の [ok, miss] 差も 0。
- **PR 旧記述 (ON で ok 818→827、ok +9、副作用 58-63・307/311/917・56) は再生成 IR の実測で再現しない**。58-63 / 307 / 311 / 917 は OFF の段階で既に ok、56 は OFF・ON とも oob。
- **対象 4 unit**: 149 は OFF = ON = oob (最上位 frame `653660 ← 6539e0 ← 664190`)。前版の「ON で最上位が `414c70` に変わる」は、再生成 IR の (c) 測定 (ON/OFF とも) では再現しなかった。`414c70` は stack の最上位に現れない。158/280/659 は OFF = ON = halt0 (`412770 ← 4128b0__lifted ← 4128b0`)。**4 unit とも ok にならない → 受入条件 1 は未達。**
- **旧 818/21 の出所**: REPORT.md §8.2 の (a)「スナップショット (旧生成物)」。(c)「再生成 IR」を採用基準とする (REPORT.md §8.2 (e))。本 REPORT は (c) を基準とする。

ネガコン: 上記 gate OFF/ON の切替で結果は変わらない。したがって本 gate は survey 上では効果を持たない (C 版 UStr 版と LStr 版が survey で同一の結果)。

## 4. liftdiff: #307 の 68 関数への波及 (A/B、同一ハーネス)

- **定義** (`tests/oob_414ad0.py` と同じ): batch の関数のうち「最初の `wasm_trap` case の wasm_detail が `memory access out of bounds @ ld_wasm.wasm.function_414ad0` で始まる」関数。基準 jsonl `tools/liftdiff/work/m11/batch_closure.jsonl` (7421 行) で **68**。
- **A** = IR 無変更の複写 (`m11_414base`)、**B** = `ir414_fix.py` で修復した IR (`m11_414fix`)。68 関数を `--set file:` で指定、`--shards 4 --state auto`。
- **実行手順**: `liftdiff68_683.sh` を end-to-end で実行 (HEAD `44bf3e9`、`FL_WIN64_DIR` = fl-win64 展開先、`PY` = python3 + capstone/pefile/numpy)。3 回実行し、いずれも rc=0 (実測 40.4 s / 39.6 s / 3 回目は run 1・2 とも同一の要約行)。
- 測定 1〜3 の要約 (`cmp68_683.py` 出力): A の oob414 = **59**、B の oob414 = **0**、verdict は A・B とも mismatch 68 / match 0。3 回とも同一。

| 指標 (68 関数、n=3 で同一) | A (IR 無変更) | B (414ad0 修復) |
|---|--:|--:|
| 最初の wasm_trap が 414ad0 の OOB | **59** | **0** |
| verdict = match | 0 | 0 |
| verdict = mismatch | 68 | 68 |

- 遷移 (cmp68_683.py): oob414→other・verdict mismatch→mismatch が **59**、other→other・verdict mismatch→mismatch が **9**。**match → 非 match の退行は 0** (A で match は 0 件のため自明)。
- B (68 関数) の最初の wasm_trap の内訳 (batch jsonl からの集計): trap なし 38、`4133f0` 18、`412e40` 6、`4128b0__lifted` 2、`__asm_rep_movsq_memcpy` 1、`4144a0` 1、`8e6e30` 1、その他の形式 1 (`dfunction_0` の表示で wasm_detail が JSON 断片)。A の内訳は `414ad0` 59・`408040` 7・`4133f0` 1・trap なし 1。
- **414ad0 の修復で消えた OOB は、別の関数の OOB (`4133f0 < 414c70`、`412e40 < 652750` 等) に置き換わった**。その原因 (deref 脱落の有無) は未確認。68 関数はいずれも verdict が mismatch のまま。
- **旧記述の 67 は誤り**: 旧 REPORT の A = 67 は再現しない (3 回とも 59)。`956d2ed` 時点の値が別の実行状態だった可能性は未確認。このため、A/B の比較は同一ハーネス・同一実行内に限って読む。

## 5. closure 全体 (7421 関数) の A/B (14 shard、同一ハーネス) — **旧測定 (`0113c86`)、本 REPORT の再測定の対象外**

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

survey 942 unit の kind は ON/OFF で全件一致 (§3)。`survey_diff.py` の「kind 以外も含めた差分」も 0 件 (HEAD `50fed21d`、測定 1〜3 とも `kind 以外も含めた差分 unit (frames は深さのみ比較): 0 []`。全出力は §3)。`956d2ed` の確認で出ていた unit 235・888 の差分は、今回の測定では再現しない。その原因は未確認 (`956d2ed` 時点の IR 生成条件を本 run では再現していない)。

## 6. 再現手順 (1 コマンド)

```sh
# m11 survey (ON/OFF。work-m11 展開済み、IR は m11_gen_ir2.sh で再生成、emsdk は m11_build.sh が source)
bash tools/m11/trap_triage/neg_683.sh
# liftdiff 68 関数 A/B (work-m11 + work-liftdiff 展開済み、PY は capstone + pefile + numpy 入り python)
FL_WIN64_DIR=... PY=... bash tools/m11/trap_triage/liftdiff68_683.sh
```
ネガコン: `liftdiff68_683.sh` の A (`--none`、IR 無変更)。survey の 0/1 比較は gate の両版比較であり、IR 版の無変更比較ではない (§2)。

## 7. 検証範囲 / 範囲外

- 範囲内: m11 survey 942 unit (ON/OFF 各 n=3、HEAD `50fed21d`)、liftdiff 68 関数 (A/B 各 n=3、end-to-end 実行、HEAD `44bf3e9`。コードは `50fed21d` と同一で、以後の REPORT のみの commit では再実行していない)。
- **n の限界**: 上記は n=3 で全件一致 (min = max)。ただし同一素材・同一マシン上の反復であり、別マシン・別負荷での再現は未確認。
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
