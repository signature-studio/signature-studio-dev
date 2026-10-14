#!/bin/bash
# test_pm_gate.sh — pm_gate.sh の判定テスト。fake curl を PATH 先頭に置く (ネットワーク不使用)。
# (a) live+fresh+直近 → 実行しない / (b)(c)(d)(e) ネガコン → 実行する / (f) 16 分前 → 実行する (境界)。
set -u
here="$(cd "$(dirname "$0")" && pwd)"
gate="$here/pm_gate.sh"
work="$(mktemp -d "${TMPDIR:-/tmp}/pm_gate_test.XXXXXX")"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/bin"
cat > "$work/bin/curl" <<'EOF'
#!/bin/bash
case "${FAKE_CURL_MODE:-body}" in
  fail) exit 22 ;;
  body) printf '%s' "$FAKE_CURL_BODY" ;;
esac
EOF
chmod +x "$work/bin/curl"

ts_ago() { python3 -c 'import datetime,sys; print((datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=int(sys.argv[1]))).strftime("%Y-%m-%dT%H:%M:%SZ"))' "$1"; }
body() { printf '{"mode":"%s","fresh":%s,"last_tick":"%s"}' "$1" "$2" "$3"; }

pass=0; fail=0
# run_case <name> <expect: skip|run> <FAKE_CURL_MODE> <FAKE_CURL_BODY>
run_case() {
  local name="$1" expect="$2" mode="$3" b="$4" marker="$work/ran.$RANDOM"
  rm -f "$work"/ran.*
  PATH="$work/bin:$PATH" FAKE_CURL_MODE="$mode" FAKE_CURL_BODY="$b" PM_WORKER_URL="http://fake.invalid" \
    "$gate" touch "$marker" > "$work/out" 2>&1
  local rc=$? got=run
  [ -e "$marker" ] || got=skip
  if [ "$rc" -eq 0 ] && [ "$got" = "$expect" ]; then
    echo "PASS $name (rc=$rc, $got)"; pass=$((pass+1))
  else
    echo "FAIL $name (rc=$rc, got=$got, expected=$expect)"; cat "$work/out"; fail=$((fail+1))
  fi
}

run_case "a: live+fresh+recent -> skip" skip body "$(body live true "$(ts_ago 1)")"
run_case "b: dry-run -> run (negative)" run body "$(body dry-run true "$(ts_ago 1)")"
run_case "c: curl failure -> run (negative)" run fail ""
run_case "d: fresh=false -> run (negative)" run body "$(body live false "$(ts_ago 1)")"
run_case "e: broken JSON -> run (negative)" run body "{not json"
run_case "f: last_tick 16 min ago -> run (boundary)" run body "$(body live true "$(ts_ago 16)")"

# URL 未設定は fail-open (実行する)。
rm -f "$work"/ran.*
PATH="$work/bin:$PATH" PM_WORKER_URL="" "$gate" touch "$work/ran.nourl" > "$work/out" 2>&1
if [ -e "$work/ran.nourl" ]; then echo "PASS g: no URL -> run (negative)"; pass=$((pass+1))
else echo "FAIL g: no URL -> run (negative)"; fail=$((fail+1)); fi

echo "pm_gate: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
