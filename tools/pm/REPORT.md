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

- 結論: fake gh の判定テストと、実データの検算は一致した。数え方 (区間・閾値・残量の扱い) は [`README.md`](README.md) の `idle_report.sh` の節。
- 全文 (測定値・ネガコン・未解決): [`REPORT_APPENDIX_2354.md`](REPORT_APPENDIX_2354.md) (§11 の分割移動)。

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

## 14. `pm_wake.sh` の判定テストと live の確認 (#2347)

既知類型との関係: 該当なし (PM 運用の記録)。測定 commit `edb3ab39` (コードを変えた最後の commit)、測定時刻 2026-10-14T15:19Z (`date -u`)。
- テスト `bash tools/pm/test_pm_wake.sh`: **20 passed, 0 failed**、所要 **0.70 s** (fake curl・fake opencode。ネットワーク不使用。ネガコン 10 件を含む)。
- ネガコンの確認: 間隔を 0 にした一時複製では c1・c2・f2 が、上限と fresh 判定を壊した複製では d2・d3・g2 が FAIL (いずれも 17 passed, 3 failed)。
- live (読み取りのみの `GET /status`、15:18Z): `needs_pm`・`stuck`・`stuck_age_max_min` が返らない。`pm_wake.sh` は `result=status-failed reason=parse`・exit 2 で、送信は 0 件。本番 Worker は #2335 の変更を含まない版と見られる `[未確認: デプロイ版]`。再デプロイ後に needs_pm 経路が有効になる。
- 差分 (測定 commit から HEAD まで・コード範囲): `git diff edb3ab39 HEAD -- tools/pm/pm_wake.sh tools/pm/test_pm_wake.sh tools/pm/systemd` の出力は空 (差分 0)。

## 15. PM Worker の同時実行の上限の推定 (#2381・PR #2485)

測定した commit: `131d3daa` (コードを変えた最後の commit。origin/main `81799351` の取り込みと競合の解消を含む)。取得時刻は UTC (2026-10-14)。`git diff d662b04e 131d3daa -- infra/pm-worker` は 302 行 (main 側の取り込み分。PR 自身の差分は `git diff origin/main 131d3daa -- infra/pm-worker` の 533 行)。以後の commit は `tools/pm` と `docs` だけで、`git diff 131d3daa HEAD -- infra/pm-worker` は 0 行。前回の測定 commit は `d662b04e` (main `5a2b7f41` の取り込みまで)。

競合の解消 (origin/main の取り込みは 3 回。1 回目は `3a6fcf81`、2 回目は `5a2b7f41`、3 回目は `131d3daa`):

- `src/engine.ts` の `status()`: PR 側の `const now` と `cnt` (`runCounts(now)`) を残し、main 側の `now` の重複宣言は 1 つにした (残さないと `SyntaxError: Identifier 'now' has already been declared` で 10 ファイルが落ちる)。counters は main 側 (#2339 の `{ ...this.zero(), ...counters }`) を採用。
- `src/config.ts`: `DEFAULT_QUEUE_MARGIN`・`DEFAULT_TARGET_MIN` (PR) と `DEFAULT_REPO` (main) を両方残した。`test/status.test.ts` の既存キー一覧は両側のキーを残した。
- `README.md`: 本機能の節と #2339 の再送の節を両方残した。
- `tools/pm/REPORT.md`: 本節は main の §13 (R2 素材投入) と §14 (`pm_wake`・#2347) と番号が衝突するため、末尾の §15 に移した。
- 3 回目 (origin/main `81799351`・競合 2 件): `infra/pm-worker/README.md` の `/status` 表は、main の `last_digest_at` 行と PR の `running` の定義行・`target_eff` ほかの行を両方残した。`test/status.test.ts` の `ADDED_KEYS` は `last_digest_at` と `target_eff` ほかを両方入れた。`src/pm.ts`・`src/classify.ts`・`src/engine.ts` は競合なしで自動マージされ、main の digest の変更と PR の変更が両方入っている (手で触っていない)。

- 単体テスト (`131d3daa`): `git archive 131d3daa infra/pm-worker tools/pm` を作業用の一時 dir に展開し、`cd infra/pm-worker && node --experimental-strip-types --no-warnings --test 'test/*.test.ts'` → **201 pass / 0 fail**、17.4 s、load 0.84 → 1.63 (Node 22.23.3)。増分 7 件は main 側の `test/digest.test.ts`。前回 (`d662b04e`) は 194 pass / 0 fail (15.3 s)。main `5a2b7f41` の `test(` 行は 181 件で、本 PR の `test/target.test.ts` の 13 件を足すと 194 件。
- Worker 実行環境の vitest (`131d3daa`): 同じ展開先で `npm ci` (86 packages・4 s) → `npx vitest run --config vitest.config.ts` (`test/runtime/` の 3 件) → **3 pass / 0 fail**、1.5 s。

ネガコン (受入条件 6)。対応するテストは `test/target.test.ts`:

| 条件 | テスト |
|---|---|
| 正例: running=60・queued=20 が 30 分 → 70 (29 分では 80) | 「(正例) running=60・queued=20」 |
| 正例: running=20・queued=15 が 30 分 → 30 | 「(正例) running=20・queued=15」 |
| (a) queued=0 → TARGET / (d) cap 100 でも 80 を超えない | 「(a) running=40・queued=0」 |
| (b) queued>0 が 29 分だけ → 変えない / (f) dry-run で POST 0 | 「(正例) running=60・queued=20」 |
| (c) cap_est=5 → target_eff ≥ 30 | 「(c) cap_est=5」 |
| (e) 24 時間後に TARGET へ戻る | 「(e) 24 時間の窓」 |
| (g) TARGET=40 → target_eff ≤ 40 | 「(g) TARGET を env で 40」 |
| 上限の引き上げ・古い peak で押し上げ直さない・room=0 | 「上限が上がったら」「上限を 60 → 20」「room は target_eff」 |
| 純関数: 30 分の streak・観測の空きをまたがない・観測の保持 | 「saturatedRunning」「nextCap / capValue」「観測の保持」 |

review #2485 の変更: 観測は `fresh` な tick だけ記録する (`src/engine.ts` の tick)。観測の空き (2 分超) をまたぐ streak は数えない (`SAT_GAP_MS`。テストは「saturatedRunning」)。`fresh` の分岐を直接作るテストは無い (tick 単位の stale を mock で作れない)。既存の tick テスト (`test/status.test.ts`) で回帰は見た。

## 16. oc-pm の refs_orphan 検出 (#2337・PR #2478)

- 測定 commit: `b7fb7a40` (main `b3c699d4` の取り込み merge。修正本体は `ebfd0a41`)。全文 (測定・ネガコン・Refs のみ判定の差): [`REPORT_APPENDIX_2337.md`](REPORT_APPENDIX_2337.md) (§16 の分割移動)。
- 結論: `npm test` 213 件 PASS / 0 FAIL (n=3)。`test:unit` 10 件・`test:workers` 3 件 PASS。ネガコン 5 種は各 1 件ずつ壊して FAIL を確認。
- 差分の証跡: `git diff b7fb7a40 HEAD -- infra/pm-worker/src infra/pm-worker/test` の出力は 0 行 (本節を commit した後の HEAD で確認)。
- 未解決: refs-only の判定が 2 系統 (指標 `refsOnlyBody`・refs_orphan `refsOnlyNumbers`)。判定の差は付録 §16-3。追跡は #2623 ([CI-115])。

## 17. /oc 投稿の観測のネガコン (#2342・#2473 の vitest 化)

- 測定 commit: `dd9931bf` (`test/launchobs.test.ts` を `test/unit/launchobs.test.ts` に移して vitest 化。README の 1 行)。worktree で `pnpm install --frozen-lockfile --config.minimum-release-age=0` (診断用。既定設定は 2026-10-15 05:55Z まで `ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION`)。
- 結論: `test:unit` (vitest) **19 件 PASS** (うち観測 9 件)・2.1 s。`test:workers` **3 件 PASS**・1.5 s。`npm test` (node:test) **204 件 PASS / 0 FAIL**・17.7 s。load 0.33 (Node 22.23.3)。
- ネガコン: `src/launchobs.ts` を 1 行ずつ壊して FAIL を確認。(b) の題名一致を外す → (b) と純関数の 2 件 FAIL。5 分の境界 `>` を `>=` → (a) と純関数の 2 件 FAIL。元に戻した後 `git diff -- src` は 0 行。
- 差分の証跡: `git diff dd9931bf HEAD -- infra/pm-worker/src infra/pm-worker/test` の出力は 0 行 (本節を commit した後の HEAD で確認)。
- 未解決: 受入 2 の残り (観測済み launch の 3 時間判定の置き換え。既定案は完了時刻から 3 時間) は子 issue #2645 ([CI-123]) へ移した。

## 18. 実装 App の自己 merge の実測 (#2600・PR #2624)

- **測定** (別 subagent の実測。取得時刻・クエリは #2600 本文に記録が無い。PR #2624 の作成者は再測定していない): 直近 24 時間の merged PR 986 件のうち約 119 件 (12%、95% CI 83〜157) が、merged_by = 実装 App (`opencode-for-signature-studio[bot]`) の自己 merge だった。PR 作成の 6〜45 秒後に merge され、merge 前の review は 0 件 (確認できた 19/19)。確認できた 8 件は全てコードを含み、`.github/scripts` と `infra/pm-worker` を含む。
- **原因**: `.github/prompts/implementer.md` 規範 9 が `gh pr merge --auto --merge` を指示していた (`8e4b343d`、2026-10-12 追加)。main に承認必須の Ruleset が無く (`branches/main/protection` は 404、ruleset 24866584 に `pull_request` ルールは無い)、`allow_auto_merge: true` のため Auto Merge は即時 merge になった。
- **対応**: 規範 9 から Auto Merge の指示を消し、実装者の merge を禁止した。merge は approve した reviewer が同じ run で行う (PR #2624)。
- **未検証**: 承認の無い PR への auto-merge の挙動 (REST に有効化 API が無く GraphQL が要る)。Ruleset 未適用の下での技術的な防止 (PR #2624 の未解決表)。
