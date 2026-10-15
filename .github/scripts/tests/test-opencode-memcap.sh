#!/bin/bash
# test-opencode-memcap.sh — opencode action の "Run OpenCode" step の memory cap (CI-177) を検証する。
# 偽の opencode が上限 (OC_MEM_CAP_MB) を超えて確保する子プロセスを起動すると、その子だけが kill され、
# opencode 本体は続行して rc=0 で終わり、step の後続 (= always() の step) が走ることを確かめる。
# cgroup scope が作れない環境 (sudo 不可) ではこのテストは SKIP (exit 0) する。
# 実行: bash .github/scripts/tests/test-opencode-memcap.sh
# CI: .github/workflows/scripts-test.yaml が .github/actions/** の変更ごとに実行する。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ACTION="$HERE/../../actions/opencode/action.yml"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0

if ! sudo -n systemd-run --scope --quiet -- true >/dev/null 2>&1; then
  echo "SKIP: sudo -n systemd-run --scope が使えない (cgroup 上限のテストは実行できない)"
  exit 0
fi

start="$(grep -n '^    - name: Run OpenCode' "$ACTION" | cut -d: -f1)"
runl="$(awk -v s="$start" 'NR>s && /^      run: \|/{print NR; exit}' "$ACTION")"
endl="$(awk -v s="$start" 'NR>s && /^    # 作業の記録/{print NR; exit}' "$ACTION")"
if [ -z "$start" ] || [ -z "$runl" ] || [ -z "$endl" ]; then
  echo "FAIL: Run OpenCode step を action.yml から抽出できない"
  exit 1
fi
sed -n "$((runl+1)),$((endl-1))p" "$ACTION" | sed 's/^        //' > "$TMP/step.sh"
sed -i 's/wait_s=15/wait_s=0/' "$TMP/step.sh"

dir="$TMP/case"
mkdir -p "$dir/bin" "$dir/runner"
# 偽の opencode: 上限を超えて確保する子 (python) を起動し、その終了コードを記録してから正常終了する。
cat > "$dir/bin/opencode" <<'SH'
#!/bin/bash
cat > /dev/null
python3 -c "
x=[]
while True: x.append(b'a'*(10*1024*1024))
" &
child=$!
wait "$child"
echo "child_rc=$?" > "$FAKE_OC_OUT"
printf '%s\n' '{"sessionID":"ses_cap","type":"text","part":{"text":"ok"}}'
SH
chmod +x "$dir/bin/opencode"

# 上限は 400MB (テスト用)。子は 400MB を大きく超えて確保しようとする。
(
  export PATH="$dir/bin:$PATH" RUNNER_TEMP="$dir/runner" GITHUB_OUTPUT="$dir/out" \
    OC_PROMPT_FILE="$TMP/prompt.txt" OC_MODEL=test/model OC_AGENT=build OC_SAMPLE_SECS=1 \
    OC_MEM_CAP_MB=400 FAKE_OC_OUT="$dir/child"
  echo "prompt" > "$TMP/prompt.txt"
  timeout 300 bash --noprofile --norc "$TMP/step.sh" > "$dir/log" 2>&1
  echo "step_rc=$?" > "$dir/step_rc"
)

rc="$(sed -n 's/^rc=//p' "$dir/out" 2>/dev/null)"
sid="$(sed -n 's/^sid=//p' "$dir/out" 2>/dev/null)"
child_rc="$(sed -n 's/^child_rc=//p' "$dir/child" 2>/dev/null)"

if grep -q 'memory cap: 400MB (cgroup scope)' "$dir/log"; then
  echo "PASS: cgroup scope で上限 400MB を付けて起動"
else
  echo "FAIL: cgroup scope で起動していない"; tail -5 "$dir/log"; fail=1
fi
if [ "$rc" = 0 ] && [ "$sid" = ses_cap ]; then
  echo "PASS: 上限超過の子がいても opencode は rc=0 で続行し、sid を出した"
else
  echo "FAIL: rc=$rc sid=$sid (期待 0 / ses_cap)"; tail -5 "$dir/log"; fail=1
fi
if [ -n "$child_rc" ] && [ "$child_rc" != 0 ]; then
  echo "PASS: 上限超過の子は kill された (child_rc=$child_rc)"
else
  echo "FAIL: 子が kill されていない (child_rc=${child_rc:-none})"; fail=1
fi

exit "$fail"
