# #683: function_414ad0 の `[arg1]` deref 復元 — 4 unit (149/158/280/659) と #307 の 68 関数への波及

**判定: 受入条件 1 は未達** (4 unit はいずれも ok にならない)。受入条件 2 は部分 (68 関数で「最初の trap が 414ad0 の OOB」は消えるが、verdict は全件 mismatch のまま)。受入条件 3 (ok→非 ok の退行 0) は達成。**Closes しない (Refs #683)**。
既知類型との関係 (`docs/DEFECTS.md`): **D4** (disp=0 の 1 段 deref 脱落) の再発。新規類型なし。
検証起点 = `8d883c3` (main)。実装 commit = `309fb3c` (`m11_ov.c` / `m11_build.sh`)。本 REPORT・スクリプト・IR 版は後続 commit。

## 1. 機械語と lift 後 IR の突合 (function_414ad0, VA 0x414ad0..0x414ba9)

- 機械語の `[rbx]` (rbx = 入口 rcx = `var s` のアドレス) の 1 段 deref は **4 箇所** (414af3 / 414b49 / 414b64 / 414b78)。
- 作業 IR (`work-m11` の `boot_final3.ll`) では `%arg1` を ptr とする load が **0 件**。`%arg1` を値のまま `icmp eq i64 %arg1, 0` / `add i64 %arg1, -N` に使い、`%arg2-4` を ptr として読む (414b6c の `load i32, ptr (%37-4)` がトラップ位置 0xbc575 = unit 149/158/280/659 の入口)。
- IR はさらに機械語と違う点がある: 414b49 の `call 0x414850` の引数が `[rbx]` の新しい値ではなく **スタック slot のアドレス**、戻り値が機械語 (rax = 旧 `[rbx]`) でなく arg1。転記では機械語どおりに写した。

## 2. 転記 (C 版) と IR 版

- **C 版**: `tools/m11/m11_ov.c` の `function_414ad0` (逆アセンブル 414ad0..414ba9 の分岐を 1 対 1 で写す)。helper 412c20 / 414850 / 409c80 / 412d60 / 409470 は既存本体を直接呼ぶ。
  gate: `-DM11_OV_414AD0` (既定 **1**)。`M11_OV_414AD0=0 bash m11_build.sh` で IR 版に戻る (ネガコン)。`m11_build.sh` は `work/ov_414ad0.stamp` で ov.o だけ切り替える。
- **IR 版** (`trap_triage/ir414_fix.py`): C 版と同じ分岐・同じ deref 復元を LLVM IR で書いたもの。liftdiff は C 上書きを取り込まないため、68 関数の batch はこちらを使う。`--none` は無変更の複写 (A 側・ネガコン)。
- 既存の上書きと同じく `function_414ad0` は強シンボルで IR の weak 定義を置き換える。build: `cc m11_ov.c` 成功、`wasm-ld signature mismatch: 0, undefined symbol: 0`。

## 3. m11 survey (942 unit): 転記 OFF (= 検証起点と同じ) / ON

`bash trap_triage/neg_683.sh` (ON/OFF を順に build + `survey_units.mjs` + `survey_diff.py`)。コミット済み HEAD + 本 commit の `m11_build.sh`・`m11_ov.c`。n=1。

| 構成 | ok | oob | halt0 | miss | noproc | 計 |
|---|--:|--:|--:|--:|--:|--:|
| OFF (転記なし) | 818 | 21 | 56 | 46 | 1 | 942 |
| ON (転記あり、既定) | 827 | 11 | 57 | 46 | 1 | 942 |

- **OFF = 検証起点と同じ** (REPORT_596 §1 の `ok 818 / halt0 56 / miss 46 / oob 21 / noproc 1` と一致)。
- 遷移 (OFF → ON, unit 単位): ok→ok 818 / **ok→非 ok 0** / halt0→ok 3 (307, 311, 917) / oob→ok 6 (58-63) / oob→halt0 4 (56, 158, 280, 659) / oob→oob 11 / halt0→halt0 53。
- **対象 4 unit**: 149 は OFF=oob → ON=oob (最上位 frame が `414bb0 ← 652500 ← 653660` から `414c70 ← 653660 ← 6539e0` に変わる)。158/280/659 は OFF=oob → ON=**halt0** (`412770 ← 4128b0__lifted ← 4128b0`)。
  **4 unit とも ok にならない → 受入条件 1 は未達。**
- 副作用 (4 対象 unit 以外の変化): 58-63 (417b70 / 8cbb00 系の既知 oob 群) が ok になり、56 は oob→halt0。307/311/917 が halt0→ok。原因は未調査 (414ad0 を経由する unit 群と推定)。m11 survey の ok 増 (+9) はこの副作用を含む。

ネガコン: OFF build は転記なしの基準と一致 (818/21、4 unit の frame も基準と同じ)。ON↔OFF の 1 箇所切替だけで 4 unit の結果が変わることを確認 (4 unit: OFF oob → ON oob/halt0)。

## 4. liftdiff: #307 の 68 関数への波及 (A/B、同一ハーネス)

- **定義** (`tests/oob_414ad0.py` と同じ): batch の関数のうち「最初の `wasm_trap` case の wasm_detail が `memory access out of bounds @ ld_wasm.wasm.function_414ad0` で始まる」関数。基準 jsonl `tools/liftdiff/work/m11/batch_closure.jsonl` (7421 行) で **68**。
- **A** = IR 無変更の複写 (`m11_414base`)、**B** = `ir414_fix.py` で修復した IR (`m11_414fix`)。68 関数を `--set file:` で指定、`--shards 4 --state auto` (boot_state は両者とも基準 `work/m11/boot_state.json` の複写)。batch 所要 A 9 s / B 10 s (load は batch 中で約 1〜3)。

| 指標 (68 関数) | A (IR 無変更) | B (414ad0 修復) |
|---|--:|--:|
| 最初の wasm_trap が 414ad0 の OOB | **59** | **0** |
| verdict = match | 0 | 0 |
| verdict = mismatch | 68 | 68 |
| wasm_trap case 総数 | 228 | 147 |
| wasm_trap が 0 件の関数 | 1 | 38 |

- 遷移: 414ad0 OOB 59 → other 59 (verdict は全件 mismatch → mismatch)。**match → 非 match の退行は 0** (A で match は 0 件のため自明)。
- B の最初の trap の内訳: `4133f0` の OOB (経路 `4133f0 < 414c70`) **18**、`412e40` の OOB (経路 `412e40 < 653660`) 6、`4128b0__lifted` の unreachable 2、`__asm_rep_movsq_memcpy` 1、`4144a0` 1、`8e6e30` 1、残り 38 件は trap なし。
- **414ad0 の修復で消えた OOB は、次の同型 deref 脱落 (414c70 → 4133f0) に置き換わった**。68 関数はいずれも verdict が mismatch のまま。
- 注意 (ハーネスの再現性): A (4 shard・68 関数) と既存 closure jsonl (14 shard・7421 関数) は 68 件中 **50 件しか完全一致しない**。OOB414 は 59 (A) と 68 (closure) で、差の 9 関数は最初の trap 関数が変わる (例 0x65c540: closure = 414ad0, A = 408040)。shard・実行順 (memory 状態の持ち越し) による差と推定 (**未確認**)。このため A/B の比較は同一ハーネス内 (4 shard) に限って読む。
- closure 全体 (7421 関数) を修復 IR で流した結果は §5 に追記 (同じ shard 数 14 で基準 jsonl と比較)。

## 5. closure 全体 (7421 関数) の修復 IR 版

(§5 は closure batch 完了後に追記)

## 6. 再現手順 (1 コマンド)

```sh
# m11 survey (ON/OFF、work-m11 展開済み、emsdk は m11_build.sh が source)
bash tools/m11/trap_triage/neg_683.sh
# liftdiff 68 関数 A/B (work-m11 + work-liftdiff 展開済み、PY は capstone 入り python)
FL_WIN64_DIR=... PY=... bash tools/m11/trap_triage/liftdiff68_683.sh
```
ネガコン: `neg_683.sh` の OFF (`M11_OV_414AD0=0`)、`liftdiff68_683.sh` の A (`--none`)。

## 7. 検証範囲 / 範囲外

- 範囲内: m11 survey 942 unit (ON/OFF 各 1 回)、liftdiff 68 関数 (A/B 各 1 回)、closure 7421 関数 (修復 IR 1 回・§5)。
- 範囲外: n≥3 の再現 (未実施)、`m11_e2e.sh` 全体 (stage4 / bit-exact) への影響 (未実施)、C 版と IR 版の相互検算 (別々に書いたが、突合は未実施)、副作用 9 unit (58-63, 56, 307, 311, 917) の原因 (未調査)。
- 既存 REPORT の数値 (`818 / 21` 等) は、既定 ON で **main の build の数値が変わる**ため古くなる。他 REPORT の書換えは行わない (PM 判断)。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 149 の新しい最上位 `414c70` (文字列連結系, 機械語 414cbf `mov rcx,[rcx]` の 1 段 deref。IR は `icmp eq i64 %arg1, %arg2` (24 行目) で値比較。**同型と推定・IR の 0 件突合は未実施**) | 4 対象 unit のうち 149 が oob のまま | #307 にコメント (同型 deref の次候補)。新規子は PM 採番 |
| 158/280/659 の halt0 (`412770 ← 4128b0__lifted`) の原因 | 4 unit が ok にならない | #683 の継続 (本 PR は Refs) |
| liftdiff 68 の次の trap 4133f0 (18) / 412e40 (6) | 68 関数が verdict match に届かない | #307 |
| A (4 shard) と closure jsonl (14 shard) の 9/68 不一致 (harness の shard・状態依存の疑い) | liftdiff batch の再現性 | #307 (harness 件) |
| 副作用 9 unit (oob→ok 58-63, halt0→ok 307/311/917, oob→halt0 56) の原因 | ok 増分の解釈 | #596 |
| `652500` が 4 unit で rcx=0 で呼ばれる観測 (REPORT_596 §4) | 414ad0 を直しても残る可能性 | #596 |
| C 版 (m11_ov.c) と IR 版 (ir414_fix.py) の相互検算 | 転記の正しさ (独立検算) | PM 判断 (検収 subagent) |
| 既定 ON による main の survey 数値の変化 (REPORT_596 / REPORT.md の 818/21 等) | 既存数値の更新 | PM 判断 (既定 OFF に戻すか) |
