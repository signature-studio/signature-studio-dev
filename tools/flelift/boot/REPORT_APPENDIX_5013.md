# tools/flelift/boot — FLE-39 (#5013): FLE_BOOT_LOG_CAP 超過で boot.threw が log_cap にならない経路

> 測定値の正本。親 #4970。REPORT §0 から参照。

既知類型との関係: 該当なし (`docs/DEFECTS.md` D1a〜D23 と照合。本件は計測側の打ち切り経路で、lift の類型は判定していない)。

## 1. 結論

- **受入条件 1 は未達**。既定経路 (`run_boot default`) で `FLE_BOOT_LOG_CAP` を超過させると `log_cap.hit = "bytes"` は記録されるが、`boot.threw` は `log_cap ...` ではなく `exit` (code 0) になる。
- **止まった場合と止まらなかった場合の差は無い**。cap あり (4096 bytes) / cap なし (0) の両方で `units_run` 895・`boot_threw: exit`・`exit` 1 回・`longjmp` 1 回。cap の超過は止める効果を持たず、計数だけが残る。
- 原因 (確認できた範囲): cap の `throw` は `console.log/error` の中で投げられるが、`fle_boot.mjs` が差し替える前に `fleboot_plain.cjs` が `out`/`err` を `console.log/error` に束縛しているため、guest の `fprintf(stderr, ...)` は cap を経由せずに出力される。`imp_ExitProcess` は後続の `fprintf` と `fle_throw_kind("exit")` を発し、この `exit` 例外が boot の最終的な `threw` になる。cap の例外が boot 境界の外へ届かなかった直接の証跡は未取得 (次の作業)。

## 2. 測定 (既定経路 `run_boot default`)

| 項目 | 値 |
|---|---|
| 実行 | `FL_WIN64_DIR=<展開先> SS_EMSDK_ENV=<emsdk_env.sh> FLE_BOOT_WORK=<work> FLE_BOOT_TAG=fle39cap FLE_BOOT_RUNS=default FLE_BOOT_LOG_CAP=4096 FLE_BOOT_TIMEOUT=600 bash tools/flelift/boot/fle6_measure.sh` |
| 所要 | 3 分 39 秒 (gen-A → lift 84 s → clang-plain 119 s → boot 9 s) |
| load | lift 開始 0.81 / clang 開始 0.81 / boot 開始 2.42 (4 vCPU) |
| 結果 JSON | `tools/flelift/boot/results/boot_summary_fle39cap_default.json` (11,456 B・絶対パス無し) |
| `FLEBOOT_RESULT` | `units_run 895` / `units_total 942` / `boot_threw "exit"` / `log_cap {hit: bytes, bytes: 932930, lines: 14429, elapsed_ms: 648}` / `getmem 3680` / `freemem 1499` / `longjmp 1` / `exit 1` / `ipp_total 67` |
| ログ | `$RUNNER_TEMP/fle39/w_cap/run_fle39cap_default.log` (933,819 B・repo 外。ログは成果物として残さない) |

## 3. 対照 (cap あり / なし の直接比較・`fle_boot.mjs` 単体)

`fleboot_plain.cjs` (同じビルド) を `fle_boot.mjs` で直接実行 (`FLE_IPP=` 既定 3・`FLE_TOLERANT=0`・`FLE_DIAG_NULLFILL=0`・`--boot-only`)。

| FLE_BOOT_LOG_CAP | rc | units_run | boot_threw | log_cap | longjmp | getmem / freemem |
|--:|--:|--:|---|---|--:|---|
| 0 (無効) | 0 | 895 | `exit` | null | 1 | 3680 / 1499 |
| 4096 | 0 | 895 | `exit` | `hit: bytes` (elapsed 623 ms) | 1 | 3680 / 1499 |

結論: cap の超過は停止条件として効いていない。停止点・計数は cap の有無で同一。

## 4. 修正 (本 PR)

- `fle6_measure.sh` の `default)` 行: 6 番目の引数を `"${6:-0}"` 固定から、環境変数 `FLE_BOOT_LOG_CAP` を読む形に変えた (既定 0 = 無効・従来と同じ)。これまで default 経路では環境変数で cap を渡せなかった。
- 挙動の修正 (boot の停止を cap で確実にする) は**未実施**。cap の例外を boot 境界まで届かせるには、`imp_ExitProcess` の `exit` 経路と stderr の `fprintf` を cap 経由にする変更が要るが、本 run では実測の範囲を超えるため残す (§5)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| cap の throw が boot 境界まで届かない経路の特定 (guest 内の例外変換位置) と、停止させる修正 | 受入条件 1 (`boot.threw = log_cap`) | #5013 (部分達成のため Refs。後続は子 issue へ) |
