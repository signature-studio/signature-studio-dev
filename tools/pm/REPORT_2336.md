# PM Worker: 規則 A の自動 close (#2336) の実測

> **正本**: 運用手順 (判定条件・保存の範囲・戻し方・`LIVE_CLOSE`) は `infra/pm-worker/README.md` の『自動 close: 規則 A』。
> 本書は測定値だけを持つ。`tools/pm/REPORT.md` (§12 までの PM 運用の実測) とは別に置く (250 行上限のため)。

## 1. 結論

- 規則 A (merged PR を持つ親 issue を閉じる) を `infra/pm-worker/src/autoclose.ts` に実装した。**既定は記録のみ** (`counters.wouldClose`)。GitHub へ書くのは `LIVE_CLOSE="1"` のときだけ。
- 実データ (REST の生 JSON・取得 2026-10-14 15:14Z) で、Worker の判定と**別実装 (Python・本文の正規表現だけ)** の再計算が一致した (差分 0)。候補は全履歴 27 件・24 時間窓 22 件。
- 判定条件 (a)〜(g) のネガコンは単体テストで効くことを確かめた。各条件を外すと対応テストが FAIL する (§4)。実データでも、各除外理由が 0 件ではない (§3)。

## 2. 測定の対象と再現

- 検証起点 (測定した commit): **`d119e5e2`** (origin/main `b016a6e7` の取り込み merge)。競合は 3 件 (`docs/DOC_MAP.md`: 両方の行を残す / `infra/pm-worker/src/webhook.ts`: `PrState`・`applyPr` とも規則 A の `closes`・`mentions` と main の `mergedAt`・`refsOnly` を両方残す / `infra/pm-worker/test/status.test.ts`: キーの和集合)。規則 A のコードは実装 `9a478217`・照合テスト `c7d5e4b6`・実データ照合スクリプト `0bf3aa8f` から変えていない。main 側の変更 (launch 観測・run の作成時刻・自律運転の指標・`refsOnly`・`mergedAt` の保存) は規則 A の判定 (`autoclose.ts`) に触れない。
- 規則 A の実装 (`src/autoclose.ts`・`src/refs.ts`・テスト・フィクスチャ) の差分: `git diff 0bf3aa8f HEAD -- infra/pm-worker/src/autoclose.ts infra/pm-worker/src/refs.ts infra/pm-worker/test/autoclose.test.ts infra/pm-worker/test/fixtures/rule_a.input.json infra/pm-worker/test/rule_a_crosscheck.py` が空であること。
- 測定 commit からの差分: `git diff d119e5e2 HEAD -- infra/pm-worker tools/pm/rule_a_realcheck.py tools/pm/rule_a_realcheck.sh` は空 (測定の後に入るのはこの REPORT の更新だけ)。
- 再現:
  - 実データ照合 (読み取りのみ): `bash tools/pm/rule_a_realcheck.sh` (gh の認証が要る。大物は `${RUNNER_TEMP}` 配下の一時ディレクトリに置く)。
  - 単体: `cd infra/pm-worker && npm test` (node `--test`・依存パッケージ無し)。
  - 固定 fixture の照合: `python3 infra/pm-worker/test/rule_a_crosscheck.py infra/pm-worker/test/fixtures/rule_a.input.json` と TS 側の `test/autoclose.test.ts` の 1 件 (Python と同じ候補)。

## 3. 実データ dry-run (取得 2026-10-14 15:14Z)

取得: open issue (PR を除く)・open PR・closed PR (全履歴)・blocked_by の REST 応答 (`tools/pm/rule_a_realcheck.sh` が取る。生データは一時ディレクトリに置き、リポジトリには含めない)。
Worker の経路 (`applyEvent` で REST の payload を保存し、`detectRuleA` で判定) と、独立した再計算 (`tools/pm/rule_a_realcheck.py`) を比べた。

| 窓 | Worker | 独立 | 差分 (Worker のみ / 独立のみ) | 子を持つ親 (open) | 除外: 子以外が blocking | 除外: open PR が参照 | 除外: needs-user-input | 除外: merged PR 無し |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| 全履歴 | 27 | 27 | 0 / 0 | 67 | 7 | 7 | 0 | 26 |
| 24 時間窓 (updated_at) | 22 | 22 | 0 / 0 | 67 | 5 | 6 | 0 | 34 |

- 窓の定義: Worker の全体同期と同じ (closed PR を `updated_at` の新しい順に、24 時間より前まで読む)。窓を外れた merged PR は保存されないので、その親は閉じない (保守的)。
- 除外の数: 子を持つ親 67 = 候補 + 除外 (全履歴: 27 + 7 + 7 + 0 + 26 = 67。窓: 22 + 5 + 6 + 0 + 34 = 67)。取得時の needs-user-input の除外は 0 件 (realcheck の `excluded_by` に載らない)。
- 注意: リポジトリの issue / PR は他の作業で動く。同日の取得は 14:41Z に全履歴 28・窓 23、14:47Z に 27・22、14:51Z に 26・21、15:14Z に 27・22 (その間の issue / PR の更新による)。数値は取得時点の値。Worker と独立の一致 (差分 0) は取得のたびに確かめる。
- 観測: 14:41Z 取得の全履歴 28 件は、すべて `Refs #N` で merge された PR を持っていた (`Closes` は 0 件。14:51Z の 26 件は未集計)。規則 A の定義 (Closes / Refs / Fixes) に従う結果で、既存の『Refs のみで merge』運用 (issue #2336 の背景) と同じ形。

## 4. ネガコンと単体テスト

`infra/pm-worker/test/autoclose.test.ts` (24 件。うち Python との照合 1 件。`npm test` は全 198 件 PASS (HEAD `d119e5e2`)。198 には規則 A 以外の main 側のテストを含む)。

判定の条件を 1 つずつ外すと (`src/autoclose.ts` を一時的に書き換えて実行)、対応するテストが FAIL することを確かめた:

| 外した条件 | FAIL したテスト | 件数 |
|---|---|---:|
| (c) 親を参照する open PR の除外 | ネガコン (c) | 1 |
| (d) 子以外の blocking の除外 | ネガコン (d) | 1 |
| (d') blocked_by 不明の除外 | ネガコン (d') | 1 |
| (b) needs-user-input の除外 | ネガコン (b) | 1 |
| (a) 子が無い親の除外 | ネガコン (a)・(g) | 2 |
| (e) merged PR の要求 | ネガコン (e) | 1 |
| 移行前の保存値の判定停止 (mentions 無し) | 移行ガード | 1 |

(f) 親が closed は、open の issue だけを候補にする構造のため、条件を外す書き換えは無い (テストは基本形の不変条件として固定)。

## 5. 書き込みの経路 (dry-run / live)

| 項目 | 結果 (テスト) |
|---|---|
| 既定 (`LIVE_CLOSE` 未設定・`LIVE=1` だけ) | 書き込み 0 回。`counters.wouldClose` が増え、同じ候補は 3 時間は数えない |
| `LIVE_CLOSE="1"` | コメント (PM App の token) → `PATCH state=closed, state_reason=completed` の順。`counters.closed` |
| 1 tick の上限 | 7 件のうち 1 tick で 5 件、次の tick で残り 2 件 |
| 書き込みの失敗 | 500 の後は 24 時間再試行しない (コメントの二重投稿を防ぐ) |
| 同期が古い (`fresh=false`) | 閉じない |
| レート制限の守り (残量 < 1,500) | 閉じない。止めた候補は記録しないので、守りが解けた次の tick で閉じる |

## 6. 検証

- `npm test` (node --test・HEAD `d119e5e2`): 198 件 PASS / 0 FAIL。
- 実データ照合 (HEAD `d119e5e2`・取得 15:14Z): `bash tools/pm/rule_a_realcheck.sh` は終了コード 0・所要 43 秒 (実測)。Worker と独立の差分は全履歴・窓とも 0 / 0 (`only_worker`・`only_independent` は空)。
- 型チェック (HEAD `d119e5e2`): `tsc --noEmit --ignoreConfig --lib es2022,dom --types "" --allowImportingTsExtensions src/*.ts` は 39 件。同じ条件の origin/main (`b016a6e7`) は 34 件。増えた 5 件は全て TS5097 (`.ts` 拡張子の import。既存の import と同じ書き方)。TS5097 以外は main と同じ 7 件 (`crypto.ts` 2・`github.ts` 1・`hmac.ts` 3・`config.ts` 1 の既存の型の差)。新規の型エラーは 0。
- バンドル (HEAD `d119e5e2`・出力は `$RUNNER_TEMP`): `bun build src/index.ts --target=browser --format=esm --external 'node:*' --minify` が成功 (20 モジュール・57.92 KB)。
- 範囲外・未実行: `test:workers` (vitest + workerd) は依存 (`node_modules`) が無く未実行。Cloudflare への反映・`wrangler.toml` の変更・secret は範囲外 (依頼者 / PM)。`LIVE_CLOSE` は未設定のまま。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 24 時間窓より前に merge された PR の参照は Worker が持たない (移行前の保存値) | 該当する親は規則 A で閉じない (全履歴 27 件と窓 22 件の差。保守的な側) | PM 判断。REST で merged PR の参照を取り直す子 issue の要否 (本 run では未起票) |
| 規則 A は Refs でも閉じる (issue 本文の定義どおり)。残りの作業は子 issue が追跡している前提 | 子の起票漏れがあると、親の残作業が見えないまま閉じる | PM 判断 (親 #2319 の検収で確認) |
| `LIVE_CLOSE="1"` (live 化) と `wrangler.toml` への反映 | 反映まで記録のみ | 依頼者 / PM (Cloudflare 書き込みは範囲外) |
| `test:workers` (vitest) の CI 組み込み | 単体は node の `npm test` で代替 | 依存導入の判断 (PM) |
