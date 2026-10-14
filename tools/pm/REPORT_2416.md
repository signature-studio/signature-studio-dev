# tools/pm 付録 — #2416 `/status` の build (deploy commit) の測定と wrangler の確認

> **正本の宣言**: `infra/pm-worker/README.md` の build 節 (『再デプロイ』手順 4・5、『ロールバック』3) の根拠。PR #2477 の差し戻し round 1 への対応。
> `tools/pm/REPORT.md` (250 行上限ちょうど) は変更していない。PM Worker の測定値は `tools/pm/REPORT.md` と本付録が正本 (`docs/DOC_MAP.md` §4)。
> PR #2477 が `origin/main` と競合したため main を取り込んだ (競合解消)。main は取り込み中にも進み、取り込みは 5 回。うち 4 回で `infra/pm-worker/src`・`test` が変わった (4 回目 `9a55b831` は変えていない)。5 回目 `e94dca2f` は競合解消 (`test/status.test.ts`) と main 側の src・test の変更を含む。測定は、`src`・`test` を最後に変えた commit `e94dca2f` で取り直した (§0-2)。

**結論**: 検証 HEAD `e94dca2f` の `npm test` (190 件)・`npm run test:unit` (10 件)・`npm run test:workers` (4 件) は、3 回ずつ全件 pass。`wrangler` 4.151.0 の dry-run (5 案) は全て exit 0。`--define` は引用符付きでも引用符なしでも hash は bundle に入らない (引用符なしは hash の先頭文字で結果が変わる。§3)。`--var` は bindings に `(hidden)` で出る。実 Worker での反映は未確認 (README の `[未確認]`)。

## 0. 取得方法・環境

### 0-1 版と環境

| 項目 | 値 |
|---|---|
| 測定 commit | `e94dca2f` (`Merge remote-tracking branch 'origin/main' into 2416-pm-worker-status-build`。PR #2477 の競合解消)。コードを変えた最後の commit (main の 5 回目の取り込み) |
| 検証 HEAD | `e94dca2f` (測定は HEAD と clean な作業ツリーで実施。コードは未編集。`npm ci` 後も `git status --porcelain` は空。`package*.json` は変えていない) |
| Node / npm | v22.23.3 / 10.9.9 |
| wrangler | 4.151.0 (`npx wrangler --version`) |
| vitest | v4.1.11 (`vitest run` の `RUN` 行。`package.json` は `^4.1.11`) |
| CPU | `nproc` = 4、`os.availableParallelism()` = 4 |
| `node --test` の並列数 | 3 (既定の `--test-concurrency` = `os.availableParallelism() - 1`。Node 公式 docs の Command-line API) |
| 対象 | `npm test` = `test/*.test.ts` の 16 ファイル。`npm run test:unit` = `test/unit/**/*.test.ts` の 1 ファイル (fetch をモックした Node の単体テスト。main 由来)。`npm run test:workers` = `test/runtime/**/*.test.ts` の 1 ファイル (`do.workers.test.ts`、workerd 上で実行) |

### 0-2 測定したコードと検証 HEAD の差分 (WORKFLOW §5・§6)

```sh
git diff c8f2fdc8 e94dca2f -- infra/pm-worker/src infra/pm-worker/test | wc -l   # 940 (前版の測定 commit からの差。競合解消と main の取り込みで変わった分)
git diff e94dca2f HEAD -- infra/pm-worker/src infra/pm-worker/test | wc -l       # 0 (最終 HEAD。本付録の追記だけで src・test は変えない)
```

- 前版の測定 (測定 commit `c8f2fdc8`、検証 HEAD `c8f2fdc8`。`npm test` 183 件) は、競合解消の取り込み (`e94dca2f`) で `src`・`test` が変わったため無効になった。その数値は git 履歴の `c8f2fdc8` 版に残る。
- さらに前の測定 (測定 commit `815eb526`、検証 HEAD `199bbc02`・`345eb75f`。149 件) と、中間の取り込み commit `037fa935` (162 件)・`efd86292` (180 件) も、後の取り込みで `src`・`test` が変わったため数値は置き換えた。
- 本付録の数値は、取り込み commit `e94dca2f` で測った。最終 HEAD (本付録を含む commit) の `src`・`test` の差分は上の 0 行。最終 HEAD の hash は PR 本文の検証欄に書く。

### 0-3 取得方法

- **wall**: `time.time()` を `npm run` の前後で取った差 (npm と vitest の起動・終了を含む)。
- **`npm test` の所要**: TAP 末尾の `# duration_ms` (node --test が出す全体の所要)。
- **`npm run test:workers` / `npm run test:unit` の所要**: vitest の出力行 `Duration` の値。wall とは別の量。
  差し戻し (指摘 4) の『実測 3 s』は、wall と Duration のどちらか不明だった。本付録では両方を分けて記録する。
- **load average**: `/proc/loadavg` の 1 / 5 / 15 分値を、各 run の前後で取った。1 分値は直前の run の負荷を含む。
- 変動する値は n = 3 の **min–max**。測定は 1 回ずつ直列 (並行実行なし)。依存は `npm ci` で入れたあとに測定した (測定の外)。

## 1. `npm test` (`node --experimental-strip-types --no-warnings --test 'test/*.test.ts'`)

| run | wall (s) | `# duration_ms` | pass / fail / cancelled | load (前 → 後、1/5/15 分) |
|---|---:|---:|---|---|
| 1 | 9.56 | 9398.0 | 190 / 0 / 0 | 0.52/0.47/0.20 → 1.04/0.59/0.25 |
| 2 | 9.81 | 9713.5 | 190 / 0 / 0 | 1.04/0.59/0.25 → 1.20/0.63/0.26 |
| 3 | 9.98 | 9872.0 | 190 / 0 / 0 | 1.20/0.63/0.26 → 1.39/0.69/0.29 |
| **min–max** | **9.56–9.98** | **9398.0–9872.0** | 190 / 0 / 0 (3 回とも) | 1 分値の最大 1.39 (nproc 4 未満) |

- TAP の `# tests 190`・`# suites 0`・`# skipped 0`・`# todo 0` (3 回とも同じ)。並列数は既定の 3。

## 2. `npm run test:workers` (`vitest run --config vitest.config.ts`)

| run | wall (s) | vitest `Duration` | Tests (pass / fail) | load (前 → 後、1/5/15 分) |
|---|---:|---|---|---|
| 1 | 1.81 | 1.05 s | 4 / 0 | 1.39/0.69/0.29 → 1.36/0.70/0.29 |
| 2 | 1.69 | 974 ms | 4 / 0 | 1.36/0.70/0.29 → 1.36/0.70/0.29 |
| 3 | 1.76 | 1.04 s | 4 / 0 | 1.36/0.70/0.29 → 1.33/0.70/0.29 |
| **min–max** | **1.69–1.81** | **974 ms–1.05 s** | 4 / 0 (3 回とも) | — |

- vitest の `Test Files  1 passed (1)`・`Tests  4 passed (4)` (3 回とも)。
- wall (1.69–1.81 s) と vitest の `Duration` (974 ms–1.05 s) は別の量。1 つの値に丸めて書かない。

## 2-1 `npm run test:unit` (`vitest run --config vitest.unit.config.ts`)

| run | wall (s) | vitest `Duration` | Tests (pass / fail) | load (前 → 後、1/5/15 分) |
|---|---:|---|---|---|
| 1 | 0.98 | 655 ms | 10 / 0 | 1.33/0.70/0.29 → 1.33/0.70/0.29 |
| 2 | 1.06 | 731 ms | 10 / 0 | 1.33/0.70/0.29 → 1.33/0.70/0.29 |
| 3 | 1.05 | 737 ms | 10 / 0 | 1.33/0.70/0.29 → 1.33/0.70/0.29 |
| **min–max** | **0.98–1.06** | **655–737 ms** | 10 / 0 (3 回とも) | — |

- `Test Files  1 passed (1)`・`Tests  10 passed (10)` (3 回とも)。

## 3. wrangler の `--define` / `--var` (dry-run)

すべて `CI=1 npx wrangler deploy --dry-run --outdir <tmp>/<案>` に次の引数を足したもの。`<HASH>` は `git rev-parse e94dca2f` の全 40 字 (`e94dca2f3a5f15f2228bd3dd51c542f6e9d5fab0`)。`<tmp>` は作業用の一時 dir で、確認後に削除した。dry-run は Cloudflare に接続せず、認証は不要。

| 案 | 追加した引数 | exit | bindings の `BUILD_COMMIT` | bundle (`index.js`) に hash が入るか |
|---|---|---:|---|---|
| a | `--define BUILD_COMMIT:<HASH>` (引用符なし) | 0 | 表示なし | **0 件**。bundle は d と同一 (define は `env.BUILD_COMMIT` の参照に効かない) |
| b | `--define 'BUILD_COMMIT:"<HASH>"'` (引用符あり) | 0 | 表示なし | **0 件**。bundle は d と同一 |
| c | `--var BUILD_COMMIT:<HASH>` | 0 | `env.BUILD_COMMIT ("(hidden)")` | **0 件** (runtime の binding。bundle は d と同一) |
| d | (引数なし) | 0 | 表示なし | 0 件 |
| e | `--var TARGET:999` | 0 | `env.TARGET ("(hidden)")` (`[vars]` の `"50"` を上書き) | — (binding の上書きの確認) |

- 案 a の exit は hash の先頭文字で変わる。`e94dca2f…` (英字始まり) は識別子として受理されるので exit 0。先頭が数字の hash (中間の取り込み commit `037fa935…`) では `Invalid define value (must be an entity name or JS literal)` で exit 1 になった (同じ dry-run を `037fa935` で実施)。どちらの場合も hash は bundle に入らない。
- 全ケース `Total Upload: 103.79 KiB / gzip: 32.14 KiB` (前版 `c8f2fdc8` の 94.78 KiB / 29.68 KiB。main 側の src 変更による増加)。bindings の一覧は、c のみ `BUILD_COMMIT` の行が増える (a・b・d・e は同じ一覧)。
- `index.js` は 106,279 バイト・2,420 行 (a・b・c・d・e で同一。前版 97,051 バイト・2,235 行)。
- c の値が upload の metadata で実際に渡るかは dry-run では見えない (表示は `(hidden)`)。届くことは実 Worker の `/status` でのみ確かめられる (§4-3)。

## 4. 検証範囲・ネガティブコントロール・未確認

### 4-1 検証範囲

- `npm test` 190 件・`npm run test:unit` 10 件・`npm run test:workers` 4 件を、検証 HEAD と同一のコードで 3 回ずつ実行。wrangler dry-run は 5 案を各 1 回。
- `/status` の `build` の挙動は、既存テストで確認済み: `test/status.test.ts` (`BUILD_COMMIT` 未設定で `null`・形式が違う値は `null`・キー集合のスナップショットに `build` を含む)、`test/runtime/do.workers.test.ts` (workerd の DO env から hash を読む・未設定で `null`)。
- wrangler は dry-run のみ (bindings の表示と bundle の内容)。

### 4-2 ネガティブコントロール

- **a**: `--define` の引用符なしは、hash が英字で始まれば通るが、bundle は d と同一で hash は入らない。数字で始まる hash では build が失敗する (§3 の注)。どちらも hash を bundle に入れられないので、README 手順 4 (c) の『`--define` は採らない』の根拠になる。
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
# リポジトリ直下 (検証 HEAD e94dca2f)
git diff e94dca2f HEAD -- infra/pm-worker/src infra/pm-worker/test | wc -l
cd infra/pm-worker && npm ci
npm test                  # TAP 末尾の # pass / # duration_ms。wall は前後の時刻差
npm run test:unit         # 出力の Duration / Tests 行
npm run test:workers      # 出力の Duration / Tests 行
H=$(git rev-parse e94dca2f)
CI=1 npx wrangler deploy --dry-run --outdir <tmp>/a --define BUILD_COMMIT:$H
CI=1 npx wrangler deploy --dry-run --outdir <tmp>/b --define "BUILD_COMMIT:\"$H\""
CI=1 npx wrangler deploy --dry-run --outdir <tmp>/c --var BUILD_COMMIT:$H
CI=1 npx wrangler deploy --dry-run --outdir <tmp>/d
CI=1 npx wrangler deploy --dry-run --outdir <tmp>/e --var TARGET:999
grep -c "$H" <tmp>/b/index.js     # 0
```
