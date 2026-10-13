#!/bin/bash
# rerun_review.sh <PR 番号> [oc_artifacts の素材名...]
# PR 本文に oc_artifacts: 行を (無ければ) 追加し、API で本文の反映を確認してから close → reopen で
# review を再起動する。本文編集の反映前に reopen して素材が渡らなかった失敗 (PR #305・#324) の再発防止。
# 待機は sleep ではなく `timeout N tail -f /dev/null` (sleep 禁止ルール)。
set -uo pipefail
R="${REPO:-signature-studio/signature-studio-dev}"
pr="$1"; shift
want="$*"
tmp="$(mktemp)"
wait_s() { timeout "$1" tail -f /dev/null >/dev/null 2>&1 || true; }

gh api "repos/$R/pulls/$pr" --jq .body > "$tmp"
if [ -n "$want" ]; then
  # 既存の行は置き換える (素材名が古い PR 用)
  grep -v '^oc_artifacts:' "$tmp" > "$tmp.new" || true
  printf '\noc_artifacts: %s\n' "$want" >> "$tmp.new"
  gh pr edit "$pr" --repo "$R" --body-file "$tmp.new" >/dev/null || { echo "edit failed"; exit 1; }
fi

expect="$(grep '^oc_artifacts:' "${tmp}.new" 2>/dev/null || grep '^oc_artifacts:' "$tmp" || true)"
[ -n "$expect" ] || { echo "no oc_artifacts line in PR #$pr body"; exit 2; }

# 本文の反映を API で確認 (最大 12 回 x 5 秒)
for i in $(seq 1 12); do
  now="$(gh api "repos/$R/pulls/$pr" --jq .body | grep '^oc_artifacts:' || true)"
  [ "$now" = "$expect" ] && break
  wait_s 5
done
[ "$now" = "$expect" ] || { echo "body edit not visible after 60s"; exit 3; }
# 反映後にさらに数秒置き、Actions が読む event payload にも載るようにする
wait_s 8

gh pr close "$pr" --repo "$R" >/dev/null 2>&1 || true
gh pr reopen "$pr" --repo "$R" 2>&1 | tail -1
echo "restarted review for PR #$pr with: $expect"
rm -f "$tmp" "$tmp.new"
