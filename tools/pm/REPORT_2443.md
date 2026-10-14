# tools/pm REPORT 付録 — PM Worker live 切替の再測定の未了 (#2443 / PR #2453)

`tools/pm/REPORT.md` §12 の付録。測定値の正本は §12 (件数) と本付録 (測定 commit と head の差分)。

## 1. 測定 commit と head の差分

- 測定した Worker: `2f884d99` (main) の Worker コード。dry-run の版は `7441616e` (REPORT §12-1 の Worker 欄)。
- PR の head: `8a158e61`。PR 内の変更は `infra/pm-worker/README.md`・`wrangler.toml`・`tools/pm/REPORT.md` の文書と設定のみで、Worker のコードは変えていない。
- ただし `2f884d99` の後に main へ #2422 (#2338: rate-guard・status 観測・redact) が入り、head にはそれが含まれる。

```
$ git diff --stat 2f884d99 8a158e61 -- infra/pm-worker/src infra/pm-worker/test
 infra/pm-worker/src/app.ts                      |   8 +-
 infra/pm-worker/src/engine.ts                   | 132 ++++--
 infra/pm-worker/src/github.ts                   |  18 +-
 infra/pm-worker/src/ratelimit.ts                |  37 ++
 infra/pm-worker/src/redact.ts                   |  19 +
 infra/pm-worker/test/runtime/do.workers.test.ts |  21 +
 infra/pm-worker/test/status.test.ts             | 516 ++++++++++++++++++++++++
 7 files changed, 722 insertions(+), 29 deletions(-)
```

- 差分は 0 ではない。全文は `git diff 2f884d99 8a158e61 -- infra/pm-worker/src infra/pm-worker/test` で再現する (722 行追加・29 行削除の全文は本付録に貼らない)。
- 判定の入力 (`launch.ts`・`classify.ts`・`phase.ts`・`config.ts`) の差分は 0: `git diff --stat 2f884d99 8a158e61 -- infra/pm-worker/src/launch.ts infra/pm-worker/src/classify.ts infra/pm-worker/src/phase.ts infra/pm-worker/src/config.ts` の出力は空。
- 測定 commit の Worker コードと `04c176f2` の Worker コードは同一 (`git diff 2f884d99 04c176f2 -- infra/pm-worker/src infra/pm-worker/test` は空)。前の PR 本文が `04c176f2` と書いたのは、この版で測ったという意味。

## 2. launch の判定に効く差分 (ソースの読み。実測ではない)

| 箇所 | 変更 | 判定への影響 |
|---|---|---|
| `engine.ts` `plan()` の `stop` (500 行付近) | `restGuardOn(rest.remaining)` のとき `rate-guard` | `remaining < 1500` のときだけ `gated` になり、`picks` が空 (dry-run の `would_launch_now` も空) |
| `engine.ts` launch ループ (571 行付近) | 投稿の直前に `if (restGuardOn(...)) break;` | 投稿の応答で残量が下がった場合に残りを投稿しない |
| `engine.ts` `countChanged`・`reconcile` | 食い違いの件数を数える | 判定に入らない (`reconcile_diff` のみ) |
| `engine.ts` `pushLog`・`setError`・`status()` | `redact` を通す・新しい key | 判定に入らない (log・status の文字列) |
| `github.ts` `Gh.remaining` | ヘッダの値だけを採用する | 書き込みのみで読む箇所は無い |

よって、REST 残量が 1,500 以上の間は head の判定の入力と式は測定 commit と同じで、§12-1〜12-3 の件数は main 版と一致するはず。1,500 未満の間は launch が止まり、件数は測定値と違う。この推論は実測で確かめていない。

## 3. 再測定が未了の理由 (この run)

- この run の runner には Cloudflare の資格情報 (wrangler の OAuth) が無く、head の Worker を deploy できない。公開の `GET /status` は main 版で、`rest_remaining` は `null` (未観測)。head の値は取れない。
- VM 側の入力 (`launched.json`・`relaunch.json`・`phase.json`・`issues_state.json`) は VM にだけあり、`.gitignore` で repo に無い。VM の per-issue の取得時刻も未保存 (§12-1 の推定の根拠)。
- 13:24Z の `rest_remaining` は未記録 (測定時の main 版に rate の観測が無かった)。gate が件数に効いたかは判定できない。
- よって「VM と Worker を同時刻に取る」比較は、この run では実行できない。

## 4. 再測定の手順 (PM が VM で行う)

1. head (`8a158e61` 以降) の `infra/pm-worker` で一時の dry-run 版を作る。`wrangler.toml` の `TARGET="1000"`・`BATCH="1000"`・`NO_PR_COOLDOWN_H="24"`・`LIVE_LAUNCH="0"`・`LIVE_DISPATCH="0"`。`npx wrangler deploy --dry-run` で bindings を確かめてから deploy する。
2. 同じ分 (± 1 分) に VM で `issue_snapshot.py` → `launch_issues.py` の classify を実行し、Worker で `GET /status?detail=1` を取る。§12-1〜12-3 の表を同じ集計で取り直す。
3. 取得時の `rest_remaining`・`rest_reset_at` を `/status` から控える。1,500 未満なら件数は gate の影響を受けているので、その旨を §12 に書く。
4. ネガコン 4 行 (`LIVE_LAUNCH`・`LIVE_DISPATCH` の組み合わせ) を head の版で取り直す。前回は `04c176f2` の Worker (rate-guard 無し) で取った。
5. §12 の測定 commit を head に更新し、`git diff <測定 commit> HEAD -- infra/pm-worker/src infra/pm-worker/test --stat` の出力を §12 に書く。
6. `wrangler.toml` を main の値に戻して deploy する (§12-5 と同じ)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| head の Worker 版での §12-1〜12-3 とネガコン 4 行の再測定 (上の §4) | live 切替の件数の根拠が測定 commit `2f884d99` のまま。1,500 未満の間は件数が変わる | PR #2453 (blocking)。merge 前に §4 を行うか、`LIVE_LAUNCH` の切替を外す (PM 判断) |
