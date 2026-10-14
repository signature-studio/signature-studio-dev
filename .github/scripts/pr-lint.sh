#!/bin/bash
# pr-lint.sh — push 前に差し戻しの上位原因を決定的に検査する (#2322)。
# 検査: (a) REPORT 行数上限 (b) 追加行の repo 外絶対パス (c) Closes/Refs と受入の整合
#       (d) oc_artifacts の値域 (watchdog.sh の ARTIFACT_RE) (e) 新規 REPORT の DOC_MAP 登録
# 使い方: bash .github/scripts/pr-lint.sh --base <ref> --head <ref> --body-file <PR 本文ファイル>
# 既定は警告のみ (終了 0)。OC_LINT_STRICT=1 で違反があれば終了 1。
# 出力: <file>:<line>: <rule>: <message>
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="" HEAD_REF="" BODY=""
usage() { echo "usage: pr-lint.sh --base <ref> --head <ref> --body-file <path>" >&2; exit 2; }
while [ $# -gt 0 ]; do
  case "$1" in
    --base) [ $# -ge 2 ] || usage; BASE="$2"; shift 2 ;;
    --head) [ $# -ge 2 ] || usage; HEAD_REF="$2"; shift 2 ;;
    --body-file) [ $# -ge 2 ] || usage; BODY="$2"; shift 2 ;;
    *) usage ;;
  esac
done
{ [ -n "$BASE" ] && [ -n "$HEAD_REF" ] && [ -n "$BODY" ]; } || usage
[ -f "$BODY" ] || { echo "pr-lint: body file not found: $BODY" >&2; exit 2; }

ARTIFACT_RE="$(sed -n "s/^ARTIFACT_RE='\(.*\)'\$/\1/p" "$HERE/watchdog.sh" | head -n1)"
[ -n "$ARTIFACT_RE" ] || { echo "pr-lint: ARTIFACT_RE が watchdog.sh に無い" >&2; exit 2; }

VIOL=0
report() { # report <file> <line> <rule> <message>
  VIOL=$((VIOL + 1))
  printf '%s:%s: %s: %s\n' "$1" "$2" "$3" "$4"
  [ "${OC_LINT_STRICT:-0}" = 1 ] || printf '::warning::%s:%s: %s: %s\n' "$1" "$2" "$3" "$4"
}

# 行数上限は docs/DOC_MAP.md §1 の REPORT.md 行から読む。読めなければ 250。
dm="$(git show "$HEAD_REF:docs/DOC_MAP.md" 2>/dev/null || true)"
MAX="$(grep -m1 -F '| `REPORT.md` (日本語)' <<< "$dm" | grep -oE '[0-9]+ 行' | grep -oE '[0-9]+' | head -n1 || true)"
[ -n "$MAX" ] || MAX=250

# (a) 変更された REPORT 系ファイルの行数
while IFS= read -r f; do
  case "$(basename "$f")" in REPORT*.md) ;; *) continue ;; esac
  n="$(git show "$HEAD_REF:$f" 2>/dev/null | wc -l)"
  [ "$n" -gt "$MAX" ] && report "$f" "$((MAX + 1))" "report-lines" "$n 行 > 上限 $MAX 行 (docs/DOC_MAP.md §1)。付録へ分割移動する"
done < <(git diff --diff-filter=AMR --name-only "$BASE...$HEAD_REF")

# (b) 追加行の repo 外絶対パス (本スクリプトと自身のテストは検査対象外)
ABS_RE='(^|[^A-Za-z0-9_./~-])(/home/|/opt/|/Users/)|\$HOME/'
while IFS=$'\t' read -r f n text; do
  grep -qE "$ABS_RE" <<< "$text" && report "$f" "$n" "repo-abs-path" "repo 外の絶対パス。docs/REFERENCES.md のエントリ ID で参照する"
done < <(git diff --unified=0 "$BASE...$HEAD_REF" -- . ':!.github/scripts/pr-lint.sh' ':!.github/scripts/tests/test-pr-lint.sh' \
  | awk '/^\+\+\+ /{f=substr($0,7); next} /^@@/{split($3,a,","); sub(/^\+/,"",a[1]); n=a[1]-1; next} /^\+/{n++; print f "\t" n "\t" substr($0,2); next}')

# (c) Closes/Refs と受入の整合
if grep -qE '(^|[^A-Za-z])Closes #[0-9]+' "$BODY"; then
  while IFS=: read -r n _; do
    report "$BODY" "$n" "closes-unmet" "Closes #N なのに未達の受入条件がある (Closes を外すか、未達を子 issue に移して本文から外す)"
  done < <(grep -nE '\[ \]|未達' "$BODY" || true)
elif grep -qE '(^|[^A-Za-z])Refs #[0-9]+' "$BODY" && ! grep -q '理由' "$BODY"; then
  report "$BODY" 1 "refs-reason" "Refs #N のみで merge するなら「理由:」行が必要"
fi

# (d) oc_artifacts の値域 (none 単独は可。名前は watchdog.sh と同じく a-z0-9 と空白・- に絞ってから照合)
hit="$(grep -m1 -nE '^[[:space:]]*oc_artifacts:' "$BODY" || true)"
if [ -n "$hit" ]; then
  ln="${hit%%:*}"
  line="${hit#*:}"
  names="$(printf '%s' "${line#*oc_artifacts:}" | tr -cd 'a-z0-9 -' | xargs)"
  if [ "$names" != "none" ]; then
    for name in $names; do
      printf '%s' "$name" | grep -qE "$ARTIFACT_RE" || report "$BODY" "$ln" "oc-artifacts" "oc_artifacts の名前 '$name' は許可リスト (watchdog.sh ARTIFACT_RE) にない"
    done
  fi
fi

# (e) 新規 REPORT は docs/DOC_MAP.md に登録する
while IFS= read -r f; do
  case "$(basename "$f")" in REPORT*.md) ;; *) continue ;; esac
  grep -qF "$f" <<< "$dm" || report "$f" 1 "doc-map" "新規 REPORT は docs/DOC_MAP.md の索引に登録する"
done < <(git diff --diff-filter=A --name-only "$BASE...$HEAD_REF")

echo "pr-lint: violations=$VIOL (strict=${OC_LINT_STRICT:-0}, report_max=$MAX)" >&2
if [ "${OC_LINT_STRICT:-0}" = 1 ] && [ "$VIOL" -gt 0 ]; then exit 1; fi
exit 0
