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

全文は [`REPORT_APPENDIX_2380.md`](REPORT_APPENDIX_2380.md) (250 行上限のため分割移動・#2434)。

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

測定した commit: `e88e1890` (`infra/pm-worker` は #2422・#2423 を含む origin/main `803d5164` と同一。以後の main の変更は `package.json` の `packageManager` の固定 (#2452) だけ)。`git diff 2f884d99 e88e1890 -- infra/pm-worker/src infra/pm-worker/test` は 19 ファイル +1,841/−56。launch の判定に効くのは engine.ts の rate-guard (launch を止める条件)と、pm-apply・needs-user-input の issue を ready/relaunch から user に移す規則 (#2423)。取得時刻は UTC (2026-10-14)。
VM: 13:18〜13:22Z の `issue_snapshot.py` に増分 (`since=13:17Z`、REST 7 回) を当てて `launch_issues.py` の classify (14:03:28Z。`full_bot_body` は REST を使わず空にした。relaunch の素材追加の判定だけ変わり得る)。Worker: `GET /status?detail=1` (14:04Z。reconcile 14:02:49Z。head から作った dry-run の版、候補の全件を出すため一時ビルドで `TARGET=1000 BATCH=1000 NO_PR_COOLDOWN_H=24`、`rest_remaining=4980`)。

### 12-1. 分類の件数 (全カテゴリ)

| カテゴリ | VM | Worker | 差の理由 |
|---|---:|---:|---|
| blocked | 64 | 72 | +8: 親 #73 #882 #1274 #1317 #2145 #2152 #2316 #2373 (open な子を持つ。Worker は親を blocked に置く) |
| started | 4 | 4 | |
| user | 2 | 3 | +1: #2362 (`pm-apply`。#2423 の規則で ready から user へ) |
| stopped | 281 | 279 | −2: #125 #448 は VM の `relaunch.json` で count=2 (上限) |
| recent | 6 | 9 | +3: #2224 #2226 #2247 (`oc:no-pr`。bot の報告が 12:31Z で、`NO_PR_COOLDOWN_H=24` の cooldown 中。VM は停止語が無く ready) |
| relaunch | 0 | 2 | +2: #125 #448 (Worker は履歴を持たず、最大 2 回の再投入) |
| ready | 57 | 45 | −12: 親 8 + #2362 + #2224 #2226 #2247 |
| 合計 | 414 | 414 | |

### 12-2. ready の集合 (issue 番号)

- 共通 43 件 (Worker の `would_launch_now`)。art 行の差は 0。VM のみ 14 件: 12-1 の 12 件 + #2461 #2462。Worker のみ: relaunch #125 #448。
- #2461 #2462 は `would_launch_now` に出ない。広げた設定では `(relaunch + ready)[: max(n, len(relaunch))]` が ready の末尾 2 件を落とす (`launch_issues.py` の `cmd_launch` と `planLaunch` で同じ式)。Worker の ready 45 = 43 + 2 から、この 2 件は Worker の ready に入っていると推定 (`/status` は ready の集合を出さない)。

### 12-3. `NO_PR_COOLDOWN_H`

既定の 3 (14:05Z、他は上と同じ) では Worker の ready が 188 件 (24 のときは 45 件)。VM の ready に無い候補が 142 件あり、全て `oc:no-pr` で、VM では stopped (停止語 `stop_re` を含む報告から 24 時間は stopped)。最後の着手か bot の報告から 3.0〜5.8 時間 (中央値 4.6 時間) で、cooldown が 3 時間だと再着手の対象に戻る。`24` ではこの 142 件が cooldown に入る。

### 12-4. 二重着手の確認

`launched.json` で VM が 3 時間以内 (11:03Z 以降) に着手したのは 74 件。うち Worker が選ぶのは 10 件 (#942 #1170 #1527 #1817 #1974 #1985 #2159 #2288 #2303 #2310)。全て着手の 0.02〜0.16 時間後に bot が報告し、VM の ready にも入っている。着手中で未報告の `recent` は VM 6 件・Worker 9 件 (差は上の 3 件で、どちらも Worker の選択に入らない)。

### 12-5. 初回の保存状態と oc-pm

旧版の保存は `comments?since=` を古い順に 40 ページ (4,000 件) で打ち切っていたため、直近の bot の報告を欠いた。phase は初期値の Review-Only (open PR 12 件 > 10 で解除されず)。一時ビルドで全体同期を前倒しし (13:17:10Z、REST 123 回・うちコメント 102 回・打ち切り無し・`fresh=true`)、phase を VM の `phase.json` (`review_only=false`) に合わせた。前後 (13:15:52Z と 13:17:33Z、`NO_PR_COOLDOWN_H=3`) で ready 256 → 164、stopped 31 → 143。
oc-pm の検出 (`pm_detected`) は 4 種とも 0 件、`would_dispatch_pm` は空 (14:04Z)。検出の手がかり (`sig`) は #2423 以後の webhook と reconcile でだけ埋まるため、live 直後は送信が少ない。

### 12-6. 未解決

- VM の `relaunch.json` (67 件。count=1 が 60、2 が 7) は Worker に無い。履歴の無い issue を最大 2 回余分に再投入し得る (#2343)。
- 保存 phase の初期値 (未保存なら Review-Only): 新しいデプロイ先で open PR が 10 以上だと launch が止まる。今回は VM の値で保存した (#2343)。rate-guard が launch を止める場面と、live の oc-pm 送信 (PM agent の起動) は未測定 (fake gh のテストだけ)。

## 13. R2 素材投入の頻度 (#2434・手順は `docs/WORKFLOW.md` §11)

既知類型との関係: 該当なし (PM 運用の記録)。測定時刻 2026-10-14T14:33:25Z (`date -u`)。
ここで数えるのは **許可名 (`ARTIFACT_RE`) を増やした回数**であり、R2 への投入回数ではない。

- 数え方: main の first-parent 履歴で、`.github/scripts/prepare-event-context.sh` の `ARTIFACT_RE=` 行が親と変わった merge を数える。再現: `git log --first-parent --format='%h %cI %s' -G'^ARTIFACT_RE=' -- .github/scripts/prepare-event-context.sh`
- 結果: **7 件** (初回 `7bd4ce08` 2026-10-12T19:10:33Z の 1 件 + 追加 6 件: #293・#318・#320・#646・#610・#761)。最後の追加は `3fed6297` (#761) の 2026-10-13T14:23:39Z。issue 本文の「5 回」とは数えが違う (7 回が実測)。
- 最後の追加から測定時刻まで **0 件** (24 時間 9 分 46 秒)。
- 独立検算: 同じ first-parent 履歴を Python で線形に走査し、名前の集合の増分で数えた → 7 件 (初回 1 + 増分 6) で一致。commit 単位の `git log -G` (feature branch の commit を含む) でも 7 件 (`ba6e25f9`〜`9e52c39d`)。
- watchdog 側の copy (`.github/scripts/watchdog.sh`。`pr-lint.sh` が読む) は後から追随した: `analysis-mac-shared` は `3b2346a0` (2026-10-13T14:22:02Z)、`work-fw-stage1` は `33a18408` (2026-10-13T15:13:01Z) で入った。`9e52c39d` の時点の watchdog.sh には mac-shared が無い (grep 0 件)。
- R2 への投入の記録: repo 内にあるのは 2026-10-12 の全素材の再投入 1 回 (依頼者操作。`docs/pm/RETRO_2026-10-13.md`)。PM が VM で記録したとされる昇格ログは 1 件 (2026-10-13T14:16:50Z) だが、本 run では VM のログを確認していない `[未確認]`。
- 未解決: open の #874 ([CI-18] mac pkg 素材の R2 化) の投入状況は本 run で未確認 (R2 の一覧は認証情報を使わずに取得していない)。起票先: 既存の #874 (新規起票なし)。
