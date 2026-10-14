#!/bin/bash
# test-pr-lint.sh — pr-lint.sh を一時 git repo の fake PR で検証する (#2322)。
# 実行: bash .github/scripts/tests/test-pr-lint.sh   (全て通れば exit 0、1 件でも落ちれば exit 1)
# CI: .github/workflows/scripts-test.yaml が .github/scripts/** の変更ごとに実行する (配線は別 issue CI-52)。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../pr-lint.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
R="$TMP/repo"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

git init -q -b main "$R"
g() { git -C "$R" "$@"; }
mkdir -p "$R/docs" "$R/tools/x" "$R/src"
printf '%s\n' '| `REPORT.md` (日本語) | **250 行** | 分割 |' > "$R/docs/DOC_MAP.md"
for i in $(seq 1 250); do echo "line $i"; done > "$R/tools/x/REPORT.md"
echo base > "$R/src/a.txt"
g add docs tools src && g commit -qm base

pass=0 fail=0
ok() { pass=$((pass + 1)); printf 'ok   %s\n' "$1"; }
ng() { fail=$((fail + 1)); printf 'FAIL %s\n' "$1"; }

new_case() { g checkout -q -B "$1" main; }
commit_case() { g add docs tools src && g commit -q --allow-empty -m "$1"; }
body() { printf '%b' "$1" > "$TMP/body.md"; echo "$TMP/body.md"; }
# lint <body-file> [strict]: OUT と RC に結果を入れる
lint() {
  local strict="${2:-1}"
  OUT="$(cd "$R" && OC_LINT_STRICT="$strict" bash "$SCRIPT" --base main --head "$(g rev-parse --abbrev-ref HEAD)" --body-file "$1" 2>&1)"
  RC=$?
}
has_rule() { grep -qE "^[^ ]+:[0-9]+: $1: " <<< "$OUT"; }
has_violation() { grep -qE '^[^ ]+:[0-9]+: [a-z-]+: ' <<< "$OUT"; }

# --- 違反の検出 (OC_LINT_STRICT=1 で終了 1) ---

new_case v-artifacts
echo "x" >> "$R/src/a.txt"; commit_case v-artifacts
lint "$(body 'Closes #2147\n\noc_artifacts: fetchsh\n')"
{ [ "$RC" = 1 ] && has_rule oc-artifacts; } && ok "#2147 型: oc_artifacts: fetchsh を検出" || ng "#2147 型: oc_artifacts: fetchsh を検出 (rc=$RC)"

new_case v-abspath
echo 'path=$HOME/analysis/x' >> "$R/src/a.txt"; commit_case v-abspath
lint "$(body 'Refs #2239\n理由: test\n')"
{ [ "$RC" = 1 ] && has_rule repo-abs-path; } && ok "#2239 型: \$HOME/analysis/x の追加行を検出" || ng "#2239 型: \$HOME/analysis/x の追加行を検出 (rc=$RC)"

new_case v-closes
echo "y" >> "$R/src/a.txt"; commit_case v-closes
lint "$(body 'Closes #2250\n\n| 受入 | 結果 |\n|---|---|\n| 1 | 未達 |\n')"
{ [ "$RC" = 1 ] && has_rule closes-unmet; } && ok "#2250 型: Closes なのに未達 [ ] を検出" || ng "#2250 型: Closes なのに未達 [ ] を検出 (rc=$RC)"

new_case v-closes-cell
echo "z" >> "$R/src/a.txt"; commit_case v-closes-cell
lint "$(body 'Closes #2250\n\n| 受入 | 結果 |\n|---|---|\n| 1 | 未達 (子 issue #2331 へ) |\n')"
{ [ "$RC" = 1 ] && has_rule closes-unmet; } && ok "表セル 未達 (…) を検出" || ng "表セル 未達 (…) を検出 (rc=$RC)"

new_case v-refs-prose
echo "w" >> "$R/src/a.txt"; commit_case v-refs-prose
lint "$(body 'Refs #2300\n\n背景として理由を述べる。\n')"
{ [ "$RC" = 1 ] && has_rule refs-reason; } && ok "Refs #N: 散文の 理由 だけでは合格にしない" || ng "Refs #N: 散文の 理由 だけでは合格にしない (rc=$RC)"

new_case v-report
echo "line 251" >> "$R/tools/x/REPORT.md"; commit_case v-report
lint "$(body 'Closes #1\n')"
{ [ "$RC" = 1 ] && has_rule report-lines; } && ok "REPORT 251 行を検出" || ng "REPORT 251 行を検出 (rc=$RC)"

new_case v-docmap
mkdir -p "$R/tools/y" && printf 'a\nb\n' > "$R/tools/y/REPORT.md"; commit_case v-docmap
lint "$(body 'Closes #1\n')"
{ [ "$RC" = 1 ] && has_rule doc-map; } && ok "新規 REPORT の DOC_MAP 未登録を検出" || ng "新規 REPORT の DOC_MAP 未登録を検出 (rc=$RC)"

new_case v-warn-only
echo "x" >> "$R/src/a.txt"; commit_case v-warn-only
lint "$(body 'Closes #2147\n\noc_artifacts: fetchsh\n')" 0
{ [ "$RC" = 0 ] && has_violation && grep -q '::warning::' <<< "$OUT"; } && ok "既定 (非 strict) は警告のみ終了 0" || ng "既定 (非 strict) は警告のみ終了 0 (rc=$RC)"

# --- ネガコン (全て終了 0・違反 0 件) ---

new_case n-refs-reason
echo "x" >> "$R/src/a.txt"; commit_case n-refs-reason
lint "$(body 'Refs #2300\n\n理由: 残作業は次 PR で対応\n')"
{ [ "$RC" = 0 ] && ! has_violation; } && ok "ネガ: 正当な Refs #N + 理由行" || ng "ネガ: 正当な Refs #N + 理由行 (rc=$RC)"

new_case n-plugins
echo "x" >> "$R/src/a.txt"; commit_case n-plugins
lint "$(body 'Closes #1\n\noc_artifacts: fl-win64 plugins-ott\n')"
{ [ "$RC" = 0 ] && ! has_violation; } && ok "ネガ: oc_artifacts: fl-win64 plugins-ott" || ng "ネガ: oc_artifacts: fl-win64 plugins-ott (rc=$RC)"

new_case n-none
echo "x" >> "$R/src/a.txt"; commit_case n-none
lint "$(body 'Closes #1\n\noc_artifacts: none\n')"
{ [ "$RC" = 0 ] && ! has_violation; } && ok "ネガ: oc_artifacts: none" || ng "ネガ: oc_artifacts: none (rc=$RC)"

new_case n-entry-id
echo 'see [WIN64] in docs/REFERENCES.md' >> "$R/src/a.txt"; commit_case n-entry-id
lint "$(body 'Closes #1\n')"
{ [ "$RC" = 0 ] && ! has_violation; } && ok "ネガ: [WIN64] のエントリ ID 参照" || ng "ネガ: [WIN64] のエントリ ID 参照 (rc=$RC)"

new_case n-sync-exempt
echo "sync" >> "$R/docs/STATUS.md"; commit_case n-sync-exempt
OUT="$(cd "$R" && OC_LINT_STRICT=1 bash "$SCRIPT" --base main --head HEAD --body-file "$(body 'Closes #2\n\n| 受入 |\n|---|\n| 1 未達 |\n')" --title 'docs(status): sync 2026-10-14' 2>&1)"; RC=$?
{ [ "$RC" = 0 ] && ! has_violation; } && ok "ネガ: docs(status): sync の STATUS のみ PR は (c) 対象外" || ng "ネガ: docs(status): sync の STATUS のみ PR は (c) 対象外 (rc=$RC)"

new_case n-prose-mention
echo "x" >> "$R/src/a.txt"; commit_case n-prose-mention
lint "$(body 'Closes #1\n\n背景: #2250 の未達 [ ] 検出を記す。\n')"
{ [ "$RC" = 0 ] && ! has_violation; } && ok "ネガ: 本文の散文に 未達 や [ ] を書いても違反にしない" || ng "ネガ: 本文の散文に 未達 や [ ] を書いても違反にしない (rc=$RC)"

new_case n-report-250
sed -i '$ s/.*/changed/' "$R/tools/x/REPORT.md"; commit_case n-report-250
lint "$(body 'Closes #1\n')"
{ [ "$RC" = 0 ] && ! has_violation; } && ok "ネガ: REPORT ちょうど 250 行" || ng "ネガ: REPORT ちょうど 250 行 (rc=$RC)"

echo
echo "test-pr-lint: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
