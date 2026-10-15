# tools/pm 付録: REPORT §16 の全文 (oc-pm の refs_orphan 検出 #2337・PR #2478)

> **REPORT の付録**: `tools/pm/REPORT.md` §16 の全文 (250 行上限のため分割移動)。測定値の正本はこの付録。

## 16. oc-pm の refs_orphan 検出 (#2337・PR #2478)

- 測定 commit: `b7fb7a40` (main `b3c699d4` の取り込み merge。pm-worker のコードは main 側の変更を含めてここで確定)。修正本体は `ebfd0a41` (閉じキーワードの `owner/repo#N` と親行の規則)。取得時刻は UTC (2026-10-14)。環境: runner・Node v22.23.3。load は各測定の直前の `/proc/loadavg` の 1 分値。
- 差分の証跡: `git diff b7fb7a40 HEAD -- infra/pm-worker/src infra/pm-worker/test` の出力は 0 行 (本節を commit した後の HEAD で確認)。

### 16-1. 測定

| 項目 | 結果 |
|---|---|
| `cd infra/pm-worker && npm test` (n=3) | 213 件 PASS / 0 FAIL。10.87・10.35・10.25 s。load 0.42・0.95・1.18 (main 由来の 13 件を含む) |
| `npm run test:unit` (vitest) | 10 件 PASS / 0 FAIL。581 ms。load 1.30 |
| `npm run test:workers` (vitest + workerd) | 3 件 PASS / 0 FAIL。943 ms。load 1.30 |
| `bun build src/index.ts --target=browser --format=esm --external 'node:*'` | 96.68 KB (96,678 bytes)。`--minify` を付けると 63.31 KB (63,314 bytes) |

### 16-2. ネガコン (1 件を壊して FAIL を確認・測定 commit `b7fb7a40`)

`infra/pm-worker` を scratch に複写し (`tools/` は symlink)、baseline は 213 件 PASS。worktree は変えていない。

| 壊し方 | 結果 (全 213 件) | FAIL した項目 |
|---|---|---|
| `src/refs.ts`: CLOSE_RE の `(?:[\w.-]+\/[\w.-]+)?` を外す | FAIL 2 (PASS 211) | ネガコン (a)・解析 |
| `src/refs.ts`: 親行を `^親[:：]` (空白を許さない) に戻す | FAIL 1 (PASS 212) | 解析 (`親 : #2319`) |
| `src/webhook.ts`: `refsOnlyNums` を `[]` に | FAIL 10 (PASS 203) | 検出・(b)(c)(f)・送信・(d)(e)(g)・REST 経路 |
| `src/webhook.ts`: `pr.merged_at` の条件を外す | FAIL 1 (PASS 212) | REST 経路 |
| `src/pm.ts`: `refs_orphan` の `dayMax` 10 を 1000 に | FAIL 1 (PASS 212) | ネガコン (d) |

### 16-3. Refs のみの判定の差 (指標と refs_orphan・未統一)

同じ本文に 2 つの判定を当てた結果。`refsOnlyBody` は指標 `refs_only_merge_rate_24h` (`src/webhook.ts`・#2335)、`refsOnlyNumbers` は refs_orphan (`src/refs.ts`)。指標の値を変えるかは PM 判断のため、本 PR では統一しない。追跡は #2623 ([CI-115])。(#2623 で統一済み。以下の表は統一前の記録。統一後の実測は [`REPORT_APPENDIX_2623.md`](REPORT_APPENDIX_2623.md))

| 入力 | 指標 (`refsOnlyBody`) | refs_orphan (`refsOnlyNumbers`) |
|---|---|---|
| `Closes:#6 Refs #5` | true (指標が閉じキーワードを取りこぼす) | false (正) |
| `Refs owner/repo#5` | true (別リポの番号を Refs と数える) | false (同じリポの親ではない) |
| `Refs:#5` | false | true |
| `Refs #12345678` | true | false (番号は 7 桁まで) |

両者が一致する例: `Closes owner/repo#6 Refs #5`・`Fixes owner/repo#6` + `Refs #5`・`Closes #6` + `Refs #5` (両方 false)、`Refs #5` (両方 true)。

親行は `src/classify.ts`・`tools/pm/launch_issues.py` と同じ規則に揃えた (最初の `親:` 行の最初の `#N` だけ。`親 : #N` の空白を許す)。`親: #10` と `親: #11` の併記は 10 だけを親とする。

### 16-4. 検証範囲

- 検証は fetch のモック (node:test と vitest) まで。実 GitHub API・Cloudflare 上の Worker・live の送信は未実行。
- `LIVE_*` のスイッチの値は変更していない。
- 取り込みの経緯: main `5745f0c9`・`d460d139`・`322f81b6` (競合解消は各 merge の commit message)、main `80d02d77` (競合なし)。
