# REPORT N1532 — 同一 commit の全再生成 IR で 0 詰め引数 7 カテゴリを実測 (#1532, #1430 案 A)

既知類型との関係: 該当なし (測定のみ・コード変更なし。sigfix 分類の定義は `m11_argrecover.py` 既存)。
親: #1430 (PR #1480 の基準 before 節の未達)。

## 1. 結論

- **測定 commit `392d8ba5`** (origin/main, 2026-10-14 時点) で `m11_e2e.sh --full` を実行し、全再生成 IR から 0 詰め引数 7 カテゴリを実測した。
  和は **1,983** (`1,963` は旧測定 commit `7e149974` の `work-m11` 由来)。
- **差 +20 の内訳**: 0 詰め site 1,049 → 1,061 (+12)。旧 1,049 site は全て同一の行 (caller/callee/k/have/want/status/分類) で残り、新規 12 site (引数 20) が増分。
- **原因 commit は未特定**。`m11_scan` の入力 (`boot_ranges_extra.txt`・`scan_index.json`) は旧と byte 一致で、差は lift・tail 固定点・IR 段で生じている。二分探索による特定は本 run の時間内に収まらず、子 issue に残す (§6)。
- 受入条件のうち **未達 1 件** (site 単位突合は完了したが原因 commit の特定は未了)。測定 commit と差分の添付は §5 に記載。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| 測定 commit | `392d8ba5` (worktree `ws-1532`, branch `1532-m11-sigfix-full-ir`) |
| 比較元 | `7e149974` の `work-m11` (旧 REPORT §9 の 1,963 の出所) |
| PE | fl-win64 `extracted/block00031_PE.bin` (22,227,016 B、tar を `$RUNNER_TEMP/fl-win64` に展開) |
| functions_dll.csv | Ghidra 12.1.4 (`ghidra_12.1.4_PUBLIC_20260921`) + JDK 21.0.12 で `tools/m2/ghidra_scripts/DumpFunctions.java` を実行 (618 s, 59,010 行) |
| 実行環境 | 4 vCPU, load 0.58→1.07 (e2e 中), capstone/pefile 入り venv (`$HOME/.local/agent-py`) |

## 3. 全再生成 e2e の実測

| コマンド | 所要 | rc | 結果 (M11_SUMMARY) |
|---|---|---|---|
| `bash tools/m11/m11_e2e.sh --full` (n=1) | 649 s (load 1.07→0.84 の開始・終了) | 0 | reached_stage 4 / units_run_full 53 / 942 / survey ok 872, trap 23 (oom 0, clobber 0), miss 46 / wasm 6,043,394 B / ldfix applied, qstore applied / ir_sha256 `dc193f12…` |

- 旧 REPORT §14 の最終行 (`866/29(2)/46/1`, units_run 53) と比べ、survey ok は 866 → 872。通常起動の units_run は同じ 53。survey の差は本 run の対象外 (原因未切り分け)。
- `reached_stage 4` は REPORT §14 と同じ。停止理由は今回 `unreachable` (`function_8c5eb0` ← `function_56fde0` ← icall) で、旧 §14 の Halt0 停止 (unit 57) とは一致しない。差の原因は未切り分け (§7)。

## 4. 0 詰め引数 7 カテゴリの実測 (sigfix 0 詰め, `m11_sigfix_stats.sh`)

`m11_sigfix_stats.sh` を同 worktree で実行 (`work/sigfix_stats/`)。段階ごとの値:

| 段階 | 値 |
|---|---|
| sigfix 書換え | 6,689 site (型未対応 skip 1) |
| 0 詰め call site | **1,061 site / 2,084 引数** (旧 1,049 / 2,064) |
| 分類された 0 詰め引数 | **1,983** (旧 1,963) |
| 突合 site | matched 1,016 / no_pdata 23 / unmatched 22 |

7 カテゴリの値 (旧 = `7e149974` 由来 REPORT §9 / 新 = `392d8ba5`):

| カテゴリ | 旧 | 新 | 差 |
|---|---:|---:|---:|
| callee_nopdata | 2 | 2 | 0 |
| callee_unused | 313 | 313 | 0 |
| inherit | 1,172 | 1,185 | +13 |
| set_const | 18 | 18 | 0 |
| set_const_xmm_callee | 48 | 49 | +1 |
| set_other | 378 | 384 | +6 |
| stack_set_other | 32 | 32 | 0 |
| **和** | **1,963** | **1,983** | **+20** |

REPORT §9 の表示では `set_other 410 / inherit 1,172`・`xmm 48` と書かれていた。ここで 7 カテゴリの和を検算: 旧 `2+313+1172+18+48+378+32 = 1963` (一致)、新 `2+313+1185+18+49+384+32 = 1983` (一致)。

**注**: `m11_sigfix_stats.sh` は `m11_argrecover_verify.py` の段で止まり、`results/sigfix_zeropad_remaining.tsv` は再生成されなかった (`set -e`)。本 REPORT の site 突合は `fixes.json` の `site_detail` から作った TSV (`work/` 配下、commit しない) で行った。

## 5. site 単位の突合 (旧 TSV との差)

- 旧 `tools/m11/results/sigfix_zeropad_remaining.tsv` (1,049 行) の 1,049 site は、**同一の caller/callee/k/have/want/status/分類で全て残存** (`only_old` 0・分類差 0)。
- 新規 12 site (引数 20 件)。

| caller | callee | 引数 | 分類 |
|---|---|---|---|
| function_442320 | function_441fc0 | 3 | 0:inherit, 1:set_other, 2:inherit |
| function_4441c0 | function_443f90 | 4 | 0:set_other, 1:set_other, 2:inherit, 3:set_other |
| function_4441f0 | function_443f90 | 4 | 0:set_other, 1:set_const_xmm_callee, 2:inherit, 3:set_other |
| function_457340 〜 function_457860 (9 site) | function_412d60 | 2 | 1:inherit (各 1) |

- 増分 20 引数の内訳: inherit +13 = 2+1+1+9、set_other +6 = 1+3+2、xmm +1。
- **観察**: 新規 site の 9 件は全て `function_412d60` への呼出し。`412d60` は REPORT §10/§12 で C 転記 (`m11_ov.c`) された関数。ただし callee の転記が差の直接原因かは未確認 (本 run では IR の差分を commit 単位に切っていない)。
- 新規 caller (`function_442320`・`function_441fc0` 系・`function_4441c0`・`function_4441f0`・`function_457340`〜) は **旧 `boot_final.ll` に定義が無い** (grep 0 件)。新 `boot_final.ll` では 1 件ずつ定義がある。

## 6. 原因 commit の特定 (未了)

- 入力は一致: `tools/m11/work/boot_ranges_extra.txt` (1 行) と `scan_index.json` は旧 `work-m11` と byte 一致。
- 差は lift・tail 固定点 (`m11_tail.py` 反復 3 回)・gen_ir2 段のいずれかで生じている。`7e149974..392d8ba5` の `tools/m11` 変更は 72 ファイル (+5,471 / −55)。
- 特定には少なくとも `m11_e2e.sh --full` を 2〜3 回 (1 回 649 s) 追加で回す必要があり、本 run の 60 分上限内に収まらないと判断して子 issue に残す (§7)。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 新規 12 site (引数 20) の原因 commit の特定 (lift/tail/IR のどの段か) | 旧 1,963 と新 1,983 の差の説明が無い。受入条件「原因 commit を特定する」が未達 | 子 issue #1702 [M11-N117] (本 run で起票) |
| `m11_argrecover_verify.py` が stack 引数位置 (pos≥4) を扱えない (`ALIAS[4]` で KeyError) | 0 詰め 33 fixes のうち pos≥4 の 15 件 (pos4: 11 + pos5: 4) は独立検算できない (→ PR #1868 で解消: `REPORT_N1835.md`) | 上と同じ子 issue に併記 |
| `m11_sigfix_stats.sh` が verify 失敗で TSV を再生成しない | `results/sigfix_zeropad_remaining.tsv` が旧値のまま。再現手順が途中で止まる | 上と同じ子 issue |
| `m11_e2e.sh --full` の survey 結果が旧 REPORT §14 と異なる (ok 866 → 872) | 当 run の数値比較の前提が変わる | #132 にコメント (本 run では未調査) |

## 8. 検証

- `m11_argrecover_verify.py` (reg 引数 pos 0〜3 の 18 fixes): **match 18 / mismatch 0** (`fixes_reg.json`)。
- ネガティブコントロール: 先頭 3 件の定数を改変 (`--corrupt 3`) → **3 件 MISMATCH を検出** (FAIL を確認)。
- 0 詰め 7 カテゴリの和の検算: 旧・新ともに各カテゴリの和で再計算 (§4) し一致。
- 全 1,049 旧 site の突合 (§5) で `only_old` 0 / 分類差 0。

## 9. 再現

```sh
cd tools/m11
export FL_WIN64_DIR=<fl-win64 の展開先> PATH="$HOME/.local/agent-py/bin:$PATH"
bash m11_e2e.sh --full                 # 約 649 s (4 vCPU)。M11_SUMMARY を確認
bash m11_sigfix_stats.sh               # 0 詰め site/引数の集計 (verify は reg 引数のみ)
python3 m11_argrecover_verify.py work/sigfix_stats/fixes_reg.json --pe $FL_WIN64_DIR/extracted/block00031_PE.bin
```

Ghidra の `functions_dll.csv` は `tools/m2/ghidra_scripts/DumpFunctions.java` を `analyzeHeadless` で実行 (JDK 21)。本 run は `$RUNNER_TEMP/ghidra/` に展開した 12.1.4 を使った (618 s)。

## 10. 差分

- 測定 commit: `392d8ba5`。コード変更なし (本 REPORT の追加のみ)。
- 測定 commit `392d8ba5` から commit `2c711fd3` までの `git diff --stat 392d8ba5 2c711fd3 -- tools/m11` の実出力:

```
tools/m11/REPORT_N1532.md | 121 ++++++++++++++++++++++++++++++++++++++++++++++
1 file changed, 121 insertions(+)
```

- REPORT 以外のコード差分 (`git diff --stat 392d8ba5 HEAD -- tools/m11 ':!tools/m11/REPORT_N1532.md'`) は出力 0 件 (変更 0)。
