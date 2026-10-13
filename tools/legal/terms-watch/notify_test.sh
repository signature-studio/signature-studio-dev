#!/usr/bin/env bash
# notify.sh の単体検証 (偽 gh。実 issue は作らない): 既存 issue 無し → create / 同題の open issue 有り → comment / gh 失敗 → 非 0。
#   bash tools/legal/terms-watch/notify_test.sh
set -uo pipefail
ROOT="$(git rev-parse --show-toplevel)"
T="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/tw-notify.XXXXXX")"
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/out"
echo 3 > "$T/out/exit_code"; echo "ERROR ni-eula — HTTP 403" > "$T/out/log.txt"
cat > "$T/bin/gh" <<'EOF'
#!/usr/bin/env bash
echo "$*" >> "$FAKE_GH_LOG"
case "$1 $2" in
  "issue list") [ "${FAKE_GH_FAIL:-}" = list ] && exit 1; echo "$FAKE_GH_LIST" ;;
  "issue create") [ "${FAKE_GH_FAIL:-}" = create ] && exit 1; echo "https://example.invalid/issues/1" ;;
  "issue comment") [ "${FAKE_GH_FAIL:-}" = comment ] && exit 1 ;;
esac
exit 0
EOF
chmod +x "$T/bin/gh"
TITLE='[LGL-5] terms-watch: 規約の差分検出/取得失敗 (週次監視の自動起票)'
fail=0
run() { # run <name> <want-exit> <want-verb> <list-json> <fail-mode>
  : > "$T/gh.log"
  PATH="$T/bin:$PATH" FAKE_GH_LOG="$T/gh.log" FAKE_GH_LIST="$4" FAKE_GH_FAIL="$5" TW_OUT="$T/out" GITHUB_REPOSITORY=o/r \
    bash "$ROOT/tools/legal/terms-watch/notify.sh" >/dev/null 2>&1; got=$?
  verb="$(grep -oE '^issue (create|comment)' "$T/gh.log" | head -1 | cut -d' ' -f2)"
  printf '%-36s exit want=%s got=%s / verb want=%s got=%s\n' "$1" "$2" "$got" "${3:-なし}" "${verb:-なし}"
  [ "$got" = "$2" ] && [ "${verb:-}" = "${3:-}" ] || fail=1
}
run "既存 issue 無し → 起票" 0 create '[]' ""
run "同題 open issue 有り → コメント" 0 comment "[{\"number\":42,\"title\":\"$TITLE\"}]" ""
run "別題の issue のみ → 起票" 0 create '[{"number":7,"title":"other"}]' ""
run "gh issue list 失敗 → 非 0" 1 "" '[]' list
run "gh issue create 失敗 → 非 0" 1 create '[]' create
run "gh issue comment 失敗 → 非 0" 1 comment "[{\"number\":42,\"title\":\"$TITLE\"}]" comment
exit $fail
