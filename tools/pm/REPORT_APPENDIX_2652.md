# tools/pm REPORT 付録 (#2652): PM Worker の保存値の版による補完

- 対象: `infra/pm-worker` の保存値の版 (`SIGNAL_VER`)。版が保存値と違う最初の tick で全体同期を 1 回走らせ、導入前に保存された `oc:no-pr` の起票者と outcome を補完する (失敗は `SIGNAL_RETRY_MS` = 15 分ごとに再試行)。
- PR: #2671 (`2652-pm-worker-no-pr-detect`)。運用の正本は `infra/pm-worker/README.md`。

## 0. 結論

- 修正のテスト `infra/pm-worker/test/no_pr_backfill.test.ts` は 4 件 PASS。`stale` を固定すると 1・2・4 が FAIL (ネガコン・§3)。
- pm-worker の全テスト (node:test) は 294/294 PASS (main 取り込み後の測定 commit・§2)。
- この PR は merge もデプロイもしていない。本番の補完件数は**未測定** (§5)。
- vitest (`test:unit`) と `test:workers` は**未実行** (§6)。理由は release-age の拒否。

## 1. 測定の対象

- 測定 commit: `9b63061b` (PR ブランチに main `5d88dda2` を merge した commit)。コードを変えた最後の commit。
- 修正本体は `c03a80a8` (`engine.ts`・`test/helpers.ts`・`test/no_pr_backfill.test.ts`)。main の取り込みで pm-worker に 13 ファイル (+823 / −51) が入ったため、測定 commit を `c03a80a8` から `9b63061b` に移した。
- 差分の証跡: `git diff 9b63061b HEAD -- infra/pm-worker/src infra/pm-worker/test` の出力は 0 行。この付録の commit より後の HEAD でも 0 行を確認した (docs だけの commit は code を変えない)。
- 差分の証跡 (参考): `git diff c03a80a8 9b63061b --stat -- infra/pm-worker` は main 取り込み分。本 PR の修正 3 ファイルは `c03a80a8` のまま。

## 2. テスト (`infra/pm-worker`)

コマンド: `cd infra/pm-worker && node --experimental-strip-types --no-warnings --test 'test/*.test.ts'` (nproc 4)

| 測定 commit | 件数 | 結果 | 所要 | load (終了時 1/5/15 分) |
|---|---|---|---|---|
| `c03a80a8` (main 取り込み前) | 281 | 281 PASS / 0 FAIL | wall 15.76 s (user 32.86 s) | 1.30 / 0.63 / 0.28 (16:59:09Z) |
| `9b63061b` (main 取り込み後) | 294 | 294 PASS / 0 FAIL | 14,872 ms (TAP の duration) | 1.80 / 0.80 / 0.34 (16:59:38Z) |

- 前提の load: 16:58:41Z に 0.23 / 0.41 / 0.20。単一の run の測定で n=1 (min–max レンジは取っていない)。
- 件数は main 取り込みの前後で 281 → 294 (純増 13 件)。増減の内訳は main 側の変更による (個別の対応は未確認)。

## 3. ネガコン (`stale` の固定)

- 変更: `infra/pm-worker/src/engine.ts` の `tickInner` の 1 行 `const stale = this.meta.signalVer !== SIGNAL_VER && ...` を `const stale = false;` に置換して `test/no_pr_backfill.test.ts` を実行し、元の行に戻した (戻し後の sha256 の先頭 16 桁は変更前と同じ `de85ebcd1c6470be`)。

| 条件 | 結果 |
|---|---|
| 修正のまま (対照) | 4 / 4 PASS (403.6 ms) |
| `stale = false` | 1 FAIL・2 FAIL・3 PASS・4 FAIL (pass 1 / fail 3) |

テストの対応: 1 版の無い保存値は最初の tick で全体同期され、Bot 起票の split 30 件が `no_pr` の対象になる (PM への dispatch は 1 時間 12 件まで。2 回目の tick は 0 件)。2 対象外の 7 種 (外部起票者・ラベル無し・outcome 無し・保留ラベル・PM の後続応答・reason が artifact・人間 CONTRIBUTOR 起票) は検出されない。3 版が最新なら周期内の tick は reconcile だけ。4 失敗した全体同期は 1 分後に再試行せず、15 分後に再試行する。

## 4. 本番 `/status` (読み取りのみ)

取得: `curl -sS https://signature-studio-pm.pycabbage.workers.dev/status` (2026-10-14T16:58:54Z・HTTP 200)。

| キー | 値 |
|---|---|
| `mode_launch` / `mode_dispatch` | live / live |
| `fresh` / `sync_truncated` | true / [] |
| `last_full_sync` | 2026-10-14T13:17:10.427Z |
| `last_full_sync_rest_calls` / `last_full_sync_comment_rest_calls` | 123 / 102 |
| `comment_window_h` / `comment_max_pages` | 24 / 150 |
| `no_pr_by_reason` | split 5 / artifact 27 / unknown 0 / blocked 11 / stop 0 |
| `pm_detected.no_pr` | 1 |
| `rest_remaining` (`rest_reset_at` 17:40:11Z) | 4968 |

- `/status` からは、本番がこの PR の版を動かしているかは判定できない (`signal_ver` は公開していない。公開は見送り)。
- deploy 後の確認: 最初の tick で `last_full_sync` が deploy 時刻の数分内に進めば、版による全体同期が走った (周期は 6 時間。直前の全体同期から 6 時間未満で deploy した場合は、進んだ時刻で区別する)。
- 16:58:54Z の `pm_detected.no_pr` (1) は、版の無い保存値を数えないので、補完で増える件数を含まない。

## 5. 補完の件数 (未測定。作成者の記録は未再現)

- この run では補完の件数を測っていない。`/status` の値 (§4) は、補完の対象 (版の無い保存値) を含まないので材料にならない。
- 作成者の記録 (PR 作成時。リポジトリに無い一時スクリプトによる。この run では再現していない・検算していない): 24 時間のコメント 10,006 件を REST で取得し、修正前の `Engine.fullSync` を偽の fetch で実行した。open の `oc:no-pr` 218 件のうち 218 件に outcome と起票者が入り、`no_pr` は 49 件検出された。
- 作成者の記録 (REST・読み取りのみ・取得時刻は未記録): open の `oc:no-pr` は 216 件。最後の outcome の reason は split 64 / artifact 88 / blocked 29 / stop 5 / unknown 30 (全期間の最後の outcome)。
- 推定: 本番で補完されて `no_pr` の対象になる件数は、作成者の記録の 49 件が目安 (本番の値ではない)。根拠の 1 つは、本番の `no_pr_by_reason` の合計が 43 件 (§4) で、作成者の REST 記録の open `oc:no-pr` 216 件より少ないこと (取得時刻は違う)。保存状態が outcome を持たない issue を多く含むと推定する。版の導入時刻は GitHub 上で確認していない。

## 6. 未実行: vitest (`test:unit`)・`test:workers`

- **未実行。** 理由: `pnpm install --frozen-lockfile` が `ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION` で拒否された (この run で再確認)。拒否された lockfile のエントリは `@cloudflare/vitest-plugin@1.4.2` (05:53:30Z 公開)・`miniflare@5.20261012.0-beta` (05:43:25Z)・`wrangler@4.151.0` (05:48:57Z)。cutoff は 2026-10-13T17:00:36Z。release-age のポリシーは変更していない (迂回していない)。
- 静的な影響 (読解の結論。実行による確認ではない): `test/unit` で tick を呼ぶのは `resync_redeliver.test.ts` の `scanAfter` の 8 箇所 (行 69・81・92・95・108・116・117・131)。どれも直前に `markFresh` を呼ぶ。`markFresh` は `signalVer = SIGNAL_VER` を記録するので、補完の分岐 (`stale`) には入らない。`launchobs.test.ts` は `launch` を直接呼ぶ。`resync_redeliver.test.ts` の (e) は `resync` を呼ぶ。よって今回の経路は `test/unit` を通らない。
- `test:workers` (workerd・`test/runtime/do.workers.test.ts`) も同じ理由で未実行。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 補完の窓は 24 時間 (`commentWindowH`)。窓より古い outcome は保存値に入らない | 古い outcome の `oc:no-pr` は検出されない | PM の判断 (既定案 = 24 時間のまま。窓を広げると REST の回数が増える。PR #2671 のコメント) |
| 補完の件数 (本番) は未測定。作成者の記録 (218 件・49 件) は再現していない | deploy 後の PM 起動の増加量が見積もれない | PM (deploy の判断。`LIVE_LAUNCH` / `LIVE_DISPATCH` の状態を確認してから deploy。deploy 後は §4 の確認手順) |
| `test:unit` (vitest) と `test:workers` を未実行 | vitest の結果が未確認 | 次の検収 (vitest が入る環境)。`pnpm install` の拒否 (§6) は PM の release-age ポリシーの判断 |
| 人間起票の `oc:no-pr` は `author_association` が CONTRIBUTOR のため対象外 (`src/pm.ts` の `authorAllowed`) | 人間起票の `no_pr` は検出されない | PM (起票者の信頼判定の方針。既定案 = 対象外のまま) |
| `/status` に `signal_ver` を出していない (minor-4) | 補完が済んだかを外から確認できない (§4 の方法で代替) | PM (任意の改善。必要なら子 issue) |

## 8. 再現

```
cd infra/pm-worker && node --experimental-strip-types --no-warnings --test 'test/*.test.ts'
cd infra/pm-worker && node --experimental-strip-types --no-warnings --test test/no_pr_backfill.test.ts
curl -sS https://signature-studio-pm.pycabbage.workers.dev/status
git diff 9b63061b HEAD -- infra/pm-worker/src infra/pm-worker/test
```

ネガコン (§3) は `src/engine.ts` の 1 行を `const stale = false;` に置き換えて 2 行目を実行し、元の行に戻す。
