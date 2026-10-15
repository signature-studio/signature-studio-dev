# tools/flelift/boot — FLE-37 (#4983): 既定経路の FLE_BOOT_LOG_CAP が効かない不具合の修正

> 測定値の正本。親 #4970。REPORT.md §0 から参照。

既知類型との関係: 該当なし (計測側の引数の受け渡し。lift の類型は判定していない)。

## 1. 結論

- 原因: `fle6_measure.sh` の `run_boot` が `FLE_BOOT_LOG_CAP="${6:-0}"` と書いていたため、6 番目の引数を渡さない `default` 経路では環境変数の値を無視して常に 0 になった。結果 JSON の `log_cap` は null。
- 修正: `FLE_BOOT_LOG_CAP="${6:-${FLE_BOOT_LOG_CAP:-0}}"` (引数があれば引数を優先、無ければ環境変数、無ければ 0)。
- 実測: 修正後の `default` 経路で `FLE_BOOT_LOG_CAP=4096` を指定すると `log_cap` に `bytes`・`lines` が入り、`hit: "bytes"` が立つ。修正前の式に戻すと同じ指定で `log_cap: null` になる (規則を壊すと落ちる確認)。
- 上限を超えても boot 自体は既定と同じ結果 (units 895・`exit`・IPP 判定 OK) で終わった。上限は出力の計数と打ち切りの経路を確かめるためのもので、結果を変えていない。

## 2. 測定

- 測定 commit: `7b4b8f68f` (修正を含む commit。ベースは `origin/main` = `1c98a13a7`。worktree `ws-4983`・ブランチ `4983-fle-boot-log-cap`)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR`)。`[EMSDK]` (`docs/REFERENCES.md`) の emsdk。
- 4 vCPU・load は各工程の開始時 (lift 0.86 / clang 0.98 / boot 1.65)。

### 2-1. 修正後: `FLE_BOOT_LOG_CAP=4096` で `run_boot default`

```sh
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 FLE_BOOT_WORK=$RUNNER_TEMP/fle4983/w_cap FLE_BOOT_RUNS=default \
  FLE_BOOT_TAG=fle4983cap FLE_BOOT_LOG_CAP=4096 FLE_BOOT_TIMEOUT=600 FLE_EXTRA_ROOTS= \
  bash tools/flelift/boot/fle6_measure.sh
```

| 工程 | 所要 (実測) |
|---|---|
| gen-A | 6 s |
| lift | 52 s |
| clang-plain (8 shard) | 62 s |
| boot default | 6 s |
| 全体 (`time`) | 2 分 6 秒 (real 125.7 s) |

結果 (`results/boot_summary_fle4983cap_default.json` の `log_cap` と `FLEBOOT_RESULT`):

| 項目 | 値 |
|---|---|
| `log_cap.cap` | 4096 |
| `log_cap.hit` | `"bytes"` |
| `log_cap.bytes` | 932,930 |
| `log_cap.lines` | 14,429 |
| `log_cap.elapsed_ms` | 377 |
| `units_run` / `units_total` | 895 / 942 |
| `boot_threw` | `exit` |
| GetMem / FreeMem | 3,680 / 1,499 |
| `FLEBOOT_IPP_CHECK` | ok (mode 3・`ptr_15F34A0` = `0x7f10001c`) |

units 895 は REPORT §0 の既定経路の値 (`REPORT_APPENDIX_672.md` §C) と一致する。

### 2-1b. コミット済み HEAD `7b4b8f68f` での再測定

同じ指定 (`FLE_BOOT_TAG=fle4983head`) で再実行。`log_cap` = `{hit: "bytes", bytes: 932930, lines: 14429, elapsed_ms: 328}`、units 895・GetMem 3,680 / FreeMem 1,499・`exit`・IPP OK は 2-1 と同値。所要: lift 50 s・clang-plain 60 s・boot default 5 s・全体 real 121.0 s (load 1.00〜1.65・4 vCPU)。`git diff 1c98a13a7 HEAD -- tools/flelift/boot/fle6_measure.sh` は 1 行 (本修正)。

### 2-2. 規則の確認: 修正前の式 `${6:-0}` に戻す

同じ `FLE_BOOT_LOG_CAP=4096` を指定し、`run_boot` の式だけを修正前 (`FLE_BOOT_LOG_CAP="${6:-0}"`) に戻した一時スクリプトで `default` を実行 (結果ファイルは残さない)。

| 式 | `log_cap` |
|---|---|
| 修正前 `${6:-0}` | `null` |
| 修正後 `${6:-${FLE_BOOT_LOG_CAP:-0}}` | `{cap: 4096, hit: "bytes", bytes: 932930, lines: 14429}` |

### 2-3. 上限なし (既定) の確認

`FLE_BOOT_LOG_CAP` を指定しない (`=0`) で `fle_boot.mjs` を直接実行すると `log_cap` は null のまま (既存の挙動は変えていない)。式 `${6:-${FLE_BOOT_LOG_CAP:-0}}` の優先順は、6 番目の引数あり → その値、無し → 環境変数、無し・空 → 0 (`bash` で各場合を確認)。

## 3. 未解決・範囲外

- `hit` が立った後も boot は `exit` まで走った (`boot_threw: "exit"`)。上限超過で boot を `log_cap` の例外として止める経路 (`boot.threw` が `log_cap ...` になる分類) は、本 issue では測定していない。
- 既定の上限 (`diag_*` の 256MiB) の値は変えていない。
