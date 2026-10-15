# REPORT #3973 — PM Worker: 親 issue の prio:critical を子に継承する (CI-181)

測定値の正本 (`docs/DOC_MAP.md`)。規則と運用の正本は `infra/pm-worker/src/launch.ts` の `effectivePrioMap` と `infra/pm-worker/README.md`。PR は #3993。

## 測定 commit と差分

- 測定 commit (コードを変えた最後の commit): `4d3e21b36` (`feat(pm-worker): inherit prio:critical from the parent issue (親: #N) (#3973)`)。base は `origin/main` (`cac0e4112`)。
- 測定 commit から HEAD までのコード差分 (`git diff 4d3e21b36 HEAD -- infra/pm-worker`): 本 REPORT を入れる commit は `tools/pm/` と `docs/` だけを変えるため、`infra/pm-worker` の差分は 0 (出力なし)。

## 単体テスト (`infra/pm-worker`・`npm test` = `node --experimental-strip-types --no-warnings --test 'test/*.test.ts'`)

| 版 | 件数 | PASS | FAIL | 所要 | load (1 分平均・4 vCPU) |
|---|---|---|---|---|---|
| 変更前 `a9afb18ec` | 422 | 422 | 0 | 14.45 s | 測定時に未記録 |
| 変更後 `4d3e21b36` (1 回目) | 430 | 430 | 0 | 13.75 s | 測定時に未記録 |
| 変更後 `4d3e21b36` (HEAD で再現) | 430 | 430 | 0 | 13.57 s | 0.54 → 1.14 |

新規 8 件は `test/prio_inherit.test.ts`: 規則 1 (親 critical の子)・規則 2 (子の明示が優先)・規則 3 (祖父母 1 段)・規則 4 (closed・無い・自己参照・循環・親が low)・#3748 形の回帰 (sortReady と planLaunch の先頭)・countRunsByPrio・cooldown・engine (`plan().picks` と `/status` の `ready_by_prio`)。

## ネガコン (継承を外した読み)

`effectivePrioMap` を『自身の明示 (labels) だけ』に置換した複製 (作業ツリーの外の一時ディレクトリ・`tools` は同じ実体を参照) に、`test/prio_inherit.test.ts` を当てた:

```
tests 8 / pass 1 / fail 7
not ok 規則 1 / 規則 3 / 規則 4 / 回帰 (#3748 形) / countRunsByPrio / cooldown / engine
ok     規則 2 (明示が優先。継承の有無に依らず正しい値)
```

## ミューテーション (`npm run test:mutation`)

- `scripts/mutation_halt.mjs` (停止規則): 9 件中 9 件 killed (survived 0)。
- `scripts/mutation_no_pr.mjs` (oc:no-pr の再投入): 8 件中 8 件 killed (survived 0)。

## pr-lint

`bash .github/scripts/pr-lint.sh --base origin/main --head HEAD --body-file <PR 本文>`: violations=0 (strict=0)。

## 製品 KPI

対象外 (PM Worker の着手順だけを変える。FLEngine の起動・GUI には触れない)。素材 (fl-win64) は使わない (純関数と Worker の状態だけ)。

## 未解決

- GitHub sub-issue の親からの継承: 子 issue #3989 (`[CI-184]`) で起票。
