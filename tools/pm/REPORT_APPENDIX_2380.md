# tools/pm 付録: REPORT §10 の全文 (PM Worker のコメント同期 #2380)

> **REPORT の付録**: `tools/pm/REPORT.md` §10 の全文 (250 行上限のため無変更で分割移動)。測定値の正本はこの付録。

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
