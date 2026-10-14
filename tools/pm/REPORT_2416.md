# tools/pm 付録 — #2416 `/status` の build (deploy commit) の測定と wrangler の確認

> **正本の宣言**: `infra/pm-worker/README.md` の build 節 (『再デプロイ』手順 4・5、『ロールバック』3) の根拠。PR #2477 の差し戻し round 1 への対応。
> `tools/pm/REPORT.md` (250 行上限ちょうど) は変更していない。PM Worker の測定値は `tools/pm/REPORT.md` と本付録が正本 (`docs/DOC_MAP.md` §4)。

**結論**: 検証 HEAD `199bbc02` の `npm test` (149 件) と `npm run test:workers` (4 件) は、3 回とも全件 pass。`wrangler` 4.151.0 の dry-run では、`--define` は引用符付きでのみ通り hash は bundle に入らない。`--var` は bindings に `(hidden)` で出る。実 Worker での反映は未確認 (README の `[未確認]`)。

## 0. 取得方法・環境

### 0-1 版と環境

| 項目 | 値 |
|---|---|
| 測定 commit | `815eb526` (`feat(pm-worker): /status に deploy した commit (build) を載せる (#2416)`)。コードを変えた最後の commit |
| 検証 HEAD | `199bbc02` (測定は HEAD と clean な作業ツリーで実施。コードは未編集。`npm ci` 後の `git status --porcelain` は空) |
| Node / npm | v22.23.3 / 10.9.9 |
| wrangler | 4.151.0 (`npx wrangler --version`) |
| vitest | v4.1.11 (`vitest run` の `RUN` 行。`package.json` は `^4.1.11`) |
| CPU | `nproc` = 4、`os.availableParallelism()` = 4 |
| `node --test` の並列数 | 3 (既定の `--test-concurrency` = `os.availableParallelism() - 1`。Node 公式 docs の Command-line API) |
| 対象 | `npm test` = `test/*.test.ts` の 13 ファイル。`npm run test:workers` = `test/runtime/**/*.test.ts` の 1 ファイル (`do.workers.test.ts`、workerd 上で実行) |

### 0-2 測定したコードと検証 HEAD の差分 (WORKFLOW §5・§6)

```sh
git diff 815eb526 199bbc02 -- infra/pm-worker/src infra/pm-worker/test | wc -l   # 0
git diff --stat 815eb526 199bbc02                                                  # infra/pm-worker/README.md | 2 +- (1 file changed)
```

- `815eb526..199bbc02` の commit は `199bbc02` の 1 件 (README の 1 行の文言修正)。`src/`・`test/` の差分は 0 行。
- よって測定したテストとコードは、検証 HEAD と同一。測定は docs の commit より前に行った。
- 本付録を追記した後の HEAD (`345eb75f`) でも `git diff 815eb526 345eb75f -- infra/pm-worker/src infra/pm-worker/test | wc -l` は 0 (追記後に再確認)。同じ HEAD で `npm test` を 1 回再実行: 149 pass / 0 fail、wall 13.64 s、`# duration_ms` 13460.8 (§1 の n=3 とは別の確認)。

### 0-3 取得方法

- **wall**: `date +%s.%N` を `npm run` の前後で取った差 (npm と vitest の起動・終了を含む)。
- **`npm test` の所要**: TAP 末尾の `# duration_ms` (node --test が出す全体の所要)。
- **`npm run test:workers` の所要**: vitest の出力行 `Duration` の値。wall とは別の量。
  差し戻し (指摘 4) の『実測 3 s』は、wall と Duration のどちらか不明だった。本付録では両方を分けて記録する。
- **load average**: `/proc/loadavg` の 1 / 5 / 15 分値を、各 run の前後で取った。1 分値は直前の run の負荷を含む。
  `test:workers` の 3 回は `npm test` の直後に続けて測ったので、開始時の値は直前の負荷の残り。
- 変動する値は n = 3 の **min–max**。測定は 1 回ずつ直列 (並行実行なし)。依存は `npm ci` で入れたあとに測定した (測定の外)。

## 1. `npm test` (`node --experimental-strip-types --no-warnings --test 'test/*.test.ts'`)

| run | wall (s) | `# duration_ms` | pass / fail / cancelled | load (前 → 後、1/5/15 分) |
|---|---:|---:|---|---|
| 1 | 13.90 | 13742.8 | 149 / 0 / 0 | 0.25/0.27/0.14 → 0.97/0.43/0.20 |
| 2 | 13.44 | 13304.4 | 149 / 0 / 0 | 0.97/0.43/0.20 → 1.41/0.55/0.24 |
| 3 | 13.64 | 13488.7 | 149 / 0 / 0 | 1.41/0.55/0.24 → 1.59/0.64/0.27 |
| **min–max** | **13.44–13.90** | **13304–13743** | 149 / 0 / 0 (3 回とも) | 1 分値の最大 1.59 (nproc 4 未満) |

- TAP の `# tests 149`・`# suites 0`・`# skipped 0`・`# todo 0` (3 回とも同じ)。並列数は既定の 3。

## 2. `npm run test:workers` (`vitest run --config vitest.config.ts`)

| run | wall (s) | vitest `Duration` | Tests (pass / fail) | load (前 → 後、1/5/15 分) |
|---|---:|---|---|---|
| 1 | 2.53 | 1.45 s | 4 / 0 | 1.35/0.61/0.27 → 1.35/0.61/0.27 |
| 2 | 2.52 | 1.44 s | 4 / 0 | 1.35/0.61/0.27 → 1.40/0.64/0.28 |
| 3 | 2.53 | 1.45 s | 4 / 0 | 1.40/0.64/0.28 → 1.40/0.64/0.28 |
| **min–max** | **2.52–2.53** | **1.44–1.45 s** | 4 / 0 (3 回とも) | — |

- vitest の `Test Files  1 passed (1)`・`Tests  4 passed (4)` (3 回とも)。
- wall (2.52–2.53 s) と vitest の `Duration` (1.44–1.45 s) は別の量。1 つの値に丸めて書かない。

## 3. wrangler の `--define` / `--var` (dry-run)

すべて `CI=1 npx wrangler deploy --dry-run --outdir <tmp>/<案>` に次の引数を足したもの。`<HASH>` は `git rev-parse 815eb526` の全 40 字 (`815eb5267dc4d9d7aa4e9cd5544c26f4fda9a521`)。`<tmp>` は作業用の一時 dir で、確認後に削除した。dry-run は Cloudflare に接続せず、認証は不要。

| 案 | 追加した引数 | exit | bindings の `BUILD_COMMIT` | bundle (`index.js`) に hash が入るか |
|---|---|---:|---|---|
| a | `--define BUILD_COMMIT:<HASH>` (引用符なし) | **1** | build が失敗。`Invalid define value (must be an entity name or JS literal)` | — (bundle は出ない) |
| b | `--define 'BUILD_COMMIT:"<HASH>"'` (引用符あり) | 0 | 表示なし | **0 件**。`buildCommit(env.BUILD_COMMIT)` の参照は置換されず、bundle は d と `cmp` で同一 |
| c | `--var BUILD_COMMIT:<HASH>` | 0 | `env.BUILD_COMMIT ("(hidden)")` | **0 件** (runtime の binding。bundle は d と `cmp` で同一) |
| d | (引数なし) | 0 | 表示なし | 0 件 |
| e | `--var TARGET:999` | 0 | `env.TARGET ("(hidden)")` (`[vars]` の `"50"` を上書き) | — (binding の上書きの確認) |

- 全ケース `Total Upload: 86.97 KiB / gzip: 27.40 KiB`。bindings の一覧は、c のみ `BUILD_COMMIT` の行が増える (b と d は同じ一覧)。
- `index.js` は 89,061 バイト・2,084 行 (b・c・d・e で同一)。
- c の値が upload の metadata で実際に渡るかは dry-run では見えない (表示は `(hidden)`)。届くことは実 Worker の `/status` でのみ確かめられる (§4-3)。

## 4. 検証範囲・ネガティブコントロール・未確認

### 4-1 検証範囲

- `npm test` 149 件・`npm run test:workers` 4 件を、検証 HEAD と同一のコードで 3 回ずつ実行。
- `/status` の `build` の挙動は、既存テストで確認済み: `test/status.test.ts` (`BUILD_COMMIT` 未設定で `null`・形式が違う値は `null`)、`test/runtime/do.workers.test.ts` (workerd の DO env から hash を読む・未設定で `null`)。
- wrangler は dry-run のみ (bindings の表示と bundle の内容)。

### 4-2 ネガティブコントロール

- **a**: `--define` の引用符なしは build が失敗する。引用符付き (b) は通るが hash は bundle に入らない。どちらも README 手順 4 (c) で『`--define` は採らない』とした根拠。
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
# リポジトリ直下 (検証 HEAD 199bbc02)
git diff 815eb526 HEAD -- infra/pm-worker/src infra/pm-worker/test | wc -l
cd infra/pm-worker && npm ci
npm test                  # TAP 末尾の # pass / # duration_ms。wall は前後の date 差
npm run test:workers      # 出力の Duration / Tests 行
H=$(git rev-parse 815eb526)
CI=1 npx wrangler deploy --dry-run --outdir <tmp>/a --define BUILD_COMMIT:$H
CI=1 npx wrangler deploy --dry-run --outdir <tmp>/b --define "BUILD_COMMIT:\"$H\""
CI=1 npx wrangler deploy --dry-run --outdir <tmp>/c --var BUILD_COMMIT:$H
CI=1 npx wrangler deploy --dry-run --outdir <tmp>/d
CI=1 npx wrangler deploy --dry-run --outdir <tmp>/e --var TARGET:999
grep -c "$H" <tmp>/b/index.js     # 0
```
