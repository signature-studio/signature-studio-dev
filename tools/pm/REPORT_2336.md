# PM Worker: 規則 A の自動 close (#2336) の実測

> **正本**: 運用手順 (判定条件・保存の範囲・戻し方・`LIVE_CLOSE`) は `infra/pm-worker/README.md` の『自動 close: 規則 A』。
> 本書は測定値だけを持つ。`tools/pm/REPORT.md` (§12 までの PM 運用の実測) とは別に置く (250 行上限のため)。

## 1. 結論

- 規則 A (merged PR を持つ親 issue を閉じる) を `infra/pm-worker/src/autoclose.ts` に実装した。**既定は記録のみ** (`counters.wouldClose`)。GitHub へ書くのは `LIVE_CLOSE="1"` のときだけ。
- 実データ (REST の生 JSON・取得 2026-10-14 14:47Z 前後) で、Worker の判定と**別実装 (Python・本文の正規表現だけ)** の再計算が一致した (差分 0)。候補は全履歴 27 件・24 時間窓 22 件。
- 判定条件 (a)〜(g) のネガコンは単体テストで効くことを確かめた。各条件を外すと対応テストが FAIL する (§4)。実データでも、各除外理由が 0 件ではない (§3)。

## 2. 測定の対象と再現

- 検証起点 (測定した commit): **`0bf3aa8f`** (コードを変えた最後の commit。`9a478217` 実装・`c7d5e4b6` 照合テスト・`0bf3aa8f` 実データ照合スクリプト)。
- 差分の確認 (測定後の HEAD との差。本書を含む commit の後に実行): `git diff 0bf3aa8f HEAD -- infra/pm-worker tools/pm/rule_a_realcheck.py tools/pm/rule_a_realcheck.sh` が空であること (本書と DOC_MAP の追記は差分の範囲外)。
- 再現:
  - 実データ照合 (読み取りのみ): `bash tools/pm/rule_a_realcheck.sh` (gh の認証が要る。大物は `${RUNNER_TEMP}` 配下の一時ディレクトリに置く)。
  - 単体: `cd infra/pm-worker && npm test` (node `--test`・依存パッケージ無し)。
  - 固定 fixture の照合: `python3 infra/pm-worker/test/rule_a_crosscheck.py infra/pm-worker/test/fixtures/rule_a.input.json` と TS 側の `test/autoclose.test.ts` の 1 件 (Python と同じ候補)。

## 3. 実データ dry-run (取得 2026-10-14 14:47Z 前後)

取得: open issue 413 (PR を除く)・open PR 13・closed PR 1,244 (全履歴)・blocked_by を持つ open issue 73 件。
Worker の経路 (`applyEvent` で REST の payload を保存し、`detectRuleA` で判定) と、独立した再計算 (`tools/pm/rule_a_realcheck.py`) を比べた。

| 窓 | Worker | 独立 | 差分 (Worker のみ / 独立のみ) | 子を持つ親 (open) | 除外: 子以外が blocking | 除外: open PR が参照 | 除外: needs-user-input | 除外: merged PR 無し |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| 全履歴 | 27 | 27 | 0 / 0 | 58 | 6 | 6 | 1 | 18 |
| 24 時間窓 (updated_at) | 22 | 22 | 0 / 0 | 58 | 4 | 5 | 1 | 26 |

- 窓の定義: Worker の全体同期と同じ (closed PR を `updated_at` の新しい順に、24 時間より前まで読む)。窓を外れた merged PR は保存されないので、その親は閉じない (保守的)。
- 除外の数: 子を持つ親 58 = 候補 + 除外 (全履歴: 27 + 6 + 6 + 1 + 18 = 58。窓: 22 + 4 + 5 + 1 + 26 = 58)。
- 注意: リポジトリの issue / PR は他の作業で動く。同日 14:41Z の取得 (全履歴 28・窓 23) からの差は、その間の更新による。数値は取得時点の値。Worker と独立の一致 (差分 0) は取得のたびに確かめる。
- 観測: 14:41Z 取得の全履歴 28 件は、すべて `Refs #N` で merge された PR を持っていた (`Closes` は 0 件)。規則 A の定義 (Closes / Refs / Fixes) に従う結果で、既存の『Refs のみで merge』運用 (issue #2336 の背景) と同じ形。

## 4. ネガコンと単体テスト

`infra/pm-worker/test/autoclose.test.ts` (24 件。うち Python との照合 1 件。`npm test` は全 171 件 PASS)。

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

- `npm test` (node --test・HEAD `0bf3aa8f`): 171 件 PASS / 0 FAIL (実行 13.7 秒)。
- 型チェック: `tsc --noEmit --ignoreConfig --lib es2022,dom --types "" src/*.ts` で、エラーは main と同じ 6 件 (`crypto.ts`・`github.ts`・`hmac.ts` の既存の型の差)。今回の変更による新規エラーは 0。
- バンドル: `bun build src/index.ts --target=browser --format=esm --external 'node:*' --minify` が成功 (19 モジュール)。
- 範囲外・未実行: `test:workers` (vitest + workerd) は依存 (`node_modules`) が無く未実行。Cloudflare への反映・`wrangler.toml` の変更・secret は範囲外 (依頼者 / PM)。`LIVE_CLOSE` は未設定のまま。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 24 時間窓より前に merge された PR の参照は Worker が持たない (移行前の保存値) | 該当する親は規則 A で閉じない (全履歴 27 件と窓 22 件の差。保守的な側) | PM 判断。REST で merged PR の参照を取り直す子 issue の要否 (本 run では未起票) |
| 規則 A は Refs でも閉じる (issue 本文の定義どおり)。残りの作業は子 issue が追跡している前提 | 子の起票漏れがあると、親の残作業が見えないまま閉じる | PM 判断 (親 #2319 の検収で確認) |
| `LIVE_CLOSE="1"` (live 化) と `wrangler.toml` への反映 | 反映まで記録のみ | 依頼者 / PM (Cloudflare 書き込みは範囲外) |
| `test:workers` (vitest) の CI 組み込み | 単体は node の `npm test` で代替 | 依存導入の判断 (PM) |
