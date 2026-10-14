# tools/pm — PM 運用ツール (VM 版。退役の途中)

PR / Issue / Actions run の運用ツール。2026-10-14 に VM の timer を停止し、再開しない運用に切り替えた
(`infra/pm-worker/README.md` の『切替の記録』)。`/oc` の投稿と `oc-watchdog`・`oc-pm` の送信は Worker
(`infra/pm-worker`、Cloudflare) が担い、点検は Actions の `watchdog.sh`、PM の判断は Actions の `pm` job (PM agent) に移した (配線済み。実 run の確認は親 #2319 の A4)。
このディレクトリの大半は VM 版のツールで、後継と退役の扱いは下の『VM 退役後の扱い』の表が正本。実装 agent は使わない。
数値の正本は [`REPORT.md`](REPORT.md)、運用規約の正本は `docs/WORKFLOW.md` §11。

## 前提

- `gh` が認証済みであること (keyring が解錠されていること。ロック中は `gh` が止まる。
  トークンの平文保存や PAT への切替で回避しない。依頼者に解錠を依頼する)。
- `python3`、`jq`、`curl`、systemd user (`systemctl --user`)。heartbeat は OpenCode CLI を使う。
- 操作は **REST を基本**にする。GraphQL は 5,000 点/時の枠を使い切った実績がある (RETRO §D)。
  GraphQL を使うのは次だけ: `pr_gaps.py` (PR 一覧の全ページ取得)、`sync_status.py` (Project V2 の Status 更新)、`gh pr ready`。`find_unreviewed.sh` は REST (`--paginate`) を使う。

## 環境変数

| 変数 | 既定 | 用途 |
|---|---|---|
| `PM_SESSION_ID` | **必須** (無ければ heartbeat.sh は起動せず終了) | heartbeat が送信する PM セッション ID。環境ごとに設定する |
| `PM_DIR` | このディレクトリ | 状態ファイルとログの置き場 (heartbeat の文面にも使う) |
| `PM_TMP` | `${TMPDIR:-/tmp}/pm` | 一時ファイル |
| `OPENCODE_BIN` | `opencode` | heartbeat が使う OpenCode CLI |
| `PM_SESSION_ID_FILE` | 無し | `pm_wake.sh` が読む PM セッション ID のファイル (1 行)。`PM_SESSION_ID` が空のときだけ使う。宛先のセッションが入れ替わっても、ファイルを書き換えれば追従できる |
| `PM_WAKE_STATE` / `PM_WAKE_LOG` | `pm_wake.state.json` / `pm_wake.log` | `pm_wake.sh` の状態 (送信の時刻・fresh=false の開始時刻) と記録。どちらも gitignore 済み |
| `PM_WAKE_NOW` | 現在時刻 | テスト用に `pm_wake.sh` の時刻を epoch 秒で固定する |
| `DRY=1` | 無し | 計画の表示だけ (rest_heal / sync_status / launch / blocked) |
| `ONLY=<番号,…>` / `MAX` / `AGAIN` | 無し | 対象の絞り込み / 1 回の件数 / 同じ PR への再依頼間隔 (分) |
| `TARGET` / `BATCH` | 50 / 25 | `launch_issues.py launch` の同時稼働の目標 / 1 回の投入数 |

## ツール

> 2026-10-14 の切替で、VM の timer と `heartbeat.sh` の着手・点検の役は Worker と Actions に移った (timer は停止したまま再開しない)。各ファイルの後継と退役の扱いは『VM 退役後の扱い』の表が正本。
>
> **heartbeat は監査専用 (指示 145、2026-10-15 に再開)。着手 (launch)・watchdog は Worker、PM の判断は PM agent。**
> `pm-heartbeat.service` だけを 2 時間ごと (`PM_HEARTBEAT_SECONDS=7200`) に動かし、文面は `heartbeat_msg_audit.txt` (`PM_HEARTBEAT_MSG_FILE`)。
> 送るのは Actions・チケット・開発フローの監査の依頼だけ。`pm-launch.timer`・`pm-watchdog.timer` は再開しない (Worker と二重になる)。戻し方: `systemctl --user disable --now pm-heartbeat.service`。

| ファイル | 用途 |
|---|---|
| `watch_runs.sh` | 実行中の Actions run を REST で監視し、1 本終わるたびに 1 行出して終了する。**終了通知を受けたら、結果の処理より先に再起動する** (指示 116)。詳細は [`watch_runs.notes.md`](watch_runs.notes.md) |
| `heartbeat.sh` | `PM_HEARTBEAT_SECONDS` (既定 1800) ごとに PM のセッションへ固定文を送る。env `PM_HEARTBEAT_MSG_FILE` があればその文面、無ければ内蔵の 30 分版 (指示 102・116・120。着手・点検の指示を含むため使わない)。運用は `heartbeat_msg_audit.txt` + 7200 秒の監査専用 (指示 145)。`systemd/pm-heartbeat.service`。必要なときだけ起こす置換は `pm_wake.sh` (下の『heartbeat からの置換』) |
| `pm_wake.sh` | `/status` を読み、PM のセッションが必要なときだけ固定文を送る (`heartbeat.sh` の置換。#2347)。送るのは needs_pm > 0・fresh=false が 30 分続く・stuck_age_max_min > 360 のどれかのときだけで、送信は 3 時間に 1 回・24 時間に 6 回まで。終了コードは 0 (判定の結果) / 1 (セッション ID 無し) / 2 (`/status` の取得・解析失敗。`needs_pm` が無い古い Worker も含む) / 3 (送信失敗)。テスト: `bash tools/pm/test_pm_wake.sh` |
| `pm_watchdog_ping.sh` | 5 分ごとに `repository_dispatch` (`oc-watchdog`) を送り、Actions の watchdog を起こす (GitHub の schedule が発火しないため)。`systemd/pm-watchdog.*` |
| `pm_gate.sh` | `pm_gate.sh <command...>`。Worker (`infra/pm-worker`) が primary (`/status` が `mode=live`・`fresh=true`・`last_tick` が 15 分以内) の間は command を実行せず終了 0 にする。それ以外 (取得失敗・dry-run・JSON 不正) は command を実行する (fail-open)。URL は env `PM_WORKER_URL`、無ければ `tools/pm/worker_url`。テスト: `bash tools/pm/test_pm_gate.sh` |
| `launch_issues.py` | 指示 130〜132 の自動着手。`plan` (仕分け) / `blocked` (blocked_by を GitHub に同期) / `launch` (`/oc` コメントで着手)。`systemd/pm-launch.*` が 10 分おきに `launch` を実行。Opened PR 数は `oc:stuck` の PR を除き、stuck が `STUCK_HIGH` (既定 40) を超えたら launch を止める。停止報告の判定は run-outcome・PM マーカー付きコメントを除く (#2325)。テスト: `python3 -m unittest tools/pm/test_launch_issues.py` |
| `worker_url` | Worker (`infra/pm-worker`) の URL (1 行・末尾の `/` なし)。`pm_gate.sh` と Actions の `watchdog.sh` が `<URL>/status` を読む。`watchdog.sh` は Worker が止まっていれば障害 issue (ラベル `pm-worker-down`) を起票する (`docs/WORKFLOW.md` §11) |
| `../../infra/pm-worker/` | `launch_issues.py` の launch と `pm_watchdog_ping.sh` の後継 (Cloudflare Worker。webhook + Cron/alarm 駆動)。2026-10-14 から live (`LIVE_LAUNCH`・`LIVE_DISPATCH` が `"1"`)。切替の記録と戻し方は `infra/pm-worker/README.md` の『切替の記録』 |
| `issue_snapshot.py` | open の issue / PR / run / 最新の bot コメントを `issues_state.json` に保存する (`launch_issues.py` が呼ぶ) |
| `manual_deps.json` | 停止報告に根拠のある依存 (子 → [依存先])。**追跡する設定ファイル** (他の json は状態で、`.gitignore`) |
| `rest_heal.py` | open PR を CONFLICT / FIX / NOREVIEW / DRAFT / APPROVED / COVERED / STUCK_LABELLED に分類し、足りない次の一手を `/oc` コメントか close→reopen で補う。watchdog (`.github/scripts/watchdog.sh`) の補助 |
| `sync_status.py` | Project V2 の Status を PR / Issue の実態に同期する (冪等)。Status は参考で、チケット状態の正は issue の open/closed + ラベル + PR (`docs/WORKFLOW.md` §3)。実行しないと Status が陳腐化する。**退役後は同期をやめる (根拠: #2356。下表)** |
| `pm_needs.py` | 最新の差し戻しが PM 判断を求めていて、PM の応答が無い PR を列挙する。heartbeat のたびに実行して未回答を 0 にする |
| `idle_report.sh` | watchdog の run 履歴から『idle>0 が 15 分以上続いた回数』を数える (VM の `pm-watchdog.timer` を止めてよいかの soak 判定用)。REST のみ。`idle_report.sh --since <ISO> --until <ISO>`。使い方は下の節。テスト: `bash tools/pm/test_idle_report.sh` |
| `pr_gaps.py` | open PR を「レビュー中 / 修正中 / 担当なし」に分類する |
| `dismiss_spam.py` | watchdog が水増しした `(watchdog)` の request-changes を取り下げる (`DRY=1` で確認) |
| `find_silent_runs.sh` | success で終わったのに報告を残していない実装 run を検出する (`SINCE` / `MAX`) |
| `find_unreviewed.sh` / `rerun_review.sh` | review が付いていない ready PR の列挙 / PR の close→reopen で review を再起動 (素材名を引数に取る) |
| `restart_failed.sh` | 失敗した run の再投入 (`impl` / `review` / `both`、`SINCE`) |
| `systemd/` | user unit の例。`/PATH/TO/REPO` を置換して `~/.config/systemd/user/` に置く |

## VM 退役後の扱い

`git ls-files tools/pm` の全ファイル。退役は [#2355](https://github.com/signature-studio/signature-studio-dev/issues/2355) の手順に従い、
『退役前に必要な作業』が済んだ行から削除する (削除は別コミットで行う。本表の作成では削除しない)。
systemd の停止・変更は PM が行い、この README には含まれない。

| ファイル | 後継 | 廃止の根拠 | 退役前に必要な作業 | 担当 issue |
|---|---|---|---|---|
| `.gitignore` | 残す | 状態ファイル (`launched.json` など) を追跡しないための除外。退役後も誤コミット防止に残す | なし | - |
| `README.md` | 残す | 本書 (運用ツールの地図と退役の表) | なし | #2436 |
| `REPORT.md` | 残す | 測定値の正本 | なし | - |
| `REPORT_APPENDIX_2380.md` | 残す | 測定値の付録 (REPORT §10 の全文。250 行上限のため REPORT.md から分割移動) | なし | - |
| `dismiss_spam.py` | 廃止 | 旧 watchdog が『(watchdog)』を付けて出した request-changes の取り下げ (#731) の一回限りの後始末。ただし現行の `watchdog.sh` の FIX_IDLE も本文の末尾に同じ `(watchdog)` を付けて reviewer の token で出すため、このスクリプトは現行の FIX_IDLE も取り下げ対象にする | 退役前に、FIX_IDLE の本文から marker を外す (または判定を変える) 変更を main に入れてから、`DRY=1` で対象 0 件を確認して削除する。それまで watchdog の稼働中には実行しない | #2355 |
| `find_silent_runs.sh` | 廃止 (後継: `record-run-outcome.sh`。App token が発行された run でだけ動く。token が無ければ何もしない (`.github/workflows/opencode.yaml` の `Record the run outcome` step)) | implement の run の末尾 (`if: always()`) で `record-run-outcome.sh` が、PR も push も無い終了 (success を含む) に `oc:no-pr` と理由マーカーを残す。報告の無い success は、この経路で `oc:no-pr` として見える | 削除のみ | #2355 |
| `find_unreviewed.sh` | `watchdog.sh` | verdict の無い現在 head の PR (NOREVIEW) を `watchdog.sh` が点検ごとに戻す | 削除のみ | #2355 |
| `heartbeat.sh` | 残す (監査専用。指示 145) | 着手・点検の役は Worker・`pm` job (`oc-pm`) が担う。2 時間ごとの監査の依頼だけを `PM_HEARTBEAT_MSG_FILE` の文面で送るため、2026-10-15 に再開した。内蔵の 30 分版の文面は使わない。必要なときだけ起こす補助は `pm_wake.sh` (#2347) | なし (停止は `disable --now`) | #2347・#2607 |
| `heartbeat_msg_audit.txt` | 残す (監査専用。指示 145) | `heartbeat.sh` が `PM_HEARTBEAT_MSG_FILE` で読む監査専用の文面 (着手・watchdog・merge・ラベル操作を含まない) | なし | #2607 |
| `idle_report.sh` | 残す | REST のみで VM に依存しない。watchdog の担当なし時間の計測として残す (VM 停止の判定用の役は終わった) | なし | #2354 |
| `issue_snapshot.py` | 廃止 | open issue の集計は Worker の同期 (`fullSync`・`reconcile`) が担う。`launch_issues.py` だけが読んでいた | `launch_issues.py` と同時に削除。状態の扱いは下の『状態ファイル』の節 | #2355 |
| `launch_issues.py` | Worker | `plan`・`launch` は Worker が live (`/oc` の投稿と着手の判断)。`blocked` (GitHub の依存欄への同期) は Worker が書かないため、退役後は依存欄が新規分で更新されない。判定は本文の `blockedBy:` を Worker の `classify.ts` が読むので、影響は表示のみ | 『状態ファイル』の節の扱いを反映してから削除。`classify_crosscheck.py`・`phase_crosscheck.py` (`infra/pm-worker/test/`) が `launch_issues.py` を importlib で読み、`classify.test.ts`・`phase.test.ts` がそれを `python3` で呼ぶため、先に crosscheck の Python 依存を fixture 固定に置き換える。依存欄の同期が要るなら別 issue | #2355 |
| `manual_deps.json` | 残す (Worker が import) | 停止報告に根拠のある依存。Worker のビルドが `infra/pm-worker/src/config.ts` の 1 行目で読むため、移すとビルドが壊れる | パスを変えない | - |
| `pm_gate.sh` | 廃止 | Worker が live の間に VM の launch・ping を止める standby ゲート。VM の timer を再開しないので不要 (#2341 は closed) | 削除のみ | #2355 |
| `pm_wake.sh` | 残す | PM セッションを必要なときだけ起こす VM 側の経路 (`heartbeat.sh` の置換。#2347)。timer の有効化は PM が判断する | なし (有効化の判断は PM) | #2347 |
| `pm_needs.py` | Worker | 差し戻しが PM 判断を求めて未回答の PR の検出は、Worker の `needs.ts` (同じ語彙 `NEEDS_KEY`) が担う。ただし `infra/pm-worker/test/needs_crosscheck.py` が `pm_needs.py` の `KEY` を importlib で読み、`needs.test.ts` がそれを `python3` で呼ぶため、ファイルを消すとこのテストが落ちる | crosscheck の Python 依存を fixture 固定に置き換えてから削除 (`needs_crosscheck.py` が `pm_needs.py` を読まない形にする) | - |
| `pm_watchdog_ping.sh` | Worker | `oc-watchdog` の 5 分送信は Worker の `LIVE_DISPATCH` が担う (2026-10-14 から live) | 削除のみ。timer は停止済み | #2355 |
| `pr_gaps.py` | `watchdog.sh` | 『レビュー中・修正中・担当なし』の分類は `watchdog.sh` が点検ごとに出す (`open=… covered=… idle=…`) | 削除のみ | - |
| `rerun_review.sh` | `watchdog.sh` | review の再起動 (close→reopen) は、`watchdog.sh` の NOREVIEW が `reopen-pr.sh` で行う | 削除のみ | #2355 |
| `rest_heal.py` | `watchdog.sh` | 冒頭に『watchdog.sh が main に入るまでの橋渡し』と書かれた役。`watchdog.sh` が同じ分類で戻す | 削除のみ | #2355 |
| `restart_failed.sh` | 実装 run: Worker (`oc:no-pr` の再着手)。review 側: `watchdog.sh` (NOREVIEW → `reopen-pr.sh`) | 失敗した実装 run の再投入は、`oc:no-pr` の再着手 (`NO_PR_COOLDOWN_H`) に置き換わる。即時の再投入は無くなり、再着手は cooldown の後になる。review 側は watchdog の点検 (NOREVIEW) で戻るため、即時の再起動は無くなる。レート制限の判定は #2344 | 遅れを許容する判断を PR 本文に書いてから削除。理由別の再着手は #2334 | #2334・#2344 |
| `status_sync.py` | 未実装 (#2362) | `docs/STATUS.md` の自動節を更新する後継の workflow が未配線 (pm-apply) | 後継が main に入るまで残す。入らない間は STATUS の自動節が古いままになる | #2362 |
| `sync_status.py` | 廃止 | Project V2 の Status 同期を退役と同時にやめる (PM 判断 2026-10-14)。根拠は #2356 (PM App に Projects の書き込み権限を追加するかの依頼者への質問。既定は『追加しない』で not_planned で閉じた)。このため App の token では Project V2 の Status を更新できず、Status は参考扱い | 済 (#2435) | #2435 |
| `systemd/pm-heartbeat.service` | 残す (監査専用。指示 145) | 2026-10-15 に `enable --now`。間隔と文面は env で指定する (例の unit に記載) | なし (systemd の変更は PM が行う) | #2607 |
| `systemd/pm-launch.service` | Worker | `/oc` の投稿は Worker (`LIVE_LAUNCH`)。timer は 2026-10-14 に停止し、再開しない | 停止済み。ファイルの削除は退役の最後 | #2355 |
| `systemd/pm-launch.timer` | Worker | 同上 | 停止済み | #2355 |
| `systemd/pm-wake.service` | 例 (有効化は PM) | `pm_wake.sh` の unit の例。`/PATH/TO/...` を置換して使う。VM の timer は停止したまま | なし | #2347 |
| `systemd/pm-wake.timer` | 例 (有効化は PM) | 同上 (10 分ごと) | なし | #2347 |
| `systemd/pm-watchdog.service` | Worker | `oc-watchdog` の送信は Worker (`LIVE_DISPATCH`) | 停止済み | #2355 |
| `systemd/pm-watchdog.timer` | Worker | 同上 | 停止済み | #2355 |
| `test_idle_report.sh` | 残す | `idle_report.sh` と同じ | なし | #2354 |
| `test_launch_issues.py` | 廃止 | `launch_issues.py` と同時。Worker の規則は `infra/pm-worker/test/` (vitest と `*_crosscheck.py`) で確かめる。ただし `*_crosscheck.py` は `launch_issues.py` を importlib で読むので、この依存を fixture 固定に置き換えてから削除する | `launch_issues.py` と同時に削除 (crosscheck の依存の置き換えが先) | #2355 |
| `test_pm_gate.sh` | 廃止 | `pm_gate.sh` と同時 | 同上 | #2355 |
| `test_pm_wake.sh` | 残す | `pm_wake.sh` の判定テスト (fake curl・fake opencode。CI の scripts-test が拾う) | なし | #2347 |
| `test_status_sync.py` | 未実装 (#2362) | `status_sync.py` の検証。後継の workflow が入るまで残す | `status_sync.py` と同時に削除 (後継 #2362 が main に入るまで残す) | #2362 |
| `watch_runs.notes.md` | 廃止 | `watch_runs.sh` の注記。測定値は `REPORT.md` §8 に移送済み | `watch_runs.sh` と同時に削除 | #2355 |
| `watch_runs.sh` | Worker・`watchdog.sh` | PM が run の完了を待つための監視。完了は Worker が `workflow_run` の webhook で受け、点検は `watchdog.sh` が行う。PM は oc-pm で起動されるので待つ必要が無い | 削除のみ | #2355 |
| `worker_url` | 残す | `watchdog.sh` が Worker の `/status` を読む先。VM に依存しない | なし | - |

## Worker 稼働中の standby (`pm_gate.sh`)

> 旧手順 (2026-10-14 の切替より前)。VM の timer は再開しないため、今は使わない。`pm_gate.sh` は上の表で廃止。

Worker が primary になった後も、VM の timer は止めず standby にする (Worker が止まったときの自動フェイルオーバー)。
`pm_gate.sh` で `ExecStart` を包むと、Worker が健全な間は VM 側の command を実行せず二重投稿を避けられる。
ゲートは `curl` で `/status` を 1 回読むだけで、`gh` や GitHub REST は使わない。

例 (`~/.config/systemd/user/pm-launch.service` の `ExecStart`。`pm-watchdog.service` も同じ形):

```
ExecStart=/bin/bash /PATH/TO/REPO/tools/pm/pm_gate.sh /usr/bin/env python3 /PATH/TO/REPO/tools/pm/launch_issues.py launch
```

戻し方: `ExecStart` を gate なしの元の行に戻し、`systemctl --user daemon-reload` を実行する。
systemd の変更自体は PM が行う (この README には含まれない)。

## heartbeat からの置換 (`pm_wake.sh`)

`heartbeat.sh` は、内蔵の文面 (30 分版) では PM セッションを無条件で起こす (運用は監査専用の 2 時間ごと。上の注)。`pm_wake.sh` は、PM のセッションでしか進まないものがあるときだけ起こす (#2347、親 #2319)。
systemd timer から 10 分ごとに 1 回ずつ呼ぶ。`/status` (公開・集計のみ) を `curl` で 1 回読み、次の kind のどれかのときだけ固定文を `opencode api post` で送る。

| kind | 条件 | 送る文面 |
|---|---|---|
| `needs_pm` | `needs_pm > 0` | needs-pm の issue / PR を処理する |
| `worker_stale` | `fresh=false` が 30 分続く (経過は状態ファイルに持つ) | Worker の同期状態を確認する |
| `stuck_old` | `stuck_age_max_min > 360` (PM agent が機能していない) | oc:stuck の PR を処理する |

- 上限: 送信の間隔は 3 時間以上、24 時間に 6 回まで。失敗した試行も数える。
- 文面は kind ごとの固定文だけ。`/status` の値 (件数・時刻・題名) は入れない。
- 記録 (`pm_wake.log`、1 行ずつ): `result=sent` / `skip` (上限) / `none` (条件なし) / `status-failed` / `send-failed` / `no-session`。

置換の手順 (有効化は PM が行う。systemd の変更は、この README には含まれない):

1. PM セッション ID を 1 行でファイルに書く (例: `~/.config/pm-wake/session_id`)。
2. 1 回だけ手で動かして記録を確かめる: `PM_SESSION_ID_FILE=~/.config/pm-wake/session_id bash tools/pm/pm_wake.sh; echo $?` のあと、`tools/pm/pm_wake.log` の最後の行を読む。
3. `systemd/pm-wake.service` と `systemd/pm-wake.timer` の `/PATH/TO/...` を置換し、`~/.config/systemd/user/` に置く。`systemctl --user daemon-reload` の後に `systemctl --user enable --now pm-wake.timer`。
4. `pm-heartbeat.service` は、内蔵の 30 分版の文面では無効化したままにする (監査専用の文面・7200 秒での稼働は指示 145。上の注)。

戻し方: `systemctl --user disable --now pm-wake.timer`。heartbeat に戻すなら `systemctl --user enable --now pm-heartbeat.service` (`heartbeat.sh` の既定の文面・間隔は変えていない)。

## watchdog の担当なし時間を集計する (`idle_report.sh`)

`.github/scripts/watchdog.sh` は点検のたびに `open=N covered(REVIEWING/FIXING)=N idle=N ...` を出力する。
`idle_report.sh` はこの行を watchdog の run のジョブログから読み、時系列にして **idle>0 が 15 分以上続いた回数**を数える。
新しい計測コードは要らない。REST のみで GraphQL を使わない。`gh` の認証 (`actions:read`) が要る。

```
bash tools/pm/idle_report.sh --since 2026-10-14T00:00:00Z --until 2026-10-14T12:00:00Z --cache "$PM_DIR/idle_cache.jsonl" > idle.json
```

- 出力: 標準出力に JSON (`streaks_ge_threshold` が回数、`by_bucket` が日ごと、`streaks` が全区間、`samples`・`runs` が標本の質)、
  標準エラーに人間向けの要約 (`--quiet` で省く)。
- オプション: `--repo OWNER/REPO` (省略時は env `OC_REPO`、無ければ git の origin)、`--threshold-min 15`、
  `--events repository_dispatch,schedule,push` (既定は 3 つ全部)、`--bucket day|hour`、`--cache FILE`。
- 数え方: 標本は watchdog の 1 回の点検 (run の watchdog job のログの最後の `idle=` 行と、その行の時刻)。
  idle>0 の標本が途切れず続く間を 1 つの区間とし、その最初と最後の標本の時刻の差が閾値 (15 分) 以上なら 1 回と数える (ちょうども数える)。
  idle=0 の標本を挟むと別の区間になる。標本の欠落 (間隔が 15 分超) は区間を切らず、`samples.gaps_over_threshold` に数える。
  0 回を『問題なし』と読む前に、`samples.count` と `gaps_over_threshold` を見る (標本が 0 件なら要約に警告を出す)。
- 誤差は両方向で、計測値は下限とも上限とも言えない:
  - 両端: 区間の直前 (idle=0 の標本の後) と直後 (idle=0 の標本の前) で idle>0 が始まっていた・続いていた可能性があり、実際の担当なし時間は計測値より長いことがある (過小)。
  - 標本の間: 2 つの idle>0 の標本の間で idle=0 に戻っていても見えず、1 区間に合算される (過大)。欠落 (間隔が 15 分超) をまたぐ区間は中の状態が不明なので、この誤差が大きくなりうる。
  - よって 0 回を『問題なし』の根拠にしない。`samples.longest_gap_min` と `gaps_over_threshold` を併せて見る。
- 期間は run の作成時刻 (`created_at`) で切る。標本の時刻 (watchdog の idle 行の時刻) は run の作成より後ろになり、`--until` を数分越えて出うる。
- **oc:stuck の PR は idle に入り続ける**: watchdog は `oc:stuck` の PR を触らず、カバー済みにもしない。
  stuck が 1 件でも残る間は idle>0 が続き、回数は soak 判定の指標にならない。同じログの `#N STUCK_LABELLED:` の行数を引いた
  idle での回数を `excluding_stuck_labelled` に出す (人の判断待ちを除いた担当なし)。soak 判定は後者で見る。
- 対象にする run: `repository_dispatch` は表題が `watchdog` のもの (`oc-fix #N` は除く)、`schedule`・`push` は全て
  (main への merge のたびに watchdog が走る)。完了していない run、watchdog job が skipped の run、ログが読めない run は
  標本にせず、`runs.skipped` に理由別で数える。
- 取得量と上限: `actions/workflows/opencode.yaml/runs?event=<E>&created=<A>..<B>` を event ごと・6 時間の窓ごとに全ページ取得する
  (created 付きの検索は 1 検索 1,000 件が上限。窓の `total_count` が 1,000 を超えたら終了コード 4 で中断する。env
  `IDLE_REPORT_WINDOW_HOURS` で窓を狭める)。run 1 件につき jobs とログの 2 回呼ぶ。push の run は merge のたびに増えるので、
  長い期間は `--events repository_dispatch,schedule` に絞るか `--cache` を使う。
- レート制限: 応答ごとに `X-Ratelimit-Remaining` を見て、1,500 (env `IDLE_REPORT_MIN_REMAINING`) 未満なら理由を標準エラーに出して
  終了コード 3 で中断する (結果の JSON は出さない)。ログ本文は blob へのリダイレクト先から返りヘッダが無いので、直前の jobs 応答の値で見る。
- `--cache FILE`: 完了した run の読み取り結果 (JSONL) を run ごとに追記し、次回は jobs・ログを取りに行かない。中断しても続きから再開できる。
- 終了コード: 0 正常 / 2 引数不正 / 3 残量不足で中断 / 4 API 失敗・1 窓の run が多すぎる。
- 検証: `bash tools/pm/test_idle_report.sh` (fake gh。idle=0 が続く・14 分 (ネガコン)・16 分・idle=0 を挟む・残量 1,499 の中断ほか)。結果は [`REPORT.md`](REPORT.md) §11。

## 状態ファイル (`PM_DIR` に作られる。コミットしない)

`issues_state.json` (snapshot) / `phase.json` (LAUNCH か Review-Only) / `launched.json` (3 時間の重複防止) /
`relaunch.json` (素材を足した再投入の履歴、最大 2 回) / `stop_deps_candidates.json`・`wave2_cat.json` (書き手は無い) / `*.log`。

**VM 退役時の扱い: 下表の状態ファイルは Worker に取り込まず、破棄する** (取り込み口 `/admin/import` は [#2343](https://github.com/signature-studio/signature-studio-dev/issues/2343) で未実装)。
件数と内訳は [`REPORT.md`](REPORT.md) §12 が正本。

| 状態 | 後継 | 扱い | 影響 |
|---|---|---|---|
| `launched.json` | Worker の `launchedAt`。`PM_LOGINS` (PM 名義) の `/oc` コメントから再構成する (同期窓 24 時間、#2380) | 破棄 | 切替 (VM の timer 停止) 以後は書き込まれない。Worker は同じ情報を GitHub から読むので、窓内の二重化は起きない。**VM を戻すときは空から始まる**ため、戻す前に Worker を dry-run にする (両方が live だと二重投稿になる) |
| `relaunch.json` | Worker の DO `relaunch` (切替後の再投入だけを記録) | 破棄 (取り込みは #2343) | 履歴の無い issue は、直近 24 時間に停止報告が来た場合に限り、最大 2 回余分に再投入され得る (同じ素材行を含む) |
| `phase.json` | Worker の DO `meta/phase` (`phase.ts`。open PR (stuck を除く) が 80 を超えたら Review-Only、10 未満で解除、間は直前の値) | 破棄。切替時に VM の値 (`review_only=false`) を一度だけ保存済み (REPORT §12-5) | 保存が無い状態 (新しいデプロイ先・DO の再作成) は Review-Only で始まり、open PR が 10 以上の間は新規着手しない (安全側の停滞) |
| `issues_state.json` | Worker の DO (`issues`・`pmArt`・`botLast`)。snapshot は持たない | 破棄 | PM の `oc_artifacts:` 行は、同期窓 (24 時間) より古いコメントからは新たに読まれない。DO に取り込み済みの古い行が残るかは未確認。必要な issue は PM が行を書き直す (#2343) |
| `*.log`・`*.log.err`・`*.log.tmp` | - | 退役時に破棄 | 判断の根拠は issue コメントと `REPORT.md` に残る |
| `stop_deps_candidates.json`・`wave2_cat.json` | - | 破棄 | 実行時の状態。`tools/pm/.gitignore` の 2 行にだけ残り、リポジトリに書き手も読み手も無い。Worker は参照しないので影響なし |

## 運用の約束

- **Cloudflare のリソース (worker・token) は新規に作らない**。R2 への投入は既存 token の一時昇格だけで行い、
  終わったら必ず Read のみへ戻す (手順は `docs/WORKFLOW.md` §11)。
- `git add -A` / `git add .`、破壊的な git 操作、`pkill -f` (自分のシェルを殺す) は使わない。
- 10 秒以上の待機は使わず、`timeout N tail -f /dev/null` で行う。10 秒未満の再試行間隔 (2〜4 秒・0.4〜1.5 秒) の `time.sleep` だけは許容する。
- 新規着手は、Opened PR が 10 件を下回れば開始、80 件を超えれば Review-Only (指示 130)。
- 判断の根拠は issue / PR のコメントに残す (PM が決めたことを agent に伝える唯一の経路)。

## 廃止

- `sweep_prs.sh` (GraphQL 版の PR 仕分けと依頼): 後継は `.github/scripts/watchdog.sh` と `rest_heal.py`。
  GraphQL の枠を使い切る原因になったので使わない。
- `preflight.sh`: subagent 時代の読了証跡。廃止 (`docs/DECISIONS.md` D6)。
