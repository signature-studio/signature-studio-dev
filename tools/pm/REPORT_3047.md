# PM Worker の率制限 alert を watchdog から oc:rate-limit の issue に出す (#3047・CI-142)

> **正本**: 本付録 (`tools/pm/REPORT_3047.md`)。`tools/pm/REPORT.md` は 250 行上限のため本体へ追記しない (`docs/DOC_MAP.md` §1)。
> 運用の正本は `docs/WORKFLOW.md` §11 の『PM Worker の率制限 alert』。

## 1. 変更

- `.github/scripts/watchdog.sh`: `rate_check` (判定)・`rate_down` (追記か起票)・`rate_body`・`rate_file`。採番は `ci_next_title_n` に切り出し、PM Worker 停止の起票 (`worker_down`) と共有する。
- `.github/scripts/tests/test-watchdog.sh`: 40a〜40q (expect 23 件)。
- `docs/WORKFLOW.md` §11: 率制限 alert の 1 節。

判定: `fresh` が true の `/status` で、`rate_limit_alert` が JSON の `true`、または `rest_remaining` が 1500 未満。
`fresh` が false の値は使わない (古いかもしれないため。停止は `pm-worker-down` が扱う)。`/status` が取れない・JSON 不正なら何もしない (終了コードは変えない)。
起票先: ラベル `oc:rate-limit` の open issue があれば 60 分に 1 回まで追記。無ければ題名 `[CI-n] PM Worker 率制限 alert (日付)` を起票する。ラベルは `notify-rate-limit.sh` (run 側) と共有し、二重の issue を作らない。
5 件・30%・2 回連続は Worker (`ratealert.ts`) が判定する。watchdog は `rate_limit_alert` の真偽だけを読む。1500 は `ratelimit.ts` と同じ値で、40q が一致を確かめる。

## 2. 測定 (測定 commit `0f217ac4`)

| 測定 | 結果 |
|---|---|
| `bash .github/scripts/tests/test-watchdog.sh` (HEAD `0f217ac4`) | rc 0・**141 passed / 0 failed**・wall 15 s・OS の loadavg (1 分値) 0.37 → 0.51 |
| 同 (新規 40a〜40q のみ・ネガコン含む) | 23 expect すべて ok |
| `bash .github/scripts/tests/test-pr-loop.sh` / `test-run-outcome.sh` / `test-workflow-pm-job.sh` | 0 fail / 0 fail / 40 passed 0 failed |
| `shellcheck -S warning .github/scripts/watchdog.sh` | 警告 0 |

**規則を壊したときの FAIL (mutation・一時コピーで実行)**:

| 変異 | 落ちたテスト |
|---|---|
| M1: 境界を `-le` にした (1500 で起票) | 40c (`rest_remaining 1500` で何もしない) |
| M3: `fresh` の判定を外した (stale を使う) | 40f |
| M5: `rate_limit_alert` の真偽判定を外した (文字列 `"true"` も真) | 40e |
| M6: 追記の 60 分の間隔を外した | 40i・40k |

M1 の複製では既定 URL の 2 件 (`tools/pm/worker_url` の確認) も落ちた。複製にそのファイルを入れていないことによる見かけ上の失敗で、本物の worktree では PASS。

差分: `git diff 0f217ac4 HEAD -- .github/scripts infra/pm-worker` の出力は 0 行 (本付録と DOC_MAP の登録だけを後の commit で足すため)。

## 3. 本番 `/status` の読み取り (変更を入れる前、読み取りのみ)

2026-10-14 21:27 UTC 頃の `/status`: `mode` live・`configured` / `installed` / `fresh` true・`rate_limit_alert` false・`rest_remaining` 4891 (`rest_reset_at` 21:41 UTC)。
→ デプロイ後の最初の点検は `rate=ok` になり、起票も追記も起きない見込み。実際の点検の出力 (`rate=ok`) の確認は、merge 後の次の点検で行う (未確認)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 回復時の自動 close は入れていない (受入条件外) | 率制限が戻っても `oc:rate-limit` の issue は人が close するまで open のまま | PM の判断 (本 issue の受入条件外) |
| merge 後の本番の点検で `rate=ok` が出ることの実 run での確認 | 未確認 (本番の点検ログの 1 回分) | merge 後の次の watchdog の run で確認する |
