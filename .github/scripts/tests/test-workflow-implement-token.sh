#!/bin/bash
# test-workflow-implement-token.sh — .github/workflows/opencode.yaml の GITHUB_TOKEN の権限と参照先を検査する (#2622・#2638 レビュー m2)。
# 不変条件: 最上位の permissions は {}・implement job の permissions は pull-requests: write だけ (issues・contents を足さない)・
# github.token を読むのは implement の Record the PR head (fix mode) step の env (OC_MARK_TOKEN) だけ
# (agent の step と job の env には渡さない)。
# 実行: bash .github/scripts/tests/test-workflow-implement-token.sh
# CI: .github/workflows/scripts-test.yaml が .github/scripts/tests/test-*.sh を glob で拾う。
# shellcheck disable=SC2016  # SC2016: ${{ }} は workflow 内の文字列として探すもので、shell では展開しない
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WF="${OC_WORKFLOW_FILE:-$HERE/../../workflows/opencode.yaml}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0 fail=0
ok() { pass=$((pass + 1)); printf 'ok   %s\n' "$1"; }
ng() { fail=$((fail + 1)); printf 'FAIL %s\n' "$1"; }
expect() { if [ "$2" = 0 ]; then ok "$1"; else ng "$1"; fi; }

# job_block <file> <job>: jobs: 直下の job 1 つ分 (コメントだけの行は除く)
job_block() {
  awk -v j="$2" '
    /^jobs:/ { in_jobs = 1; next }
    !in_jobs { next }
    /^  [A-Za-z0-9_-]+:[[:space:]]*(#.*)?$/ { on = ($0 ~ ("^  " j ":")) ; if (on) print; next }
    /^[^ #]/ { on = 0 }
    on && !/^[[:space:]]*#/ { print }
  ' "$1"
}

# checks <file>: 全検査を実行し、ok / FAIL 行を出す
checks() {
  local f="$1" perm refs

  grep -q '^permissions: {}$' "$f"
  expect "top-level permissions is {} (GITHUB_TOKEN は既定で権限なし)" $?

  perm="$(job_block "$f" implement | awk '/^    permissions:/ { on = 1; print; next } on && /^      / { print; next } { on = 0 }')"
  [ "$perm" = "$(printf '    permissions:\n      pull-requests: write')" ]
  expect "implement job permissions is exactly pull-requests: write (issues・contents を足さない)" $?

  # github.token を含む行を、どの step にあるか付けて出す (job の env や agent の step にあれば step 名が違う)
  refs="$(job_block "$f" implement | awk '
    /^      - / { step = $0; sub(/^      - /, "", step) }
    /github\.token/ { print step " | " $0 }')"
  [ "$(printf '%s\n' "$refs" | grep -c .)" = 1 ] \
    && printf '%s\n' "$refs" | grep -qF 'name: Record the PR head (fix mode) | ' \
    && printf '%s\n' "$refs" | grep -qF 'OC_MARK_TOKEN: ${{ github.token }}'
  expect "github.token is read only as OC_MARK_TOKEN in the Record the PR head (fix mode) step" $?
}

# mutate <name> <awk 式> <FAIL 行に含まれるはずの文字列>: awk で壊した workflow を作り、対応する FAIL が出ることを確かめる (ネガコン)
mutate() {
  local name="$1" prog="$2" want="$3" m="$TMP/mut.yaml"
  awk "$prog" "$WF" > "$m" || { ng "negative control: $name (mutation failed)"; return; }
  checks "$m" | grep '^FAIL' | grep -qF -- "$want"
  expect "negative control: $name -> FAIL '$want'" $?
}

[ -f "$WF" ]
expect "workflow file exists" $?

checks "$WF"

mutate "issues: write added to implement" \
  '/^  implement:/ { inj = 1 } /^  [a-z][a-z-]*:/ && !/^  implement:/ { inj = 0 } inj && !done && /^      pull-requests: write$/ { print; print "      issues: write"; done = 1; next } { print }' \
  "implement job permissions"
mutate "contents: read added to implement" \
  '/^  implement:/ { inj = 1 } /^  [a-z][a-z-]*:/ && !/^  implement:/ { inj = 0 } inj && !done && /^      pull-requests: write$/ { print; print "      contents: read"; done = 1; next } { print }' \
  "implement job permissions"
mutate "github.token passed to the agent step" \
  '/^        id: oc$/ { armed = 1 } armed && !done && /^          GH_TOKEN:/ { print; print "          OC_MARK_TOKEN: ${{ github.token }}"; done = 1; next } { print }' \
  "github.token is read only"
mutate "OC_MARK_TOKEN removed from the record step" \
  '/^          OC_MARK_TOKEN: \$\{\{ github\.token \}\}$/ && !done { done = 1; next } { print }' \
  "github.token is read only"
mutate "top-level permissions widened" \
  '/^permissions: \{\}$/ && !done { print "permissions: read-all"; done = 1; next } { print }' \
  "top-level permissions"

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
