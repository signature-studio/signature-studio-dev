#!/bin/bash
# heartbeat.sh — PM_HEARTBEAT_SECONDS ごと (既定 1800 秒 = 30 分) に PM セッションへプロンプトを送り、応答の停止で作業が止まらないようにする (指示 102・116・120)。
# 起動: systemctl --user enable --now pm-heartbeat.service (再起動後も自動復帰)。
# 送るのは固定文だけ。セッション ID が無効になった場合は送信に失敗するだけで、ループは続く。
# 指示 145: 運用は PM_HEARTBEAT_SECONDS=7200・PM_HEARTBEAT_MSG_FILE=heartbeat_msg_audit.txt (監査専用)。env 無しの既定は下の 30 分版。
# PM_HEARTBEAT_MSG_FILE を指定して読めない・空のときは、送らずに終了する (既定の 30 分版には戻さない)。
SID="${PM_SESSION_ID:-}"
if [ -z "$SID" ]; then
  echo "heartbeat.sh: PM_SESSION_ID is required" >&2
  exit 1
fi
INTERVAL="${PM_HEARTBEAT_SECONDS:-1800}"
MSG='[heartbeat 30分ごと / 自動送信] 作業を止めずに続行してください。
1. watch_runs.sh が動いていなければ background で再起動する (bash __PM_DIR__/watch_runs.sh)。
2. 全ての open PR が「レビュー中」か「レビューを受けて修正中」のどちらかであること (担当なし 0) を、watchdog の DRY で実測して維持する。足りなければ rest_heal.py で補う。
3. approve 済みで未 merge の PR、oc:stuck の PR、失敗した run の原因 (ログで確認) を処理する。
4. 新規着手は指示 130〜132 に従う: Opened PR が 10 件を下回れば Review-Only を解除して着手 (python3 __PM_DIR__/launch_issues.py launch)、80 件を超えれば Review-Only。blocked_by の無い未着手タスクは即座に issue コメントで着手し、同時着手は 30 以上を維持 (指示 131)。プロダクト完成まで自走 (指示 133)。モデル変数の変更は、率制限の失敗をログで確認した場合に、許可された 2 コマンドのみ (指示 126)。'
MSG_FILE="${PM_HEARTBEAT_MSG_FILE:-}"
if [ -n "$MSG_FILE" ]; then
  MSG="$(cat "$MSG_FILE" 2>/dev/null)"
  [ -n "${MSG//[[:space:]]/}" ] || { echo "heartbeat.sh: PM_HEARTBEAT_MSG_FILE is missing or empty: $MSG_FILE" >&2; exit 1; }
fi
PM_DIR="${PM_DIR:-$(cd "$(dirname "$0")" && pwd)}"
MSG="${MSG//__PM_DIR__/$PM_DIR}"
while true; do
  timeout "$INTERVAL" tail -f /dev/null
  timeout 60 "${OPENCODE_BIN:-opencode}" api post "/api/session/$SID/prompt" -d "$(jq -cn --arg t "$MSG" '{text:$t}')" > /dev/null 2>&1 || true
done
