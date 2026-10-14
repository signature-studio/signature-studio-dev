#!/bin/bash
# test-workflow-pm-job.sh — .github/workflows/opencode.yaml の pm job (PM agent。oc-pm。#2330) の構造を検査する。
# 不変条件: token は permission-issues / permission-pull-requests の write だけ (contents を要求しない)・
# CF_* (R2) を参照しない・should_run=false の dispatch では agent を起動しない・他の job の if: に oc-pm が混ざらない。
# 実行: bash .github/scripts/tests/test-workflow-pm-job.sh
# CI: .github/workflows/scripts-test.yaml が .github/workflows/opencode.yaml の変更ごとに実行する。
# shellcheck disable=SC2016,SC2319  # SC2016: ${{ }} は workflow 内の文字列として探すもので、shell では展開しない。SC2319: expect は直前の検査の終了コードを読む
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
# job_if <file> <job>: job 直下の if: (折り畳みの継続行を含む) を 1 行に連結して出す
job_if() {
  job_block "$1" "$2" | awk '
    /^    if:/ { on = 1; sub(/^    if:[[:space:]]*(>-|>|\|)?[[:space:]]*/, ""); printf "%s", $0; next }
    on && /^      / { sub(/^[[:space:]]+/, " "); printf "%s", $0; next }
    on { on = 0 }
    END { printf "\n" }
  ' | sed 's/^[[:space:]]*//'
}
# job_steps <file> <job> <dir>: steps を <dir>/step-NN に分ける
job_steps() {
  mkdir -p "$3"
  job_block "$1" "$2" | awk -v d="$3" '
    /^    steps:/ { in_steps = 1; next }
    !in_steps { next }
    /^      - / { n++; f = sprintf("%s/step-%02d", d, n) }
    f { print > f }
  '
}
# top_section <file> <key>: トップレベルのキー 1 つ分 (コメントだけの行は除く)
top_section() {
  awk -v k="$2" '
    $0 ~ ("^" k ":") { on = 1; print; next }
    /^[^ #]/ { on = 0 }
    on && !/^[[:space:]]*#/ { print }
  ' "$1"
}

# checks <file>: 全検査を実行し、ok / FAIL 行を出す
checks() {
  local f="$1" d pm rc
  d="$(mktemp -d "$TMP/chk.XXXXXX")"
  pm="$d/pm"
  job_block "$f" pm > "$pm"

  [ -s "$pm" ]
  expect "pm job exists" $?

  # 受入 1: 受け口と job の骨格
  top_section "$f" on | grep -E '^    types: \[' | grep -q 'oc-pm'
  expect "on.repository_dispatch.types has oc-pm" $?
  top_section "$f" on | grep -E '^    types: \[' | grep -q 'oc-fix' && top_section "$f" on | grep -E '^    types: \[' | grep -q 'oc-watchdog'
  expect "on.repository_dispatch.types keeps oc-fix and oc-watchdog" $?
  [ "$(job_if "$f" pm)" = "github.event_name == 'repository_dispatch' && github.event.action == 'oc-pm'" ]
  expect "pm job if: is exactly repository_dispatch + oc-pm" $?
  grep -qx '    timeout-minutes: 30' "$pm"
  expect "pm job timeout-minutes is 30" $?
  grep -qx '      group: oc-pm-${{ github.event.client_payload.kind }}-${{ github.event.client_payload.ref }}' "$pm" \
    && grep -qx '      cancel-in-progress: false' "$pm"
  expect "pm job concurrency group is oc-pm-<kind>-<ref>, cancel-in-progress false" $?
  top_section "$f" run-name | grep -q "format('oc-pm {0} #{1}', github.event.client_payload.kind, github.event.client_payload.ref)" \
    && top_section "$f" run-name | grep -q "format('oc-fix #{0}', github.event.client_payload.pr)" \
    && top_section "$f" run-name | grep -q "'watchdog'"
  expect "run-name names oc-pm <kind> #<ref> and keeps oc-fix and watchdog" $?

  # 受入 2: token の権限 (contents を要求しない) と R2 の認証を渡さない
  [ "$(grep -c 'actions/create-github-app-token' "$pm")" = 1 ]
  expect "pm job mints exactly one App token" $?
  [ "$(grep -E '^[[:space:]]+permission-[a-z-]+:' "$pm" | sed 's/^[[:space:]]*//' | sort | tr '\n' ' ')" = "permission-issues: write permission-pull-requests: write " ]
  expect "token permissions are exactly permission-issues: write and permission-pull-requests: write" $?
  ! grep -q 'permission-contents' "$pm"
  expect "token does not request contents" $?
  ! grep -qE '^    permissions:' "$pm"
  expect "pm job does not widen GITHUB_TOKEN permissions" $?
  grep -q 'client-id: ${{ vars.OC_APP_CLIENT_ID }}' "$pm" && grep -q 'private-key: ${{ secrets.OC_APP_PRIVATE_KEY }}' "$pm" && ! grep -q 'OC_REVIEW_APP' "$pm"
  expect "token comes from the implementer App (OC_APP_*)" $?
  ! grep -qiE 'CF_|cf-account|cf-r2' "$pm"
  expect "pm job does not reference CF_* (R2) secrets or agent-setup cf-* inputs" $?
  [ "$(grep -oE 'secrets\.[A-Za-z0-9_]+' "$pm" | sort -u | tr '\n' ' ')" = "secrets.OC_APP_PRIVATE_KEY secrets.OC_AUTH_EXPORT " ]
  expect "pm job reads only the OC_APP_PRIVATE_KEY and OC_AUTH_EXPORT secrets" $?
  grep -qx "          artifacts: none" "$pm" && grep -qx "          artifacts-required: 'false'" "$pm"
  expect "agent-setup runs with artifacts: none and artifacts-required: 'false'" $?

  # 受入 3: dispatch_ok=false (should_run=false) では agent を起動しない
  job_steps "$f" pm "$d/steps"
  local s gated=0 total=0 ctxstep="" refuse=""
  for s in "$d"/steps/step-*; do
    [ -e "$s" ] || continue
    if grep -qE 'uses: \./\.github/actions/(agent-setup|opencode)$|assemble-prompt\.sh' "$s"; then
      total=$((total + 1))
      grep -qE "^        if: steps\.context\.outputs\.should_run == 'true'$" "$s" && gated=$((gated + 1))
    fi
    grep -q 'prepare-event-context.sh' "$s" && ctxstep="$s"
    grep -q "should_run != 'true'" "$s" && refuse="$s"
  done
  [ "$total" = 3 ] && [ "$gated" = 3 ]
  expect "agent-setup, assemble-prompt and the opencode run are all gated on should_run == 'true' ($gated/$total)" $?
  [ -n "$ctxstep" ] && grep -qx '        id: context' "$ctxstep" && grep -q 'GH_TOKEN: ${{ steps.app-token.outputs.token }}' "$ctxstep"
  expect "Prepare event context (id: context) runs with the App token" $?
  [ -n "$refuse" ] && grep -qx '          exit 1' "$refuse"
  expect "a rejected dispatch fails the job (should_run != 'true' -> exit 1)" $?
  # token の発行は Prepare event context より前 (対象の取得に GH_TOKEN が要る)
  awk '/create-github-app-token/ { a = NR } /prepare-event-context\.sh/ { c = NR } END { exit !(a && c && a < c) }' "$pm"
  expect "the App token is minted before Prepare event context" $?
  # untrusted な payload を run に展開しない: client_payload を式展開してよいのは concurrency group の 1 行だけ
  [ "$(grep -c 'client_payload' "$pm")" = 1 ]
  expect "client_payload is expanded only in the concurrency group" $?

  # 受入 4: 他の job は oc-pm で起動しない。repository_dispatch を含む if: は必ず action を限定している
  local j
  for j in watchdog implement review review-recover; do
    local cond
    cond="$(job_if "$f" "$j")"
    [ -n "$cond" ] && ! printf '%s' "$cond" | grep -q 'oc-pm'
    expect "job $j: if: exists and does not mention oc-pm" $?
    rc=$(printf '%s' "$cond" | grep -o "github.event_name == 'repository_dispatch'" | wc -l)
    [ "$rc" = "$(printf '%s' "$cond" | grep -oE "github.event.action == '[a-z-]+'" | wc -l)" ]
    expect "job $j: every repository_dispatch in if: is limited to one action" $?
  done
  job_if "$f" watchdog | grep -q "github.event.action == 'oc-watchdog'"
  expect "job watchdog: still starts on oc-watchdog" $?
  job_if "$f" implement | grep -q "github.event.action == 'oc-fix'"
  expect "job implement: still starts on oc-fix" $?
  grep -qx '      group: opencode-watchdog' <(job_block "$f" watchdog) \
    && grep -q 'group: opencode-impl-' <(job_block "$f" implement) \
    && grep -q 'group: opencode-review-${{' <(job_block "$f" review) \
    && grep -q 'group: opencode-review-recover-' <(job_block "$f" review-recover)
  expect "the concurrency groups of the other jobs are unchanged" $?
}

out="$(checks "$WF")"
printf '%s\n' "$out"
n_fail="$(printf '%s\n' "$out" | grep -c '^FAIL')"
n_ok="$(printf '%s\n' "$out" | grep -c '^ok')"
pass=$n_ok fail=$n_fail

# ネガコン: 壊した workflow では対応する検査が失敗すること (検査自体が効いていることの確認)
# mutate <name> <old>=><new> <FAIL 行に含まれるはずの文字列>: pm job 内の最初の <old> (1 行内の文字列) を <new> に置き換える。
# <new> の \n は改行になる。
mutate() {
  local name="$1" spec="$2" want="$3" m="$TMP/mut.yaml" old new
  old="${spec%%=>*}"
  new="${spec#*=>}"
  awk -v old="$old" -v new="$new" '
    !done && inpm && (i = index($0, old)) { $0 = substr($0, 1, i - 1) new substr($0, i + length(old)); done = 1 }
    /^  pm:/ { inpm = 1 }
    { print }
    END { exit !done }
  ' "$WF" > "$m" || { ng "negative control: $name (mutation target not found)"; return; }
  checks "$m" | grep '^FAIL' | grep -qF -- "$want"
  expect "negative control: $name -> FAIL '$want'" $?
}
mutate "contents permission added" "          permission-issues: write=>          permission-issues: write\n          permission-contents: read" "token does not request contents"
mutate "extra permission added" "          permission-issues: write=>          permission-issues: write\n          permission-actions: read" "exactly permission-issues"
mutate "CF secret passed" "          artifacts: none=>          cf-account-id: \${{ secrets.CF_ACCOUNT_ID }}\n          artifacts: none" "CF_*"
mutate "R2 artifacts requested" "          artifacts: none=>          artifacts: fl-win64" "artifacts: none"
mutate "agent not gated on should_run" "        if: steps.context.outputs.should_run == 'true'=>        if: true" "gated on should_run"
mutate "rejected dispatch no longer fails" "          exit 1=>          exit 0" "rejected dispatch fails the job"
mutate "job if: widened to every dispatch" "if: github.event_name == 'repository_dispatch' && github.event.action == 'oc-pm'=>if: github.event_name == 'repository_dispatch'" "pm job if:"
mutate "App token minted by the reviewer App" "client-id: \${{ vars.OC_APP_CLIENT_ID }}=>client-id: \${{ vars.OC_REVIEW_APP_CLIENT_ID }}" "implementer App"

# 他の job への影響: implement の if: に oc-pm を足した workflow では失敗する
m="$TMP/mut-impl.yaml"
sed "0,/github.event.action == 'oc-fix')/s//github.event.action == 'oc-fix' || github.event.action == 'oc-pm')/" "$WF" > "$m"
checks "$m" | grep '^FAIL' | grep -q 'job implement'
expect "negative control: oc-pm added to the implement if: -> FAIL 'job implement'" $?

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
