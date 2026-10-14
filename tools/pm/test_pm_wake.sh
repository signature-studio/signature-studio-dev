#!/bin/bash
# test_pm_wake.sh — pm_wake.sh の送信判定テスト。fake curl・fake opencode を PATH 先頭に置く (ネットワーク不使用)。
# 時刻は PM_WAKE_NOW で固定する。ネガコン: (a)(c)(d)(e)(g)(g2)(j)。
set -u
here="$(cd "$(dirname "$0")" && pwd)"
wake="$here/pm_wake.sh"
work="$(mktemp -d "${TMPDIR:-/tmp}/pm_wake_test.XXXXXX")"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/bin"
cat > "$work/bin/curl" <<'EOF'
#!/bin/bash
case "${FAKE_CURL_MODE:-body}" in
  fail) exit 22 ;;
  body) printf '%s' "$FAKE_CURL_BODY" ;;
esac
EOF
cat > "$work/bin/opencode" <<'EOF'
#!/bin/bash
printf '%s\n' "$*" >> "$FAKE_OC_LOG"
if [ "${FAKE_OC_RC:-0}" -ne 0 ]; then echo "fake send error" >&2; fi
exit "${FAKE_OC_RC:-0}"
EOF
chmod +x "$work/bin/curl" "$work/bin/opencode"

T0=1800000000
MIN=60
H=3600
status() { printf '{"needs_pm":%s,"fresh":%s,"stuck_age_max_min":%s}' "$1" "$2" "$3"; }
sent_count() { if [ -f "$1/sent" ]; then wc -l < "$1/sent" | tr -d ' '; else echo 0; fi; }

# wake <dir> <now> <curl mode> <body> [KEY=VALUE ...] — 結果は RC に入る
wake() {
  local d="$1" now="$2" mode="$3" b="$4"
  shift 4
  env PATH="$work/bin:$PATH" PM_WAKE_NOW="$now" PM_WAKE_STATE="$d/state.json" PM_WAKE_LOG="$d/log" \
    PM_SESSION_ID=ses_test PM_WORKER_URL=http://fake.invalid OPENCODE_BIN="$work/bin/opencode" \
    FAKE_CURL_MODE="$mode" FAKE_CURL_BODY="$b" FAKE_OC_LOG="$d/sent" "$@" \
    bash "$wake" > "$d/out" 2>&1
  RC=$?
}

pass=0; fail=0
new_case() { D="$(mktemp -d "$work/case.XXXXXX")"; }
ok() { echo "PASS $1"; pass=$((pass+1)); }
ng() { echo "FAIL $1 (rc=$RC, sent=$(sent_count "$D"))"; cat "$D/out"; fail=$((fail+1)); }

new_case
wake "$D" "$T0" body "$(status 0 true null)"
if [ "$RC" -eq 0 ] && [ "$(sent_count "$D")" -eq 0 ] && grep -q 'result=none' "$D/log"; then ok "a: 条件なし -> 送らない (negative)"; else ng "a"; fi

new_case
wake "$D" "$T0" body "$(status 2 true null)"
if [ "$RC" -eq 0 ] && [ "$(sent_count "$D")" -eq 1 ] && grep -q '/api/session/ses_test/prompt' "$D/sent" && grep -q 'needs_pm' "$D/sent"; then ok "b: needs_pm=2 -> 送る"; else ng "b"; fi

wake "$D" "$((T0 + H))" body "$(status 2 true null)"
if [ "$RC" -eq 0 ] && [ "$(sent_count "$D")" -eq 1 ]; then ok "c1: 1 時間後の 2 回目 -> 送らない (negative)"; else ng "c1"; fi
wake "$D" "$((T0 + 3 * H))" body "$(status 2 true null)"
if [ "$RC" -eq 0 ] && [ "$(sent_count "$D")" -eq 2 ]; then ok "c2: 3 時間ちょうど -> 送る (boundary)"; else ng "c2"; fi

new_case
for k in 0 1 2 3 4 5; do wake "$D" "$((T0 + k * 3 * H))" body "$(status 2 true null)"; done
if [ "$(sent_count "$D")" -eq 6 ]; then ok "d1: 3 時間ごとに 6 回送る"; else ng "d1"; fi
wake "$D" "$((T0 + 18 * H))" body "$(status 2 true null)"
if [ "$RC" -eq 0 ] && [ "$(sent_count "$D")" -eq 6 ]; then ok "d2: 24 時間に 6 回の次 -> 送らない (negative)"; else ng "d2"; fi
wake "$D" "$((T0 + 25 * H))" body "$(status 2 true null)"
if [ "$RC" -eq 0 ] && [ "$(sent_count "$D")" -eq 7 ]; then ok "d3: 最初の送信が 24 時間を過ぎたら送る"; else ng "d3"; fi

new_case
wake "$D" "$T0" fail ""
if [ "$RC" -eq 2 ] && [ "$(sent_count "$D")" -eq 0 ] && grep -q 'result=status-failed curl_rc=22' "$D/log"; then ok "e1: /status 取得失敗 -> 送らず記録 (negative)"; else ng "e1"; fi
wake "$D" "$T0" body "{not json"
if [ "$RC" -eq 2 ] && [ "$(sent_count "$D")" -eq 0 ] && grep -q 'result=status-failed reason=parse' "$D/log"; then ok "e2: JSON 不正 -> 送らず記録 (negative)"; else ng "e2"; fi

new_case
wake "$D" "$T0" body "$(status 2 true null)" FAKE_OC_RC=1
if [ "$RC" -eq 3 ] && grep -q 'result=send-failed kind=needs_pm rc=1' "$D/log" \
  && [ "$(jq -r '.attempts | length' "$D/state.json")" -eq 1 ] && [ "$(jq -r '.last.rc' "$D/state.json")" -eq 1 ]; then
  ok "f1: 送信失敗 -> 終了 3・記録・状態に試行と rc を残す"
else ng "f1"; fi
wake "$D" "$((T0 + 5 * MIN))" body "$(status 2 true null)"
if [ "$RC" -eq 0 ] && [ "$(sent_count "$D")" -eq 1 ]; then ok "f2: 失敗した試行も 3 時間の間隔に数える (negative)"; else ng "f2"; fi

new_case
wake "$D" "$T0" body "$(status 0 false null)"
wake "$D" "$((T0 + 29 * MIN))" body "$(status 0 false null)"
if [ "$(sent_count "$D")" -eq 0 ]; then ok "g1: fresh=false が 29 分 -> 送らない (negative)"; else ng "g1"; fi
wake "$D" "$((T0 + 31 * MIN))" body "$(status 0 false null)"
if [ "$RC" -eq 0 ] && [ "$(sent_count "$D")" -eq 1 ] && grep -q 'worker_stale' "$D/sent"; then ok "g2: fresh=false が 31 分 -> 送る"; else ng "g2"; fi

new_case
wake "$D" "$T0" body "$(status 0 false null)"
wake "$D" "$((T0 + 20 * MIN))" body "$(status 0 true null)"
wake "$D" "$((T0 + 25 * MIN))" body "$(status 0 false null)"
wake "$D" "$((T0 + 31 * MIN))" body "$(status 0 false null)"
if [ "$RC" -eq 0 ] && [ "$(sent_count "$D")" -eq 0 ]; then ok "g3: fresh=true で経過がリセットされる (negative)"; else ng "g3"; fi

new_case
wake "$D" "$T0" body '{"needs_pm":2,"fresh":true,"stuck_age_max_min":null,"dummy_title":"STATUS_MARK_XYZ"}'
if [ "$(sent_count "$D")" -eq 1 ] && ! grep -q 'STATUS_MARK_XYZ' "$D/sent"; then ok "h: 文面に /status 由来の文字列を入れない"; else ng "h"; fi

new_case
wake "$D" "$T0" body "$(status 0 true 360)"
if [ "$(sent_count "$D")" -eq 0 ]; then ok "k1: stuck_age_max_min=360 -> 送らない (boundary, negative)"; else ng "k1"; fi
wake "$D" "$T0" body "$(status 0 true 361)"
if [ "$(sent_count "$D")" -eq 1 ] && grep -q 'stuck_old' "$D/sent"; then ok "k2: stuck_age_max_min=361 -> 送る (boundary)"; else ng "k2"; fi

new_case
wake "$D" "$T0" body "$(status 2 true null)" PM_SESSION_ID= PM_SESSION_ID_FILE=
if [ "$RC" -eq 1 ] && [ "$(sent_count "$D")" -eq 0 ] && grep -q 'result=no-session' "$D/log"; then ok "j1: セッション ID が無い -> 終了 1 (negative)"; else ng "j1"; fi
printf 'ses_file\n' > "$D/sid"
wake "$D" "$T0" body "$(status 2 true null)" PM_SESSION_ID= PM_SESSION_ID_FILE="$D/sid"
if [ "$RC" -eq 0 ] && grep -q '/api/session/ses_file/prompt' "$D/sent"; then ok "j2: PM_SESSION_ID_FILE から読む"; else ng "j2"; fi

new_case
printf 'not json' > "$D/state.json"
wake "$D" "$T0" body "$(status 2 true null)"
if [ "$RC" -eq 0 ] && [ "$(sent_count "$D")" -eq 1 ]; then ok "l: 壊れた状態ファイルは初期値として扱う"; else ng "l"; fi

echo "test_pm_wake: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
