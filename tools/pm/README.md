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
| `pm_gate.sh` | `pm_gate.sh <command...>`。Worker (`infra/pm-worker`) が primary (`/status` が `mode=live`・`fresh=true`・`last_tick` が 15 分以内) の間は command を実行せず終了 0 にする。それ以外 (取得失敗・dry-run・JSON 不正) は command を実行する (fail-open)。URL は env `PM_WORKER_URL`、無ければ `tools/pm/worker_url`。テスト: `bash tools/pm/test_pm_gate.sh` |
| `launch_issues.py` | 指示 130〜132 の自動着手。`plan` (仕分け) / `blocked` (blocked_by を GitHub に同期) / `launch` (`/oc` コメントで着手)。`systemd/pm-launch.*` が 10 分おきに `launch` を実行。Opened PR 数は `oc:stuck` の PR を除き、stuck が `STUCK_HIGH` (既定 40) を超えたら launch を止める。停止報告の判定は run-outcome・PM マーカー付きコメントを除く (#2325)。テスト: `python3 -m unittest tools/pm/test_launch_issues.py` |
| `../../infra/pm-worker/` | `launch_issues.py` の launch と `pm_watchdog_ping.sh` の代替 (Cloudflare Worker。webhook + Cron/alarm 駆動)。現在は dry-run のみで、`pm-launch.timer` / `pm-watchdog.timer` は引き続きこちらが正本。切替手順は `infra/pm-worker/README.md` |
| `issue_snapshot.py` | open の issue / PR / run / 最新の bot コメントを `issues_state.json` に保存する (`launch_issues.py` が呼ぶ) |
| `manual_deps.json` | 停止報告に根拠のある依存 (子 → [依存先])。**追跡する設定ファイル** (他の json は状態で、`.gitignore`) |
| `rest_heal.py` | open PR を CONFLICT / FIX / NOREVIEW / DRAFT / APPROVED / COVERED / STUCK_LABELLED に分類し、足りない次の一手を `/oc` コメントか close→reopen で補う。watchdog (`.github/scripts/watchdog.sh`) の補助 |
| `sync_status.py` | Project V2 の Status を PR / Issue の実態に同期する (冪等)。実行しないと Status が陳腐化する |
| `pm_needs.py` | 最新の差し戻しが PM 判断を求めていて、PM の応答が無い PR を列挙する。heartbeat のたびに実行して未回答を 0 にする |
| `idle_report.sh` | watchdog の run 履歴から『idle>0 が 15 分以上続いた回数』を数える (VM の `pm-watchdog.timer` を止めてよいかの soak 判定用)。REST のみ。`idle_report.sh --since <ISO> --until <ISO>`。使い方は下の節。テスト: `bash tools/pm/test_idle_report.sh` |
| `pr_gaps.py` | open PR を「レビュー中 / 修正中 / 担当なし」に分類する |
| `dismiss_spam.py` | watchdog が水増しした `(watchdog)` の request-changes を取り下げる (`DRY=1` で確認) |
| `find_silent_runs.sh` | success で終わったのに報告を残していない実装 run を検出する (`SINCE` / `MAX`) |
| `find_unreviewed.sh` / `rerun_review.sh` | review が付いていない ready PR の列挙 / PR の close→reopen で review を再起動 (素材名を引数に取る) |
| `restart_failed.sh` | 失敗した run の再投入 (`impl` / `review` / `both`、`SINCE`) |
| `systemd/` | user unit の例。`/PATH/TO/REPO` を置換して `~/.config/systemd/user/` に置く |

## Worker 稼働中の standby (`pm_gate.sh`)

Worker が primary になった後も、VM の timer は止めず standby にする (Worker が止まったときの自動フェイルオーバー)。
`pm_gate.sh` で `ExecStart` を包むと、Worker が健全な間は VM 側の command を実行せず二重投稿を避けられる。
ゲートは `curl` で `/status` を 1 回読むだけで、`gh` や GitHub REST は使わない。

例 (`~/.config/systemd/user/pm-launch.service` の `ExecStart`。`pm-watchdog.service` も同じ形):

```
ExecStart=/bin/bash /PATH/TO/REPO/tools/pm/pm_gate.sh /usr/bin/env python3 /PATH/TO/REPO/tools/pm/launch_issues.py launch
```

戻し方: `ExecStart` を gate なしの元の行に戻し、`systemctl --user daemon-reload` を実行する。
systemd の変更自体は PM が行う (この README には含まれない)。

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
  idle>0 の標本が途切れず続く間を 1 つの区間とし、最初と最後の標本の間隔が閾値 (15 分) 以上なら 1 回と数える。
  15 分ちょうども数える (標本の間隔が粗く、実際の担当なし時間は計測値以上のため)。idle=0 の標本を挟むと別の区間になる。
  標本の欠落 (間隔が 15 分超) は区間を切らず、`samples.gaps_over_threshold` に数える。0 回を『問題なし』と読む前に、
  `samples.count` と `gaps_over_threshold` を見る (標本が 0 件なら要約に警告を出す)。
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
- 検証: `bash tools/pm/test_idle_report.sh` (fake gh。idle=0 が続く・14 分 (ネガコン)・16 分・idle=0 を挟む・残量 1,499 の中断ほか)。結果は [`REPORT.md`](REPORT.md) §10。

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
