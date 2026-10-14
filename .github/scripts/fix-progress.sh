#!/bin/bash
# fix-progress.sh — reviewer の差し戻しを受けた fix モードの進捗を検証する (#719)。
# 指示 122/123: 差し戻された PR が「修正もレビューもされていない」状態に戻らないようにする。
#
#   gate          窓の判定と印の投稿 (#2873)。agent を実行しない fixgate job で走る。$GITHUB_ENV は書かない。
#                 結果は $GITHUB_OUTPUT に stop=true/false と reason を出す (reason: none / reset / ceiling / code /
#                 pm-decision / user-decision / repeat / unknown / stuck-label / not-open / stale-head)。
#                 途中で失敗したら stop=true と reason=record-failed を出して非 0 で終わる (下の record と同じ)。
#   snapshot      agent の起動直前の PR head と時刻を $GITHUB_ENV に記録する (#2873)。implement job で走る。
#                 OC_GATE_STOP (gate の stop) が false のときだけ OC_RECORD_OK=1 を残す。それ以外は失敗する (fail-closed)。
#   record        gate と snapshot を続けて行う旧経路 (移行中の互換。#2323・#2622・#2869)。
#                 窓 = 直近の oc-fix-limit / oc-fix-reset コメント以降の差し戻し (印は MARK_LOGIN の投稿だけを数える。#2622)。窓が MAX 件に達したら、
#                 直近 3 件が機械的な類型のみ・繰り返し無し・合計が天井未満なら次の窓へ進める (oc-fix-reset)。
#                 それ以外は oc:stuck を付けて止め、PM agent 用の oc-pm-intent マーカーを残す。
#                 結果は $GITHUB_OUTPUT に stop=true/false で出す (上限で止めた stop=true なら oc:stuck ラベルを付けて PR にコメントする)。
#                 窓の判定まで終えたときだけ $GITHUB_ENV に OC_RECORD_OK=1 を書く
#                 record が途中で失敗したら stop=true と reason=record-failed を出して非 0 で終わる (入力検査・gh の失敗を含む)。
#                 fail-closed: stop が無いと check が none と判定し、write 権限の retry が起動する (#2638 B3・#2869)。
#                 この失敗では oc:stuck を付けず PR にもコメントしない。job が赤くなり、原因は run のログで見る。
#                 ただし次の場合は agent を起動せず stop=true にするだけ (notice を残す。oc:stuck は付けない。#2601):
#                 PR が open でない (merge・close 済み)、または差し戻しの元の review (pull_request_review の event) の commit が
#                 現在の head と違う (古い head への差し戻し。その後に push された head の review が判定を担う)
#   check         head が進んだか / 根拠コメントを投稿したかを判定し、result を $GITHUB_OUTPUT に出す
#                 (OC_RECORD_OK が無ければ result を出さずに失敗する。record が終わっていないのに none と判定しない #2869)
#                   pushed   : head が進んだ (push が synchronize を起こし、review が再起動する)
#                   answered : push せず PR にコメントした (review は起動しないので reopen で起こす)
#                   none     : どちらもしていない
#   retry-prompt  none だったときの再試行用プロンプトを作る
#   reopen        reopen-pr.sh に委譲する (close -> reopen。旧 workflow との互換)
#
# 入力 (env): GH_TOKEN, OC_REPO, OC_PR_NUMBER (数字のみ), RUNNER_TEMP, GITHUB_ENV, GITHUB_OUTPUT
# 任意 (env): OC_MAX_FIX_REVIEWS (窓の件数, 既定 5)・OC_MAX_FIX_TOTAL (合計の天井, 既定 15)・
#             OC_MAX_RESETS_PER_HOUR (repo 全体の自動再開上限, 既定 6)・OC_REPEAT_JACCARD (繰り返しのしきい値, 既定 0.6)
#             snapshot だけ: OC_GATE_STOP (gate の stop 出力。false のときだけ通す)
# 実装 App は PR の comment を投稿する時 user.login が opencode-for-signature-studio[bot] になる。
set -Eeuo pipefail

OC_SUBCMD="${1:-}"
# record・gate・snapshot が途中で終わったら (入力検査・gh の失敗など)、stop=true と reason=record-failed を出して非 0 で終わる (#2869)。
# 入力検査より前に置く (#2638 B3・m3)。agent と retry は走らせない。PR にはコメントしない (コメントも失敗しうる)。trap の中では gh を呼ばない。
OC_RECORD_DONE=0
record_abort() {
  local rc=$? cmd="${OC_FAIL_CMD:-?}"
  trap - ERR EXIT
  if [ "$OC_RECORD_DONE" != 1 ]; then
    cmd="${cmd//$'\n'/ }"
    echo "::error::fix-progress ${OC_SUBCMD:-record} failed (exit $rc, line ${OC_FAIL_LINE:-?}, command: ${cmd:0:120}): the fix run is skipped (reason=record-failed)"
    printf 'stop=true\nreason=record-failed\n' >> "${GITHUB_OUTPUT:-/dev/null}"
    exit 1
  fi
}
case "$OC_SUBCMD" in
  record | gate | snapshot)
    trap 'OC_FAIL_LINE=$LINENO; OC_FAIL_CMD=$BASH_COMMAND' ERR
    trap record_abort EXIT
    ;;
esac

: "${OC_REPO:?}" "${OC_PR_NUMBER:?}"
if ! grep -qE '^[0-9]{1,7}$' <<< "$OC_PR_NUMBER"; then
  echo "::error::OC_PR_NUMBER must be digits only: the fix-progress step is skipped" >&2
  exit 1
fi
pr_head() { gh api "repos/$OC_REPO/pulls/$OC_PR_NUMBER" --jq .head.sha; }
STUCK_LABEL="${OC_STUCK_LABEL:-oc:stuck}"
# 起動主体は完全一致で見る (前方一致だと意図しないアカウント名でも通り、write 権限の fix が起動しうる)。
REVIEWER_LOGIN="${OC_REVIEWER_LOGIN:-oc-reviewer-for-signature-studio[bot]}"
IMPLEMENTER_LOGIN="${OC_IMPLEMENTER_LOGIN:-opencode-for-signature-studio[bot]}"
# 差し戻しの往復 (changes_requested -> fix -> push -> review -> changes_requested) と、
# push せず根拠だけ返す往復 (answered -> reopen -> review -> changes_requested) は、どちらも
# 1 周に oc-reviewer の CHANGES_REQUESTED review を 1 件ずつ増やす。件数で両方を抑える。
# 窓は直近の停止コメント (oc-fix-limit) か再開コメント (oc-fix-reset) 以降の差し戻し。
# 窓の印を信じる作者は MARK_LOGIN (job の GITHUB_TOKEN = github-actions[bot]) だけ (#2622)。
# agent と script は同じ実装 App の token を持つので、実装 App 名義の印は agent が偽造できる。
# 印の投稿には OC_MARK_TOKEN (workflow が github.token を渡す) を使う。無ければ窓を閉じない (停止側へ倒す)。
STOP_MARK='<!-- oc-fix-limit -->'
MARK_LOGIN="${OC_MARK_LOGIN:-github-actions[bot]}"
MARK_TOKEN="${OC_MARK_TOKEN:-}"
MAX_FIX_REVIEWS="${OC_MAX_FIX_REVIEWS:-5}"
MAX_FIX_TOTAL="${OC_MAX_FIX_TOTAL:-15}"
MAX_RESETS_PER_HOUR="${OC_MAX_RESETS_PER_HOUR:-6}"
REPEAT_JACCARD="${OC_REPEAT_JACCARD:-0.6}"

# 窓の判定 (jq)。入力は $cm (PR のコメント配列) と $rv (reviewer の CHANGES_REQUESTED review 配列)。
# classes マーカーの欠落・不正は unknown。conflict と merge-failed の差し戻しは計数しない。
JQ_DEFS='
def allowed: ["doc","remeasure","artifact","closes","path","input","conflict","code","pm-decision","user-decision"];
def cls: (([(.body // "") | capture("oc-review:[^>]*classes=(?<c>[^ >]*)") | .c | split(",")] | first // []) as $c
  | if ($c | length) == 0 or (($c - allowed) | length) > 0 then ["unknown"] else $c end);
def counted: (cls | any(. == "conflict") | not) and ((.body // "") | contains("[merge-failed]") | not);
def grams: explode as $e | [range(0; ($e | length) - 1) | [$e[.], $e[. + 1]] | implode] | unique;
def bullets: [split("\n")[] | select(test("^\\s*([-*]|[0-9]+\\.)\\s")) | sub("^\\s*([-*]|[0-9]+\\.)\\s+"; "") | gsub("\\s"; "")] | join("") | grams;
def jac($a; $b): (($a + $b) | unique | length) as $u | if $u == 0 then 0 else (($a - ($a - $b)) | length) / $u end;
'
DECIDE='
[$cm[] | select(.user.login == $ml and .user.type == "Bot" and ((.body // "") | contains("<!-- oc-fix-limit -->"))) | .created_at] | (max // "") as $limit
| [$cm[] | select(.user.login == $ml and .user.type == "Bot" and ((.body // "") | contains("<!-- oc-fix-reset")) and .created_at > $limit)] as $resets
| (if ($resets | length) > 0 then ($resets | map(.created_at) | max) else $limit end) as $wstart
| [$rv[] | select(.submitted_at > $limit and counted)] as $all
| [$rv[] | select(.submitted_at > $wstart and counted)] as $win
| ($win | length) as $n
| ($all | length) as $total
| ($resets | length) as $rs
| ($win | .[-3:]) as $last3
| ([$last3[] | cls] | add // []) as $lc
| [$last3[] | (.body // "") | bullets] as $sets
| (if $n < $max then "none"
   elif $total >= $maxtotal or $rs >= 2 then "ceiling"
   elif ($lc | any(. == "code")) then "code"
   elif ($lc | any(. == "pm-decision")) then "pm-decision"
   elif ($lc | any(. == "user-decision")) then "user-decision"
   elif ($sets | length) >= 3 and ([range(0; ($sets | length) - 1) | jac($sets[.]; $sets[. + 1])] | all(. >= $t)) then "repeat"
   elif ($lc | any(. == "unknown")) and $rs >= 1 then "unknown"
   else "reset" end) as $d
| {decision: $d, n: $n, total: $total, k: ($rs + 1)}
'

# gate_run <pr_json>: 窓の判定と印の投稿 (record と gate が呼ぶ)。結果は stop (true/false) と reason に入れる。
# $GITHUB_ENV と $GITHUB_OUTPUT は書かない (呼び出し側が書く)。
gate_run() {
  local pr_json="$1" head_now pr_state review_commit labels cm rv dec decision n total k hour_ago recent
  head_now="$(jq -r .head.sha <<< "$pr_json")"
  pr_state="$(jq -r .state <<< "$pr_json")"
  # 差し戻しの元になった review の commit (pull_request_review の event payload にだけある。repository_dispatch では空)
  review_commit="$(jq -r '.review.commit_id // empty' "${GITHUB_EVENT_PATH:-/dev/null}" 2> /dev/null || true)"
  # 上限ガード: ラベルが付いている PR は fix を起動しない。
  # 止めたことは PR に 1 回だけコメントし、ラベルで PM に引き渡す (watchdog もこのラベルで止まる)。
  stop=false
  # 取得の失敗で止まる (set -e)。pipefail 付きの if では API の失敗が『ラベル無し』と判定されてしまうため分ける (#2638 m2)。
  labels="$(gh api "repos/$OC_REPO/issues/$OC_PR_NUMBER" --jq '.labels[].name')"
  if grep -qx "$STUCK_LABEL" <<< "$labels"; then
    stop=true
    reason=stuck-label
    echo "PR #$OC_PR_NUMBER already has $STUCK_LABEL: the fix run is skipped"
  elif [ "$pr_state" != open ]; then
    stop=true
    reason=not-open
    echo "::notice::PR #$OC_PR_NUMBER is $pr_state (not open): the fix run is skipped"
  elif [ -n "$review_commit" ] && [ "$review_commit" != "$head_now" ]; then
    stop=true
    reason=stale-head
    echo "::notice::the CHANGES_REQUESTED review is for ${review_commit:0:7}, but the PR head is now ${head_now:0:7}: the fix run is skipped"
  else
    cm="$(gh api --paginate "repos/$OC_REPO/issues/$OC_PR_NUMBER/comments" | jq -s '[.[][]]')"
    rv="$(gh api --paginate "repos/$OC_REPO/pulls/$OC_PR_NUMBER/reviews" \
      | jq -s --arg l "$REVIEWER_LOGIN" '[.[][] | select(.user.login == $l and .state == "CHANGES_REQUESTED")]')"
    dec="$(jq -c -n --argjson cm "$cm" --argjson rv "$rv" --arg ml "$MARK_LOGIN" \
      --argjson max "$MAX_FIX_REVIEWS" --argjson maxtotal "$MAX_FIX_TOTAL" --argjson t "$REPEAT_JACCARD" \
      "$JQ_DEFS $DECIDE")"
    decision="$(jq -r .decision <<< "$dec")"
    n="$(jq -r .n <<< "$dec")"
    total="$(jq -r .total <<< "$dec")"
    k="$(jq -r .k <<< "$dec")"
    echo "oc-reviewer CHANGES_REQUESTED on PR #$OC_PR_NUMBER: window=$n total=$total (limit $MAX_FIX_REVIEWS, ceiling $MAX_FIX_TOTAL) -> $decision"
    # 窓を閉じる印は MARK_TOKEN でしか投稿できない。無ければ信じられる印を残せないので、窓を閉じずに止める。
    if [ "$decision" = reset ] && [ -z "$MARK_TOKEN" ]; then
      decision=ceiling
      echo "OC_MARK_TOKEN is not set: the window marker cannot be trusted, so the window stays open: stop"
    fi
    # 自動再開は repo 全体で 1 時間 MAX_RESETS_PER_HOUR 件まで (暴走防止)。数えられなければ止める。
    if [ "$decision" = reset ]; then
      hour_ago="$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)"
      if ! recent="$(gh api --paginate -X GET "repos/$OC_REPO/issues/comments" -f since="$hour_ago" \
        | jq -s --arg t "$hour_ago" --arg ml "$MARK_LOGIN" \
          '[.[][] | select(.user.login == $ml and .user.type == "Bot" and ((.body // "") | contains("<!-- oc-fix-reset")) and .created_at >= $t)] | length')"; then
        recent="$MAX_RESETS_PER_HOUR"
      fi
      if [ "$recent" -ge "$MAX_RESETS_PER_HOUR" ]; then
        decision=ceiling
        echo "automatic resets in the last hour: $recent (limit $MAX_RESETS_PER_HOUR): stop"
      fi
    fi
    if [ "$decision" = reset ]; then
      GH_TOKEN="$MARK_TOKEN" gh pr comment "$OC_PR_NUMBER" --repo "$OC_REPO" \
        --body "reviewer の差し戻し ${n} 件 (合計 ${total}) を計数し、直近 3 件が機械的な類型のみ・繰り返し無しのため、窓 ${k}/3 を閉じて次の窓へ進めます。<!-- oc-fix-reset n=${k} -->"
    elif [ "$decision" != none ]; then
      stop=true
      gh api -X POST "repos/$OC_REPO/labels" -f name="$STUCK_LABEL" -f color=B60205 \
        -f description="automation gave up: needs a human/PM decision" > /dev/null 2>&1 || true
      gh api -X POST "repos/$OC_REPO/issues/$OC_PR_NUMBER/labels" -f "labels[]=$STUCK_LABEL" > /dev/null
      GH_TOKEN="${MARK_TOKEN:-${GH_TOKEN:-}}" gh pr comment "$OC_PR_NUMBER" --repo "$OC_REPO" \
        --body "reviewer の差し戻しが ${n} 件に達したため、自動修正を止めます (上限 ${MAX_FIX_REVIEWS}、合計 ${total}、停止理由 ${decision})。自動復旧を試みます。PM agent が処理します。ラベル \`${STUCK_LABEL}\` を外すと再開できます (再開後は、この停止コメント以降の差し戻しだけを数えます)。${STOP_MARK} <!-- oc-pm-intent: stuck pr=${OC_PR_NUMBER} reason=${decision} -->"
    fi
    reason="$decision"
  fi
}

case "${1:-}" in
  record)
    pr_json="$(gh api "repos/$OC_REPO/pulls/$OC_PR_NUMBER")"
    head_now="$(jq -r .head.sha <<< "$pr_json")"
    {
      printf 'OC_HEAD_BEFORE=%s\n' "$head_now"
      printf 'OC_START_TS=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$GITHUB_ENV"
    gate_run "$pr_json"
    if [ "$stop" = false ]; then printf 'OC_RECORD_OK=1\n' >> "$GITHUB_ENV"; fi
    printf 'stop=%s\nreason=%s\n' "$stop" "$reason" >> "$GITHUB_OUTPUT"
    OC_RECORD_DONE=1
    ;;
  gate)
    pr_json="$(gh api "repos/$OC_REPO/pulls/$OC_PR_NUMBER")"
    gate_run "$pr_json"
    printf 'stop=%s\nreason=%s\n' "$stop" "$reason" >> "$GITHUB_OUTPUT"
    OC_RECORD_DONE=1
    ;;
  snapshot)
    # gate の結果 (OC_GATE_STOP) が false のときだけ通す。true・空・未設定は fail-closed で止める。
    if [ "${OC_GATE_STOP:-}" != false ]; then
      echo "::error::fix-progress snapshot: the window gate did not pass (OC_GATE_STOP=${OC_GATE_STOP:-unset})" >&2
      exit 1
    fi
    head_now="$(pr_head)"
    [ -n "$head_now" ] || exit 1
    {
      printf 'OC_HEAD_BEFORE=%s\n' "$head_now"
      printf 'OC_START_TS=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      printf 'OC_RECORD_OK=1\n'
    } >> "$GITHUB_ENV"
    OC_RECORD_DONE=1
    ;;
  check)
    : "${OC_HEAD_BEFORE:?}" "${OC_START_TS:?}"
    if [ "${OC_RECORD_OK:-}" != 1 ]; then
      echo "::error::fix-progress check: record did not finish the window check (OC_RECORD_OK is unset): no result is given" >&2
      exit 1
    fi
    # head が読めなければ result を出さずに失敗する。空文字を比べると pushed と誤判定され、retry も reopen も走らない無音終了になる (#2899)。
    if ! head_after="$(pr_head)" || [ -z "$head_after" ]; then
      echo "::error::could not read the head of PR #$OC_PR_NUMBER: no fix progress result is written" >&2
      exit 1
    fi
    if [ "$head_after" != "$OC_HEAD_BEFORE" ]; then
      result=pushed
    else
      n="$(gh api --paginate "repos/$OC_REPO/issues/$OC_PR_NUMBER/comments" \
        | jq -s --arg t "$OC_START_TS" --arg l "$IMPLEMENTER_LOGIN" '[.[][] | select(.created_at > $t and .user.login == $l)] | length')"
      if [ "$n" -gt 0 ]; then result=answered; else result=none; fi
    fi
    echo "fix progress: $result (head before ${OC_HEAD_BEFORE:0:10})"
    echo "result=$result" >> "$GITHUB_OUTPUT"
    ;;
  retry-prompt)
    : "${OC_PROMPT_SRC:?}"
    out="$RUNNER_TEMP/opencode-prompt-retry.txt"
    {
      cat "$OC_PROMPT_SRC"
      printf '\n## 再試行 (前回は何もせずに終了した)\n\n'
      printf '前回の試行は commit を push せず、PR にコメントも投稿せずに終了した。これは禁止されている。\n'
      printf '今回は必ず次のどちらかを行うこと。\n'
      printf '1. reviewer の指摘を修正して PR ブランチへ push する。\n'
      printf '2. 修正しない指摘ごとに根拠を PR コメントへ書く (`gh pr comment`)。\n'
    } > "$out"
    chmod 600 "$out"
    echo "prompt_file=$out" >> "$GITHUB_OUTPUT"
    ;;
  reopen)
    # 旧 workflow (reopen サブコマンドを呼ぶ版) との互換。実体は reopen-pr.sh。
    exec bash "$(dirname "$0")/reopen-pr.sh"
    ;;
  *)
    echo "usage: $0 record|gate|snapshot|check|retry-prompt|reopen" >&2
    exit 2
    ;;
esac
