# tools/pm 付録 — #2416 `/status` の build (deploy commit) の測定と wrangler の確認

> **正本の宣言**: `infra/pm-worker/README.md` の build 節 (『再デプロイ』手順 4・5、『ロールバック』3) の根拠。PR #2477 の差し戻し round 1 への対応。
> `tools/pm/REPORT.md` (250 行上限ちょうど) は変更していない。PM Worker の測定値は `tools/pm/REPORT.md` と本付録が正本 (`docs/DOC_MAP.md` §4)。
> PR #2477 が `origin/main` と競合したため main を取り込んだ (競合解消)。取り込みは 6 回。6 回目 `952eae2d` は競合 2 件 (`docs/DOC_MAP.md` の表の行、`infra/pm-worker/test/status.test.ts` の `ADDED_KEYS`) を両側残しで解消した。main 側では pm-worker が npm から pnpm に移った (#2585) ため、測定の依存の入れ方を pnpm に改めた。測定は、`src`・`test` を最後に変えた commit `952eae2d` で取り直した (§0-2)。

**結論**: 検証 HEAD `952eae2d` の `npm test` (203 件)・`npm run test:unit` (10 件)・`npm run test:workers` (4 件) は、3 回ずつ全件 pass。`wrangler` 4.151.0 の dry-run (5 案) は、案 a (`--define` 引用符なし) を除く 4 案が exit 0。案 a は hash の先頭が数字 (`9`) のため `Invalid define value` で exit 1。`--define` は引用符付きでも引用符なしでも hash は bundle に入らない。`--var` は bindings に `(hidden)` で出る。実 Worker での反映は未確認 (README の `[未確認]`)。

## 0. 取得方法・環境

### 0-1 版と環境

| 項目 | 値 |
|---|---|
| 測定 commit | `952eae2d` (`Merge remote-tracking branch 'origin/main' into 2416-pm-worker-status-build`。PR #2477 の競合解消)。コードを変えた最後の commit (main の 6 回目の取り込み) |
| 検証 HEAD | `952eae2d` (測定は HEAD と clean な作業ツリーで実施。コードは未編集。`pnpm install --frozen-lockfile --config.minimum-release-age=0` 後も `git status --porcelain` は空。PR 側は `package*.json`・lockfile を変えていない。main 由来の pnpm 移行を取り込んだ) |
| 依存の入れ方 | `pnpm install --frozen-lockfile --config.minimum-release-age=0` (§0-4) |
| Node / pnpm / npm | v22.23.3 / 12.10.1 / 10.9.9 (`npm test`・`npm run test:*` は npm、依存は pnpm) |
| wrangler | 4.151.0 (`./node_modules/.bin/wrangler --version`) |
| vitest | v4.1.11 (`vitest run` の `RUN` 行。`package.json` は `^4.1.11`) |
| CPU | `nproc` = 4、`os.availableParallelism()` = 4 |
| `node --test` の並列数 | 3 (既定の `--test-concurrency` = `os.availableParallelism() - 1`。Node 公式 docs の Command-line API) |
| 対象 | `npm test` = `test/*.test.ts` の 17 ファイル (node の `--test`。依存なし)。`npm run test:unit` = `test/unit/**/*.test.ts` の 1 ファイル (fetch をモックした Node の単体テスト。main 由来)。`npm run test:workers` = `test/runtime/**/*.test.ts` の 1 ファイル (`do.workers.test.ts`、workerd 上で実行) |

### 0-2 測定したコードと検証 HEAD の差分 (WORKFLOW §5・§6)

```sh
git diff e94dca2f 952eae2d -- infra/pm-worker/src infra/pm-worker/test | wc -l   # 479 (前版の測定 commit からの差。main の取り込みで変わった分)
git diff 952eae2d HEAD -- infra/pm-worker/src infra/pm-worker/test | wc -l       # 0 (最終 HEAD。本付録の追記だけで src・test は変えない)
```

- 前版の測定 (測定 commit `e94dca2f`、検証 HEAD `e94dca2f`・`89e3c4db`。`npm test` 190 件・`npm ci` で依存を入れた) は、main の 6 回目の取り込み (`952eae2d`) で `src`・`test` が変わったため無効になった。その数値は git 履歴の `e94dca2f`・`89e3c4db` 版に残る。
- さらに前の測定 (`c8f2fdc8`・`815eb526`・`037fa935`・`efd86292` など) も、後の取り込みで `src`・`test` が変わったため数値は置き換えた。
- 本付録の数値は、取り込み commit `952eae2d` で測った。最終 HEAD (本付録を含む commit) の `src`・`test` の差分は上の 0 行。最終 HEAD の hash は PR 本文の検証欄に書く。

### 0-3 取得方法

- **wall**: `date +%s.%N` を `npm` の前後で取った差 (npm と vitest の起動・終了を含む)。
- **`npm test` の所要**: TAP 末尾の `# duration_ms` (node --test が出す全体の所要)。
- **`npm run test:workers` / `npm run test:unit` の所要**: vitest の出力行 `Duration` の値。wall とは別の量。
  差し戻し (指摘 4) の『実測 3 s』は、wall と Duration のどちらか不明だった。本付録では両方を分けて記録する。
- **load average**: `/proc/loadavg` の 1 / 5 / 15 分値を、各 run の前後で取った。1 分値は直前の run の負荷を含む。
- 変動する値は n = 3 の **min–max**。測定は 1 回ずつ直列 (並行実行なし)。依存は `pnpm install` で入れたあとに測定した (測定の外)。

### 0-4 依存の入れ方 (release-age の診断用の設定)

- 既定設定の `pnpm install --frozen-lockfile` は、lockfile の `miniflare@5.20261012.0-beta`・`wrangler@4.151.0`・`@cloudflare/vitest-plugin@1.4.2` が公開から 24 時間未満のため `ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION` で失敗した (2026-10-14 の実測。README『Workers Builds の接続状態と pnpm 経路』の release-age の項と同じ)。
- 測定は `--config.minimum-release-age=0` を付けて行った。診断用の設定で、lockfile・`pnpm-workspace.yaml` は変えていない (`--frozen-lockfile`)。解除の判断は PM (#2585 の範囲外)。
- wrangler は `pnpm exec` を使うと、同じ release-age の事前チェックで WARN が出る。このため dry-run は `./node_modules/.bin/wrangler` を直接呼んだ (バージョンは同じ 4.151.0)。

## 1. `npm test` (`node --experimental-strip-types --no-warnings --test 'test/*.test.ts'`)

| run | wall (s) | `# duration_ms` | pass / fail / cancelled | load (前 → 後、1/5/15 分) |
|---|---:|---:|---|---|
| 1 | 12.29 | 12180.1 | 203 / 0 / 0 | 0.95/0.51/0.21 → 1.47/0.64/0.26 |
| 2 | 12.27 | 12166.2 | 203 / 0 / 0 | 1.44/0.65/0.26 → 2.33/0.87/0.34 |
| 3 | 11.83 | 11721.3 | 203 / 0 / 0 | 2.22/0.87/0.34 → 2.18/0.91/0.36 |
| **min–max** | **11.83–12.29** | **11721.3–12180.1** | 203 / 0 / 0 (3 回とも) | 1 分値の最大 2.33 (nproc 4 未満) |

- TAP の `# tests 203`・`# suites 0`・`# skipped 0`・`# todo 0` (3 回とも同じ)。並列数は既定の 3。

## 2. `npm run test:workers` (`vitest run --config vitest.config.ts`)

| run | wall (s) | vitest `Duration` | Tests (pass / fail) | load (前 → 後、1/5/15 分) |
|---|---:|---|---|---|
| 1 | 1.87 | 1.11 s | 4 / 0 | 1.47/0.64/0.26 → 1.44/0.65/0.26 |
| 2 | 1.92 | 1.15 s | 4 / 0 | 2.33/0.87/0.34 → 2.22/0.87/0.34 |
| 3 | 1.85 | 1.12 s | 4 / 0 | 2.18/0.91/0.36 → 2.09/0.91/0.37 |
| **min–max** | **1.85–1.92** | **1.11–1.15 s** | 4 / 0 (3 回とも) | — |

- vitest の `Test Files  1 passed (1)`・`Tests  4 passed (4)` (3 回とも)。
- wall (1.85–1.92 s) と vitest の `Duration` (1.11–1.15 s) は別の量。1 つの値に丸めて書かない。

## 2-1 `npm run test:unit` (`vitest run --config vitest.unit.config.ts`)

| run | wall (s) | vitest `Duration` | Tests (pass / fail) | load (前 → 後、1/5/15 分) |
|---|---:|---|---|---|
| 1 | 1.02 | 692 ms | 10 / 0 | 1.47/0.64/0.26 → 1.47/0.64/0.26 |
| 2 | 1.18 | 859 ms | 10 / 0 | 2.33/0.87/0.34 → 2.33/0.87/0.34 |
| 3 | 1.02 | 719 ms | 10 / 0 | 2.18/0.91/0.36 → 2.18/0.91/0.36 |
| **min–max** | **1.02–1.18** | **692–859 ms** | 10 / 0 (3 回とも) | — |

- `Test Files  1 passed (1)`・`Tests  10 passed (10)` (3 回とも)。

## 3. wrangler の `--define` / `--var` (dry-run)

すべて `CI=1 ./node_modules/.bin/wrangler deploy --dry-run --outdir work/dryrun/<案>` (`infra/pm-worker/work/` は gitignore) に次の引数を足したもの。`<HASH>` は `git rev-parse 952eae2d` の全 40 字 (`952eae2dd261fdb26d37ba1777b336882a4a99a4`)。dry-run は Cloudflare に接続せず、認証は不要。

| 案 | 追加した引数 | exit | bindings の `BUILD_COMMIT` | bundle (`index.js`) に hash が入るか |
|---|---|---:|---|---|
| a | `--define BUILD_COMMIT:<HASH>` (引用符なし) | 1 | 表示なし | ビルドが失敗 (`Invalid define value (must be an entity name or JS literal)`)。bundle は出ない |
| b | `--define 'BUILD_COMMIT:"<HASH>"'` (引用符あり) | 0 | 表示なし | **0 件**。bundle は d と同一 (define は `env.BUILD_COMMIT` の参照に効かない) |
| c | `--var BUILD_COMMIT:<HASH>` | 0 | `env.BUILD_COMMIT ("(hidden)")` | **0 件** (runtime の binding。bundle は d と同一) |
| d | (引数なし) | 0 | 表示なし | 0 件 |
| e | `--var TARGET:999` | 0 | `env.TARGET ("(hidden)")` (`[vars]` の `"50"` を上書き) | — (binding の上書きの確認) |

- 案 a の exit は hash の先頭文字で変わる。今回の hash `952eae2d…` は数字 (`9`) で始まるので exit 1。英字で始まる hash (前版 `e94dca2f…`) では exit 0 だった (前版の実測)。どちらの場合も hash は bundle に入らない。
- 案 b・c・d・e の `Total Upload: 107.82 KiB / gzip: 33.56 KiB`。`index.js` は 110,410 バイト・2,513 行 (b・c・d・e で同一)。
- bindings の一覧は、c のみ `BUILD_COMMIT` の行が増える (b・d・e は同じ一覧)。
- c の値が upload の metadata で実際に渡るかは dry-run では見えない (表示は `(hidden)`)。届くことは実 Worker の `/status` でのみ確かめられる (§4-3)。

## 4. 検証範囲・ネガティブコントロール・未確認

### 4-1 検証範囲

- `npm test` 203 件・`npm run test:unit` 10 件・`npm run test:workers` 4 件を、検証 HEAD と同一のコードで 3 回ずつ実行。wrangler dry-run は 5 案を各 1 回。
- `/status` の `build` の挙動は、既存テストで確認済み: `test/status.test.ts` (`BUILD_COMMIT` 未設定で `null`・形式が違う値は `null`・キー集合のスナップショットに `build` を含む)、`test/runtime/do.workers.test.ts` (workerd の DO env から hash を読む・未設定で `null`)。
- wrangler は dry-run のみ (bindings の表示と bundle の内容)。

### 4-2 ネガティブコントロール

- **a**: `--define` の引用符なしは、hash が英字で始まれば通るが、bundle は d と同一で hash は入らない。今回の hash (数字で始まる) では build が失敗した。どちらも hash を bundle に入れられないので、README 手順 4 (c) の『`--define` は採らない』の根拠になる。
- **b**: 引用符付きは通るが、やはり hash は bundle に入らない。
- **d**: `--var` を付けないと bindings に `BUILD_COMMIT` が出ない。このとき `/status` の `build` は `null` (`test/status.test.ts` の未設定ケース)。README 手順 5 の『`null` のままなら反映とは判断しない』の前提。
- **e**: `--var` は同名の `[vars]` を上書きする (`TARGET` が `"50"` → `(hidden)`)。

### 4-3 範囲外・未確認 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 Worker の `/status` の `build` に、`--var` で渡した hash が出ること | 手順 5 の反映の判定が実機で未確認 | 次の再デプロイで PM が README 手順 5 の `build` を見て確認 (README 末尾の `[未確認]`) |
| `--var` なしの deploy で `build` が `null` に戻ること | 手順 5 の『`null` は反映とみなさない』の実機での裏付け | 次の再デプロイ (README 末尾の `[未確認]`)。推定: コードと vitest から `null` |
| rollback で戻し先の `BUILD_COMMIT` (binding) が戻ること。戻らないときの `build` の値 (現在の hash のままか `null` か) | 『ロールバック』3 で戻し先の `build` を見る前提 | README 末尾の `[未確認]` の rollback 項目 (実機で未実行) |

- 実 Worker への `wrangler deploy`・`wrangler rollback` は、この測定では行っていない (認証を使う操作のため)。

## 5. 再現コマンド

```sh
# リポジトリ直下 (検証 HEAD 952eae2d)
git diff 952eae2d HEAD -- infra/pm-worker/src infra/pm-worker/test | wc -l
cd infra/pm-worker && pnpm install --frozen-lockfile --config.minimum-release-age=0
npm test                  # TAP 末尾の # pass / # duration_ms。wall は前後の時刻差
npm run test:unit         # 出力の Duration / Tests 行
npm run test:workers      # 出力の Duration / Tests 行
H=$(git rev-parse 952eae2d)
CI=1 ./node_modules/.bin/wrangler deploy --dry-run --outdir work/dryrun/a --define BUILD_COMMIT:$H
CI=1 ./node_modules/.bin/wrangler deploy --dry-run --outdir work/dryrun/b --define "BUILD_COMMIT:\"$H\""
CI=1 ./node_modules/.bin/wrangler deploy --dry-run --outdir work/dryrun/c --var BUILD_COMMIT:$H
CI=1 ./node_modules/.bin/wrangler deploy --dry-run --outdir work/dryrun/d
CI=1 ./node_modules/.bin/wrangler deploy --dry-run --outdir work/dryrun/e --var TARGET:999
grep -c "$H" work/dryrun/b/index.js     # 0
```
