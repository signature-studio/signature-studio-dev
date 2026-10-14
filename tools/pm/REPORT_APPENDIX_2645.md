# tools/pm REPORT 付録 (#2645): 観測済み launch の 3 時間 recent の完了時刻化

本体 [`REPORT.md`](REPORT.md) §17 の未解決 (#2645) の実装記録。本体は 250 行上限のため、測定・ネガコンの全文はこの付録に置く。

## 観測済み launch の 3 時間 recent を、観測した run の完了から数える (#2645)

測定した commit: `252bc259` (コードを変えた最後の commit。main `e1e816c2` の取り込み merge で競合 3 件を解消)。測定時刻は UTC 2026-10-14 16:43〜16:44。
- 結論: 観測済み launch の `recent` の基準を、投稿時刻から、観測した run の完了時刻 (`launchObs.doneAt` = `RunState.updatedAt`) に置き換えた。完了時刻が無い観測済み launch と観測記録の無い古い launch は、従来どおり投稿から 3 時間。
- 単体 `node --test`: **277 pass / 0 fail**、18.8 s、load 0.37 → 1.39 (本 PR の増分 0 件。(e) は main が vitest 化した `test/unit/launchobs.test.ts` へ移した)。vitest unit (`test/unit`): **29 pass / 0 fail**、1.35 s (main の 19 件に増分 10 件: `test/unit/launch_observed.test.ts` の 9 件 (分類 (a)〜(d) と完了時刻の 2 種) と `test/unit/launchobs.test.ts` の (e) 1 件)。vitest workers: **3 pass / 0 fail**、1.54 s。
- ネガコン (各 1 件ずつ壊して FAIL を確認し、元に戻して確認): M1〜M9 は取り込み前の `cd72e291` で測定。M1 進行中の run を started にしない → (a) FAIL。M2 完了でなく投稿から 3 時間 → (b)(c) FAIL。M3 完了から 3 時間の上限を外す → (c) FAIL。M4 完了時刻なしの投稿からの窓を 0 → (d1) FAIL。M5 同じ窓を 30 時間 → (d2) FAIL。M6 完了時刻を見ない → (b)(c) FAIL。M7 `doneAtOf` が進行中の run を含める → 2 件 FAIL。M8 完了時刻を前へだけ進めない → advanceLaunch 1 件 FAIL。M9 observed への遷移で完了時刻を残さない → advanceLaunch 1 件 FAIL。取り込み後も観測の分岐は変わっていない (`launchobs.ts` は無変更、`classify.ts` の観測の行は差分 0)。M10 engine が完了時刻を渡さない → 取り込み後の `test/unit/launchobs.test.ts` の (e) 1 件 FAIL (28 pass / 1 fail)。
- 互換: `tools/pm/launch_issues.py`・`test/fixtures/classify.input.json` は変更なし。`test/classify.test.ts` の Python 突き合わせ (`launchState` を渡さない入力) は通る。
- 差分の証跡: `git diff 252bc259 HEAD -- infra/pm-worker` の出力は 0 行 (本節を commit した後の HEAD で確認)。
- 未解決: 本番 Worker への反映 (デプロイ) は #2645 の範囲外。反映後の挙動は本番で未確認。

### 取り込み後の再測定 (main `a8c02d48` を merge commit `8d27342e` で取り込み)

- 競合 1 件 (`tools/pm/REPORT.md` の末尾): 本 PR の節番号が main の heartbeat の節 (#2629・§18) と衝突し、一旦 §19 に振った。その後 main の #2648 が §19 を使ったため、本節は REPORT.md の節から外し、本付録に置いた (REPORT.md §17 の未解決の行から参照)。コードの競合は無し (`src/` は自動マージ。PR の変更は main に対する差分として残っている)。
- 測定 commit: `8d27342e` (コードを変えた最後の commit。取り込み merge)。測定は commit 済みの HEAD で実施。前節の `252bc259` の差分証跡 (`git diff 252bc259 HEAD -- infra/pm-worker`) は、main の変更が入ったため 0 行ではない。
- `pnpm run test` (node:test): **293 pass / 0 fail**、18.6 s、load 0.89 → 1.35 (Node 22.23.3)。前節の 277 件から増えたのは main 側のテストを含むため。
- `pnpm run test:unit` (vitest): **29 pass / 0 fail**、1.06 s。
- `pnpm run test:workers` (vitest + workerd): **4 pass / 0 fail**、1.52 s。
- ネガコン M10 (engine が完了時刻を渡さない: `src/engine.ts` の `doneAtOf(runs, title, launchedMs)` を `undefined` に置換) を取り込み後に再実行: `test/unit/launchobs.test.ts` の (e) 1 件 FAIL (28 pass / 1 fail)。元に戻した後、`src/engine.ts` は退避したファイルと cmp で一致。
- 型: `tsc --ignoreConfig --strict --noUnusedLocals --noUnusedParameters --noEmit --target es2022 --module esnext --moduleResolution bundler --allowImportingTsExtensions` で `src/launchobs.ts`・`src/classify.ts`・`src/engine.ts`・`src/gui.ts` を検査。出力は `crypto.ts`・`github.ts`・`hmac.ts` の既存 6 件のみ (本 PR は触らない)。
- 差分の証跡: `git diff 8d27342e HEAD -- infra/pm-worker` の出力は 0 行 (本節を commit した後の HEAD で確認)。
