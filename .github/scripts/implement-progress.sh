#!/bin/bash
# implement-progress.sh — implement run (issue_comment / workflow_dispatch) の無音終了の検知と、job 内の 1 回だけの再試行 (#5727 受入 6)。
# fix モードの fix-progress.sh と同じ形: agent が何も残さずに終わったら、同じ job の中で 1 回だけ再試行する。
#
# サブコマンド:
#   mark          job の開始時刻を記録する (GITHUB_OUTPUT: start_epoch, start_iso)。checkout より前に置く (git を使わない)
#   sha           agent を起動する直前の HEAD を記録する (GITHUB_OUTPUT: start_sha)
#   check         run が副作用を残したか判定する (GITHUB_OUTPUT: result=done|none|unknown, retry=true|false, reason=...)
#                   done    : 実装 App が issue にコメントした / 対象ブランチ (<N>-...) に新しい commit がある / 対象 PR が作成・更新された
#                   none    : 上のどれも無い (無音終了)。再試行の候補
#                   unknown : 読めなかった・一覧が 100 件を超えた。安全側に倒し、再試行しない
#   retry-prompt  再試行用プロンプトを作る (GITHUB_OUTPUT: prompt_file)
#
# retry=true は result=none かつ次の全部を満たすときだけ: 作業ツリーが clean で HEAD が開始時のまま
# (前回の残骸を持ち越さない。このスクリプトは git reset / clean をしない) かつ job の残り時間が OC_RETRY_NEED_SEC 以上。
# 入力 (env): GH_TOKEN, OC_REPO, OC_ISSUE_NUMBER, OC_START_ISO, OC_START_SHA, OC_JOB_START_EPOCH, OC_PROMPT_SRC, GITHUB_OUTPUT
# 任意 (env): OC_IMPLEMENTER_LOGIN (既定 opencode-for-signature-studio[bot]), OC_JOB_LIMIT_SEC (既定 3600),
#             OC_RETRY_NEED_SEC (既定 1080 = 再試行 15 分 + 後段の判定の余裕 3 分), RUNNER_TEMP
set -Eeuo pipefail

OC_SUBCMD="${1:-}"
IMPLEMENTER_LOGIN="${OC_IMPLEMENTER_LOGIN:-opencode-for-signature-studio[bot]}"
LIMIT="${OC_JOB_LIMIT_SEC:-3600}"
NEED="${OC_RETRY_NEED_SEC:-1080}"
out_kv() { # out_kv <key> <value>: GITHUB_OUTPUT (無ければ標準出力) に 1 行足す
  if [ -n "${GITHUB_OUTPUT:-}" ]; then printf '%s=%s\n' "$1" "$2" >> "$GITHUB_OUTPUT"; else printf '%s=%s\n' "$1" "$2"; fi
}

case "$OC_SUBCMD" in
  mark)
    out_kv start_epoch "$(date +%s)"
    out_kv start_iso "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    ;;
  sha)
    out_kv start_sha "$(git rev-parse HEAD)"
    ;;
  check)
    : "${OC_REPO:?}" "${OC_ISSUE_NUMBER:?}" "${OC_START_ISO:?}" "${OC_START_SHA:?}" "${OC_JOB_START_EPOCH:?}"
    R="$OC_REPO" N="$OC_ISSUE_NUMBER" S="$OC_START_ISO"
    case "$N" in '' | *[!0-9]*)
      echo "::error::OC_ISSUE_NUMBER must be digits only" >&2
      exit 1
      ;;
    esac
    result=none reason=none
    # 1. 実装 App の issue コメント (run 開始以降)
    if cm="$(gh api --paginate "repos/$R/issues/$N/comments?per_page=100" \
      | jq -s -r --arg l "$IMPLEMENTER_LOGIN" --arg s "$S" '[.[][] | select(.user.login == $l and (.created_at // "") >= $s)] | length')"; then
      if [ "$cm" -gt 0 ]; then result=done reason=comment; fi
    else
      result=unknown reason=comments-unreadable
    fi
    # 2. 対象ブランチ (<N>-...) の commit (run 開始以降)
    if [ "$result" = none ]; then
      if refs="$(gh api "repos/$R/git/matching-refs/heads/$N-" 2> /dev/null)"; then
        while read -r sha; do
          [ -n "$sha" ] || continue
          d="$(gh api "repos/$R/commits/$sha" --jq .commit.committer.date 2> /dev/null)" || { result=unknown reason=commit-unreadable; break; }
          if [[ "$d" > "$S" || "$d" == "$S" ]]; then result=done reason=push; break; fi
        done < <(jq -r '.[]?.object.sha // empty' <<< "$refs")
      else
        result=unknown reason=refs-unreadable
      fi
    fi
    # 3. この issue を指す PR (作成・更新・merge) の一覧。1 ページを超えて更新されていたら判定しない
    if [ "$result" = none ]; then
      if prs="$(gh api "repos/$R/pulls?state=all&sort=updated&direction=desc&per_page=100")"; then
        hit="$(jq -r --argjson n "$N" --arg s "$S" '[.[] | select(((.head.ref // "") | test("^" + ($n | tostring) + "-")) or ((.body // "") | test("(Closes|Refs|Fixes|Resolves) #" + ($n | tostring) + "([^0-9]|$)"; "i"))) | select((.updated_at // "") >= $s)] | length' <<< "$prs")"
        overflow="$(jq -r --arg s "$S" 'if length == 100 then (((.[-1].updated_at // "") >= $s) | tostring) else "false" end' <<< "$prs")"
        if [ "$hit" -gt 0 ]; then
          result=done reason=pr
        elif [ "$overflow" = true ]; then
          result=unknown reason=pr-overflow
        fi
      else
        result=unknown reason=prs-unreadable
      fi
    fi
    # 再試行の可否: 残り時間と作業ツリーの状態
    remaining=$((LIMIT - ($(date +%s) - OC_JOB_START_EPOCH)))
    retry=false
    if [ "$result" = none ]; then
      if [ -n "$(git status --porcelain)" ] || [ "$(git rev-parse HEAD)" != "$OC_START_SHA" ]; then
        reason=dirty-worktree
      elif [ "$remaining" -lt "$NEED" ]; then
        reason=no-time-left
      else
        retry=true
      fi
    fi
    echo "implement-progress: result=$result reason=$reason retry=$retry remaining=${remaining}s" >&2
    out_kv result "$result"
    out_kv reason "$reason"
    out_kv retry "$retry"
    ;;
  retry-prompt)
    : "${OC_PROMPT_SRC:?}"
    out="${RUNNER_TEMP:-/tmp}/opencode-prompt-implement-retry.txt"
    {
      cat "$OC_PROMPT_SRC"
      printf '\n## 再試行 (前回は何も残さずに終了した)\n\n'
      printf '前回の試行は PR を作らず、commit を push せず、issue にもコメントせずに終了した。これは禁止されている。\n'
      printf '今回は必ず次のどちらかを行うこと。\n'
      printf '1. 実装して PR を出す (本文に Closes #%s)。\n' "$OC_ISSUE_NUMBER"
      printf '2. PR を出せない理由を issue へ `gh issue comment` で書く (判断待ち・素材不足・分割など)。\n'
    } > "$out"
    chmod 600 "$out"
    out_kv prompt_file "$out"
    ;;
  *)
    echo "usage: $0 mark|sha|check|retry-prompt" >&2
    exit 2
    ;;
esac
