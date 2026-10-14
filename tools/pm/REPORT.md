# tools/pm — PM 運用の実測 (GitHub Actions 移行後)

PM 運用の数値 (PR 件数・PR とチケットの対応・Project V2 Status・Actions run 集計) の**正本**。
`docs/pm/RETRO_2026-10-13.md` と `docs/pm/DIRECTIVES.md` の数値はここを指す。

- 数値はすべて **基準時刻 (UTC)** と **取得方法** を併記する。
- 「PM 記録」は、取得時刻・取得コマンドを保存していない値。再計測できないので、その旨を明記して残す。
  再計測して得た値 (取得時刻付き) と混ぜない。

## 0. 取得方法

- PR 一覧: `gh pr list --state all --limit 1000 --json number,state,isDraft,createdAt,mergedAt,closedAt,headRefName,body`
- 時点 t の状態 (再構成): `createdAt ≤ t` の PR のうち、`mergedAt ≤ t` なら MERGED、
  未 merge で `closedAt ≤ t` なら CLOSED、それ以外は OPEN。
- `isDraft` は取得時点の値しか得られない (履歴は一覧で取れない)。draft/ready の内訳は取得時刻付きでのみ記録する。
- チケット対応: `headRefName` の先頭 `<N>-` を一次キーとする (`docs/WORKFLOW.md` §9 の命名規則)。
  数字で始まらない branch は「非チケット」とする。`body` の `Closes #N` は使わない
  (1 PR が複数 issue を参照することがあり、件数が二重になるため)。

## 1. PR 件数 (時点別)

| 基準時刻 (UTC) | 取得方法 | 全 PR | merged | open | closed |
|---|---|---:|---:|---:|---:|
| 2026-10-13 09:20Z | 再構成 (createdAt・mergedAt・closedAt) | 262 | 182 | 77 | 3 |
| 2026-10-13 11:03Z | 実測 (`gh pr list`) | 266 | 192 | 71 | 3 |

09:20Z → 11:03Z の差分:
- 新規 PR 4 件: #720・#721・#723・#724 (#721 は merge 済み)。
- 09:20Z に open だった 77 件のうち 9 件が merge された。
- 77 − 9 + 3 (新規の open: #720・#723・#724) = 71。

## 2. PR とチケットの対応

### 2-1. 09:20Z (再構成)

- 全 PR 262 = チケット紐付き 256 + 非チケット 6。
- 非チケット 6 件: #1 (`feat/add-opencode`, merged)・#280 (`docs/restructure-2026-10`, merged)・
  #282 (`feat/add-opencode`, merged)・#283 (`docs/predecessor-analysis`, merged)・
  #279 (`sync/origin-reconcile-2026-10-12`, closed)・#289 (`feat/opencode-enhance-01`, merged)。
- チケット紐付き 256 件 = **249 チケット** (1 本 242 件・2 本 7 件・3 本以上 0 件)。
- 2 本のチケット: #76 (open 1・merged 1)・#181 (open 1・merged 1)・#284 (merged 2)・#417 (merged 1・closed 1)・
  #507 (merged 2)・#513 (merged 2)・#593 (merged 2)。
- open 77 PR は **77 チケットに 1 対 1**。同一チケットに open PR が 2 本以上ある例は 0 件。

旧版 RETRO の「PR を持つチケット 250 件 (1 本 243・2 本 6・3 本 1)」は取得方法を残していない値で、
上記の方法では再現できなかった (PR 258 件となり全 PR 262 件と合わない)。上記に置き換える。

### 2-2. 11:03Z (実測)

- 全 PR 266 = チケット紐付き 260 + 非チケット 6 (2-1 と同じ 6 件)。
- チケット紐付き 260 件 = **252 チケット** (1 本 244 件・2 本 8 件)。2 本は 2-1 の 7 件に #719 (#721 merged・#724 open) が加わる。
- open 71 PR は **71 チケットに 1 対 1**。

## 3. 11:03Z の open PR

- open 71 件: **ready 71・draft 0** (`gh pr list` の `isDraft` 実測)。
- 代表例: #723 (RETRO・指示 121〜123 の記録。`722-retro-directives`)、#724 (watchdog。`719-watchdog`、10:42:29Z 作成)。

## 4. 09:20Z の open PR の分類 (PM 記録)

取得時刻・分類の基準は保存していない。PM の手動分類による PM 記録として残す。

- open 77 件の分類: レビュー中 16 / 修正中 5 / **どちらでもない 56 (73%)**。
- open 77 件の内訳: draft 12 + ready 65 (PM 記録。draft の履歴は再構成できない)。
- stacked PR (base が未 merge の別 PR): #676・#708 の 2 本 (PM 記録)。
- watchdog の DRY 実行 (PR-B の検出ロジック): 77 件中 71 件が対象 (PM 記録)。

## 5. Project V2 Status (PM 記録・未再計測)

取得時刻は保存していない。現在値は取得していない。

- 同期前: In review 11 件はすべて open PR を持たない issue (移行残骸)。
  open ready PR 65 件のチケットの Status は Backlog 36・In progress 23・Ready 6・In review 0。
- 同期後: Done 187・Ready 63・Backlog 131・In review 76。同期時点の open ready PR 76 と一致させた (PM 記録)。
- 反映: `sync_status.py` で 62 遷移 (PM 記録)。自動化は未実施。

## 6. Actions run・障害 (PM 記録・未再計測)

取得時刻と取得コマンドは保存していない。

- 2026-10-12〜13 の共倒れ: 実装 run 12 件・review run 10 件が失敗。原因はレート制限 (`rate_limit_error ... cooling down`)。
  依頼者が `OC_MODEL_ID` を OpenRouter 経由に変更し、変更直後の確認で新規失敗は止まった (PM 記録)。
- bot 起点の run 48 件のうち skipped 23・cancelled 19。concurrency が workflow 単位だったため (PR #436 で job 単位へ)。
- reviewer の `set +e` 未対応による 95 秒の exit 1 (PR #455 で修正)。
- PM の GraphQL 枯渇 09:37〜10:16Z (PM 操作が GraphQL を多用。REST へ切替)。

## 7. 他 area の実測の参照先

RETRO §3 の良い点の根拠。数値はこちらが正本。

- OTT: `tools/ott/REPORT.md` の scenario matrix 89 本 / 50,236 cell の native 一致。
- Serum 2 host: `tools/targets/serum2/host/REPORT.md` の e2e 23/23 OK。

## 8. 運用の計測値 (watch_runs.notes.md から移送・取得時刻は PM 記録)

- `pm_needs.py` の 1 回の実行: 約 1〜2 分 (REST のみ・PM 記録)。
- 競合 PR の fix を repository_dispatch (watchdog) で起動し、検出から push まで: 約 2.5 分 (#576, #689・PM 記録)。
- schedule(*/5) の発火: #724 の merge から 80 分時点で 0 件、2 時間時点で 0 件 (PM 記録)。
- `m11_gen_ir2.sh` の所要: 約 26 秒 (PM 記録)。

## 9. actions/runs の全ページ取得 (#889)

`actions/runs` を `per_page=100` の 1 ページだけ読むと、未完了 run が 100 件を超えたときに古い run が落ちる。
`pr_gaps.py`・`sync_status.py`・`issue_snapshot.py`・`restart_failed.sh`・`rest_heal.py` を全ページ取得に直した
(`rest_heal.py` は `gh api --paginate --slurp` で読む `runs()` ヘルパ)。

実測 (取得時刻 UTC・`gh api --paginate` の結果。`total_count` は `per_page=1` の値):

| 条件 | total_count | 全ページ取得件数 | 所要 |
|---|---:|---:|---:|
| `status=in_progress` (17:53:43Z) | 48 | 47 | 2.7 s (取得時点の実行中 run が変動) |
| `status=in_progress` (17:53:45Z 再取得) | 47 | 47 | 同上 |
| `status=in_progress` `per_page=10` (5 ページ) | - | 45 (`per_page=100` と一致) | - |
| `status=queued` | 1 | 0 | 0.8 s |
| `status=pending` | 3 | 3 | - |

- `per_page=10` (5 ページ) と `per_page=100` の比較は、取得時点の変動を含む 1 回の比較である。
  実行中 run の件数は連続した呼び出しで変動した (in_progress の total_count 43 → 44 → 43、全ページ取得の重複除去後 43 → 44 → 45)。
  そのため「ページ跨ぎで欠落が無い」とは断定せず、その時点の 1 スナップショットの一致として扱う。
- `status=completed` は GitHub API の 1000 件上限があるため、本ツールは使わない (対象は実行中の 4 状態のみ)。
- 件数が 100 件を超える状態の再現は、本 run ではできなかった (実行中 run が 50 件前後)。

## 10. PM Worker のコメント同期 (#2380)

測定した commit: `7e8df56f` (コードを変えた最後の commit。main の #2332・#2418 を取り込んだ merge)。取得時刻は UTC (2026-10-14)。コメント件数の再測定は同期の実装と独立。

コメント件数の再測定 (`GET /repos/<R>/issues/comments?sort=created&direction=desc&per_page=100` を `created_at` が窓の端に届くまで読む。本文は取らない):

| 窓 | 取得時刻 | 窓内の件数 | ページ数 | 取得方法 |
|---|---|---:|---:|---|
| 3 時間 | 12:19Z | 1,145 | 12 | 全ページ |
| 24 時間 | 12:20Z | 10,265 | 103 | 全ページ |
| 48 時間 | 12:34Z | 12,321 | 124 | 窓の端をまたぐページを二分探索 |

直近 24 時間が 48 時間の 83% を占める (件数が直近に集中して増えている)。PR は全 1,211 件 (12:17Z。`search/issues` の `total_count`)。§1 の 262 件 (2026-10-13 09:20Z) から約 27 時間で約 950 件増えたので、`state=all` の 30 ページ (3,000 件) は数日で上限に届く。

実 API で `Engine.fullSync` を 1 回 (dry-run・メモリ store・GitHub へ書き込まない。認証は実装 App の installation token)。open issue 412〜414・open PR 10〜12:

| `COMMENT_MAX_PAGES` | 所要 | REST 回数 (全体 / うちコメント) | `fresh` | `sync_truncated` |
|---:|---:|---:|---|---|
| 80 (コードの既定) | 80.7 s | 181 / 81 | false | `comments` pages=80 |
| 150 (`wrangler.toml`) | 95.5 s | 202 / 102 | true | なし |

- 既定の 80 ページでは 24 時間の窓に届かない (窓内 102〜103 ページ。窓は時間とともに動くので 1 ページ前後ずれる)。そのため `wrangler.toml` に `COMMENT_MAX_PAGES = "150"` を置いた。窓内の件数が 15,000 件を超えたら打ち切りになり、`/status` の `sync_truncated` に出る。
- 窓内 10,265 件の読み取りは、最後の 103 ページ目が窓の端をまたぐので 103 回で終わる (「窓内の件数 / 100 の切り上げ」と一致。受入条件 5 の上限は + 1)。

単体テスト (`cd infra/pm-worker && npm test`、Node 22.23、コミット済み `7e8df56f`): 97 件 PASS / 0 FAIL、11.3 s、load average 1.20 (main 側 81 + `test/sync.test.ts` 16)。
ネガコン (merge 前の `1c33bdd2` で、実装を 1 か所だけ壊して `test/sync.test.ts` が落ちるか。落ちた件数): `fresh()` が打ち切りを見ない 9 / 上限の次の 1 ページを読まない 6 / 同時刻の comment id による比較をやめる 2 / コメントを昇順で読む 6 / watchdog が `fresh()` を見ない 3。元に戻すと 16 件 PASS。
旧実装相当 (昇順・40 ページ・窓 48 時間) は 48 時間 12,000 件の fixture で古い側の 4,000 件しか読めず、2 時間前の `/oc` と最新の bot 報告が入らない (テスト (a))。

測定 commit から HEAD までのコード差分: `git diff 7e8df56f HEAD -- infra/pm-worker/src infra/pm-worker/test` は出力なし (差分 0)。

## 11. `idle_report.sh` の検証 (#2354・watchdog の担当なし時間の集計)

既知類型との関係: 該当なし (lift の欠陥ではなく PM 運用ツール)。使い方と数え方の定義は [`README.md`](README.md) の `idle_report.sh` の節。

- 測定 commit: `95b501b2` (コードを変えた最後の commit)。それ以降の `tools/pm/idle_report.sh` `tools/pm/test_idle_report.sh` の差分: `git diff 95b501b2 HEAD -- tools/pm/idle_report.sh tools/pm/test_idle_report.sh` の出力は 0 行。`f10dfd36` から `95b501b2` までの変更は説明文 (コメント・README) だけ (`git diff f10dfd36 95b501b2 -- tools/pm/idle_report.sh tools/pm/test_idle_report.sh` の非コメント行は 0 行)。
- 環境: runner (4 コア)。load average は各測定の直後の `/proc/loadavg` の 1 分値。

### 11-1. fake gh のテスト (`bash tools/pm/test_idle_report.sh`)

| 項目 | 結果 |
|---|---|
| 判定数 | 41 件中 41 PASS・0 FAIL (3 回とも同じ) |
| 所要 (n=3、95b501b2) | 7.3〜7.6 秒 (load 0.24〜0.28) |
| (a) idle=0 が 10 標本 | 0 回 |
| (b) idle>0 が 14 分 (ネガコン) | 0 回 (区間 14 分)。`--threshold-min 14` なら 1 回 |
| (b2) idle>0 がちょうど 15 分 | 1 回 (境界は数える) |
| (c) idle>0 が 16 分 | 1 回 (区間 16 分・標本 9 件・最大 idle=3) |
| (d) idle=0 を挟む | 16 分 + 0 + 16 分 → 2 回。10 分 + 0 + 10 分 → 0 回 (区間 2 つ、合算しない) |
| (e) `X-Ratelimit-Remaining` | 1,499 → 終了コード 3・標準エラーに `X-Ratelimit-Remaining=1499`・JSON は出さない。1,500 → 続行。jobs 応答だけ 1,499 でも中断 |
| 全ページ・窓の分割 | `per_page=2`・窓 1 時間で、窓の境界をまたぐ 20 分の区間を 1 回・標本 6 件 (欠落・重複なし)・`page=2` を取得 |
| 窓の上限 | `total_count` が 1,000 超 → 終了コード 4 |
| REST のみ | gh の呼び出しは全て `api <path>`。graphql の呼び出し 0 件 (fake gh は graphql を exit 99 にする) |

ネガコン (実装を 1 行壊して FAIL を確認。コピーに対して `f10dfd36` のコードで実施。以後の変更は説明文だけで、判定のロジックは同じ):

| 壊し方 | FAIL した判定 |
|---|---|
| 区間の判定 `>=` を `>` に | 3 件 (b の閾値 14 分・b2・ANSI 付き 15 分) |
| 残量の検査を無効化 | 4 件 (e の全部) |
| idle=0 で区間を閉じない | 3 件 (d の全部) |

### 11-2. 実データの確認 (`signature-studio/signature-studio-dev` の REST)

2026-10-14T13:04Z に取得 (測定 commit `95b501b2`)。`--since 2026-10-14T10:00:00Z --until 2026-10-14T12:30:00Z`・`--bucket` 既定 (day)・`--events` 既定 (3 event)。期間は run の作成時刻で切る。標本の時刻は `--until` を数分越えうる (例: run `38564218200` は作成 12:29:44Z で期間内、その標本は 12:30:26Z)。

| 項目 | 値 |
|---|---|
| run 一覧 (3 event・重複除去後) | 155 件 (うち oc-fix 19・watchdog job が cancelled でログ無し 12) |
| 標本 | 124 件 (idle>0: 112 件・最大 idle=19・最長の標本間隔 4.97 分・15 分超の間隔 0 回) |
| idle>0 が 15 分以上続いた回数 | 1 回 (10:00:33Z〜12:07:40Z の 127.12 分) |
| 同 (`excluding_stuck_labelled`: STUCK_LABELLED の行数を引いた idle) | 2 回 (11:10:04Z〜11:25:52Z の 15.8 分と 11:34:59Z〜12:07:40Z の 32.68 分) |
| 所要・API | 144 秒 (load 0.21)・276 回・`X-Ratelimit-Remaining` の最小 4,155 |
| `--cache` 付きの 2 回目 | 8 秒・API 4 回 (cache_hits 136) |

- 別算法の検算: 同じ測定の JSONL (124 標本) を Python で集計し直した (時刻順に idle>0 を畳む。ツールの jq とは別の実装)。
  通常の idle は 1 回 (127.12 分)・stuck 除外は 2 回 (15.8 分・32.68 分) で一致した。
- この期間は oc:stuck の PR が残っており、通常の idle は 127 分連続で 0 にならなかった。stuck 除外の値で soak を判定する理由は README に書いた。

### 11-3. 検証範囲・未解決

確認範囲: `schedule` の run は実リポジトリで 5 件 (`actions/workflows/opencode.yaml/runs?event=schedule`: 2026-10-13 18:23Z・23:00Z、2026-10-14 01:48Z・06:47Z (cancelled)・12:29:44Z)。うち 12:29:44Z の run `38564218200` は実測期間に入り (作成 10:00〜12:30Z)、その watchdog job (`115852677230`) のログの idle 行 (12:30:26.96Z・`idle=1`) を読めた (標本 124 件に含む)。この標本は 12:27:49Z〜12:30:26Z の区間 (5 標本・2.62 分・不計数) の末尾。他の 4 件は実測期間の外で、ログは未確認。
レート制限の中断と 1,000 件上限は fake gh でだけ確認した (実 API で残量を 1,500 未満にはしていない)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `schedule` の run のうち実測期間の外の 4 件 (cancelled 1 件を含む) のログは未確認。cron は約 18 時間に 5 件と疎 | 今後の発火ぶんの標本が読めるかは未確認 (読めなければ `runs.skipped.no_idle_line` に数えるので気づける) | #2355 (timer 停止の手順書) の soak 開始時の確認項目 (訂正コメント済み) |
| soak の合格ライン (何日・何回までを許すか) は未決 | ツールは回数を出すだけで、判定はしない | #2355 にコメント (判定は PM) |

## 12. PM Worker の live 切替前の突き合わせ (#2443)

測定した commit: `8a158e61` (`infra/pm-worker` は #2422 を含む origin/main と同一)。`git diff 2f884d99 8a158e61 -- infra/pm-worker/src infra/pm-worker/test` は 7 ファイル +722/−29 (engine.ts 132・app.ts 8・github.ts 18・ratelimit.ts 37 新・redact.ts 19 新・test 2 本)。launch の判定に効くのは engine.ts の rate-guard だけ。取得時刻は UTC (2026-10-14)。
VM: 13:18〜13:22Z の `issue_snapshot.py` に増分 (`since=13:17Z`、REST 7 回) を当てて `launch_issues.py` の classify (13:52:32Z。`full_bot_body` は REST を使わず空にした。relaunch の素材追加の判定だけ変わり得る)。Worker: `GET /status?detail=1` (13:53:16Z。reconcile 13:52:15Z、Version は head から作った dry-run。候補の全件を出すため一時ビルドで `TARGET=1000 BATCH=1000 NO_PR_COOLDOWN_H=24`、`rest_remaining=4985`)。

### 12-1. 分類の件数 (全カテゴリ)

| カテゴリ | VM | Worker | 差の理由 |
|---|---:|---:|---|
| blocked | 69 | 76 | +7: 親 #73 #882 #1274 #1317 #2145 #2152 #2316 (open な子を持つ。Worker は親を blocked に置く) |
| started | 6 | 6 | |
| user | 2 | 2 | |
| stopped | 281 | 279 | −2: #125 #448 は VM の `relaunch.json` で count=2 (上限) |
| recent | 10 | 10 | |
| relaunch | 0 | 2 | +2: #125 #448 (Worker は履歴を持たず、最大 2 回の再投入) |
| ready | 47 | 40 | −7: 上の親 7 件 |
| 合計 | 415 | 415 | |

### 12-2. ready の集合 (issue 番号)

- 共通 38 件 (Worker の `would_launch_now`)。art 行の差は 0。VM のみ 9 件: 親 7 件 + #2457 #2461。Worker のみ: relaunch #125 #448。
- #2457 #2461 は `would_launch_now` に出ない。広げた設定では `(relaunch + ready)[: max(n, len(relaunch))]` が ready の末尾 2 件を落とす (`launch_issues.py` の `cmd_launch` と `planLaunch` で同じ式)。Worker の ready 40 = 38 + 2、VM の ready 47 − 親 7 = 40 から、この 2 件は Worker の ready に入っていると推定 (`/status` は ready の集合を出さない)。

### 12-3. `NO_PR_COOLDOWN_H`

既定の 3 (13:54Z、他は上と同じ) では Worker の ready が 183 件 (うち候補 181 + relaunch 2)。VM の ready に無い 141 件は全て `oc:no-pr` で、最後の着手か bot の報告から 3.0〜5.6 時間 (中央値 4.5 時間)。`24` ではこの 141 件が cooldown に入り、ready は 40 件。VM の classify も、停止語 (`stop_re`) を含む報告から 24 時間は stopped に置く (この 141 件は VM でも stopped)。

### 12-4. 二重着手の確認

`launched.json` で VM が 3 時間以内 (10:52Z 以降) に着手したのは 89 件。うち Worker が選ぶのは 13 件 (#942 #1170 #1527 #1817 #1974 #1985 #2159 #2258 #2265 #2272 #2288 #2303 #2310)。全て着手の 0.02〜0.42 時間後に bot が報告し、VM の ready にも入っている。着手中で未報告の `recent` は VM も Worker も 10 件で、Worker の選択に入らない。

### 12-5. 初回の保存状態

旧版の保存は `comments?since=` を古い順に 40 ページ (4,000 件) で打ち切っていたため、直近の bot の報告を欠いた。phase は初期値の Review-Only (open PR 12 件 > 10 で解除されず)。一時ビルドで全体同期を前倒しし (13:17:10Z、REST 123 回・うちコメント 102 回・打ち切り無し・`fresh=true`)、phase を VM の `phase.json` (`review_only=false`) に合わせた。前後 (13:15:52Z と 13:17:33Z、`NO_PR_COOLDOWN_H=3`) で ready 256 → 164、stopped 31 → 143。

### 12-6. 未解決

- VM の `relaunch.json` (67 件。count=1 が 60、2 が 7) は Worker に無い。履歴の無い issue を最大 2 回余分に再投入し得る (#2343)。
- 保存 phase の初期値 (未保存なら Review-Only): 新しいデプロイ先で open PR が 10 以上だと launch が止まる。今回は VM の値で保存した (#2343 が扱う phase の引継ぎ)。
- rate-guard が実際に launch を止める場面は未測定 (`rest_remaining` は 4,985。fake gh のテストだけ)。
