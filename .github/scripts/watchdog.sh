#!/bin/bash
# watchdog.sh — open PR を「レビュー中」か「レビューを受けて修正中」のどちらかに保つ (#719)。
#
# 指示 122/123: 修正もレビューもされていない PR (IDLE) を 1 秒も作らない。主経路はイベント駆動
# (差し戻し -> fix、push -> review) だが、イベントの取りこぼし・run の失敗・main の更新による競合は
# イベントが起きないので、push to main と schedule (5 分) でこのスクリプトが全 open PR を点検して戻す。
#
# 判定 (PR ごと)。まず「カバー済み」か:
#   REVIEWING/FIXING : その PR に紐づく実行中/待機中の opencode.yaml の run がある (pull_request 系は pull_requests に番号が出る。
#                      PM の /oc コメント起動は run のタイトルが PR タイトルと一致する)
# カバーされていなければ IDLE であり、理由ごとに戻す (updated_at が SETTLE 分以内なら、直前の操作の
# イベントが伝播中とみなして次回に回す):
#   CONFLICT          main と競合。競合 PR は pull_request も pull_request_review も起動しないため、差し戻しでは fix を動かせない
#                     (往復回数だけ消費して oc:stuck に近づく)。差し戻しは出さず、repository_dispatch (type oc-fix) で fix モードの
#                     実装 run を起動する (同じ head へは DISPATCH_MAX 回まで。超えたら oc:stuck。#731)。
#                     fork からの PR は dispatch しない (write 権限の run を第三者の入力で動かさないため。oc:stuck も付けず一覧に出すだけ)
#   DRAFT             draft -> ready (ready_for_review で review が起動する)
#   FIX_IDLE          現在の head に CHANGES_REQUESTED があるのに fix run が無い -> CHANGES_REQUESTED を再提出して fix 経路へ
#   APPROVED          approve 済みで未 merge -> merge。失敗したら理由付きの CHANGES_REQUESTED
#   NOREVIEW          現在の head に verdict (APPROVED / CHANGES_REQUESTED) が無い。COMMENT だけの review も含む
#                     (Copilot 待ちの保留は廃止した) -> close -> reopen で review を再起動
# 同じ head に対する復旧が尽きた PR (watchdog の差し戻し OC_WATCHDOG_MAX 回、または review の自動再実行 3 回) は
# oc:stuck ラベルを付けて止める。fix-progress.sh が差し戻しの上限 (OC_MAX_FIX_REVIEWS) で付けるラベルも同じで、ラベル付きの PR は
# 人 (PM) の判断待ちとして一切触らない (ラベルを外すと再開する)。
# merge は --match-head-commit で、点検した head 以外 (その後に push された未レビューの commit) を巻き込まない。
# 1 回の点検で行う操作 (oc:stuck の付与を含む) は OC_MAX_ACTIONS 件まで (古い更新の PR から)。残りは次回に回す。
# 読み取りに失敗した PR・mergeable が未確定の PR は、その回は何も操作せず次回に回す (fail-closed)。
# fork からの PR (head.repo が本リポジトリでない) は CONFLICT でも dispatch しない (write 権限の run を第三者の入力で動かさない)。一覧に出して人が判断する。
#
# 入力不正の補正 (#CI-45): open PR で本文の oc_artifacts に許可されない語があり (prepare-event-context.sh が review を落とす)、
#   この head に verdict が無い (review の打ち切り) なら、その語を除いて本文を直し (除いた語を PR にコメント: oc-artifacts-fixed:<head12>)、
#   oc:stuck を外して review を再起動する。同じ head は 1 回まで。oc:stuck の理由が差し戻し上限 (oc-pm-intent: stuck) の PR は触らない。
#   fork の PR は触らない。CONFLICT は対象外。
# oc:stuck の滞留時間は issues/<N>/events の labeled (oc:stuck) から測り、stuck=N stuck-age-max=分 stuck-age-p50=分 (下側中央値) を出す。
#   点検 1 回で読むのは最大 20 PR (更新の古い順)。
#
# 宙に浮いた issue (blocked でも着手済みでもない open issue) は、最後に floating-issues=N として数えて出力する (数えるだけ。#1950)。
#
# PM Worker の停止検知 (#CI-49): tools/pm/worker_url の URL の /status を `curl -fsS -m 10` で読む (PR の点検の後)。
#   configured と installed がともに true で、fresh が false または last_tick が 15 分より古ければ、障害 issue (ラベル pm-worker-down、
#   題名 `[CI-n] PM Worker 停止 (日付)`) を起票する。configured/installed が false (/setup 未了) では起票しない。
#   open の障害 issue があれば追記のみ (OC_WORKER_NOTE_MIN 分に 1 回まで)。24 時間以内に close した障害 issue は reopen して追記する。
#   fresh が true で last_tick が 5 分以内なら、open の障害 issue にコメントして close する。
#   ファイルが無い・取得失敗・JSON 不正は警告だけ出して何もしない (終了コードは変えない)。OC_WORKER_URL_FILE で URL のファイルを差し替えられる (テスト用)。
#
# 暫定の oc-pm 起動 (#CI-50): Worker が live になるまで、PM agent の判断待ちの対象を repository_dispatch (oc-pm) で起動する。
#   stuck : oc:stuck の PR で、最新の oc-fix-limit コメントに oc-pm-intent: stuck がある (fix-progress.sh の停止印)
#   no_pr : oc:no-pr の open issue で、最後の oc-run-outcome の reason が split か stop (pm-apply・needs-user-input の付いた issue は除く)
#   送るのは kind と ref の 2 つだけ。送る前に対象へ <!-- oc-pm-dispatch:<ref> ts=... --> を残す (残せなければ送らない)。
#   上限は 1 回の点検で 3 件、1 時間に 12 件、同じ ref に 24 時間で 3 件 (記録のコメントを数える。記録は REVIEWER_LOGIN の Bot だけ数える)。
#   Worker の /status が mode=live かつ fresh=true なら送らない。/status が取れないときは live でないとみなして送る。
#   記録の一覧が読めないときは送らない (fail-closed)。DRY=1 は計画だけ表示する。
#
# 入力 (env): GH_TOKEN (reviewer App。review の提出・merge・ready・close/reopen に使う), OC_REPO,
#             RUNS_TOKEN (actions:read。省略時は GH_TOKEN), DRY=1 で操作せず計画だけ表示
set -uo pipefail

: "${OC_REPO:?}"
R="$OC_REPO"
DRY="${DRY:-0}"
REVIEWER_LOGIN="${OC_REVIEWER_LOGIN:-oc-reviewer-for-signature-studio[bot]}"
SETTLE_MIN="${OC_SETTLE_MINUTES:-4}"
MAX_ACTIONS="${OC_MAX_ACTIONS:-12}"
WD_MAX="${OC_WATCHDOG_MAX:-6}"
# 同じ head に対する競合解消の dispatch の上限 (超えたら oc:stuck)
DISPATCH_MAX="${OC_DISPATCH_MAX:-3}"
ARTIFACT_RE='^(fl-win64|plugins-(ott|freshair|serum2|massivex|kilohearts)|toolchain-(retdec|emsdk)|work-(m11|liftdiff|m6-ott|liftlib-targets|liftlib|icall|fw-stage1)|analysis-(ott-binaries|mac-shared)|apt-mingw)$'
RUNS_TOKEN="${RUNS_TOKEN:-${GH_TOKEN:-}}"
now="$(date -u +%s)"
age_min() { echo $(((now - $(date -u -d "$1" +%s)) / 60)); }

do_it() { # do_it <説明> <コマンド...>
  local what="$1"
  shift
  if [ "$DRY" = 1 ]; then
    echo "  DRY: $what"
  else
    echo "  DO : $what"
    "$@" > /dev/null || echo "::warning::failed: $what"
  fi
}
request_changes() { gh pr review "$1" --repo "$R" --request-changes --body "$2"; }
reopen() { # reopen <PR> <head>: 試行を数えるマーカー付きのコメントを残してから reopen する (verify-review-verdict.sh と同じ書式)
  local marker="review-retry:${2:0:12}"
  gh pr comment "$1" --repo "$R" \
    --body "[watchdog] 現在の head (${2:0:7}) に verdict が無いため、review を再起動します。<!-- $marker -->" || true
  OC_REPO="$R" OC_PR_NUMBER="$1" bash "$(dirname "$0")/reopen-pr.sh"
}
dispatch_fix() { # dispatch_fix <PR> <head> <reason> <artifacts>: 試行を数えるマーカー付きのコメント -> repository_dispatch (oc-fix)
  local marker="oc-dispatch:${2:0:12}"
  gh pr comment "$1" --repo "$R" \
    --body "[watchdog] この PR は main と競合しています。競合 PR は review イベントでワークフローが起動しないため、repository_dispatch で競合解消の実装 run を起動します (head ${2:0:7})。<!-- $marker -->" || true
  gh api -X POST "repos/$R/dispatches" -f event_type=oc-fix \
    -F "client_payload[pr]=$1" -f "client_payload[reason]=$3" -f "client_payload[artifacts]=$4"
}
pr_artifacts() { # pr_artifacts <PR JSON>: PR 本文の oc_artifacts 行から、allowlist に一致する語だけを取り出す
  local line name out=""
  line="$(jq -r '.body // ""' <<< "$1" | grep -m1 -E '^[[:space:]]*oc_artifacts:' || true)"
  for name in $(printf '%s' "${line#*oc_artifacts:}" | tr -cd 'a-z0-9 -'); do
    printf '%s' "$name" | grep -qE "$ARTIFACT_RE" && out="${out:+$out }$name"
  done
  printf '%s' "$out"
}
artifact_names() { # artifact_names <PR JSON>: oc_artifacts 行の語を 1 行 1 語で出す (prepare-event-context.sh と同じ分割)
  local line
  line="$(jq -r '.body // ""' <<< "$1" | grep -m1 -E '^[[:space:]]*oc_artifacts:' || true)"
  printf '%s' "${line#*oc_artifacts:}" | tr -cd 'a-z0-9 -' | tr ' ' '\n' | grep -v '^$' || true
}
bad_artifacts() { # bad_artifacts <PR JSON>: prepare-event-context.sh が拒む語 (許可名に無い語。none は単独以外も拒む)
  local names name total
  names="$(artifact_names "$1")"
  [ -n "$names" ] || return 0
  total="$(printf '%s\n' "$names" | wc -l)"
  while IFS= read -r name; do
    if [ "$name" = none ]; then
      [ "$total" -gt 1 ] && echo "$name"
    elif ! printf '%s' "$name" | grep -qE "$ARTIFACT_RE"; then
      echo "$name"
    fi
  done <<< "$names"
  return 0
}
repair_artifacts() { # repair_artifacts <PR> <head> <PR JSON> <stuck 0|1>: 許可されない語を除いて本文を直し、review を再起動する (#CI-45)
  local n="$1" head="$2" json="$3" stuck="$4" kept removed body f
  kept="$(artifact_names "$json" | grep -E "$ARTIFACT_RE" | tr '\n' ' ' | sed 's/ *$//')"
  removed="$(bad_artifacts "$json" | tr '\n' ' ' | sed 's/ *$//')"
  body="$(jq -r '.body // ""' <<< "$json")"
  f="${RUNNER_TEMP:-/tmp}/oc-artifacts-$n.md"
  awk -v new="oc_artifacts: ${kept:-none}" 'BEGIN { d = 0 } !d && /^[[:space:]]*oc_artifacts:/ { print new; d = 1; next } { print }' <<< "$body" > "$f" || return 1
  gh pr edit "$n" --repo "$R" --body-file "$f" > /dev/null || return 1
  gh pr comment "$n" --repo "$R" --body "[watchdog] PR 本文の oc_artifacts に許可されていない素材名 (${removed}) があったため、review が起動せず打ち切られていました。その語を除いて本文を更新し、review を再起動します。<!-- oc-artifacts-fixed:${head:0:12} -->" > /dev/null || true
  if [ "$stuck" = 1 ]; then gh pr edit "$n" --repo "$R" --remove-label oc:stuck > /dev/null || true; fi
  reopen "$n" "$head"
}
mark_stuck() { # mark_stuck <PR>
  gh label create oc:stuck --repo "$R" --color B60205 --description "automatic review/fix recovery exhausted; needs a human decision" --force > /dev/null 2>&1 || true
  gh pr edit "$1" --repo "$R" --add-label oc:stuck > /dev/null 2>&1 || true
}

# --- PM Worker の停止検知 (#CI-49) ---
# Worker (infra/pm-worker) の /status を読み、一度でも稼働に入った Worker (configured・installed がともに true) が止まっていたら
# 障害 issue (ラベル pm-worker-down) を起票する。configured/installed が false の Worker (/setup 未了) では起票しない。
# 読めない・JSON が不正なときは警告だけ出して何もしない。この検知の失敗は watchdog 全体の終了コードを変えない。
WORKER_URL_FILE="${OC_WORKER_URL_FILE:-$(dirname "$0")/../../tools/pm/worker_url}"
WORKER_LABEL=pm-worker-down
WORKER_STALE_SEC=900   # last_tick がこれより古い (または fresh=false) と停止
WORKER_RECOVER_SEC=300 # fresh=true かつ last_tick がこれ以内なら回復
WORKER_REOPEN_SEC=86400
WORKER_NOTE_MIN="${OC_WORKER_NOTE_MIN:-60}" # 既存の障害 issue への追記の最小間隔 (5 分ごとの点検でコメントを水増ししない)
WORKER_TITLE_LIMIT=3000 # [CI-n] の採番に読む題名の件数 (gh の既定値では足りない)。これに達したら一覧が欠けうるので起票しない
worker_line="worker=unknown"
worker_status_json=""
worker_open_issues() { # open で pm-worker-down ラベルの issue を「番号 作成時刻」で新しい順に出す。一覧が取れなければ失敗 (REST の一覧は PR だけを返す場合があるため gh issue list を使う)
  local raw
  raw="$(gh issue list --repo "$R" --state open --label "$WORKER_LABEL" --limit 200 --json number,createdAt,closedAt)" || return 1
  jq -r 'map(select(.pull_request == null)) | sort_by(.createdAt) | reverse | .[] | "\(.number) \(.createdAt)"' <<< "$raw"
}
worker_status_copy() { # worker_status_copy <status json>: /status の写し。秘密を示す名前のキーは念のため除く
  jq -S 'walk(if type == "object" then with_entries(select(.key | test("token|secret|key|private|password|pem|jwt|credential"; "i") | not)) else . end)' <<< "$1"
}
worker_body() { # worker_body <kind: new|note> <理由> <status json>
  local at
  at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ "$1" = new ]; then
    printf '%s\n' "PM Worker (\`signature-studio-pm\`) が停止している可能性があります。watchdog.sh が \`/status\` を読んで検知しました (${at})。" ""
    printf '%s\n' "- 判定: $2" "- 条件: \`configured\` と \`installed\` がともに true (一度でも稼働に入った Worker) で、\`fresh\` が false、または \`last_tick\` が 15 分より古い" ""
  else
    printf '%s\n' "[watchdog] PM Worker はまだ回復していません (${at})。判定: $2" ""
  fi
  printf '%s\n' "## /status の写し (集計のみ。秘密を含まない)" '```json'
  worker_status_copy "$3"
  printf '%s\n' '```' ""
  if [ "$1" = new ]; then
    printf '%s\n' "確認すること: cron / Durable Object alarm の停止・例外、GitHub App (PM) の失効。回復すると (\`fresh\` が true かつ \`last_tick\` が 5 分以内) watchdog.sh がこの issue にコメントして close します。" "" "@pycabbage" "<!-- oc-worker-down -->"
  else
    printf '%s\n' "<!-- oc-worker-down-note -->"
  fi
}
worker_note() { gh issue comment "$1" --repo "$R" --body-file "$2"; } # worker_note <issue> <body file>
worker_reopen() { gh issue reopen "$1" --repo "$R" && worker_note "$1" "$2"; }
worker_file() { # worker_file <title> <body file>
  gh label create "$WORKER_LABEL" --repo "$R" --color B60205 --description "PM Worker (signature-studio-pm) stopped; filed by watchdog.sh" --force > /dev/null 2>&1 || true
  gh issue create --repo "$R" --title "$1" --body-file "$2" --label "$WORKER_LABEL"
}
worker_down() { # worker_down <status json> <理由>
  local body="$1" reason="$2" open target created cm last closed all allpr maxn f="${RUNNER_TEMP:-/tmp}/oc-worker-down-body.md"
  if ! open="$(worker_open_issues)"; then
    echo "::warning::failed to list $WORKER_LABEL issues; no issue is filed or updated"
    return 0
  fi
  target="${open%%$'\n'*}"
  if [ -n "$target" ]; then
    # 既存の障害 issue があれば新規に起票せず追記だけする。直近の追記 (または起票) から WORKER_NOTE_MIN 分以内なら追記も見送る。
    created="${target#* }"
    target="${target%% *}"
    if ! cm="$(gh api --paginate "repos/$R/issues/$target/comments")"; then
      echo "::warning::failed to read comments of #$target; no note is added"
      return 0
    fi
    last="$(jq -s -r --arg who "$REVIEWER_LOGIN" --arg c "$created" \
      '[.[][] | select(.user.login == $who and .user.type == "Bot" and ((.body // "") | contains("oc-worker-down-note"))) | .created_at] + [$c] | max' <<< "$cm")"
    if [ "$(age_min "$last")" -lt "$WORKER_NOTE_MIN" ]; then
      echo "worker: #$target is already reported (last note ${last}); no new note"
      return 0
    fi
    worker_body note "$reason" "$body" > "$f"
    do_it "add a note to the open $WORKER_LABEL issue #$target" worker_note "$target" "$f"
    return 0
  fi
  if ! closed="$(gh issue list --repo "$R" --state closed --label "$WORKER_LABEL" --limit 200 --json number,createdAt,closedAt)"; then
    echo "::warning::failed to list closed $WORKER_LABEL issues; no issue is filed"
    return 0
  fi
  target="$(jq -r --argjson sec "$WORKER_REOPEN_SEC" \
    '[.[] | select(.pull_request == null and .closedAt != null and (.closedAt | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601) > (now - $sec))] | sort_by(.closedAt) | last | .number // empty' <<< "$closed")"
  if [ -n "$target" ]; then
    worker_body note "$reason" "$body" > "$f"
    do_it "reopen #$target (closed within 24h) and add a note" worker_reopen "$target" "$f"
    return 0
  fi
  if ! all="$(gh issue list --repo "$R" --state all --limit "$WORKER_TITLE_LIMIT" --json title)" ||
    ! allpr="$(gh pr list --repo "$R" --state all --limit "$WORKER_TITLE_LIMIT" --json title)"; then
    echo "::warning::failed to count [CI-n] titles; no issue is filed"
    return 0
  fi
  if [ "$(jq length <<< "$all")" -ge "$WORKER_TITLE_LIMIT" ] || [ "$(jq length <<< "$allpr")" -ge "$WORKER_TITLE_LIMIT" ]; then
    echo "::warning::[CI-n] title list reached the limit ($WORKER_TITLE_LIMIT); no issue is filed"
    return 0
  fi
  maxn="$(jq -s -r '[.[][] | (.title // "") | capture("^\\[CI-(?<n>[0-9]+)[a-z]?\\]") | .n | tonumber] | max // 0' <<< "$all"$'\n'"$allpr")"
  worker_body new "$reason" "$body" > "$f"
  do_it "file '[CI-$((maxn + 1))] PM Worker 停止 ($(date -u +%Y-%m-%d))' with label $WORKER_LABEL" \
    worker_file "[CI-$((maxn + 1))] PM Worker 停止 ($(date -u +%Y-%m-%d))" "$f"
}
worker_recovered() { # worker_recovered <last_tick> <age 秒>: open の障害 issue にコメントして close する
  local open line
  if ! open="$(worker_open_issues)"; then
    echo "::warning::failed to list $WORKER_LABEL issues; none is closed"
    return 0
  fi
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    do_it "close #${line%% *} (PM Worker recovered)" gh issue close "${line%% *}" --repo "$R" \
      --comment "[watchdog] PM Worker が回復しました (fresh=true、last_tick=$1、$(($2 / 60)) 分前)。この issue を close します。24 時間以内に再び停止した場合は reopen します。<!-- oc-worker-recovered -->"
  done <<< "$open"
}
worker_check() { # 結果の 1 行を worker_line に入れる。常に 0 を返す
  local url body cfg inst fresh tick age="" ts reason=""
  if [ ! -f "$WORKER_URL_FILE" ]; then
    echo "::warning::tools/pm/worker_url not found; PM Worker check skipped"
    worker_line="worker=skipped (no worker_url)"
    return 0
  fi
  url="$(head -n 1 "$WORKER_URL_FILE" | tr -d '[:space:]')"
  url="${url%/}"
  if [[ ! "$url" =~ ^https?:// ]]; then
    echo "::warning::tools/pm/worker_url is not an http(s) URL; PM Worker check skipped"
    worker_line="worker=skipped (bad worker_url)"
    return 0
  fi
  if ! body="$(curl -fsS -m 10 "$url/status")"; then
    echo "::warning::could not read $url/status; PM Worker check skipped"
    worker_line="worker=skipped (status unreachable)"
    return 0
  fi
  if ! jq -e 'type == "object" and (.configured | type) == "boolean" and (.installed | type) == "boolean" and (.fresh | type) == "boolean" and ((.last_tick | type) == "string" or .last_tick == null)' <<< "$body" > /dev/null 2>&1; then
    echo "::warning::$url/status is not the expected JSON; PM Worker check skipped"
    worker_line="worker=skipped (bad status json)"
    return 0
  fi
  worker_status_json="$body"
  cfg="$(jq -r .configured <<< "$body")"
  inst="$(jq -r .installed <<< "$body")"
  fresh="$(jq -r .fresh <<< "$body")"
  tick="$(jq -r '.last_tick // ""' <<< "$body")"
  if [[ "$tick" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z$ ]] && ts="$(date -u -d "$tick" +%s 2> /dev/null)"; then
    age=$(($(date -u +%s) - ts))
    [ "$age" -lt 0 ] && age=0
  fi
  if [ "$fresh" = true ] && [ -n "$age" ] && [ "$age" -le "$WORKER_RECOVER_SEC" ]; then
    worker_line="worker=ok (fresh=true last_tick=${age}s ago)"
    worker_recovered "$tick" "$age"
  elif [ "$cfg" != true ] || [ "$inst" != true ]; then
    worker_line="worker=not-set-up (configured=$cfg installed=$inst; no issue is filed)"
  elif [ "$fresh" = false ]; then
    reason="fresh=false (last_tick=${tick:-null}${age:+、${age} 秒前})"
    worker_line="worker=down ($reason)"
    worker_down "$body" "$reason"
  elif [ -z "$age" ]; then
    echo "::warning::/status has no readable last_tick; PM Worker check skipped"
    worker_line="worker=skipped (no last_tick)"
  elif [ "$age" -gt "$WORKER_STALE_SEC" ]; then
    reason="last_tick が ${age} 秒前 (> ${WORKER_STALE_SEC} 秒): ${tick}"
    worker_line="worker=down ($reason)"
    worker_down "$body" "$reason"
  else
    worker_line="worker=ok (fresh=true last_tick=${age}s ago)"
  fi
  return 0
}

# 実行中/待機中の run (pull_requests・タイトル・workflow のファイル)。一覧が取れなければ何も操作しない。
active_raw=""
for s in in_progress queued pending waiting; do
  if ! out="$(GH_TOKEN="$RUNS_TOKEN" gh api "repos/$R/actions/runs?status=$s&per_page=100" \
    --jq '.workflow_runs[] | {event, title: .display_title, path, sha: (.head_sha // ""), prs: [.pull_requests[].number]}')"; then
    echo "::error::failed to list $s runs; no action this pass"
    exit 1
  fi
  active_raw+="$out"$'\n'
done
active="$(jq -s '.' <<< "$active_raw")"

if ! pr_raw="$(gh api --paginate "repos/$R/pulls?state=open&per_page=100")"; then
  echo "::error::failed to list open PRs; no action this pass"
  exit 1
fi
prs="$(jq -s 'add // [] | sort_by(.updated_at)' <<< "$pr_raw")"
total="$(jq length <<< "$prs")"

# oc:stuck の滞留時間 (#CI-45): 付与時刻は issues/<N>/events の labeled。読むのは最大 20 PR (更新の古い順)。
stuck_nums="$(jq -c '[.[] | select([.labels[].name] | index("oc:stuck") != null) | .number]' <<< "$prs")"
stuck_n="$(jq length <<< "$stuck_nums")"
stuck_ages=()
for sn in $(jq -r '.[0:20][]' <<< "$stuck_nums"); do
  if ev="$(gh api --paginate "repos/$R/issues/$sn/events")"; then
    at="$(jq -s -r '[.[][] | select(.event == "labeled" and .label.name == "oc:stuck") | .created_at] | last // ""' <<< "$ev")"
    [ -n "$at" ] && stuck_ages+=("$(age_min "$at")")
  else
    echo "#$sn: failed to read events (stuck age unknown)"
  fi
done
covered_n=0
acted=0
deferred=0
declare -A tally=()
summary=""

for i in $(seq 0 $((total - 1))); do
  pr="$(jq -c ".[$i]" <<< "$prs")"
  n="$(jq -r .number <<< "$pr")"
  title="$(jq -r .title <<< "$pr")"
  head="$(jq -r .head.sha <<< "$pr")"
  draft="$(jq -r .draft <<< "$pr")"
  upd_age="$(age_min "$(jq -r .updated_at <<< "$pr")")"

  # pull_request 系の run は head が現在の head と一致するものだけ担当にする (古い head の run で IDLE を隠さない)。
  # head_sha を持たない run (dispatch・comment 等) は従来どおり番号・タイトルで判定する。
  if jq -e --argjson n "$n" --arg t "$title" --arg h "$head" \
    'any(.[]; .path == ".github/workflows/opencode.yaml" and (((.prs | index($n)) != null and ((.sha // "") == "" or .sha == $h)) or ((.event == "issue_comment" or .event == "workflow_dispatch") and .title == $t) or (.event == "repository_dispatch" and .title == ("oc-fix #" + ($n | tostring)))))' \
    <<< "$active" > /dev/null; then
    covered_n=$((covered_n + 1))
    continue
  fi

  was_stuck=0
  if jq -e '[.labels[].name] | index("oc:stuck") != null' <<< "$pr" > /dev/null; then
    # 入力不正 (許可されない素材名) の PR だけ、review が打ち切られたかを読み直して補正の候補にする。それ以外は人の判断待ちで触らない。
    if [ -z "$(bad_artifacts "$pr")" ]; then
      echo "#$n STUCK_LABELLED: oc:stuck is set, waiting for a human decision"
      tally[STUCK_LABELLED]=$((${tally[STUCK_LABELLED]:-0} + 1))
      continue
    fi
    was_stuck=1
  fi

  # --- IDLE: 理由を判定する。読めなかった PR・未確定の mergeable は操作せず次回に回す ---
  mergeable=null
  for _ in 1 2 3; do
    if ! detail="$(gh api "repos/$R/pulls/$n")"; then
      echo "#$n skip: failed to read the PR (no action this pass)"
      continue 2
    fi
    mergeable="$(jq -r .mergeable <<< "$detail")"
    [ "$mergeable" != null ] && break
    sleep "${OC_MERGEABLE_WAIT:-2}"
  done
  if [ "$mergeable" = null ]; then
    echo "#$n skip: mergeability is still unknown (checked next pass)"
    continue
  fi
  if ! rvs_raw="$(gh api --paginate "repos/$R/pulls/$n/reviews")"; then
    echo "#$n skip: failed to read reviews (no action this pass)"
    continue
  fi
  if ! cm_raw="$(gh api --paginate "repos/$R/issues/$n/comments")"; then
    echo "#$n skip: failed to read comments (no action this pass)"
    continue
  fi
  rvs="$(jq -s --arg h "$head" --arg who "$REVIEWER_LOGIN" \
    '[.[][] | select(.user.login == $who and .user.type == "Bot" and .commit_id == $h)]' <<< "$rvs_raw")"
  # verdict を持つ最後の review で判定する (verify-review-verdict.sh と同じ。COMMENTED は verdict ではない)
  rv="$(jq -c '[.[] | select(.state == "APPROVED" or .state == "CHANGES_REQUESTED")] | last // {}' <<< "$rvs")"
  st="$(jq -r '.state // "NONE"' <<< "$rv")"
  wd_n="$(jq '[.[] | select((.body // "") | contains("(watchdog)"))] | length' <<< "$rvs")"
  retry_n="$(jq -s --arg m "review-retry:${head:0:12}" --arg who "$REVIEWER_LOGIN" \
    '[.[][] | select(.user.login == $who and .user.type == "Bot" and (.body | contains($m)))] | length' <<< "$cm_raw")"

  disp_n="$(jq -s --arg m "oc-dispatch:${head:0:12}" --arg who "$REVIEWER_LOGIN" \
    '[.[][] | select(.user.login == $who and .user.type == "Bot" and (.body | contains($m)))] | length' <<< "$cm_raw")"
  # 入力不正の補正 (#CI-45): この head で補正済みか / 差し戻し上限 (fix-progress.sh の停止印) で止まった PR か
  bad="$(bad_artifacts "$pr")"
  repaired_n="$(jq -s --arg m "oc-artifacts-fixed:${head:0:12}" --arg who "$REVIEWER_LOGIN" \
    '[.[][] | select(.user.login == $who and .user.type == "Bot" and (.body | contains($m)))] | length' <<< "$cm_raw")"
  pm_stuck_n="$(jq -s '[.[][] | select((.body // "") | contains("oc-pm-intent: stuck"))] | length' <<< "$cm_raw")"

  reason=""
  if [ "$mergeable" = false ]; then
    reason=CONFLICT
  elif [ "$draft" = true ]; then
    reason=DRAFT
  else
    case "$st" in
      CHANGES_REQUESTED) reason=FIX_IDLE ;;
      APPROVED) reason=APPROVED ;;
      *) reason=NOREVIEW ;;
    esac
  fi

  # oc:stuck の PR は、入力不正で review が打ち切られた (verdict 無し・差し戻し上限ではない・未補正) 場合だけ補正する
  if [ "$was_stuck" = 1 ] && { [ "$reason" != NOREVIEW ] || [ "$pm_stuck_n" -gt 0 ] || [ "$repaired_n" -gt 0 ]; }; then
    echo "#$n STUCK_LABELLED: oc:stuck is set, input repair does not apply"
    tally[STUCK_LABELLED]=$((${tally[STUCK_LABELLED]:-0} + 1))
    continue
  fi

  tally[$reason]=$((${tally[$reason]:-0} + 1))
  line="#$n $reason (updated ${upd_age}m ago)"
  if [ "$reason" = NOREVIEW ] && [ -n "$bad" ]; then
    line="$line [oc_artifacts に許可されない素材名: $(echo "$bad" | tr '\n' ' ' | sed 's/ *$//')]"
  fi
  summary="$summary- $line"$'\n'
  echo "$line"

  # fork からの PR は dispatch しない: dispatch の run は write 権限で動き、fork の本文・コメント・ブランチ内容は第三者が書ける。
  # head.repo が読めない (削除された fork など) 場合も fork とみなす。oc:stuck は付けず、人が判断する。
  # 入力不正の補正も本文を書き換えるので fork からの PR は触らない。
  if { [ "$reason" = CONFLICT ] || { [ "$reason" = NOREVIEW ] && [ -n "$bad" ]; }; } && [ "$(jq -r '.head.repo.full_name // ""' <<< "$pr")" != "$R" ]; then
    echo "  skip: fork からの PR は自動対応しない (人が判断する。oc:stuck は付けない)"
    continue
  fi

  if [ "$upd_age" -lt "$SETTLE_MIN" ]; then
    echo "  skip: a recent update is still propagating"
    continue
  fi
  if [ "$acted" -ge "$MAX_ACTIONS" ]; then
    deferred=$((deferred + 1))
    echo "  deferred (reached OC_MAX_ACTIONS=$MAX_ACTIONS)"
    continue
  fi
  acted=$((acted + 1))

  # 復旧に失敗し続ける PR を延々と叩かない。同じ head への watchdog の差し戻しが WD_MAX 回、または
  # review の自動再実行が尽きた (review-retry が 3 回) PR は oc:stuck を付けて止める (人の判断が要る)。
  # 入力不正の補正が未実施なら、review 再起動の上限より先に補正する (補正で review が起動し直す)。
  # 補正を 1 回しても入力不正が残る head は、人の判断が要る (oc:stuck)。
  repair_due=0
  if [ "$reason" = NOREVIEW ] && [ -n "$bad" ] && [ "$repaired_n" -eq 0 ]; then repair_due=1; fi
  if { [ "$reason" != NOREVIEW ] && [ "$reason" != CONFLICT ] && [ "$wd_n" -ge "$WD_MAX" ]; } || { [ "$reason" = NOREVIEW ] && [ "$repair_due" = 0 ] && [ "$retry_n" -ge 3 ]; } || { [ "$reason" = CONFLICT ] && [ "$disp_n" -ge "$DISPATCH_MAX" ]; } || { [ "$reason" = NOREVIEW ] && [ -n "$bad" ] && [ "$repaired_n" -ge 1 ]; }; then
    echo "  STUCK: automatic recovery exhausted on ${head:0:7} (watchdog=$wd_n review-retry=$retry_n dispatch=$disp_n repaired=$repaired_n): labelled oc:stuck, no further action"
    do_it "oc:stuck on #$n" mark_stuck "$n"
    continue
  fi

  case "$reason" in
    CONFLICT)
      # 競合 PR は pull_request / pull_request_review のどちらでも起動しないので、差し戻しでは fix を動かせない (#731)。
      # repository_dispatch は競合に左右されない。
      do_it "dispatch oc-fix (conflict) for #$n" dispatch_fix "$n" "$head" conflict "$(pr_artifacts "$pr")"
      ;;
    DRAFT)
      do_it "ready #$n" gh pr ready "$n" --repo "$R"
      ;;
    FIX_IDLE)
      do_it "re-request changes on #$n" request_changes "$n" \
        "[watchdog] 現在の head に対する直前の oc-reviewer の差し戻し (CHANGES_REQUESTED) の指摘を、まだ誰も修正していません。その review・inline コメント・Copilot の指摘を読み、修正して push してください。(watchdog)"
      ;;
    APPROVED)
      if [ "$DRY" = 1 ]; then
        echo "  DRY: merge #$n"
      elif gh pr merge "$n" --repo "$R" --merge --delete-branch --match-head-commit "$head" > /dev/null 2> "${RUNNER_TEMP:-/tmp}/merge-err.txt"; then
        echo "  DO : merged #$n"
      else
        err="$(head -c 300 "${RUNNER_TEMP:-/tmp}/merge-err.txt")"
        echo "  merge failed: $err"
        do_it "request-changes (merge failed) on #$n" request_changes "$n" \
          "[merge-failed] approve 済みですが merge できませんでした: ${err}。原因を解消して push してください。(watchdog)"
      fi
      ;;
    NOREVIEW)
      if [ -n "$bad" ]; then
        do_it "repair oc_artifacts (remove: $(echo "$bad" | tr '\n' ' ')) and reopen #$n" repair_artifacts "$n" "$head" "$pr" "$was_stuck"
      else
        do_it "reopen #$n (restart the review)" reopen "$n" "$head"
      fi
      ;;
  esac
done

# --- 宙に浮いた issue の集計 (数えるだけ。何も操作しない。launch は PM Worker の責務) (#1950) ---
# 依頼者指示: 全ての issue は常に『blocked』『着手済み』『closed』のいずれかであるべき。
# 宙に浮いている = open issue で、次のどれにも当たらないもの:
#   blocked   : ラベル blocked、または GitHub の issue dependencies に open な blocker がある (issue_dependencies_summary.blocked_by > 0)
#   着手済み   : この issue を指す open PR がある (ブランチ名 <N>-... か本文の Closes/Refs/Fixes #N)、または実行中の implement run がある
#               (issue_comment / workflow_dispatch の run で、run のタイトルが issue のタイトルと一致する)
#   明示的な終了状態 : ラベル oc:no-pr (implement run が PR も push も出さずに終了した印。record-run-outcome.sh)、needs-user-input、oc:stuck
# 本文の『依存: #N』『親: #N』による待ちは見ない (PM Worker の分類の責務)。そのため、これは上限値の目安である。
# 一覧が取れなければ警告だけ出し、PR の点検結果には影響させない。
floating_line="floating-issues=unknown (could not list open issues)"
if iss_raw="$(gh api --paginate "repos/$R/issues?state=open&per_page=100" 2> /dev/null)"; then
  floating="$(jq -s --argjson prs "$prs" --argjson active "$active" '
    [ .[][] | select(.pull_request == null)
      | . as $i
      | select(([$i.labels[].name] | any(. == "blocked" or . == "oc:no-pr" or . == "needs-user-input" or . == "oc:stuck")) | not)
      | select((($i.issue_dependencies_summary.blocked_by // 0) > 0) | not)
      | select(any($prs[]; ((.head.ref // "") | test("^" + ($i.number | tostring) + "-")) or ((.body // "") | test("(Closes|Refs|Fixes|Resolves) #" + ($i.number | tostring) + "([^0-9]|$)"; "i"))) | not)
      | select(any($active[]; .path == ".github/workflows/opencode.yaml" and (.event == "issue_comment" or .event == "workflow_dispatch") and (.title | gsub("^\\s+|\\s+$"; "")) == ($i.title | gsub("^\\s+|\\s+$"; ""))) | not)
      | $i.number ] | sort' <<< "$iss_raw" 2> /dev/null)" || floating=""
  if [ -n "$floating" ]; then
    floating_n="$(jq length <<< "$floating")"
    floating_line="floating-issues=$floating_n (open, not blocked, no open PR, no running implement run, none of oc:no-pr / needs-user-input / oc:stuck)"
    [ "$floating_n" -gt 0 ] && floating_line="$floating_line first: $(jq -r '.[0:20] | map("#" + tostring) | join(" ")' <<< "$floating")"
  fi
fi
echo "$floating_line"

stuck_line="stuck=$stuck_n stuck-age-max=unknown stuck-age-p50=unknown"
if [ "${#stuck_ages[@]}" -gt 0 ]; then
  mapfile -t sorted < <(printf '%s\n' "${stuck_ages[@]}" | sort -n)
  stuck_line="stuck=$stuck_n stuck-age-max=${sorted[$((${#sorted[@]} - 1))]} stuck-age-p50=${sorted[$(((${#sorted[@]} - 1) / 2))]}"
fi
echo "$stuck_line"

worker_check
echo "$worker_line"

# --- 暫定の oc-pm 起動 (#CI-50)。判定と上限は冒頭の説明を正とする ---
PM_PASS_MAX=3
PM_HOUR_MAX=12
PM_REF_DAY_MAX=3
pm_dispatch() { # pm_dispatch <kind> <ref>: 記録のコメントを残してから oc-pm を送る。記録できなければ送らない (payload は kind と ref だけ)
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  gh issue comment "$2" --repo "$R" --body "[watchdog] PM agent (oc-pm, kind=$1) を起動します。<!-- oc-pm-dispatch:$2 ts=$ts -->" > /dev/null || return 1
  gh api -X POST "repos/$R/dispatches" -f event_type=oc-pm -F "client_payload[kind]=$1" -F "client_payload[ref]=$2" > /dev/null
}
pm_line="oc-pm sent=0"
pm_cands=()
if [ -n "$worker_status_json" ] && jq -e '.mode == "live" and .fresh == true' <<< "$worker_status_json" > /dev/null 2>&1; then
  pm_line="oc-pm sent=0 (PM Worker is live and fresh; no dispatch)"
else
  for sn in $(jq -r '.[]' <<< "$stuck_nums"); do
    if ! cm="$(gh api --paginate "repos/$R/issues/$sn/comments")"; then
      echo "#$sn oc-pm: failed to read comments (not a candidate this pass)"
      continue
    fi
    fixl="$(jq -s -r --arg who "$REVIEWER_LOGIN" '[.[][] | select(.user.login == $who and .user.type == "Bot" and ((.body // "") | contains("<!-- oc-fix-limit -->")))] | last | .body // ""' <<< "$cm")"
    if printf '%s' "$fixl" | grep -q 'oc-pm-intent: stuck'; then
      pm_cands+=("stuck $sn")
    fi
  done
  if nopr_raw="$(gh issue list --repo "$R" --state open --label oc:no-pr --limit 200 --json number,labels)"; then
    for n in $(jq -r '.[] | select(([.labels[].name] | any(. == "pm-apply" or . == "needs-user-input")) | not) | .number' <<< "$nopr_raw"); do
      if ! cm="$(gh api --paginate "repos/$R/issues/$n/comments")"; then
        echo "#$n oc-pm: failed to read comments (not a candidate this pass)"
        continue
      fi
      outcome="$(jq -s -r '[.[][] | select(.user.type == "Bot" and ((.body // "") | contains("<!-- oc-run-outcome:")))] | last | .body // ""' <<< "$cm")"
      reason="$(printf '%s' "$outcome" | grep -oE 'oc-run-outcome: no-pr reason=[a-z_]+' | head -n 1 | sed 's/.*reason=//')"
      case "$reason" in
        split | stop) pm_cands+=("no_pr $n") ;;
      esac
    done
  else
    echo "::warning::failed to list oc:no-pr issues; no no_pr dispatch this pass"
  fi
  if [ "${#pm_cands[@]}" -eq 0 ]; then
    pm_line="oc-pm candidates=0 sent=0"
  else
    # 記録 (REVIEWER_LOGIN の Bot が残した oc-pm-dispatch) を 24 時間ぶん 1 回で読み、1 時間の件数と ref ごとの件数を数える。
    since="$(date -u -d "@$((now - 86400))" +%Y-%m-%dT%H:%M:%SZ)"
    pm_verb=sent
    [ "$DRY" = 1 ] && pm_verb=planned
    if ! ledger="$(gh api -X GET "repos/$R/issues/comments" -f since="$since" -f per_page=100 --paginate)" ||
      ! records="$(jq -s -r --arg who "$REVIEWER_LOGIN" '[.[][] | select(.user.login == $who and .user.type == "Bot") | (.body // "") | scan("<!-- oc-pm-dispatch:([0-9]{1,7}) ts=([^ ]+) -->")] | .[] | "\(.[0]) \(.[1])"' <<< "$ledger")"; then
      echo "::warning::failed to read the oc-pm dispatch records; no dispatch this pass"
      pm_line="oc-pm candidates=${#pm_cands[@]} $pm_verb=0 (dispatch records unreadable)"
    else
      pm_hour=0
      declare -A pm_day=()
      while read -r ref_s ts_m; do
        [ -n "$ref_s" ] || continue
        ts_s="$(date -u -d "$ts_m" +%s 2> /dev/null)" || ts_s="$now"
        age_s=$((now - ts_s))
        [ "$age_s" -lt 3600 ] && pm_hour=$((pm_hour + 1))
        [ "$age_s" -lt 86400 ] && pm_day[$ref_s]=$((${pm_day[$ref_s]:-0} + 1))
      done <<< "$records"
      pm_sent=0 pm_deferred=0 pm_skipped=0
      for c in "${pm_cands[@]}"; do
        kind="${c% *}" ref="${c#* }"
        if [ "$pm_sent" -ge "$PM_PASS_MAX" ]; then
          echo "oc-pm: $kind #$ref deferred (reached $PM_PASS_MAX in this pass)"
          pm_deferred=$((pm_deferred + 1))
          continue
        fi
        if [ "$pm_hour" -ge "$PM_HOUR_MAX" ]; then
          echo "oc-pm: $kind #$ref deferred (reached $PM_HOUR_MAX in the last hour)"
          pm_deferred=$((pm_deferred + 1))
          continue
        fi
        if [ "${pm_day[$ref]:-0}" -ge "$PM_REF_DAY_MAX" ]; then
          echo "oc-pm: $kind #$ref skipped (dispatched ${pm_day[$ref]} times in the last 24h)"
          pm_skipped=$((pm_skipped + 1))
          continue
        fi
        # 記録の後で送る。送信が失敗しても件数には数える (記録は残っているかもしれないため、上限は多めに数える)。
        do_it "dispatch oc-pm kind=$kind for #$ref" pm_dispatch "$kind" "$ref"
        pm_sent=$((pm_sent + 1))
        pm_hour=$((pm_hour + 1))
        pm_day[$ref]=$((${pm_day[$ref]:-0} + 1))
      done
      pm_line="oc-pm candidates=${#pm_cands[@]} $pm_verb=$pm_sent deferred=$pm_deferred skipped=$pm_skipped"
    fi
  fi
fi
echo "$pm_line"

echo "open=$total covered(REVIEWING/FIXING)=$covered_n idle=$((total - covered_n)) acted=$acted deferred=$deferred"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "## PR watchdog"
    echo
    echo "open=$total / covered(REVIEWING・FIXING)=$covered_n / idle=$((total - covered_n)) / acted=$acted / deferred=$deferred"
    echo
    echo "$stuck_line"
    echo
    echo "$floating_line"
    echo
    echo "$worker_line"
    echo
    echo "$pm_line"
    echo
    printf '%s' "$summary"
  } >> "$GITHUB_STEP_SUMMARY"
fi
