#!/bin/bash
# run-outcome-reason.sh — implement run の終了理由 (run-outcome の reason) を agent の最終回答から決める (#3184)。
# 分類規則の正本はこの 1 箇所。record-run-outcome.sh が source し、test-run-outcome.sh もこれを使う。
#   reason   : artifact | blocked | split | stop | unknown
#   優先順    : artifact > blocked > split > stop > unknown (先に当たったものを採る)
#   artifact : allowlist の素材名 (watchdog.sh の ARTIFACT_RE と同じ集合) が、句 (。 、 ； などで区切った節) の中で
#              『無い・足りない・不足・必要・未配置・未展開』と肯定の文脈で挙がるときだけ。否定を含む語
#              (『不足は無い』『不足なし』『必要ではない』『影響は無い』) は不足の語として数えない。
#              『必要な oc_artifacts: <名前>』は次の run への指定であり、不足の報告ではない。
#              『素材』『oc_artifacts』の語だけでは判定しない。素材名の無い『素材不足』も artifact にしない
#              (PM Worker は素材名で再着手を決めるため。判定できない停止は unknown)。
#   blocked  : 依存 issue・前提 PR 未 merge・ブロック
#   split    : 1 run に収まらない・分割・子 issue
#   stop     : 判断待ち・停止報告・着手不可
#   unknown  : 上のどれでもない (判定できない停止・着手報告のみ・run の失敗を含む)
# artifact を先頭に置くのは、素材名が具体的で、PM Worker が新しい素材が増えたときだけ自動で再着手するため。
# 使い方: source して run_outcome_reason <text> を呼ぶ。または bash run-outcome-reason.sh [file] (省略時は stdin) で reason を 1 行出す。
export LC_ALL=C.UTF-8

ARTIFACT_NAME='(fl-win64|plugins-(ott|freshair|serum2|massivex|kilohearts)|toolchain-(retdec|emsdk)|work-(m11|liftdiff|m6-ott|liftlib-targets|liftlib|icall|fw-stage1)|analysis-(ott-binaries|mac-shared)|apt-mingw)'
MISS_RE='無い|無く|無かっ|足りな|不足|未配置|未展開|未取得|欠け|欠落|見つから|取得でき(な|ませ|ず)|必要|(実在|存在)(し|して)?(い)?ませ?ん|(実在|存在)しな'
# 次の run への指定 (必要な oc_artifacts: ...) を節ごと消し、節を区切る
CLAUSE_SED='s/必要な? ?`?oc_artifacts`?[^。、；;，,]*//g; s/[。、；;，,]/\n/g'
# 否定を含む語を ◯ に置き換える (『不足は無い』の『無い』を不足と見ないため)。
# oc_artifacts を含む節の『必要』は次の run への指定 (『再起動時に必要な素材: oc_artifacts: …』) なので不足と見ない。『無い』『足りない』は数える
NEG_SED='s/(不足|問題|欠落|欠け|必要|影響|差異|差分|懸念|リスク|未配置|未展開|未取得)(では|は|が)?(無い|無く|ない|なし|無し|ありません|ゼロ)/◯/g; s/不足(して)?(い)?ません/◯/g; s/(足り|揃っ)(て|てい|ており|ます)/◯/g; /oc_artifacts/ s/必要/◯/g'

artifact_hit() { # 節ごとに、allowlist の素材名と肯定の不足語が同じ節にあるかを見る
  local c
  while IFS= read -r c; do
    grep -qE "(^|[^a-z0-9-])${ARTIFACT_NAME}([^a-z0-9-]|\$)" <<< "$c" || continue
    sed -E "$NEG_SED" <<< "$c" | grep -qE "$MISS_RE" && return 0
  done < <(sed -E "$CLAUSE_SED" <<< "$1")
  return 1
}

run_outcome_reason() { # run_outcome_reason <text> -> artifact|blocked|split|stop|unknown
  local t="$1"
  if artifact_hit "$t"; then
    echo artifact
  elif grep -qE '依存 ?issue|依存.{0,8}#[0-9]+|前提.{0,20}(未 ?merge|未マージ|未完)|blockedBy|ブロッカー|ブロック|先行 PR|先行.{0,6}#[0-9]+' <<< "$t"; then
    echo blocked
  elif grep -qE '1 ?run に収まらない|収まらない|上限に(達|収)|分割|子 issue' <<< "$t"; then
    echo split
  elif grep -qE '着手不可|着手できません|着手に必要|停止します|停止報告|PM に.*依頼|判断を|判断待ち' <<< "$t"; then
    echo stop
  else
    echo unknown
  fi
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  run_outcome_reason "$(cat "${1:--}")"
fi
