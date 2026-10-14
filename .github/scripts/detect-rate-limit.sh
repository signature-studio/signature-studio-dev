#!/bin/bash
# detect-rate-limit.sh — opencode の JSONL (OC_OUTPUT_FILE) の error イベントに率制限があるかを判定する (#2344 / CI-65)。
# 判定対象は error 行だけ。text 行に出た rate_limit_error という語は数えない (agent が率制限の話をしただけの run を除く)。
# 判定: error 行の error オブジェクトに rate_limit または provider.rate-limit を含む、または status が 429。
# 形の根拠: opencode 2.0.26 (CI の pin) に 429 / 503 (「credentials are cooling down」) の rate_limit_error を返す偽上流を当てて得た実出力を
# tests/fixtures/ に置いた。
#
# 使い方: bash detect-rate-limit.sh [<issue または PR の番号>]
# 標準出力: 率制限のとき annotation (::error title=oc-rate-limit::...) と `cause=rate_limit` の 1 行。違うとき何も出さない。
# 番号を渡したとき: 対象に <!-- oc-run-outcome: cause=rate_limit run=<run id> --> を 1 回だけ付ける (同じマーカーが既にあれば付けない)。
# 番号を渡さない (implement は record-run-outcome.sh から呼ぶ。そちらの no-pr マーカーに cause= を入れる) ときは、コメントを付けない。
#
# この script は run を失敗させない (観測用)。読めなかったら警告して 0 で終わる。出力ファイルが無ければ何もしない。
# 入力 (env): OC_OUTPUT_FILE (既定 $RUNNER_TEMP/oc-output.jsonl), GITHUB_RUN_ID, GITHUB_SERVER_URL,
#             番号を渡すときだけ: GH_TOKEN (issues:write)・OC_REPO。DRY=1 は書かずに計画だけ出す。
# コメント本文に agent を起動する語 (行頭の slash + oc 等) を入れない。
set -uo pipefail
export LC_ALL=C.UTF-8

DRY="${DRY:-0}"
f="${OC_OUTPUT_FILE:-${RUNNER_TEMP:-/tmp}/oc-output.jsonl}"
run="${GITHUB_RUN_ID:-0}"
N="${1:-}"

[ -s "$f" ] || exit 0

hits="$(jq -Rrs '
  [ split("\n")[] | fromjson? | select(type == "object" and .type == "error")
    | .error as $x
    | select(((($x | tojson) | test("rate_limit|provider\\.rate-limit"))) or (($x | type) == "object" and $x.status == 429)) ]
  | length' "$f" 2> /dev/null)" || hits=0
case "$hits" in '' | 0) exit 0 ;; esac

echo "::error title=oc-rate-limit::opencode の error 行に率制限 (rate_limit_error / HTTP 429) を検出しました (run $run)"
echo "cause=rate_limit"

case "$N" in '' | *[!0-9]*) exit 0 ;; esac
R="${OC_REPO:-}"
if [ -z "$R" ] || [ -z "${GH_TOKEN:-}" ]; then
  echo "::warning::no repo or token: the rate-limit marker is not posted on #$N"
  exit 0
fi

marker="<!-- oc-run-outcome: cause=rate_limit run=$run -->"
if ! cm="$(gh api --paginate "repos/$R/issues/$N/comments")"; then
  echo "::warning::could not read the comments of #$N: the rate-limit marker is not posted"
  exit 0
fi
if jq -s -e --arg m "$marker" '[.[][] | select((.body // "") | contains($m))] | length > 0' <<< "$cm" > /dev/null; then
  echo "#$N already has $marker: nothing to post"
  exit 0
fi
url="${GITHUB_SERVER_URL:-https://github.com}/$R/actions/runs/$run"
body="[rate-limit] この run ($url) は率制限 (rate_limit_error / HTTP 429) で失敗しました。
$marker"
if [ "$DRY" = 1 ]; then
  echo "DRY: comment on #$N: $marker"
  exit 0
fi
gh api -X POST "repos/$R/issues/$N/comments" -f body="$body" > /dev/null || echo "::warning::could not post the rate-limit marker on #$N"
exit 0
