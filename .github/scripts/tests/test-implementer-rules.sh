#!/bin/bash
# test-implementer-rules.sh — 実装 agent の規則 (路線 D5・製品 KPI・docs だけの PR 禁止) の記述が
# .github/prompts/implementer.md と docs/WORKFLOW.md に残っていることを検査する (#2684 [DOCS-28])。
# 各規則の行を削った写しでは必ず落ちることも確かめる (ネガティブコントロール)。
# 実行: bash .github/scripts/tests/test-implementer-rules.sh   (全て通れば exit 0、1 件でも落ちれば exit 1)
# CI: .github/workflows/scripts-test.yaml が .github/scripts/tests/test-*.sh を glob で拾う。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
IMPL="$ROOT/.github/prompts/implementer.md"
WF="$ROOT/docs/WORKFLOW.md"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# 各規則の固定文字列。両ファイルに 1 回以上残っていなければ落ちる。各文字列は規則の 1 行に含まれる。
KEYS=(
  '新規の lift・起動の作業は x64c / flelift / liftlib を使う'
  'RetDec 路線 (`tools/m6`〜`tools/m11`) は、issue が明示した場合と、起動指標を動かす PM 承認済みの場合を除き、新規の作業を始めない'
  '(D5: `docs/DECISIONS.md`)'
  '起動・GUI・ウィンドウに関わる PR は、本文に製品 KPI の前後'
  '動かせなかったときは『動かしていない』と書く'
  'docs だけの PR を作らない'
  'REPORT の更新は、実装と同じ PR に含める'
  '例外: 規約・ADR・PM の判断の記録'
)

# missing <implementer.md> <WORKFLOW.md>: 欠けた記述を "missing in <file>: <文字列>" で出す (何も出なければ全て残っている)
missing() {
  local f k
  for f in "$1" "$2"; do
    for k in "${KEYS[@]}"; do
      grep -qF -- "$k" "$f" 2>/dev/null || echo "missing in $(basename "$f"): $k"
    done
  done
}

# neg <impl|wf> <文字列>: 写しから文字列を含む行を削り、その欠落が報告されることを確かめる
neg() {
  local which="$1" k="$2" d="$TMP/$1" file
  mkdir -p "$d"
  cp "$IMPL" "$d/implementer.md"
  cp "$WF" "$d/WORKFLOW.md"
  if [ "$which" = impl ]; then
    file=implementer.md
    grep -vF -- "$k" "$IMPL" > "$d/implementer.md"
  else
    file=WORKFLOW.md
    grep -vF -- "$k" "$WF" > "$d/WORKFLOW.md"
  fi
  local out
  out="$(missing "$d/implementer.md" "$d/WORKFLOW.md")"
  grep -qF -- "missing in $file: $k" <<< "$out"
}

pass=0 fail=0
ok() { pass=$((pass + 1)); printf 'ok   %s\n' "$1"; }
ng() { fail=$((fail + 1)); printf 'FAIL %s\n' "$1"; }

out="$(missing "$IMPL" "$WF")"
if [ -z "$out" ]; then
  ok "実物: 路線 (D5)・製品 KPI・docs だけの PR 禁止が implementer.md と WORKFLOW.md に残っている"
else
  ng "実物: 欠けた記述がある"
  printf '%s\n' "$out"
fi

i=0
for k in "${KEYS[@]}"; do
  i=$((i + 1))
  for w in impl wf; do
    if neg "$w" "$k"; then
      ok "ネガ #$i ($w): 行を削ると欠落を検出"
    else
      ng "ネガ #$i ($w): 行を削っても欠落を検出できない"
    fi
  done
done

echo
echo "test-implementer-rules: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
