# tools/pm 付録 — #2416 `/status` の build (deploy commit) の測定と wrangler の確認

> **正本の宣言**: `infra/pm-worker/README.md` の build 節 (『再デプロイ』手順 4・5、『ロールバック』3) の根拠。PR #2477 の差し戻し (round 1・round 5) への対応。
> `tools/pm/REPORT.md` (250 行上限ちょうど) は変更していない。PM Worker の測定値は `tools/pm/REPORT.md` と本付録が正本 (`docs/DOC_MAP.md` §4)。
> main の取り込みの履歴は `git log --merges` が正本で、本付録には書かない。

**結論**: 測定 commit `2e84269d` の `npm test` (279 件)・`npm run test:unit` (19 件)・`npm run test:workers` (4 件) は、3 回ずつ全件 pass。測定の後に `src`・`test` を変えた commit は無い (§0-2)。wrangler 4.151.0 の dry-run (7 回) の結果: `--var` は bindings に `(hidden)` で出る。`--define` は引用符の有無によらず hash が bundle に入らない。引用符なしの `--define` は、hash の先頭が数字だと `Invalid define value` で exit 1 になる (測定 commit の hash は `2` 始まりで該当する)。実 Worker での反映は未確認 (README の `[未確認]`)。

## 0. 取得方法・環境

### 0-1 版と環境

| 項目 | 値 |
|---|---|
| 測定 commit | `2e84269d` (`Merge origin/main into 2416-pm-worker-status-build (#2416)`。main (`cc6d6610`) の取り込み。`infra/pm-worker/src`・`test` を最後に変えた commit) |
| 最終 HEAD | PR 本文の検証欄に書く (本付録を含む commit の hash は本付録に書けない)。測定 commit から最終 HEAD までの差分は docs だけ (§0-2) |
| 作業ツリー | 測定時は `git status --porcelain` が空 (依存の `node_modules` は gitignore) |
| 依存の入れ方 | `pnpm install --frozen-lockfile --config.minimum-release-age=0` (§0-4) |
| Node / pnpm / npm | v22.23.3 / 12.10.1 / 10.9.9 (`npm test`・`npm run test:*` は npm、依存は pnpm) |
| wrangler / vitest | 4.151.0 (`./node_modules/.bin/wrangler --version`) / v4.1.11 (`RUN` 行) |
| CPU | `nproc` = 4 |
| `node --test` の並列数 | 3 (既定の `--test-concurrency` = `os.availableParallelism() - 1`。Node 公式 docs の Command-line API) |
| 対象 | `npm test` = `test/*.test.ts` の 19 ファイル (node の `--test`。依存なし)。`npm run test:unit` = `test/unit/**/*.test.ts` の 2 ファイル (`launchobs.test.ts`・`resync_redeliver.test.ts`。fetch をモックした vitest の単体テスト、workerd なし)。`npm run test:workers` = `test/runtime/**/*.test.ts` の 1 ファイル (`do.workers.test.ts`、workerd 上で実行) |

### 0-2 測定したコードと最終 HEAD の差分 (WORKFLOW §5・§6)

```sh
git diff 2e84269d HEAD -- infra/pm-worker/src infra/pm-worker/test | wc -l    # 0 (最終 HEAD。測定 commit の後は docs だけ)
git diff 887ae3df 2e84269d -- infra/pm-worker/src infra/pm-worker/test | wc -l # 1118 (前版の測定 commit から今回の測定 commit までの差。main の取り込みで変わった分)
```

- 前版 (測定 commit `887ae3df`。`npm test` 252 件・`npm run test:unit` 19 件・`npm run test:workers` 4 件) は、main の取り込み (`cc6d6610`・#2518 など) で `src`・`test` が 1118 行変わったため無効になった。その数値は git 履歴に残る。
- 本付録の数値は、`src`・`test` を最後に変えた commit `2e84269d` で測った。最終 HEAD の hash は PR 本文の検証欄に書く。

### 0-3 取得方法

- **wall**: `date +%s.%N` を `npm` の前後で取った差 (npm と vitest の起動・終了を含む)。
- **`npm test` の所要**: TAP 末尾の `# duration_ms` (node --test が出す全体の所要)。
- **`npm run test:workers` / `npm run test:unit` の所要**: vitest の出力行 `Duration` の値。wall とは別の量。
- **load average**: `/proc/loadavg` の 1 / 5 / 15 分値を、各 run の前後で取った。1 分値は直前の run の負荷を含む。
- 変動する値は n = 3 の **min–max**。測定は 1 回ずつ直列 (並行実行なし)。依存は `pnpm install` で入れたあとに測定した (測定の外)。

### 0-4 依存の入れ方 (release-age の診断用の設定)

- 既定設定の `pnpm install --frozen-lockfile` は、lockfile の `miniflare@5.20261012.0-beta`・`wrangler@4.151.0`・`@cloudflare/vitest-plugin@1.4.2` が公開から 24 時間未満のため `ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION` で失敗する。測定時 (2026-10-14) も `pnpm install --frozen-lockfile --dry-run` で同じエラーを確認した。README『Workers Builds の接続状態と pnpm 経路』の release-age の項と同じ。
- 測定は `--config.minimum-release-age=0` を付けて行った。診断用の設定で、lockfile・`pnpm-workspace.yaml` は変えていない (`--frozen-lockfile`)。解除の判断は PM (#2585 の範囲外)。
- wrangler は `pnpm exec` を使うと、同じ release-age の事前チェックで WARN が出る。このため dry-run は `./node_modules/.bin/wrangler` を直接呼んだ (バージョンは同じ 4.151.0)。

## 1. `npm test` (`node --experimental-strip-types --no-warnings --test 'test/*.test.ts'`)

| run | wall (s) | `# duration_ms` | pass / fail / cancelled | load (前 → 後、1/5/15 分) |
|---|---:|---:|---|---|
| 1 | 18.84 | 18703.5 | 279 / 0 / 0 | 0.09/0.43/0.29 → 0.64/0.54/0.33 |
| 2 | 18.74 | 18594.9 | 279 / 0 / 0 | 0.64/0.54/0.33 → 1.83/0.83/0.43 |
| 3 | 18.70 | 18564.6 | 279 / 0 / 0 | 1.83/0.83/0.43 → 2.05/0.95/0.48 |
| **min–max** | **18.70–18.84** | **18564.6–18703.5** | 279 / 0 / 0 (3 回とも) | 1 分値の最大 2.05 (nproc 4 未満) |

- TAP の `# tests 279`・`# skipped 0`・`# todo 0`・`# cancelled 0` (3 回とも同じ)。並列数は既定の 3。
- 1 回目の実行で `duration_ms` が長かったのは `ネガコン (b): 毎分の tick が 3 日続いても digest は 24 時間に 1 件を超えない` (5656.4 ms) と `(f) open issue が 3,000 件超 → fresh=false` (4292.5 ms)。

## 2. `npm run test:workers` (`vitest run --config vitest.config.ts`)

| run | wall (s) | vitest `Duration` | Tests (pass / fail) | load (前 → 後、1/5/15 分) |
|---|---:|---|---|---|
| 1 | 2.58 | 1.49 s | 4 / 0 | 2.12/0.98/0.49 → 2.12/0.98/0.49 |
| 2 | 2.66 | 1.61 s | 4 / 0 | 2.12/0.98/0.49 → 2.19/1.02/0.50 |
| 3 | 2.56 | 1.50 s | 4 / 0 | 2.19/1.02/0.50 → 2.10/1.02/0.51 |
| **min–max** | **2.56–2.66** | **1.49–1.61 s** | 4 / 0 (3 回とも) | — |

- vitest の `Test Files  1 passed (1)`・`Tests  4 passed (4)` (3 回とも)。
- wall と vitest の `Duration` は別の量。1 つの値に丸めて書かない。

## 2-1 `npm run test:unit` (`vitest run --config vitest.unit.config.ts`)

| run | wall (s) | vitest `Duration` | Tests (pass / fail) | load (前 → 後、1/5/15 分) |
|---|---:|---|---|---|
| 1 | 1.65 | 1.21 s | 19 / 0 | 2.05/0.95/0.48 → 2.05/0.95/0.48 |
| 2 | 1.64 | 1.19 s | 19 / 0 | 2.05/0.95/0.48 → 2.12/0.98/0.49 |
| 3 | 1.68 | 1.24 s | 19 / 0 | 2.12/0.98/0.49 → 2.12/0.98/0.49 |
| **min–max** | **1.64–1.68** | **1.19–1.24 s** | 19 / 0 (3 回とも) | — |

- vitest の `Test Files  2 passed (2)`・`Tests  19 passed (19)` (3 回とも)。

## 3. wrangler の `--define` / `--var` (dry-run)

すべて `CI=1 ./node_modules/.bin/wrangler deploy --dry-run --outdir <作業用の一時 dir>` に次の引数を足したもの。`<HASH>` は測定 commit の全 40 字 (`2e84269dc81f03d452a8932bbd71ba1731891b5d`)。a2 は前版の測定 commit の hash (`c53d65838b2a4da4ccf425d505c419fba89a8281`、先頭が英字)、a3 は先頭が数字の例 (`1234567890abcdef1234567890abcdef12345678`)。dry-run は Cloudflare に接続せず、認証は不要。

| 案 | 追加した引数 | exit | bindings | bundle (`index.js`) に hash が入るか |
|---|---|---:|---|---|
| a | `--define BUILD_COMMIT:<HASH>` (引用符なし。先頭が数字の hash) | 1 | `Invalid define value (must be an entity name or JS literal)` | —(build 失敗) |
| a2 | 同 (先頭が英字の hash `c53d6583…`) | 0 | 表示なし | **0 件** |
| a3 | 同 (先頭が数字の例) | 1 | 同上 | —(build 失敗) |
| b | `--define 'BUILD_COMMIT:"<HASH>"'` (引用符あり) | 0 | 表示なし | **0 件** |
| c | `--var BUILD_COMMIT:<HASH>` | 0 | `env.BUILD_COMMIT ("(hidden)")` | **0 件** (runtime の binding。値は bundle に入らない) |
| d | (引数なし) | 0 | 表示なし | 0 件 |
| e | `--var TARGET:999` | 0 | `env.TARGET ("(hidden)")` (`[vars]` の `"58"` を上書き) | — (binding の上書きの確認) |

- a と a3 の exit 1 は、hash の先頭が数字のとき `--define` の値が JS の値として解釈できないため。a2 は英字始まりで通るが、hash は bundle に入らない。`--define` は引用符の有無と hash の先頭文字によらず、build に値を渡せない。
- a2・b・c・d・e の `Total Upload: 127.31 KiB / gzip: 38.97 KiB` (同一)。
- c の `BUILD_COMMIT` は bindings に出るが、dry-run では値が `(hidden)` で見えない。届くことは実 Worker の `/status` でのみ確かめられる (§4-3)。

## 4. 検証範囲・ネガティブコントロール・未確認

### 4-1 検証範囲

- `npm test` 279 件・`npm run test:unit` 19 件・`npm run test:workers` 4 件を、測定 commit と同一のコードで 3 回ずつ実行。wrangler dry-run は 7 回 (a・a2・a3・b・c・d・e) を各 1 回。
- `/status` の `build` の挙動は、既存テストで確認済み: `test/status.test.ts` (25 件。`BUILD_COMMIT` 未設定で `null`・形式が違う値は `null`・キー集合のスナップショットに `build` を含む)、`test/runtime/do.workers.test.ts` (workerd の DO env から hash を読む・未設定で `null`)。
- wrangler は dry-run のみ (bindings の表示と bundle の内容)。

### 4-2 ネガティブコントロール

- **N1 (`build` を返さない変更で FAIL する)**: 測定用の一時コピー (repo の外。作業ツリーは変えていない) で `src/engine.ts` の `build: this.d.cfg.build,` を削除し、`node --experimental-strip-types --no-warnings --test test/status.test.ts` を実行 → `# pass 22`・`# fail 3` (FAIL は `/status (d)` のキー集合スナップショット、`build: デプロイ時の BUILD_COMMIT をそのまま返す…`、`build: commit hash の形 … null…` の 3 件)。未改変のコピーは `# pass 25`・`# fail 0`。
- **N2**: §3 の a〜e は案の比較で、検査の負例ではない。a と a3 の exit 1 は hash の先頭文字で決まることの実測。
- **N3**: `--var` を付けない deploy で `build` が `null` になることは、`test/status.test.ts` の未設定ケースで確認 (README 手順 5 の『`null` のままなら反映とは判断しない』の前提)。

### 4-3 範囲外・未確認 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 Worker の `/status` の `build` に、`--var` で渡した hash が出ること | 手順 5 の反映の判定が実機で未確認 | 次の再デプロイで PM が README 手順 5 の `build` を見て確認 (README 末尾の `[未確認]`) |
| `--var` なしの deploy で `build` が `null` に戻ること | 手順 5 の『`null` は反映とみなさない』の実機での裏付け | 次の再デプロイ (README 末尾の `[未確認]`)。推定: コードと vitest から `null` |
| rollback で戻し先の `BUILD_COMMIT` (binding) が戻ること | 『ロールバック』3 で戻し先の `build` を見る前提 | README 末尾の `[未確認]` の rollback 項目 (実機で未実行) |
| Workers Builds を接続した場合、その deploy には `--var` が付かないので `build` は `null` になる (推定) | 接続するなら `build` で反映を判定できない | PM 判断 (#2357。README『Workers Builds を接続しない理由』の注記・#2585) |

- 実 Worker への `wrangler deploy`・`wrangler rollback` は、この測定では行っていない (認証を使う操作のため)。

## 5. 再現コマンド

```sh
# リポジトリ直下 (測定 commit 2e84269d)
git diff 2e84269d HEAD -- infra/pm-worker/src infra/pm-worker/test | wc -l
cd infra/pm-worker && pnpm install --frozen-lockfile --config.minimum-release-age=0
npm test                  # TAP 末尾の # pass / # duration_ms。wall は前後の時刻差
npm run test:unit         # 出力の Duration / Tests 行
npm run test:workers      # 出力の Duration / Tests 行
H=$(git rev-parse 2e84269d)
CI=1 ./node_modules/.bin/wrangler deploy --dry-run --outdir work/dryrun/a --define BUILD_COMMIT:$H
CI=1 ./node_modules/.bin/wrangler deploy --dry-run --outdir work/dryrun/b --define "BUILD_COMMIT:\"$H\""
CI=1 ./node_modules/.bin/wrangler deploy --dry-run --outdir work/dryrun/c --var BUILD_COMMIT:$H
CI=1 ./node_modules/.bin/wrangler deploy --dry-run --outdir work/dryrun/d
CI=1 ./node_modules/.bin/wrangler deploy --dry-run --outdir work/dryrun/e --var TARGET:999
grep -c "$H" work/dryrun/b/index.js     # 0
```
