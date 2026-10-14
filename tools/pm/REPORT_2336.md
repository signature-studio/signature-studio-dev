# PM Worker: 規則 A の自動 close (#2336) の実測

> **正本**: 運用手順 (判定条件・保存の範囲・戻し方・`LIVE_CLOSE`) は `infra/pm-worker/README.md` の『自動 close: 規則 A』。
> 本書は測定値だけを持つ。`tools/pm/REPORT.md` (§12 までの PM 運用の実測) とは別に置く (250 行上限のため)。

## 1. 結論

- 規則 A (merged PR を持つ親 issue を閉じる) を `infra/pm-worker/src/autoclose.ts` に実装した。**既定は記録のみ** (`counters.wouldClose`)。GitHub へ書くのは `LIVE_CLOSE="1"` のときだけ。
- 実データ (REST の生 JSON・取得 2026-10-14 15:55Z・issue を読める token) で、Worker の判定と**別実装 (Python・本文の正規表現だけ)** の再計算が一致した (差分 0)。候補は全履歴 23 件・24 時間窓 18 件。
- round 3 の修正: blocked_by の一覧が件数に足りない (件数 `total_blocked_by` > 一覧の件数) open issue を『不明』として扱い、同期 (`syncBlockers`) でその一覧を REST から取り直す。旧判定では、この状態の issue があっても親が閉じる候補になった (§4 の (d'') を旧条件に戻すと FAIL)。

## 2. 測定の対象と再現

- 測定 commit (コードを変えた最後の commit): **`60379098`** (round 3 の修正)。
- 測定 commit から HEAD までのコード差分: `git diff 60379098 HEAD -- infra/pm-worker tools/pm/rule_a_realcheck.py tools/pm/rule_a_realcheck.sh` は空 (HEAD の差分は `tools/pm/REPORT_2336.md` と `docs/DOC_MAP.md` だけで、範囲外)。
- 再現:
  - 実データ照合 (読み取りのみ): `bash tools/pm/rule_a_realcheck.sh` (gh の認証が要る。issue の一覧は issue を読める token で取る。大物は `${RUNNER_TEMP}` 配下に置く)。照合の対象が空 (open issue 0・closed PR 0・子を持つ親 0) のときは差分 0 でも exit 2 で止まる。
  - 単体: `cd infra/pm-worker && npm test` (node `--test`・依存パッケージ無し)。
  - 固定 fixture の照合: `python3 infra/pm-worker/test/rule_a_crosscheck.py infra/pm-worker/test/fixtures/rule_a.input.json` と TS 側の `test/autoclose.test.ts` の 1 件 (Python と同じ候補)。

## 3. 実データ dry-run (取得 2026-10-14 15:55Z)

取得: `tools/pm/rule_a_realcheck.sh` が取る REST の生 JSON (生データは一時ディレクトリに置き、リポジトリには含めない)。

| 取得する対象 | 件数 |
|---|---:|
| open issue (PR を除く) | 428 |
| open PR | 29 |
| closed PR (全履歴) | 1,305 |
| closed PR (24 時間窓・updated_at) | 991 |
| blocked_by を取った open issue (件数 > 0) | 66。うち件数と一覧の件数が食い違う issue は 0 件 |

Worker の経路 (`applyEvent` で REST の payload を保存し、`detectRuleA` で判定) と、独立した再計算 (`tools/pm/rule_a_realcheck.py`) を比べた。

| 窓 | Worker | 独立 | 差分 (Worker のみ / 独立のみ) | 子を持つ親 (open) | 除外: needs-user-input | 除外: merged PR 無し | 除外: open PR が参照 | 除外: 子以外が blocking | 除外: 一覧が不明 |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| 全履歴 | 23 | 23 | 0 / 0 | 63 | 0 | 22 | 10 | 8 | 0 |
| 24 時間窓 (updated_at) | 18 | 18 | 0 / 0 | 63 | 0 | 29 | 10 | 6 | 0 |

- 除外の数え方: `independent()` が上の順 (needs-user-input → merged PR 無し → open PR の参照 → 子以外の blocking → 一覧が不明) で、1 つの理由に割り当てる。候補 + 除外 = 子を持つ親 (全履歴: 23 + 22 + 10 + 8 = 63。窓: 18 + 29 + 10 + 6 = 63)。
- 窓の定義: Worker の全体同期と同じ (closed PR を `updated_at` の新しい順に、24 時間より前まで読む)。窓を外れた merged PR は保存されないので、その親は閉じない (保守的な側)。
- 前回の測定 (`028ad1f2`・15:39Z・全履歴 27 / 窓 22) は、レビュワーの token では issue 一覧が PR だけを返し、issue 側が 0 件になって再現できなかった。今回は issue を読める token で取り直した。件数は取得時点の issue / PR の状態で変わる (`rule_a_realcheck.py` の出力の `input` に取得件数を出す)。

## 4. ネガコンと単体テスト

`infra/pm-worker/test/autoclose.test.ts` (27 件。判定・保存・dry-run / live・同期の各テストを含む)。`npm test` は全 215 件 PASS (HEAD `60379098`)。

判定の条件を 1 つずつ外す (旧条件に戻す) と、対応するテストが FAIL する。`src/autoclose.ts` を一時的に書き換えて `node --test test/autoclose.test.ts` を実行し、TAP の `not ok` を数えた。Python 照合 (`rule_a_crosscheck.py` を呼ぶ 1 件) とエンジンの LIVE_CLOSE のネガコンを含む。実行後に元へ戻し、差分 0 を確認した。

| 外した条件 | FAIL 件数 | FAIL したテスト |
|---|---:|---|
| (a) 子が無い親の除外 | 3 | ネガコン (a)・(g)・Python 照合 |
| (b) needs-user-input の除外 | 1 | ネガコン (b) |
| (c) 親を参照する open PR の除外 | 2 | ネガコン (c)・Python 照合 |
| (d) 子以外の blocking の除外 | 2 | ネガコン (d)・Python 照合 |
| (d') 一覧が不明な issue の除外 | 2 | ネガコン (d')・(d'') |
| (e) merged PR の要求 | 3 | ネガコン (e)・Python 照合・LIVE_CLOSE のネガコン |
| 移行前の保存値の判定停止 (mentions 無し) | 1 | 移行ガード |
| (d'') 不明の判定を旧条件 (一覧が無いときだけ) に戻す | 1 | ネガコン (d'') |

(f) 親が closed: 対象は open の issue だけという構造のため、外す書き換えは無い (基本形の不変条件として固定)。

前回 (round 1) の表は数えた範囲が違ったため、この表で置き換えた。

## 5. 書き込みの経路 (dry-run / live)

| 項目 | 結果 (テスト) |
|---|---|
| 既定 (`LIVE_CLOSE` 未設定・`LIVE=1` だけ) | 書き込み 0 回。`counters.wouldClose` が増え、同じ候補は 3 時間は数えない |
| `LIVE_CLOSE="1"` | コメント (PM App の token) → `PATCH state=closed, state_reason=completed` の順。`counters.closed` |
| 1 tick の上限 | 7 件のうち 1 tick で 5 件、次の tick で残り 2 件 |
| 書き込みの失敗 | 500 の後は 24 時間再試行しない (コメントの二重投稿を防ぐ) |
| 同期が古い (`fresh=false`) | 閉じない |
| レート制限の守り (残量 < 1,500) | 閉じない。止めた候補は記録しないので、守りが解けた次の tick で閉じる |

## 6. 検証 (測定 commit `60379098`)

- `npm test` (node --test・HEAD `60379098`): 215 件 PASS / 0 FAIL (前回 212 件に、今回の 3 件を足した: (d'')・言及の件数上限・同期による一覧の取り直し)。
- 実データ照合 (HEAD `60379098`・取得 15:55Z): `bash tools/pm/rule_a_realcheck.sh` は終了コード 0・所要 47 秒。Worker と独立の差分は全履歴・窓とも 0 / 0。
- 型チェック (HEAD `60379098`): `tsc --noEmit --ignoreConfig --lib es2022,dom --types "" --allowImportingTsExtensions src/*.ts` は 7 件 (`config.ts` 1・`crypto.ts` 2・`github.ts` 1・`hmac.ts` 3 の既存の型の差。前回と同じ件数・同じファイル)。新規の型エラーは 0。
- バンドル (HEAD `60379098`): `bun build src/index.ts --target=browser --format=esm --external 'node:*' --minify` が成功 (index.js 63.91 KB)。
- vitest (`npm run test:unit` / `test:workers`): 前回 (`028ad1f2`) の実行結果 (10 件 / 3 件 PASS) のまま。HEAD `60379098` では再実行していない。
- 範囲外・未実行: Cloudflare への反映・`wrangler.toml` の変更・secret は範囲外 (依頼者 / PM)。`LIVE_CLOSE` は未設定のまま。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 24 時間窓より前に merge された PR の参照は Worker が持たない (移行前の保存値) | 該当する親は規則 A で閉じない (全履歴 23 件と窓 18 件の差。保守的な側) | PM 判断 (REST で merged PR の参照を取り直す子 issue の要否。本 run では未起票) |
| 規則 A は Refs でも閉じる (issue 本文の定義どおり)。残りの作業は子 issue が追跡している前提 | 子の起票漏れがあると、親の残作業が見えないまま閉じる | PM 判断 (親 #2319 の検収で確認) |
| `LIVE_CLOSE="1"` (live 化) と `wrangler.toml` への反映 | 反映まで記録のみ | 依頼者 / PM (Cloudflare 書き込みは範囲外) |
| `test:unit` / `test:workers` (vitest) の CI 組み込み。HEAD `60379098` での再実行 | CI では node の `npm test` だけが回る | PM 判断 (依存導入) |
| 起動側の分類 (`src/engine.ts` の `snapshot`) も、件数が一覧より多い状態を『不明』として扱わない (一覧が `[]` でも既知の『blocker なし』)。配送の取りこぼしで blocked の issue に着手しうる | 規則 A の範囲外。実データでは件数と一覧の食い違いは 0 件 | PM 判断 (規則 A と同じ条件に揃える子 issue の要否。本 run では未起票) |
