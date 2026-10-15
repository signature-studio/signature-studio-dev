# tools/pm REPORT 付録 (#3050): launch の素材行は PM の行と本文の行の和集合にする

- 対象: `infra/pm-worker/src/launch.ts` の `defaultArtLine` (launch の素材行の既定)。呼び出し元は `classify.ts` の `artifactsFor` (再投入の基準と `addArts` の足し先) と `engine.ts` の `baseArt`・picks。
- 親: #2319。issue: #3050 (`[CI-143]`)。運用の正本は `infra/pm-worker/README.md` の素材行の既定の段落。

## 0. 結論

- 素材行の既定を、PM の行と本文の行の**素材名の和集合**に変えた (旧: 排他的に先頭 1 つだけを採る)。取り込んだ `pm_art` は書き換えない (読み出し側でだけ和集合を作る)。
- 測定 commit `b0663e06`。node:test 391 件 (n=3 とも全件 PASS)・vitest unit 70 件・workers 7 件・変異テスト 9 件 (killed 9) がすべて PASS。
- ネガコン: 排他実装 (`origin/main` の `launch.ts`) に戻すと、`npm test` で 5 件が FAIL (§3)。
- issue 本文の実例 (#2716・#2880) を新しい関数で再計算すると、本文だけにあった `work-m11` (#2716)・`work-liftdiff` (#2880) が加わる (§4)。
- 本番は未 deploy (deploy は PM の作業)。本番の launch の挙動はまだ変わらない (§5)。

## 1. 測定の対象

- 実装 commit: `a0da8971` (`fix(pm-worker): launch の素材行は PM の行と本文の行の和集合にする (#3050)`)。コードはこの commit で確定。
- 測定 commit: `b0663e06` (`docs(pm-worker): 素材行の既定を和集合の規則に直す (#3050)`)。`infra/pm-worker` を変えた最後の commit (README の文書修正のみ)。
- 測定 commit から HEAD までのコード差分: `git diff b0663e06 HEAD -- infra/pm-worker/src infra/pm-worker/test` は 0 行。`git diff b0663e06 HEAD -- infra/pm-worker` も 0 行 (本 REPORT の commit は `tools/pm` と `docs/DOC_MAP.md` だけ)。

## 2. テスト (測定 commit `b0663e06`・コミット済み・`pnpm install --frozen-lockfile`)

`load` は `/proc/loadavg` の 1 分平均で、各コマンドの開始時に読んだ値。

| コマンド | 件数 | 結果 | 所要 (real) | load (開始時) |
|---|---:|---|---:|---|
| `node --experimental-strip-types --no-warnings --test 'test/*.test.ts'` (n=3) | 391 | 391 PASS / 0 FAIL (3 回とも) | 22.74 / 22.44 / 21.68 s | 0.78 → 1.83 → 2.32 |
| `npm run test:unit` (vitest unit・fetch モック) | 70 (5 files) | 70 PASS / 0 FAIL | 2.91 s | 2.65 |
| `npm run test:workers` (vitest + workerd) | 7 (2 files) | 7 PASS / 0 FAIL | 3.02 s | 2.65 |
| `npm run test:mutation` | 9 変異 | killed 9・survived 0 | 5.27 s | 2.52 |

- 旧値 (`origin/main` `94b6c6bd`・変更前): node:test 387 件。増分の +4 は、`test/launch.test.ts` の和集合テスト 3 件と、`test/classify.test.ts` の再投入の基準の和集合 1 件。
- `test/engine.test.ts` の `launch (#2758): PM の行は本文の行より優先する` は旧仕様 (PM の行が勝つ) を固定していたため、和集合の期待値 (`oc_artifacts: fl-win64 plugins-ott work-m11`) に直し、名前を `launch (#3050)` に変えた (件数は変わらず)。

## 3. ネガコン (排他実装に戻す)

`origin/main` の `infra/pm-worker/src/launch.ts` (排他実装) を `src/launch.ts` に入れ、テストは和集合のままで `npm test` を実行した。実行後は `src/launch.ts` を測定 commit の内容に戻した (`git diff --quiet HEAD -- src/launch.ts` で確認)。

- 結果: 391 件中 386 PASS / **5 FAIL**。
- FAIL したテスト:
  - `分類 (#3050): 再投入の基準は pm_art の行と本文の行の和集合 ...` (`test/classify.test.ts`)
  - `launch (#3050): PM の行と本文の行は和集合にする ...` (`test/engine.test.ts`)
  - `素材行の和集合 (#3050): PM の行と本文の行の名前を足す。本文だけの名前が加わり、PM だけの名前は残る` (`test/launch.test.ts`)
  - `素材行の和集合 (#3050): none は名前を持たない側とみなす。両方 none なら none` (`test/launch.test.ts`)
  - `素材行の和集合 (#3050): allowlist 外の名前は落ちる ...` (`test/launch.test.ts`)

## 4. 実例の再計算 (issue #3050 本文の引用)

`defaultArtLine(PM の行, 本文の行, ...)` を `node --experimental-strip-types` で実行した。PM の行は着手コメントの行、本文の行は issue 本文の行 (issue #3050 の本文に引用されたもの)。

| issue | PM の行 (着手コメント) | 本文の行 | 旧 (排他) | 新 (和集合) |
|---|---|---|---|---|
| #2716 [WIN-5] | `fl-win64 toolchain-retdec toolchain-emsdk apt-mingw` | `fl-win64 toolchain-retdec toolchain-emsdk work-m11 apt-mingw` | `fl-win64 toolchain-retdec toolchain-emsdk apt-mingw` (work-m11 無し・停止) | `fl-win64 toolchain-retdec toolchain-emsdk apt-mingw work-m11` |
| #2880 [WIN-11] | `fl-win64 toolchain-retdec toolchain-emsdk` | `fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff` | `fl-win64 toolchain-retdec toolchain-emsdk` (素材不足で停止) | `fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff` |

## 5. 本番への影響と未解決

- 本番は未 deploy。deploy は PM の作業で、本 PR では deploy していない。停止条件 (`launch_halted`・`launch_halted_overdue`) と既定値は変えていないため、deploy 後に launch が止まる条件は増えない。
- 保存済みの `pm_art` は書き換えない。deploy 後は、本文に `oc_artifacts:` 行があり `pm_art` に無い名前を持つ issue の素材行が和集合になる (再投入の基準も同じ)。
- 未解決 (起票先: PM の deploy 後の確認): deploy 後の本番 `/status` と launch の素材行の実測は未測定。
