#!/bin/bash
# test-implementer-no-merge.sh — 実装 prompt が実装 agent に merge (gh pr merge・Auto Merge・REST/GraphQL の merge) を許していないことを検査する (#2600)。
# 実行: bash .github/scripts/tests/test-implementer-no-merge.sh [implementer.md のパス]  (全て通れば exit 0、1 件でも落ちれば exit 1)
# CI: .github/workflows/scripts-test.yaml が .github/scripts/tests/test-*.sh を glob で拾う (配線は不要)。
# 旧版 (規範 9 が `gh pr merge --auto --merge` で Auto Merge を有効化するよう指示していた版) では FAIL になる。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
F="${1:-$HERE/../../prompts/implementer.md}"
pass=0 fail=0
ok() { pass=$((pass + 1)); printf 'ok   %s\n' "$1"; }
ng() { fail=$((fail + 1)); printf 'FAIL %s\n' "$1"; }

if [ ! -f "$F" ]; then
  echo "FAIL missing file: $F"
  exit 1
fi

# merge 操作 (gh pr merge / REST の pulls/<N>/merge / GraphQL の enablePullRequestAutoMerge) に触れる行は、
# 全て「禁止」として書かれていること。許可・指示として書かれた行が 1 つでもあれば落とす。
MERGE_RE='gh pr merge|pulls/[^ `]*/merge|enablePullRequestAutoMerge'
bad="$(grep -nE "$MERGE_RE" "$F" | grep -v '禁止' || true)"
if [ -z "$bad" ]; then
  ok "merge 操作に触れる行はすべて禁止として書かれている"
else
  ng "merge を許す (禁止と書かれていない) 記述がある: $bad"
fi

grep -qE "禁止.*($MERGE_RE)" "$F" && ok "merge 操作の禁止が明記されている" || ng "merge 操作の禁止が明記されていない"

grep -qF '実装者は自分の PR を merge しない' "$F" && ok "規範: 実装者は自分の PR を merge しない" || ng "規範: 実装者は自分の PR を merge しない、が無い"

echo
echo "test-implementer-no-merge: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
