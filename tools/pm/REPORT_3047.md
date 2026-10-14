# PM Worker の率制限 alert を watchdog から oc:rate-limit の issue に出す (#3047・CI-142)

> **正本**: 本付録 (`tools/pm/REPORT_3047.md`)。`tools/pm/REPORT.md` は 250 行上限のため本体へ追記しない (`docs/DOC_MAP.md` §1)。
> 運用の正本は `docs/WORKFLOW.md` §11 の『PM Worker の率制限 alert』。

## 1. 変更

- `.github/scripts/watchdog.sh`: `rate_check` (判定)・`rate_down` (追記か起票)・`rate_body`・`rate_file`。採番は `ci_next_title_n` に切り出し、PM Worker 停止の起票 (`worker_down`) と共有する。
- 再起票の抑止 (レビュー blocking の対応・commit `e0275601`): open が無いときは `gh issue list --state closed` を読み、6 時間 (`RATE_CLOSE_SEC`・notify-rate-limit.sh と同じ窓) 以内に閉じた `oc:rate-limit` の issue があれば起票しない。reopen はしない。一覧が読めなければ何もしない (fail-closed)。
- `.github/scripts/tests/test-watchdog.sh`: 40a〜40t (expect 25 件。40r〜40t が閉じた issue の抑止)。
- `docs/WORKFLOW.md` §11: 率制限 alert の 1 節 (6 時間の抑止と、二重コメントの意図を含む)。

判定: `fresh` が true の `/status` で、`rate_limit_alert` が JSON の `true`、または `rest_remaining` が 1500 未満。
`fresh` が false の値は使わない (古いかもしれないため。停止は `pm-worker-down` が扱う)。`/status` が取れない・JSON 不正なら何もしない (終了コードは変えない)。
起票先: ラベル `oc:rate-limit` の open issue があれば 60 分に 1 回まで追記。無ければ題名 `[CI-n] PM Worker 率制限 alert (日付)` を起票する。ただし 6 時間以内に閉じた同じラベルの issue があれば起票しない (人が close した直後の再起票を防ぐ)。ラベルは `notify-rate-limit.sh` (run 側) と共有し、二重の issue を作らない。
5 件・30%・2 回連続は Worker (`ratealert.ts`) が判定する。watchdog は `rate_limit_alert` の真偽だけを読む。1500 は `ratelimit.ts` と同じ値で、40q が一致を確かめる。

## 2. 測定 (測定 commit `e0275601`)

| 測定 | 結果 |
|---|---|
| `bash .github/scripts/tests/test-watchdog.sh` (HEAD `e0275601`) | rc 0・**144 passed / 0 failed**・wall 15.7 s・OS の loadavg (1 分値) 0.56 → 0.69 |
| 同 (40〜 の expect 25 件・ネガコン含む) | 25 expect すべて ok。前回 (`0f217ac4`・141 件) からの増分は 40r〜40t の 3 件 |
| `bash .github/scripts/tests/test-run-outcome.sh` / `test-workflow-pm-job.sh` | 76 passed 0 failed / 40 passed 0 failed |
| `bash .github/scripts/tests/test-pr-loop.sh` (runner の環境のまま) | 127 passed / **6 failed**。6 件は `fix-progress.sh record` の窓・停止の判定 (`(a)`〜`(e)` と `OC_RECORD_OK`)。変更前の `38252efe` でも同じ 6 件が FAIL (本 PR の差分に fix-progress.sh は無い)。`env -i` で空の環境にすると 133 passed / 0 failed。runner の `GITHUB_*` 変数 (40 個) の影響と推定 |
| `shellcheck -S warning .github/scripts/watchdog.sh` | 警告 0 |

**規則を壊したときの FAIL (mutation・一時コピーで実行)**:

| 変異 | 落ちたテスト |
|---|---|
| M1: 境界を `-le` にした (1500 で起票) | 40c (`rest_remaining 1500` で何もしない) |
| M3: `fresh` の判定を外した (stale を使う) | 40f |
| M5: `rate_limit_alert` の真偽判定を外した (文字列 `"true"` も真) | 40e |
| M6: 追記の 60 分の間隔を外した | 40i・40k |
| M7: 閉じた issue の 6 時間の確認を外した (`recent` を無視) | 40r のみ (`143 passed, 1 failed`) |

M1 の複製では既定 URL の 2 件 (`tools/pm/worker_url` の確認) も落ちた。複製にそのファイルを入れていないことによる見かけ上の失敗で、本物の worktree では PASS。

差分: `git diff e0275601 HEAD -- .github/scripts infra/pm-worker` の出力は 0 行 (本付録の commit は tools/pm だけを変える)。

## 3. 本番 `/status` の読み取り (変更を入れる前、読み取りのみ)

2026-10-14 21:27 UTC 頃の `/status`: `mode` live・`configured` / `installed` / `fresh` true・`rate_limit_alert` false・`rest_remaining` 4891 (`rest_reset_at` 21:41 UTC)。
→ デプロイ後の最初の点検は `rate=ok` になり、起票も追記も起きない見込み。実際の点検の出力 (`rate=ok`) の確認は、merge 後の次の点検で行う (未確認)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 回復時の自動 close は入れていない (受入条件外) | 率制限が戻っても `oc:rate-limit` の issue は人が close するまで open のまま | PM の判断 (本 issue の受入条件外) |
| merge 後の本番の点検で `rate=ok` が出ることの実 run での確認 | 未確認 (本番の点検ログの 1 回分) | merge 後の次の watchdog の run で確認する |
| `test-pr-loop.sh` が runner の `GITHUB_*` 変数を引き継ぐと 6 件 FAIL (変更前から同じ) | scripts-test の結果が実行環境で変わる。本 PR の変更とは無関係 | PM の判断 (テストの環境を空にするかは本 issue の範囲外) |
