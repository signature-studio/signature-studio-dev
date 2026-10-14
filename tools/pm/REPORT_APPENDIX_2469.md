> **正本**: 本付録 (`tools/pm/REPORT_APPENDIX_2469.md`)。対象は PM Worker の降格 (#2340・PR #2469)。PR #2469 の round 3 (降格中の oc-pm digest)・round 4・round 5 (降格の組を Worker と個人の `/oc` に限る。ネガコンの組み直し) の修正と測定。`tools/pm/REPORT.md` は 250 行上限のため、測定値は本付録に置き、REPORT.md §16 には測定 commit と差分 0 の証跡だけを書く。

## 1. 測定の対象と環境

- 測定 commit: `e78527db` (コードを変えた最後の commit。main `f3102162` (#2485) の取り込み merge と、ネガコンの組み直し)。範囲は `infra/pm-worker/src/engine.ts`・`infra/pm-worker/test/demote_shadow.test.ts` と、main 側の `infra/pm-worker` 一式。
- 直前のコード commit: `76932e18` (降格の組を Worker と個人に限る)。その前は `a258a7d8` (digest の降格ゲート)。
- 測定は `git archive e78527db infra/pm-worker tools/pm` をリポジトリ外の一時 dir (`_temp/wt_verify_2469`) に展開し、`npm ci` (86 packages) してから行った (作業ツリーに依存しない。`tools/pm` も要る: `src/config.ts` が `manual_deps.json` を読み、テストが `launch_issues.py` を呼ぶ)。Node v22.23.3・bun 1.4.3。
- load average (`/proc/loadavg` 1 分): `npm test` の直前 0.64、直後 1.50。`test:workers`・`test:unit`・build の後 1.35。

## 2. 結果

| 検証 | コマンド | 結果 | 所要 (wall) |
|---|---|---|---:|
| 統合・単体 | `cd infra/pm-worker && npm test` (`node --experimental-strip-types --no-warnings --test 'test/*.test.ts'`) | tests 210 / pass 210 / fail 0 (exit 0) | 19 s |
| Workers | `npm run test:workers` (`vitest run --config vitest.config.ts`) | Test Files 1 passed・Tests 3 passed | 3 s |
| unit | `npm run test:unit` (`vitest run --config vitest.unit.config.ts`) | Test Files 1 passed・Tests 10 passed | 1 s |
| build | `npm run build` (`bun build src/index.ts --target=browser --format=esm --external 'node:*' --minify`。出力は展開先の `dist/`) | exit 0 (Bundled 20 modules・9 ms・index.js 65.1 KB) | 1 s 未満 |

`npm test` の件数 210 は、main の取り込みで増えた分 (`test/target.test.ts` 13 件・`test/digest.test.ts` など) を含む。降格のネガコンの追加は既存の test の中に足したため、件数は変わらない。

## 3. 変更の内容

### 3-1. 降格中の digest (round 3・B1・`a258a7d8`)

- `digest()` の判定を `if (!this.d.cfg.liveDispatch || !gh)` から `if (!this.dispatchLive() || !gh)` に変えた。`dispatchLive()` は `cfg.liveDispatch && !meta.demoted` なので、降格中は digest も would のみになる (`counters.wouldDispatchPm` が増え、`would_dispatch_pm` に `digest#0` が残る)。
- `src/` で降格のゲートを通らない `cfg.liveLaunch`・`cfg.liveDispatch` の参照は無い (`engine.ts` の該当行は `launchLive()`・`dispatchLive()` の定義の中だけ)。
- テスト `降格中は oc-pm digest を送らず would に数える。解除の後は送る`: VM の `/oc` (+1 分) と PM App の `/oc` (+2 分) で降格 → +24 時間の tick で digest が送られず `wouldDispatchPm` が増える → `POST /demote/reset` → +48 時間の tick で 1 件送る。

### 3-2. 降格の組を Worker と個人の `/oc` に限る (round 4・`76932e18`)

- 決定: ADR D26 (`docs/DECISIONS.md`・採用・PM 補助 subagent の代理判断。経緯は PM のコメント 2026-10-14 15:36Z)。
- `noteOc` は `vm` (個人アカウント = `cfg.pmLogins`) を記録し、判定の条件に `x.vm !== vm` を足した。組は「同じ issue・`OC_DOUBLE_MS` 以内・反対の種別」だけ (先後は問わない)。記録は従来どおり両方 (shadow の突き合わせは `vm` を使う)。
- 旧 (76932e18 より前): PM のログイン全部の組。Worker 自身の launch と再投入 (Worker 同士) で自己降格していた。

### 3-3. main の取り込みと、ネガコンの組み直し (round 5・`e78527db`)

- `origin/main` (`f3102162`・#2485 の同時実行の上限の推定) を merge で取り込んだ (rebase・force push はしていない)。競合は 3 ファイル:
  - `infra/pm-worker/src/engine.ts`: コンストラクタで、main の `obs` の初期化と本 PR の `ocPosts`・`wouldRecs`・`ocWatchFrom` の初期化を両方残した。
  - `docs/DOC_MAP.md`: 本付録の行と main の `REPORT.md` の行 (#2381 を追加) を残した。
  - `tools/pm/REPORT.md`: main の §15 (#2485) を残し、本 PR の測定の節を §16 に置いた (番号の衝突を避けるため)。
- テスト (`test/demote_shadow.test.ts`) の組み直し:
  - 「同じコメントの再配送」は、個人の投稿 (VM) の 2 回配送と、39 分後の Worker の投稿 (PM_BOT) の組に直した。記録は 2 件 (`ocPosts.length`)。
  - 窓より前のネガコンを 1 件足した: Worker の `/oc` (窓の中・+1 分) と、窓より前の個人の `/oc` (−10 分) の組は降格しない。外側の `at >= from` だけを外すと、この組で降格する (従来のネガコンは内側の `x.at >= from` で止まり、外側を外しても 9 件とも pass だった)。
  - 既存の組み直し (正例の両方の順序・Worker 同士 2 件・個人同士 2 件・窓より前・1 件だけ・30 分超・`/oc` で始まらない投稿) は、round 4 の修正のまま。

## 4. ネガコン (現 HEAD `e78527db` の内容に対して 1 つずつ変異)

各変異は展開先の `src/engine.ts` だけに入れ、`test/demote_shadow.test.ts` を流した後、元の内容に戻した (`cmp` で一致を確認)。

| 変異 | 内容 | 結果 |
|---|---|---|
| (a) 降格ゲート | `digest()` の判定を `cfg.liveDispatch` に戻す | `not ok 7` (降格中は digest を送らず would に数える): 8 pass・1 fail |
| (b) 組の条件 | `noteOc` の `x.vm !== vm &&` を外す (Worker 同士・個人同士も数える) | `not ok 3` (降格 (ネガ)): 8 pass・1 fail |
| (c) id 重複除去 | `noteOc` の `if (this.ocPosts.some((x) => x.id === id)) return;` を外す | `not ok 3` (降格 (ネガ)): 8 pass・1 fail |
| (d) 窓判定 | `Math.abs(x.at - at) <= OC_DOUBLE_MS` を外す (30 分超の組も数える) | `not ok 3` (降格 (ネガ)): 8 pass・1 fail |
| (e) 窓より前 | 外側の `at >= from &&` を外す | `not ok 3` (降格 (ネガ)): 8 pass・1 fail (追加した窓より前のネガコンで検出。追加前は 9 pass) |

- 元に戻した後の `demote_shadow.test.ts`: 9 件 pass / 0 fail (`e78527db` の内容)。

## 5. 差分 (測定 commit から HEAD まで)

- `git diff e78527db HEAD -- infra/pm-worker` の出力は空 (差分 0)。この付録・REPORT.md・PR 本文の変更は `infra/pm-worker` の外だけ。

## 6. 未解決

- 降格の組 (3-2) は ADR D26 のとおり。戻すには D26 を改訂し、`x.vm !== vm` の条件を外す (旧来の組み方)。`wrangler.toml` は live のままなので、この変更を入れてから再デプロイする (D26 の影響の項)。
- PM 判断 (突き合わせの元と窓・降格の dispatch の範囲・昇格) は PR 本文の未解決表に残す。本付録の対象外。
