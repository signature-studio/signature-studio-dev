# tools/pm 付録: 実装 App の自己 merge の実測 (#2600・PR #2624)

> **tools/pm の付録**: 実装 App の自己 merge の実測の全文。`tools/pm/REPORT.md` は 250 行上限のため本節を持たない (main の §19 は #2648 の節)。測定値の正本はこの付録。

## 実装 App の自己 merge の実測 (#2600・PR #2624)

- **測定の基準**: 基準時刻 2026-10-14T16:36:11Z (UTC)。集計窓は mergedAt が 2026-10-13T16:36:11Z〜2026-10-14T16:36:11Z の 24 時間。取得: `gh pr list --repo signature-studio/signature-studio-dev --state merged --search "merged:2026-10-13T16:36:11Z..2026-10-14T16:36:11Z" --limit 1000 --json number,createdAt,mergedAt,mergedBy` (件数 980 は上限 1000 未満で、窓の全件)。PR #2624 の fix run で取得。
- **件数と割合**: 980 件のうち merged_by が実装 App (`app/opencode-for-signature-studio`) の自己 merge は **119 件 (12.14%)**。内訳は reviewer App 859 件・人 2 件。全件の数え上げのため信頼区間は付けない。
- **作成から merge まで** (119 件の `createdAt`→`mergedAt`): 最小 4 秒・中央値 12 秒・最大 137 秒。
- **merge 前の review** (119 件・`pulls/N/reviews` の `submitted_at` ≤ `mergedAt`): 118 件は 0 件。1 件 (#1927) は oc-reviewer App の `CHANGES_REQUESTED` の 10 秒後に実装 App が merge した。
- **原因**: `.github/prompts/implementer.md` 規範 9 が `gh pr merge --auto --merge` を指示していた (`8e4b343d`、2026-10-12 追加)。main に承認必須の Ruleset が無く (`branches/main/protection` は 404、ruleset 24866584 に `pull_request` ルールは無い)、`allow_auto_merge: true` のため Auto Merge は即時 merge になった。
- **対応**: 規範 9 から Auto Merge の指示を消し、実装者の merge を禁止した。merge は approve した reviewer が同じ run で行う (PR #2624)。
- **未検証**: 承認の無い PR への auto-merge の挙動 (REST に有効化 API が無く GraphQL が要る)。Ruleset 未適用の下での技術的な防止 (PR #2624 の未解決表)。
