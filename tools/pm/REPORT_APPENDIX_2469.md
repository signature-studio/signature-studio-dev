> **正本**: 本付録 (`tools/pm/REPORT_APPENDIX_2469.md`)。対象は PM Worker の降格 (#2340・PR #2469)。PR #2469 の round 3 の指摘 B1 (降格中の oc-pm digest) と、round 4 の指摘 (降格の組を Worker と個人の `/oc` に限る) の修正・測定。`tools/pm/REPORT.md` は 250 行上限のため、測定値は本付録に置き、REPORT.md §15 には測定 commit と差分 0 の証跡だけを書く。

## 1. 測定の対象と環境

- 測定 commit: `76932e18` (コードを変えた最後の commit)。範囲は `infra/pm-worker/src/engine.ts` (降格の組の判定・`digest()` の判定) と `infra/pm-worker/test/demote_shadow.test.ts`。
- その前のコード commit: `a258a7d8` (`digest()` の判定を降格ゲート `dispatchLive()` に揃えた。B1)。どちらも main `d460d139` の取り込み merge `40cb10d8` の上。
- 作業ツリーは clean (`git status --porcelain=v1 -- infra/pm-worker` が 0 行) の `76932e18` で測定。`infra/pm-worker` は `npm ci` (86 packages) 後。Node v22.23.3・bun 1.4.3。
- load average (1 分・uptime 表示): `npm test` の直前 0.47、直後 0.80。`test:workers` の直前 0.73。bun build の直後 0.99。

## 2. 結果

| 検証 | コマンド | 結果 | 所要 (wall) |
|---|---|---|---:|
| 統合・単体 | `cd infra/pm-worker && npm test` (`node --experimental-strip-types --no-warnings --test 'test/*.test.ts'`) | tests 197 / pass 197 / fail 0 | 16.9 s |
| Workers | `npm run test:workers` (`vitest run --config vitest.config.ts`) | Test Files 1 passed・Tests 3 passed | 2.5 s |
| unit | `npm run test:unit` (`vitest run --config vitest.unit.config.ts`) | Test Files 1 passed・Tests 10 passed | 1.4 s |
| build | `bun build src/index.ts --target=browser --format=esm --external 'node:*' --minify` (出力は作業用の一時ファイル) | exit 0 (Bundled 19 modules・bun の表示 8 ms) | 0.012 s |

## 3. 変更の内容

### 3-1. 降格中の digest (round 3・B1・`a258a7d8`)

- `digest()` の判定を `if (!this.d.cfg.liveDispatch || !gh)` から `if (!this.dispatchLive() || !gh)` に変えた。`dispatchLive()` は `cfg.liveDispatch && !meta.demoted` なので、降格中は digest も `would` のみになる (`counters.wouldDispatchPm` が増え、`would_dispatch_pm` に `digest#0` が残る)。
- `infra/pm-worker/src/` で降格のゲートを通らない `cfg.liveLaunch`・`cfg.liveDispatch` の参照は無い (`engine.ts` の 2 行は `launchLive()`・`dispatchLive()` の定義の中だけ)。
- 新規テスト `降格中は oc-pm digest を送らず would に数える。解除の後は送る`: VM の `/oc` (+1 分) と PM App の `/oc` (+2 分) で降格 → +24 時間の tick で digest が送られず `wouldDispatchPm` が増える → `POST /demote/reset` → +48 時間の tick で 1 件送る。

### 3-2. 降格の組を Worker と個人の `/oc` に限る (round 4・`76932e18`)

- 決定: `docs/DECISIONS.md` の D26 (採用・PM 補助 subagent が代理で判断。経緯は PM のコメント 2026-10-14 15:36Z)。
- `noteOc` は `vm` (個人アカウント = `cfg.pmLogins`) を記録し、判定の条件に `x.vm !== vm` を足した。組は「同じ issue・`OC_DOUBLE_MS` 以内・反対の種別」だけ (先後は問わない)。記録は従来どおり両方 (shadow の突き合わせは `vm` を使う)。
- 旧 (現実装): PM のログイン全部の組。Worker 自身の launch と再投入 (Worker 同士) で自己降格していた。
- テスト (`test/demote_shadow.test.ts`): 正例は「個人 → Worker」(従来) と「Worker → 個人」(新規)。ネガコンは 1 件だけ / 30 分超の組 / 窓 (`ocWatchFrom`) より前の組 (Worker → 個人) / 同じ id の再配送 (`ocPosts` は 1 件) / Worker 同士の 2 件 (`mode_launch` は live のまま) / 個人同士の 2 件 / `/oc` で始まらない投稿。旧テストの窓・再配送のネガコンは個人同士の組だったため、Worker と個人の組に組み直した。

## 4. ネガコン

- (a) 降格ゲート: `digest()` の判定を旧 `cfg.liveDispatch` に戻す → `demote_shadow.test.ts` 7 pass・1 fail (新規の digest テストが `not ok`)。
- (b) 降格の組: `x.vm !== vm` を外す (Worker 同士・個人同士も数える) → `demote_shadow.test.ts` 8 pass・1 fail (`降格 (ネガ)` が `not ok`)。
- (a)(b) の一時変更は作業ツリーで元に戻し、`76932e18` の内容で 2 節の数値を測った。

## 5. 差分 (測定 commit から HEAD まで)

- `git diff 76932e18 HEAD -- infra/pm-worker` の出力は空 (差分 0)。この付録と REPORT.md の変更は `infra/pm-worker` の外だけ。

## 6. 未解決

- 降格の組 (3-2) は ADR D26 のとおり。戻すには D26 を改訂し、`x.vm !== vm` の条件を外す (旧来の組み方)。`wrangler.toml` は live のままなので、この変更を入れてから再デプロイする (D26 の影響の項)。
- PM 判断 (突き合わせの元と窓・降格の dispatch の範囲) は PR 本文の未解決表に残す。本付録の対象外。
