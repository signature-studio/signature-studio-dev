# REPORT N1702 — sigfix 0 詰めの再測定・verify の pos 0〜7・TSV 再生成の実測 (#1702, 親 #1532)

既知類型との関係: 該当なし (測定と検算の確認のみ。コード変更なし)。
親: #1532。関連: `REPORT_N1532.md` §6・§7、`REPORT_N1835.md` (PR #1868 で pos ≥ 4 の検算を追加済み)。

## 1. 結論

- 受入条件 2 (verify が pos 0〜7 を検算、negative control で FAIL) は **達成**。`match 33 / mismatch 0`、`--corrupt 3` で `match 30 / mismatch 3`。ただし今回の fixes に現れた pos は 0〜5 だけで、pos 6・7 の実データ検算は無い (verify の分岐は pos ≥ 4 で共通のため未検証は残る)。
- 受入条件 3 (`m11_sigfix_stats.sh` が最後まで走り TSV を再生成) は **達成**。rc 0、TSV は再生成後も byte 一致 (差分 0)。
- 受入条件 1 (新規 12 site を生んだ commit の特定) は **未達**。本 run の素材では再現できない (§4)。二分探索は full e2e (約 649 s) の複数回実行が必要で、1 run に収まらないため子 issue #1904 `[M11-N125]` に分離する。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| 測定 commit | `30a7b5b4` (origin/main、コード変更の最後の commit。本 PR はコード変更なし) |
| 実行コマンド | `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/m11_sigfix_stats.sh` |
| 入力 | `tools/m11/work/boot_final.ll` (work-m11, 10 Oct 生成, md5 `31f82201…`)・PE `extracted/block00031_PE.bin` (22,227,016 B、fl-win64 から展開) |
| 所要時間 | real 3.76 s (user 3.30 s) |
| load | 0.31 (開始時 uptime) |
| 環境 | 4 vCPU、`~/.local/agent-py` の python (capstone / pefile 入り) |
| rc | 0 |

## 3. 実測値

| 項目 | 値 |
|---|---|
| sigfix 書換え | 6,675 site (型未対応 skip 1) |
| 0 詰め call site | 1,049 / 0 詰め引数 2,064 |
| const 復元 | fixes 33 / recovered 24 (base 0) |
| verify (pos 0〜7) | `[verify] fixes 33: match 33 / mismatch 0` |
| pos 別内訳 | pos0: 1, pos1: 9, pos2: 2, pos3: 6, pos4: 11, pos5: 4 |
| negative control | `m11_argrecover_verify.py work/sigfix_stats/fixes.json --pe $PE --corrupt 3` → `match 30 / mismatch 3`、rc 1 (MISMATCH 3 件を検出) |
| TSV | `results/sigfix_zeropad_remaining.tsv` を再生成。`git diff --stat -- tools/m11/results` は空 (1,049 行 + ヘッダ) |
| 終端行 | `[stats] zeropad sites 1049 / args 2064; const recovered 24 (base 0)` |

## 4. 新規 12 site (引数 20) の未特定

- 本 run で使った `work/boot_final.ll` (work-m11 と md5 一致) からは **1,049 site / 2,064 引数** が出た。これは旧値 (`7e149974`) と同じで、`REPORT_N1532.md` §4 の新値 **1,061 / 2,084** は再現しなかった。
- 新値を生んだ IR (`392d8ba5` の full 再生成) は `work-m11` に含まれていない。`boot_final.ll` の更新日は 10 Oct で、`REPORT_N1532.md` の測定 (`m11_e2e.sh --full`) より前。
- したがって「新規 12 site を生んだ commit」を特定するには、commit ごとに `m11_e2e.sh --full` (約 649 s) を回して 0 詰め site 数を測る二分探索が必要。本 run の 60 分では収まらない。

## 5. 差分

- 測定 commit `30a7b5b4` から本 REPORT の commit までの tools/m11 のコード差分: 0 (本 REPORT の追加のみ)。
- 差分の実出力は PR 本文と issue コメントに添付した。

## 6. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH="$HOME/.local/agent-py/bin:$PATH"
cd tools/m11
bash m11_sigfix_stats.sh                      # rc 0・終端行 1049 / 2064 / 24
python3 m11_argrecover_verify.py work/sigfix_stats/fixes.json --pe $FL_WIN64_DIR/extracted/block00031_PE.bin   # match 33
python3 m11_argrecover_verify.py work/sigfix_stats/fixes.json --pe $FL_WIN64_DIR/extracted/block00031_PE.bin --corrupt 3   # match 30 / mismatch 3
```

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 新規 12 site (引数 20) を生んだ commit (または段) の特定。`392d8ba5` の full 再生成 IR が素材に無い | 旧 1,963 と新 1,983 の差の説明が無い | 子 issue #1904 `[M11-N125]` |
| pos 6・7 の実データ検算 (今回の fixes は pos 0〜5 のみ) | pos 6・7 の stack 引数の検算根拠が無い | 本 PR の未解決表 (子は作らない: 入力が増えるまで検証不能) |
