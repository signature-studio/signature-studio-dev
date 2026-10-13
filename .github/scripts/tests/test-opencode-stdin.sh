#!/bin/bash
# test-opencode-stdin.sh — opencode action の "Run OpenCode" step を実スクリプトのまま実行し、
# 128KB (131072 バイト) を超えるプロンプトが標準入力で渡って成功することを検証する (#725)。
# ネガコン: 同じ step の `< "$OC_PROMPT_FILE"` を引数渡し (修正前の形) に置き換えると、同じ入力で失敗する。
# 実行: bash .github/scripts/tests/test-opencode-stdin.sh   (全て通れば exit 0、1 件でも落ちれば exit 1)
# CI: .github/workflows/scripts-test.yaml が .github/actions/** の変更ごとに実行する。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ACTION="$HERE/../../actions/opencode/action.yml"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0

# step 本体の抽出: "Run OpenCode" step の run: ブロック (8 桁インデント) を取り出し、インデントを外す。
start="$(grep -n '^    - name: Run OpenCode' "$ACTION" | cut -d: -f1)"
runl="$(awk -v s="$start" 'NR>s && /^      run: \|/{print NR; exit}' "$ACTION")"
endl="$(awk -v s="$start" 'NR>s && /^    # 作業の記録/{print NR; exit}' "$ACTION")"
if [ -z "$start" ] || [ -z "$runl" ] || [ -z "$endl" ]; then
  echo "FAIL: Run OpenCode step を action.yml から抽出できない"
  exit 1
fi
sed -n "$((runl+1)),$((endl-1))p" "$ACTION" | sed 's/^        //' > "$TMP/step-stdin.sh"
# 再試行の待機 (15 秒) はテストでは 0 にする。それ以外は実 step と同一。
sed -i 's/wait_s=15/wait_s=0/' "$TMP/step-stdin.sh"

if ! grep -qF '< "$OC_PROMPT_FILE"' "$TMP/step-stdin.sh"; then
  echo "FAIL: 抽出した step に標準入力渡し (< \"\$OC_PROMPT_FILE\") が無い"
  exit 1
fi

# ネガコン: 標準入力渡しを引数渡しに置き換える (修正前の形)。置換は 1 箇所のみ、を確認する。
cat > "$TMP/mkneg.py" <<'PY'
import sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()
old = '< "$OC_PROMPT_FILE" \\\n'
new = '"$(cat "$OC_PROMPT_FILE")" \\\n'
if s.count(old) != 1:
    sys.exit("stdin redirect not found exactly once")
open(dst, "w", encoding="utf-8").write(s.replace(old, new))
PY
python3 "$TMP/mkneg.py" "$TMP/step-stdin.sh" "$TMP/step-argv.sh" || { echo "FAIL: ネガコンを作れない"; exit 1; }

# 入力: 日本語 100000 文字 = 300000 バイト (128KB 超)。
PROMPT="$TMP/prompt.txt"
python3 -c 'import sys; sys.stdout.write("\u3042" * 100000)' > "$PROMPT"
size="$(wc -c < "$PROMPT")"
if [ "$size" -le 131072 ]; then
  echo "FAIL: テスト入力が 128KB 以下 ($size bytes)"
  exit 1
fi
echo "prompt: $size bytes"

# step を実行する。偽の opencode は標準入力を $dir/in に保存し、sessionID を含む JSONL を返す。
run_case() {  # $1=step スクリプト $2=ケース名
  local dir="$TMP/$2"
  mkdir -p "$dir/bin" "$dir/runner"
  cat > "$dir/bin/opencode" <<'SH'
#!/bin/bash
cat > "$FAKE_OC_IN"
printf '%s\n' '{"sessionID":"ses_test","type":"text","part":{"text":"ok"}}'
SH
  chmod +x "$dir/bin/opencode"
  (
    export PATH="$dir/bin:$PATH" RUNNER_TEMP="$dir/runner" GITHUB_OUTPUT="$dir/out" \
      OC_PROMPT_FILE="$PROMPT" OC_MODEL=test/model OC_AGENT=build OC_SAMPLE_SECS=1 \
      FAKE_OC_IN="$dir/in"
    bash --noprofile --norc "$1" > "$dir/log" 2>&1
  )
  local rc
  rc="$(sed -n 's/^rc=//p' "$dir/out" 2>/dev/null)"
  echo "${rc:-none}"
}

# 正: 標準入力渡しの step は 300KB のプロンプトを最後まで渡して成功する。
rc="$(run_case "$TMP/step-stdin.sh" stdin)"
if [ "$rc" = 0 ] && [ -f "$TMP/stdin/in" ] && cmp -s "$PROMPT" "$TMP/stdin/in"; then
  echo "PASS: stdin 渡し: rc=0、受け取ったプロンプトが入力と一致 ($size bytes)"
else
  echo "FAIL: stdin 渡し: rc=$rc (期待 0)、プロンプト一致=$( [ -f "$TMP/stdin/in" ] && cmp -s "$PROMPT" "$TMP/stdin/in" && echo yes || echo no)"
  tail -5 "$TMP/stdin/log" 2>/dev/null
  fail=1
fi
if grep -q '^sid=ses_test$' "$TMP/stdin/out" 2>/dev/null; then
  echo "PASS: sid 抽出 = ses_test"
else
  echo "FAIL: sid が抽出されていない"
  fail=1
fi

# ネガ: 引数渡しの step は同じ入力で失敗する (opencode まで届かない)。
rc="$(run_case "$TMP/step-argv.sh" argv)"
if [ "$rc" != 0 ] && [ ! -f "$TMP/argv/in" ]; then
  echo "PASS: ネガコン (引数渡し): rc=$rc で失敗、opencode は起動しない"
else
  echo "FAIL: ネガコン (引数渡し) が失敗しない: rc=$rc"
  fail=1
fi

exit "$fail"
