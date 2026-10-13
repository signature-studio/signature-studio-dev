#!/bin/bash
# restart_failed.sh — レート制限等で落ちた run を再投入する。
#   実装 run : 直近の issue_comment run のうち failure/cancelled で、その issue にまだ
#              open な実装 PR が無く、より新しい成功 run も無いものに /oc を再コメントする。
#   review   : find_unreviewed.sh の出力のうち、head の review run が終了済みのものに
#              rerun_review.sh を実行する。
# 使い方: restart_failed.sh impl | review | both   (既定 both)
# 再投入する /oc 本文は、元の /oc コメントから oc_artifacts 行を引き継ぐ。
set -uo pipefail
R="${REPO:-signature-studio/signature-studio-dev}"
mode="${1:-both}"
since="${SINCE:-$(date -u -d '-12 hours' +%FT%TZ)}"
PM_TMP="${PM_TMP:-${TMPDIR:-/tmp}/pm}"
mkdir -p "$PM_TMP"
C="1 issue = 1 run。AGENTS.md と docs/WORKFLOW.md に従い、N-<slug> ブランチ → PR (--base main、Closes #N は受入条件を全て満たした時だけ、未達は Refs と未解決の列挙) で進めてください。PR 本文にも同じ oc_artifacts: 行を書いてください (review が素材を取得するため)。着手から 10 分以内と、完了・停止時に必ず gh issue comment で結果を投稿してください。60 分で終わらない場合は中間 commit + draft PR にしてください。既存のブランチ・draft PR があれば、その続きから進めてください (作り直さない)。repo 外の固定パスは書かず、tools/shared/env.sh の変数を使ってください。素材が足りなければ、必要な oc_artifacts 名 (許可名は docs/WORKFLOW.md §11) を報告して停止してください。"

if [ "$mode" = impl ] || [ "$mode" = both ]; then
  # run の head の issue 番号は、実行時の event payload にしか無いので、タイトルの [..] ではなく
  # run の jobs ではなく issue_comment の comment URL から引けない。代わりに GraphQL の
  # コメント一覧 (bot 以外の /oc コメント) を起点にし、run の成否と突き合わせる。
  gh api "repos/$R/actions/runs?event=issue_comment&per_page=100" --jq \
    '.workflow_runs[]|select(.created_at>"'"$since"'" and (.conclusion=="failure" or .conclusion=="cancelled"))|"\(.id)|\(.created_at)|\(.display_title)"' \
    | sort -t'|' -k2,2 > $PM_TMP/failed_impl.txt
  while IFS='|' read id created title; do
    # run のログから issue 番号を取る (OC_ISSUE_NUMBER)。
    num="$(gh run view "$id" --repo "$R" --log 2>/dev/null | grep -m1 -oE 'OC_ISSUE_NUMBER: [0-9]+' | grep -oE '[0-9]+$')"
    [ -n "$num" ] || { echo "skip run $id: no issue number ($title)"; continue; }
    echo "$num|$id|$created|$title"
  done < $PM_TMP/failed_impl.txt | sort -t'|' -k1,1n -k3,3 | awk -F'|' '!seen[$1]++ {print}' > $PM_TMP/restart_impl.txt
  while IFS='|' read num id created title; do
    state="$(gh issue view "$num" --repo "$R" --json state --jq .state)"
    [ "$state" = OPEN ] || { echo "skip #$num: $state"; continue; }
    # bot の完了報告が失敗 run より後にあれば、成功扱い
    done_after="$(gh issue view "$num" --repo "$R" --json comments --jq '[.comments[]|select((.author.login|startswith("opencode")) and .createdAt>"'"$created"'")]|length')"
    [ "$done_after" = 0 ] || { echo "skip #$num: bot comment after failure"; continue; }
    arts="$(gh issue view "$num" --repo "$R" --json comments --jq '[.comments[]|select(.body|startswith("/oc"))|.body|split("\n")|map(select(startswith("oc_artifacts:")))|first]|map(select(.!=null))|last // ""')"
    echo "restart #$num ($title) $arts"
    gh issue comment "$num" --repo "$R" --body "/oc oc_actions_allow_write
${arts}
前回 run ($id) は GitHub Actions 側の共通サブスクリプションのレート制限 (rate_limit_error) で中断されました。作業ブランチ・draft PR・中間 commit があればそこから再開してください。
$C" >/dev/null
  done < $PM_TMP/restart_impl.txt
fi

if [ "$mode" = review ] || [ "$mode" = both ]; then
  bash "$(dirname "$0")/find_unreviewed.sh" | while IFS='|' read pr sha arts; do
    running="$(gh api "repos/$R/actions/runs?event=pull_request&per_page=100" --jq '[.workflow_runs[]|select(.head_sha[0:7]=="'"$sha"'" and (.status=="in_progress" or .status=="queued"))]|length')"
    [ "$running" = 0 ] || { echo "skip review #$pr: run in progress"; continue; }
    a="${arts#oc_artifacts: }"; [ "$arts" = NONE ] && a="fl-win64"
    echo "rerun review #$pr with: $a"
    bash "$(dirname "$0")/rerun_review.sh" "$pr" $a | tail -1
  done
fi
