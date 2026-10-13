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
`pr_gaps.py`・`sync_status.py`・`issue_snapshot.py`・`restart_failed.sh` を `gh api --paginate` に直した。

実測 (取得時刻 UTC・`gh api --paginate` の結果。`total_count` は `per_page=1` の値):

| 条件 | total_count | 全ページ取得件数 | 所要 |
|---|---:|---:|---:|
| `status=in_progress` (17:53:43Z) | 48 | 47 | 2.7 s (取得時点の実行中 run が変動) |
| `status=in_progress` (17:53:45Z 再取得) | 47 | 47 | 同上 |
| `status=in_progress` `per_page=10` (5 ページ) | - | 45 (`per_page=100` と一致) | - |
| `status=queued` | 1 | 0 | 0.8 s |
| `status=pending` | 3 | 3 | - |

- ページを跨いで件数が欠けないことを `per_page=10` (5 ページ) と `per_page=100` の比較で確認した。
- `status=completed` は GitHub API の 1000 件上限があるため、本ツールは使わない (対象は実行中の 4 状態のみ)。
- 件数が 100 件を超える状態の再現は、本 run ではできなかった (実行中 run が 50 件前後)。
