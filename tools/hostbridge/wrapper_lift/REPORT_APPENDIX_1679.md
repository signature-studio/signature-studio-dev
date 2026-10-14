# REPORT 付録 — #1679 (HB-H35): loop 外 break・undeclared label の制御構造復元

> **正本**: `tools/hostbridge/wrapper_lift/REPORT.md` §12。本付録は計測の全文。

測定 commit: `10d45b08` (`retdec_gotofix.py` / `goto_jump_check.py` を追加した commit。本 PR でこの commit 以降に変えたのは main 取り込みによる `retdec_batch.py` (+16 / -2、#1819 の `lift_set` 再試行) のみ)。
**本付録の値は `10d45b08` 時点の値で、現 HEAD (`retdec_batch.py` が変わった状態) では未測定。** 現 HEAD での再測定は `toolchain-retdec` / `toolchain-emsdk` の素材が必要で、未実施 (fix run `3f2ed9d0` の runner に素材が無かった)。再測定は `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk` 付きの run で行い、結果を本節の表に置き換える。
環境: `[RETDEC]` v5.0 (`toolchain-retdec`)・`[EMSDK]` 6.0.12 (`toolchain-emsdk`)・`fl-win64` (`$RUNNER_TEMP` に展開)。load average (1 分値) 0.07–0.74。

## 1. 原因の切り分け (受入条件 1)

RetDec の出力 C に現れる goto 相当は 2 種類ある。

| 種類 | 出力 C の形 | emcc の診断 | 件数 (block19091, 修復後) |
|---|---|---|---|
| `break -> 0x<VA>` | `// break -> 0x4074aa` の直後に `break;` (while の外) | `'break' statement not in loop or switch statement` | 78 |
| `goto lab_0x<VA>` | `goto lab_0x407dd4;` (ラベルの定義行が無い) | `use of undeclared label` | 16 |

- `break` の飛び先は、RetDec が出した注釈 `// 0x<VA>` (機械語アドレス) を持つ文として同じ関数内に存在するのが大半 (78 件中 51 件)。
- 残る 27 件は、飛び先の注釈行が同じ関数内に無い (飛び先 C が存在しない)。
- 機械語照合 (`goto_jump_check.py`、block19091 の `// break -> 0x...` 1,427 件): 1,314 件は関数の線形 decode 内に飛び先 VA への直接 jump (`j*`) があり、113 件は無い。113 件は RetDec の制御フロー復元の飛び先が、線形 decode で見える直接 jump に対応しない箇所 (未特定)。

## 2. 採用方式 (受入条件 2)

**機械的な `break` 書換えは採らない**。採ったのは次の方式 (`retdec_gotofix.py`)。

1. emcc が `'break' statement not in loop` と報告した行だけを対象にする (loop 内の `break` は触らない)。
2. その直前 3 行の `// break -> 0x<VA>` を飛び先とする。
3. 同じ関数内に `// 0x<VA>` の注釈行が無ければ直さない。
4. 条件を満たすときだけ `break;` → `goto lab_0x<VA>;`、注釈行の直前に `lab_0x<VA>:;` を置く。

根拠: 飛び先は RetDec 自身が注釈で示した分岐先で、`goto` は注釈付きの同じアドレスの文へ飛ぶ。C の制御構造は再設計せず、`break` を注釈の飛び先への `goto` に置き換えるだけ。飛び先の注釈行を同じ関数内で必ず確認してから直すため、飛び先が存在しない箇所は直さない。

**未検証**: 飛び先の一致は C 上の注釈と機械語の jump の照合による (上記 113 件は照合できていない)。wasm の実行 (bit 一致) は未実施のため、制御構造の正しさは未検証。DEFECTS 類型 (D19 等) との照合も未実施。

## 3. 修復後の emcc exit 0 件数 (受入条件 3)

| 条件 | block19091 exit 0 | error 行 | 通過関数 (19,816 / 19,826 中) | block23676 exit 0 | error 行 | 通過関数 |
|---|---|---|---|---|---|---|
| 修復なし (§9 の再掲) | 0 / 40 | 11,432 | 16,815 | 0 / 40 | 11,475 | 16,821 |
| 修復のみ (`--int-ptr`、§9 と一致) | 1 / 40 | 1,377 | 18,932 | 1 / 40 | 1,383 | 18,939 |
| 修復 + goto 化 (本 PR) | **2 / 40** | **1,326** | **18,966** | **2 / 40** | **1,332** | **18,973** |

- 所要 (emcc 合計): 修復 + goto 化 8.83 s / 8.81 s。
- 残り error (block23676、修復 + goto 化): 引数型不一致 `incompatible pointer types passing` 1,245 件 (#1680 の範囲)・`statement not in loop` 27 件・`use of undeclared label` 16 件 (計 43 件が本 issue の残り)。
- `skip_no_addr_in_func` 27 件 (飛び先の注釈が関数内に無い) は直していない。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `statement not in loop` 27 件 (飛び先の注釈無し)・`use of undeclared label` 16 件 | exit 0 が 40 件中 2 件のみ | #1954 (HB-H41) |
| 引数型不一致 1,245 件 | exit 0 が 40 件中 2 件のみ (主因) | #1680 (HB-H36) |
| 飛び先の jump が機械語に無い `break` 113 件 | 飛び先の正しさ未検証 | #1954 (HB-H41) の範囲 |
| 修復後の wasm 実行 (bit 一致) | 制御構造の正しさ未検証 | 本 issue の範囲外。実行検証は #829 (HB-H20) 系で扱う |
