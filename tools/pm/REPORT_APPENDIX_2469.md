> **正本**: 本付録 (`tools/pm/REPORT_APPENDIX_2469.md`)。対象は PM Worker の降格 (#2340) と、降格中の oc-pm digest の抑止 (PR #2469 の round 3 の指摘 B1)。`tools/pm/REPORT.md` は 250 行上限のため、測定値は本付録に置き、REPORT.md §15 には測定 commit と差分 0 の証跡だけを書く。

## 1. 測定の対象と環境

- 測定 commit: `a258a7d8` (コードを変えた最後の commit)。範囲は `infra/pm-worker/src/engine.ts` (`digest()` の判定 1 行) と `infra/pm-worker/test/demote_shadow.test.ts` (テスト 1 件の追加)。
- main の取り込み: `40cb10d8` (main `d460d139` を merge。衝突なし)。`a258a7d8` はその上に積んだ。
- 作業ツリーは clean (`git status --porcelain=v1 -- infra/pm-worker` が 0 行) の `a258a7d8` で測定。`infra/pm-worker` は `npm ci` (86 packages) 後。Node v22.23.3・bun 1.4.3。
- load average (1 分・uptime 表示): `npm test` の直前 0.41、直後 1.24。`test:workers` の直前 1.14、`test:unit` の直後 1.05。

## 2. 結果

| 検証 | コマンド | 結果 | 所要 (wall) |
|---|---|---|---:|
| 統合・単体 | `cd infra/pm-worker && npm test` (`node --experimental-strip-types --no-warnings --test 'test/*.test.ts'`) | tests 196 / pass 196 / fail 0 | 16.8 s |
| Workers | `npm run test:workers` (`vitest run --config vitest.config.ts`) | Test Files 1 passed・Tests 3 passed | 2.6 s |
| unit | `npm run test:unit` (`vitest run --config vitest.unit.config.ts`) | Test Files 1 passed・Tests 10 passed | 1.4 s |
| build | `bun build src/index.ts --target=browser --format=esm --external 'node:*' --minify` (出力は作業用の一時ファイル) | exit 0 (Bundled 19 modules・bun の表示 8 ms) | 0.013 s |

## 3. 変更の内容 (B1)

- `digest()` の判定を `if (!this.d.cfg.liveDispatch || !gh)` から `if (!this.dispatchLive() || !gh)` に変えた。`dispatchLive()` は `cfg.liveDispatch && !meta.demoted` なので、降格中は digest も `would` のみになる。`counters.wouldDispatchPm` が増え、`would_dispatch_pm` に `digest#0` が残る。
- `infra/pm-worker/src/` で降格のゲートを通らない `cfg.liveLaunch`・`cfg.liveDispatch` の参照は無い (`engine.ts` の 2 行は `launchLive()`・`dispatchLive()` の定義の中だけ)。
- 新規テスト `降格中は oc-pm digest を送らず would に数える。解除の後は送る` (`test/demote_shadow.test.ts`): VM の `/oc` (+1 分) と PM App の `/oc` (+2 分) で降格 → +24 時間の tick で digest が送られず `wouldDispatchPm` が増える → `POST /demote/reset` → +48 時間の tick で 1 件送る。

## 4. ネガコン

- 修正行を旧判定 `if (!this.d.cfg.liveDispatch || !gh)` に戻して `demote_shadow.test.ts` を実行 → 7 pass・1 fail (新規テストが `not ok`)。修正後は 8 pass。戻した作業ツリーは `a258a7d8` の内容に復元してから測定した。

## 5. 差分 (測定 commit から HEAD まで)

- `git diff a258a7d8 HEAD -- infra/pm-worker` の出力は空 (差分 0)。この付録と REPORT.md の変更は `infra/pm-worker` の外だけ。
- 参考: 前回の測定 commit `fc3022cf` からの差分 `git diff fc3022cf a258a7d8 -- infra/pm-worker` は 7 ファイル (223 行追加・5 行削除)。main の取り込み (#2349 digest・#2461 など) を含むので、前回の測定値は使わない。

## 6. 未解決

- B1 は解消。PM 判断 3 点 (降格の対象・突き合わせの元と窓・降格の dispatch 範囲) は PR 本文の未解決表に残す (本付録の対象外)。
