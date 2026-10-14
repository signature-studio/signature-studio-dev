# tools/pm — PM 運用ツール (VM 上で PM が実行する)

PM が VM 上で実行・常駐させる、PR / Issue / Actions run の運用ツール。**Actions では実行しない**
(`gh` の認証と systemd timer に依存するため)。実装 agent は使わない。数値の正本は
[`REPORT.md`](REPORT.md)、運用規約の正本は `docs/WORKFLOW.md` §11。

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
| `DRY=1` | 無し | 計画の表示だけ (rest_heal / sync_status / launch / blocked) |
| `ONLY=<番号,…>` / `MAX` / `AGAIN` | 無し | 対象の絞り込み / 1 回の件数 / 同じ PR への再依頼間隔 (分) |
| `TARGET` / `BATCH` | 50 / 25 | `launch_issues.py launch` の同時稼働の目標 / 1 回の投入数 |

## ツール

| ファイル | 用途 |
|---|---|
| `watch_runs.sh` | 実行中の Actions run を REST で監視し、1 本終わるたびに 1 行出して終了する。**終了通知を受けたら、結果の処理より先に再起動する** (指示 116)。詳細は [`watch_runs.notes.md`](watch_runs.notes.md) |
| `heartbeat.sh` | 30 分ごとに PM のセッションへ作業継続のプロンプトを送る (指示 102・116・120)。`systemd/pm-heartbeat.service` |
| `pm_watchdog_ping.sh` | 5 分ごとに `repository_dispatch` (`oc-watchdog`) を送り、Actions の watchdog を起こす (GitHub の schedule が発火しないため)。`systemd/pm-watchdog.*` |
| `launch_issues.py` | 指示 130〜132 の自動着手。`plan` (仕分け) / `blocked` (blocked_by を GitHub に同期) / `launch` (`/oc` コメントで着手)。`systemd/pm-launch.*` が 10 分おきに `launch` を実行 |
| `../../infra/pm-worker/` | `launch_issues.py` の launch と `pm_watchdog_ping.sh` の代替 (Cloudflare Worker。webhook + Cron/alarm 駆動)。現在は dry-run のみで、`pm-launch.timer` / `pm-watchdog.timer` は引き続きこちらが正本。切替手順は `infra/pm-worker/README.md` |
| `issue_snapshot.py` | open の issue / PR / run / 最新の bot コメントを `issues_state.json` に保存する (`launch_issues.py` が呼ぶ) |
| `manual_deps.json` | 停止報告に根拠のある依存 (子 → [依存先])。**追跡する設定ファイル** (他の json は状態で、`.gitignore`) |
| `rest_heal.py` | open PR を CONFLICT / FIX / NOREVIEW / DRAFT / APPROVED / COVERED / STUCK_LABELLED に分類し、足りない次の一手を `/oc` コメントか close→reopen で補う。watchdog (`.github/scripts/watchdog.sh`) の補助 |
| `sync_status.py` | Project V2 の Status を PR / Issue の実態に同期する (冪等)。実行しないと Status が陳腐化する |
| `pm_needs.py` | 最新の差し戻しが PM 判断を求めていて、PM の応答が無い PR を列挙する。heartbeat のたびに実行して未回答を 0 にする |
| `pr_gaps.py` | open PR を「レビュー中 / 修正中 / 担当なし」に分類する |
| `dismiss_spam.py` | watchdog が水増しした `(watchdog)` の request-changes を取り下げる (`DRY=1` で確認) |
| `find_silent_runs.sh` | success で終わったのに報告を残していない実装 run を検出する (`SINCE` / `MAX`) |
| `find_unreviewed.sh` / `rerun_review.sh` | review が付いていない ready PR の列挙 / PR の close→reopen で review を再起動 (素材名を引数に取る) |
| `restart_failed.sh` | 失敗した run の再投入 (`impl` / `review` / `both`、`SINCE`) |
| `systemd/` | user unit の例。`/PATH/TO/REPO` を置換して `~/.config/systemd/user/` に置く |

## 状態ファイル (`PM_DIR` に作られる。コミットしない)

`issues_state.json` (snapshot) / `phase.json` (LAUNCH か Review-Only) / `launched.json` (3 時間の重複防止) /
`relaunch.json` (素材を足した再投入の履歴、最大 2 回) / `*.log`。

## 運用の約束

- **Cloudflare のリソース (worker・token) は新規に作らない**。R2 への投入は既存 token の一時昇格だけで行い、
  終わったら必ず Read のみへ戻す (手順は `watch_runs.notes.md`)。
- `git add -A` / `git add .`、破壊的な git 操作、`pkill -f` (自分のシェルを殺す) は使わない。
- 10 秒以上の待機は使わず、`timeout N tail -f /dev/null` で行う。10 秒未満の再試行間隔 (2〜4 秒・0.4〜1.5 秒) の `time.sleep` だけは許容する。
- 新規着手は、Opened PR が 10 件を下回れば開始、80 件を超えれば Review-Only (指示 130)。
- 判断の根拠は issue / PR のコメントに残す (PM が決めたことを agent に伝える唯一の経路)。

## 廃止

- `sweep_prs.sh` (GraphQL 版の PR 仕分けと依頼): 後継は `.github/scripts/watchdog.sh` と `rest_heal.py`。
  GraphQL の枠を使い切る原因になったので使わない。
- `preflight.sh`: subagent 時代の読了証跡。廃止 (`docs/DECISIONS.md` D6)。
