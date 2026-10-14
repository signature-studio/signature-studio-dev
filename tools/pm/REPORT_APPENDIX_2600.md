# REPORT 付録 — #2600 (CI-110) 実装 agent の merge 禁止 (規範 9) の検証

`tools/pm/REPORT.md` は 250 行上限のため、本件の測定値はこの付録に置く (`docs/DOC_MAP.md` §1)。

## 1. 測定の対象と環境

- 測定 commit: **`b2355a40`** (コード・prompt・文書の最後の変更)。
- 対象: `.github/prompts/implementer.md` 規範 9、`.github/prompts/reviewer.md` 4、`.github/README.md`、`docs/WORKFLOW.md` §2・§3、`AGENTS.md` の merge 記述、`.github/scripts/tests/test-implementer-no-merge.sh` (新規)。
- 環境: GitHub Actions 系 runner (Linux)。shellcheck 0.9.0。
- 実行方法: `.github/workflows/scripts-test.yaml` と同じ glob (`.github/scripts/tests/test-*.sh`) を `GITHUB_STEP_SUMMARY=/dev/null` で 1 本ずつ実行。

## 2. 結果

| 項目 | 結果 |
|---|---|
| scripts-test の glob (9 本) | **PASS 9 / FAIL 0**。wall 23.3 s。load (1 分 / 5 分 / 15 分) は開始 0.26 / 0.34 / 0.20、終了 0.87 / 0.47 / 0.24 |
| `test-implementer-no-merge.sh` (新版 = 測定 commit の implementer.md) | pass=3 fail=0 |
| `test-implementer-no-merge.sh` (旧版 = origin/main `81799351` の implementer.md) | pass=0 fail=3。旧規範 9 の `gh pr merge --auto --merge` (49 行目) を検出して FAIL |
| `shellcheck -S warning` (新規テスト) | 0 件 |

測定 commit からの code 差分 (`git diff b2355a40 HEAD -- .github AGENTS.md docs/WORKFLOW.md`) は本付録のコミットの後も出力なし (差分 0)。本付録の commit は `tools/pm/REPORT_APPENDIX_2600.md` と `docs/DOC_MAP.md` だけを変えるため、再測定は不要。

## 3. canary 検証 (main の設定は変更しない)

canary は依頼者 (pycabbage) の session が 2026-10-14 15:49Z 頃に作った (本 run は作成していない)。対象は `zz-canary-base` (main ではない)。

| 対象 | 結果 (UTC) |
|---|---|
| Ruleset 25093156 `canary-require-review` | ref `refs/heads/zz-canary-base` のみ。`required_approving_review_count: 1`・`allowed_merge_methods: ["merge"]` |
| PR #2608 (`zz-canary-head-a` → `zz-canary-base`) | approve (oc-reviewer App) 15:50:56 → merge (mergedBy: oc-reviewer App) 15:51:03 |
| PR #2609 (`zz-canary-head-b` → `zz-canary-base`) | approve (oc-reviewer App) 15:51:08 → merge 15:51:16 |

判定: required approving review = 1 の下で、reviewer App の approve が必須承認として数えられ、reviewer の `gh pr merge --merge` が通った。
**未検証**: Auto Merge の即時 merge そのもの (canary は approve → merge の経路だけ)。Ruleset が無い main での即時 merge は #2600 本文の実測 (merge 前の review 0 件) に基づく。

## 4. 後片付け (REST で確認)

| 対象 | 操作 | 結果 |
|---|---|---|
| branch `zz-canary-head-b` | merge 時に削除 | `git/ref` が 404 (削除済み) |
| branch `zz-canary-head-a` | 本 run が `DELETE git/refs/heads/...` | 204。以後 404 |
| branch `zz-canary-base` | 本 run が `DELETE git/refs/heads/...` | 204。以後 404 |
| PR #2608・#2609 | — | MERGED のまま (閉じている) |
| Ruleset 25093156 | 本 run が `DELETE rulesets/25093156` | **403** (実装 App は administration 権限が無い)。**残存**。対象 ref が消えたため main には効かない |

## 5. main の設定 (読み取りのみ)

- Ruleset: `24866584` `Copilot review for default branch` (rules: `deletion`・`non_fast_forward`・`copilot_code_review`) のみ。**pull_request ルールは無い** (承認必須が無い)。
- `allow_auto_merge: true`、`allow_merge_commit: true`、`allow_squash_merge: false`、`allow_rebase_merge: false`。
- `branches/main/protection`: 本 run の token では 403 (権限不足で判定できない)。#2600 本文の 404 とは別の結果。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Ruleset 25093156 (`canary-require-review`) の削除 | 対象 ref `zz-canary-base` は削除済みのため main には効かない。残っているので、将来 `zz-canary-base` を作り直すと効く | 権限者 (PM・依頼者)。実装 App は削除できない (403) |
| main への承認必須 Ruleset の適用 | 無いと Auto Merge は approve 前に即時 merge になる。本 PR は実装側の Auto Merge を止めるだけ | PM 判断 (#2600 本文で範囲外) |
