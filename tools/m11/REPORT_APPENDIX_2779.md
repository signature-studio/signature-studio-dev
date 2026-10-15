# M11 REPORT_N403 §7 の付録 (#2779・本 runner の参考値)

自動生成ではない。REPORT_N403.md §7 の全文を 250 行上限のため分割移動した (内容は削除していない。Git 履歴に残る)。

## 7. 本 runner の参考値 (#2779・LB=0 / 0x10000 の後段・指紋検査を迂回)

測定日 2026-10-14。素材 fl-win64 (`block00031_PE.bin` 22,227,016 B)・work-m11 (#516 以前の snapshot)。toolchain は runner 同梱の [EMSDK]・[RETDEC] (`docs/REFERENCES.md`)。
**以下の数値は受入の根拠ではなく参考値である。** `m11_e2e.sh` の lift 成果物の PE 指紋検査 (`work/lift_pe.sha256`・WORKFLOW §11) を `M11_SKIP_LIFT_FP=1` で迂回して後段だけを回した。素材 work-m11 には生成時の PE 指紋 (`lift_pe.sha256`・`ir_conditions.json`) が無く、lift 成果物が現 PE に対応することは確認できていない。全再生成は `functions_dll.csv` (Ghidra の中間物) を要し、本 run の時間内に収まらないため行っていない。
測定 commit: `d890c724` (コードを変えた最後の commit。以降の差分は本 REPORT のみ。§7.5)。
製品 KPI (`tools/flelift/boot/REPORT.md`) は本節で測っていない。

### 7.0 解消後の再測定 (HEAD `bd5daf9d`・参考値・本節が最新)

main 取り込み後 (merge `c277b9ff`・REPORT 分割 `bd5daf9d`) の再測定。`tools/m11` の PR 差分は main と 0 (§7.4)。素材 `fl-win64`・`work-m11` を展開 (`tools/m11/work/`)。toolchain は runner の既存 [EMSDK]・[RETDEC] を使用 (artifact の再展開はしていない)。node v22.23.3 (`m11_e2e.sh` の前提は v26 で、v26 は未確認)。nproc 4。

| 条件 | 結果 | rc | wall | load (前 → 後 1/5/15 分) |
|---|---|---|---|---|
| LB=0 | units_run 53・survey ok 872 / noproc 1 / miss 46 / trap 23・寛容 ok 874 / skipped 67・gate と negctl OK・ir_sha256 `39e97946…` | 0 | 192 s | 0.43 0.55 0.30 → 0.99 0.79 0.45 |
| LB=0x10000 | gen_ir2・lb_check・build OK・units_run 37 (Halt0 早期)・survey ok 869 / noproc 1 / miss 46 / trap 26 (abort 2・unresolved function_535c2e 2)・寛容起動の出力 0 バイト (M11_TOLERANT 行無し → gate FAIL)・ir_sha256 `d8738edd…` | 1 | 708 s | 0.65 0.72 0.44 → 1.01 1.00 0.78 |

ptrcheck: LB=0x10000 は run 69,099 / 69,359・survey 70,945 / 71,001 (gate pass)。LB=0 は rc 0 で gate 合格 (ptrcheck JSON は LB=0x10000 の run で上書きされ、LB=0 の数値は未記録)。
units_run・survey・trap・ir_sha256 は §7.1 (HEAD `d890c724`) と一致する。e2e 経路 (IR `d8738edd…`) の寛容起動の出力空は §7.1 と同じ。repro 経路 (IR `ecbd43c1…`・REPORT §6) では完走しており、2 つの経路で IR の指紋が違う (§7.2)。#3160 は CLOSED のまま (再オープンしない・PM 判断)。

### 7.1 測定 (HEAD `d890c724`・参考値)

再現 (リポジトリ root。`FL_WIN64_DIR` に `extracted/block00031_PE.bin`、`tools/m11/work/` に work-m11 を展開してから実行):

```
M11_SKIP_LIFT_FP=1 M11_LB_BASE=0 bash tools/m11/m11_e2e.sh
M11_SKIP_LIFT_FP=1 M11_LB_BASE=0x10000 bash tools/m11/m11_e2e.sh
```

`M11_SKIP_LIFT_FP` は `tools/m11/m11_e2e.sh` の指紋検査だけを外すオプションで、未設定なら従来どおり検査する。実行時は `WARNING ... 参考値` の行が出る。

| 条件 | 結果 | rc | wall | load (開始前 → 終了直後、1/5/15 分) |
|---|---|---|---|---|
| LB=0 | units_run 53・survey ok 872 / noproc 1 / miss 46 / trap 23・寛容 ok 874 / skipped 67・gate と negctl OK・ir_sha256 `39e97946…` (修正前と同一) | 0 | 2 m 53 s | 0.19 0.30 0.15 → 1.00 0.63 0.31 |
| LB=0x10000 | gen_ir2・lb_check・build OK。units_run 37 (Halt0 早期)・survey ok 869 / noproc 1 / miss 46 / trap 26。e2e 経路 (`M11_SKIP_LIFT_FP=1 m11_e2e.sh`・IR `d8738edd…`) では寛容起動が 600 s の `timeout` で打ち切られ出力空 (M11_TOLERANT 行無し → gate FAIL)。repro 経路 (IR `ecbd43c1…`) では完走 (§7.2) | 1 | 11 m 38 s | 0.73 0.60 0.31 → 1.00 0.98 0.70 |

nproc は 4。load は各 run の前後の `/proc/loadavg`。LB=0 と LB=0x10000 は同じ `work/` を共有するため逐次に測った。

ptrcheck (`ptrcheck.gate`。`image_va_words_new` / 上限):

| 条件 | run (通常起動) | survey (unit 実行後) |
|---|---|---|
| LB=0 | 69,359 / 69,359 (pass) | 71,001 / 71,001 (pass) |
| LB=0x10000 | 69,099 / 69,359 (pass) | 70,945 / 71,001 (pass) |

ptrcheck JSON の `ok` (生フラグ) は両条件で false。判定は `gate.pass`。LB=0x10000 側の ptrcheck はこの参考値で確認した (ただし上限は fresh 再生成の基準値で、迂回した素材との比較は参考)。

### 7.2 #403 との比較 (参考値どうしの比較)

| 項目 | #403 (引用) LB=0 | 本節 LB=0 | #403 (引用) LB=0x10000 | 本節 LB=0x10000 |
|---|---|---|---|---|
| units_run | 53 | 53 | 37 | 37 |
| survey ok / noproc / miss / trap | 870 / 1 / 46 / 25 | 872 / 1 / 46 / 23 | 868 / 1 / 46 / 27 | 869 / 1 / 46 / 26 |
| 通常起動の終了 | OOB | trap unreachable (function_8c5eb0) | Halt0 早期 | Halt0 早期 |

units_run と LB=0x10000 の Halt0 早期は #403 と一致、survey は ±2 のずれ。受入 2 (「変わらない」) は未達。原因は未確定。候補は (a) boot5 (素材に `boot5.lift.ll` が無く、本節は RetDec で lift し直した)、(b) ld108 (#2316。#403 より後)。切り分けは子 #3161。

IR の指紋 (2 つの経路で違う): e2e 経路 (`M11_SKIP_LIFT_FP=1 m11_e2e.sh`) の LB=0x10000 IR は `d8738edd…`、repro 経路 (`m11_lb_tolerant_repro.sh 0x10000`・§6) の IR は `ecbd43c1…`。どちらが正規かは未確定。`--full` で作る IR との照合を #3161 で行って決める。

### 7.3 前 round の測定 (参考。旧 commit・同じ迂回)

| 条件 | 結果 | rc | wall |
|---|---|---|---|
| LB=0 (`94dea77f`) | units_run 53・survey ok 872 / noproc 1 / miss 46 / trap 23・寛容 ok 874 / skipped 67 | 0 | 1 m 58 s |
| LB=0 (`6566443d`) | 上と同一 (ir_sha256 `39e97946…`) | 0 | 1 m 21 s |
| LB=0x10000 (`94dea77f`) | gen_ir2 が `fix_ld108` の assert で停止 (即値不一致) | 1 | 0 m 31 s |
| LB=0x10000 (ld108 のみ修正・**未コミットの診断**) | build が `fix912` で停止 (`対象行が無い`) | 1 | 0 m 52 s |
| LB=0x10000 (`51b20449`) | gen_ir2・build OK。units_run 37・survey ok 869 / trap 26。寛容起動が 600 s で打ち切り | 1 | 11 m 10 s |

### 7.4 修正 (本 PR の commit は main 取り込み時に main 側へ置換)

`ldfix/fix_ld108.py` の head 即値 `16404608` (LB=0 の LVA 0xfa5080) と `fix912/m11_fix912.py` の VMT 即値 `994072` (0xf2b18) は LB=0 専用の固定文字列だった。LB=0x10000 の IR では +0x10000 の即値になるため、既定経路の `M11_LB_BASE=0x10000 m11_e2e.sh` は gen_ir2 で止まっていた。本 PR (`51b20449`・`d890c724`) は両者を `tools/m11/lb_base.py` の `LB` を import して直した。同じ修正が main に `fb735704` (#3160) で入っていたため、`origin/main` の merge で競合した。解消は main 側の版を採った (`tools/m11/ldfix/fix_ld108.py`・`tools/m11/fix912/m11_fix912.py` は `origin/main` と差 0)。両版の即値は LB=0 で同一 (`16404608`・`994072`)、LB=0x10000 で同一 (`16470144`・`1059608`)。LB=0 の e2e の IR 指紋 (`39e97946…`) は修正前と同一。

### 7.5 測定 commit から HEAD までの差分

コードの差分は無い (測定 commit `d890c724` → HEAD は本 REPORT のみ)。確認: `git diff d890c724 HEAD -- tools/m11 ':!tools/m11/REPORT_N403.md'` (出力 0 バイト)。
修正の差分: `git diff 94dea77f d890c724 -- tools/m11/fix912 tools/m11/ldfix tools/m11/m11_e2e.sh`。

### 7.6 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 全再生成経路 (`functions_dll.csv`・`lift_pe.sha256` 無し) で `m11_e2e.sh` 1 コマンドが通らない。§7 の値は指紋検査の迂回に依存 | 受入 1 (実測の根拠) 未達。lift 成果物と PE の対応は未確認 | #3172 (`work-m11` の更新・#728 以降の再生成) |
| e2e 経路 (`M11_SKIP_LIFT_FP=1 m11_e2e.sh`・IR `d8738edd…`) では LB=0x10000 の寛容起動が 600 s で打ち切られ出力が空。repro 経路 (IR `ecbd43c1…`) では完走 (§6) | この e2e 経路の LB=0x10000 は rc=1 | #3160 は CLOSED のまま (再オープンしない・PM 判断)。IR の照合は #3161 |
| #403 との数値差 (survey ±2)・LB=0 の停止理由 (OOB → unreachable)・LB=0x10000 の Halt0 早期 | 受入 2 (変わらない) 未達 | #3161 |
