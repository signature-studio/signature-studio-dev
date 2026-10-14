# tools/pm 付録 — main の Ruleset `main-require-review` の実測 (#2648・ADR D27)

> **正本の宣言**: Ruleset の測定値の正本は本書。手順は `docs/WORKFLOW.md` §2、方式の決定は `docs/DECISIONS.md` D27。
> `tools/pm/REPORT.md` §19 は参照だけを持つ (250 行上限のため分割移動。§18 は main の heartbeat 節 (#2629) が使っている)。

## 1. 測定の条件

- 測定 commit: `7f6ab0d0` (origin/main を取り込んだ commit)。Ruleset は API の読み取りだけで、変更していない。
- 取得: 2026-10-14 16:50Z (UTC)。設定と件数は同じ作業の中で取得。

## 2. 設定 (API・読み取りのみ)

- id `25094342`・name `main-require-review`・enforcement `active`・`required_approving_review_count=1`・`allowed_merge_methods=[merge]`・対象 `~DEFAULT_BRANCH` (既定ブランチ)・作成 2026-10-14 16:03:11Z。
- CODEOWNERS 要求・最後の push 後の承認・thread 解決は要求しない (いずれも `false`)。
- `bypass_actors`: キー無し (未設定)。`current_user_can_bypass=never`。issue #2648 の本文にある Admin (actor_id 5) の bypass とは一致しない。

## 3. 件数 (merge の窓)

- 24 時間窓 `merged:2026-10-13T16:03:11Z..2026-10-14T16:03:11Z` (Ruleset の作成前): **984 件** = reviewer App (`app/oc-reviewer-for-signature-studio`) 862 件・実装 App (`app/opencode-for-signature-studio`) 120 件 (12.2%)・人 2 件。`search/issues` の `total_count` も 984 (`--limit 1000` 未満のため切れていない)。
- 実装 App の 120 件: merge 前の APPROVED は **0 件**。APPROVED が 1 件でも付いたのは 22 件で、いずれも merge の後に付いた。
- reviewer App の 862 件: merge 前の APPROVED が 1 件以上あったのは 860 件。残り 2 件は、#2367 (APPROVED 11:53:35Z・merge は 11:53:18Z) と #1506 (承認なし・merge 2026-10-13 23:10:30Z)。
- 適用後の窓 `merged:2026-10-14T16:03:11Z..2026-10-14T16:26:38Z`: 21 件、全て reviewer App。実装 App は 0 件 (`search/issues` の `total_count` も 21)。

## 4. 取得方法 (再現)

窓の `<窓>` は §3 の `merged:` の値。一時ファイルは `work/` (gitignore 対象) に置く。

```sh
gh pr list --repo signature-studio/signature-studio-dev --state merged --search 'merged:<窓>' --limit 1000 --json number,mergedAt,mergedBy,reviews > work/win.json
gh api -X GET search/issues -f q='repo:signature-studio/signature-studio-dev is:pr is:merged merged:<窓>' --jq .total_count
jq '[.[] | .mergedBy.login] | group_by(.) | map({login: .[0], n: length})' work/win.json
jq '[.[] | select(.mergedBy.login=="app/opencode-for-signature-studio") | . as $pr | select([$pr.reviews[] | select(.state=="APPROVED" and .submittedAt <= $pr.mergedAt)] | length > 0)] | length' work/win.json
jq '[.[] | select(.mergedBy.login=="app/opencode-for-signature-studio") | select([.reviews[] | select(.state=="APPROVED")] | length > 0)] | length' work/win.json
```

- 3 行目の期待値は、24 時間窓で `app/oc-reviewer-for-signature-studio` 862・`app/opencode-for-signature-studio` 120・人 2。
- 4 行目 (実装 App・merge 前の APPROVED) は 0。5 行目 (実装 App・APPROVED あり) は 22。
- 旧方法 `gh pr list --state merged --limit 1000` は作成日時の新しい順に返すため、窓の merge を取りこぼす (検収時に 970 件と再現)。`--search 'merged:<窓>'` で取り直す。

## 5. PM 記録 (未再測定)

- canary: 承認前は 405、reviewer の APPROVED で通る、Admin bypass で通る。approve の 7〜8 秒後に merge が通った。取得コマンドと時刻が無いため、本書の件数とは照合していない。
- bypass は §2 のとおり未設定のため、bypass の部分は現状では再現できない。

## 6. 差分・未解決

- コード差分: `git diff 7f6ab0d0 HEAD -- .github/scripts .github/workflows` の出力は 0 行 (本節を commit した後の HEAD でも同じ。文書のみの変更)。
- 未解決 (PM 判断。追跡は #2648 のコメント): bypass の設定、reviewer token 失敗時の挙動、`gh pr merge --auto` の挙動。
