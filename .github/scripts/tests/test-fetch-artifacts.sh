#!/bin/bash
# test-fetch-artifacts.sh — fetch-artifacts.sh の再試行・部分取得の検出・404 判定を、偽の aws で検証する (#3976)。
# ケース: (a) 1 回目が IncompleteRead 相当で失敗・2 回目成功 → 成功 / (b) 3 回とも失敗 → 失敗
#         (c) 終了コード 0 だがサイズ不一致 → 再試行 / (d) head-object が 404 → 再試行せず missing で失敗
#         (e) 1 回目で成功 → 通知なし
# ネガコン: 再試行の無い旧ロジック (fixtures/fetch-artifacts-noretry.sh) に (a) と (c) を当てると、
#           期待を満たさず落ちることを確かめる。
# 実行: bash .github/scripts/tests/test-fetch-artifacts.sh   (全て通れば exit 0、1 件でも落ちれば exit 1)
# CI: .github/workflows/scripts-test.yaml が .github/scripts/** の変更ごとに実行する。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${FETCH_SCRIPT:-$HERE/../fetch-artifacts.sh}"
OLD="$HERE/fixtures/fetch-artifacts-noretry.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
SIZE=1000

mkdir -p "$TMP/bin"
# 偽の aws。head-object は FAKE_HEAD (ok / 404) に従い、cp は FAKE_CP_PLAN の試行ごとの結果を返す
# (fail = 部分ファイルを書いて終了 1 / short = 半分だけ書いて終了 0 / ok = 全部書いて終了 0)。
# 呼び出しは $FAKE_LOG に 1 行ずつ残す。
cat > "$TMP/bin/aws" <<'SH'
#!/bin/bash
echo "$1 $2" >> "$FAKE_LOG"
if [ "$1" = s3api ] && [ "$2" = head-object ]; then
  if [ "${FAKE_HEAD:-ok}" = 404 ]; then
    echo "An error occurred (404) when calling the HeadObject operation: Not Found" >&2
    exit 254
  fi
  echo "$SIZE_FOR_FAKE"
  exit 0
fi
if [ "$1" = s3 ] && [ "$2" = cp ]; then
  n=$(( $(cat "$FAKE_COUNT" 2>/dev/null || echo 0) + 1 ))
  echo "$n" > "$FAKE_COUNT"
  read -ra plan <<< "$FAKE_CP_PLAN"
  idx=$(( n - 1 ))
  [ "$idx" -ge "${#plan[@]}" ] && idx=$(( ${#plan[@]} - 1 ))
  dst="$4"
  [ -d "$dst" ] && dst="$dst/$(basename "$3")"
  case "${plan[$idx]}" in
    fail)
      head -c $((SIZE_FOR_FAKE / 2)) /dev/zero > "$dst"
      echo "download failed: $3 to $dst ('Connection broken: IncompleteRead(500 bytes read, 500 more expected)')" >&2
      exit 1 ;;
    short)
      head -c $((SIZE_FOR_FAKE / 2)) /dev/zero > "$dst"
      exit 0 ;;
    ok)
      head -c "$SIZE_FOR_FAKE" /dev/zero > "$dst"
      exit 0 ;;
  esac
fi
if [ "$1" = s3 ] && [ "$2" = ls ]; then
  echo "2026-10-12 18:19:38 $SIZE_FOR_FAKE fl-win64.tar.zst"
  exit 0
fi
exit 2
SH
chmod +x "$TMP/bin/aws"

# run_fetch <case> <script> <cp-plan> <head-mode>: 結果を RC / OUT / CP_CALLS / HEAD_CALLS / FILE_SIZE に入れる。
run_fetch() {
  local dir="$TMP/$1"
  mkdir -p "$dir/art"
  : > "$dir/log"
  OUT="$(env PATH="$TMP/bin:$PATH" SIZE_FOR_FAKE="$SIZE" FAKE_LOG="$dir/log" FAKE_COUNT="$dir/count" \
    FAKE_CP_PLAN="$3" FAKE_HEAD="$4" \
    R2_BUCKET=test-bucket CF_ACCOUNT_ID=test-account R2_ARTIFACTS=fl-win64 FETCH_RETRY_BASE_SEC=0 \
    bash "$2" "$dir/art" 2>&1)"
  RC=$?
  CP_CALLS="$(grep -c '^s3 cp' "$dir/log")"
  HEAD_CALLS="$(grep -c '^s3api head-object' "$dir/log")"
  FILE_SIZE="$(stat -c %s "$dir/art/fl-win64.tar.zst" 2>/dev/null || echo none)"
}

# 期待の判定。それぞれ 0 = 満たす / 1 = 満たさない。
expect_a() { [ "$RC" -eq 0 ] && [ "$CP_CALLS" -eq 2 ] && [ "$FILE_SIZE" -eq "$SIZE" ] \
  && grep -qF 'fetched artifacts/fl-win64.tar.zst' <<< "$OUT" && grep -qF '::notice::fetched artifacts/fl-win64.tar.zst after 2 attempts' <<< "$OUT"; }
expect_c() { [ "$RC" -eq 0 ] && [ "$CP_CALLS" -eq 2 ] && [ "$FILE_SIZE" -eq "$SIZE" ]; }

report() { # report <PASS|FAIL> <name> [detail]
  if [ "$1" = PASS ]; then echo "PASS $2"; else echo "FAIL $2 ${3:-}"; fail=1; fi
}

run_fetch a "$SCRIPT" "fail ok" ok
if expect_a; then report PASS "(a) IncompleteRead 後に再試行して成功"; else report FAIL "(a)" "rc=$RC cp=$CP_CALLS size=$FILE_SIZE out=$OUT"; fi

run_fetch b "$SCRIPT" "fail fail fail" ok
if [ "$RC" -eq 1 ] && [ "$CP_CALLS" -eq 3 ] && [ "$FILE_SIZE" = none ] \
  && grep -qF 'download failed after 3 attempts: artifacts/fl-win64.tar.zst' <<< "$OUT"; then
  report PASS "(b) 3 回失敗で終了 1・部分ファイルを残さない"
else
  report FAIL "(b)" "rc=$RC cp=$CP_CALLS size=$FILE_SIZE out=$OUT"
fi

run_fetch c "$SCRIPT" "short ok" ok
if expect_c; then report PASS "(c) サイズ不一致 (終了 0) を失敗として再試行"; else report FAIL "(c)" "rc=$RC cp=$CP_CALLS size=$FILE_SIZE out=$OUT"; fi

run_fetch d "$SCRIPT" "ok" 404
if [ "$RC" -eq 1 ] && [ "$CP_CALLS" -eq 0 ] && [ "$HEAD_CALLS" -eq 1 ] \
  && grep -qF 'missing R2 object(s) in s3://test-bucket: artifacts/fl-win64.tar.zst' <<< "$OUT" \
  && ! grep -qF 'after 3 attempts' <<< "$OUT"; then
  report PASS "(d) 404 は再試行せず missing として終了 1"
else
  report FAIL "(d)" "rc=$RC cp=$CP_CALLS head=$HEAD_CALLS out=$OUT"
fi

run_fetch e "$SCRIPT" "ok" ok
if [ "$RC" -eq 0 ] && [ "$CP_CALLS" -eq 1 ] && [ "$FILE_SIZE" -eq "$SIZE" ] \
  && grep -qF 'fetched artifacts/fl-win64.tar.zst' <<< "$OUT" && ! grep -qF '::notice::' <<< "$OUT"; then
  report PASS "(e) 1 回目で成功すれば通知なし"
else
  report FAIL "(e)" "rc=$RC cp=$CP_CALLS out=$OUT"
fi

# ネガコン: 旧ロジックは (a) と (c) を満たしてはならない (満たすなら検出できていない)。
run_fetch neg-a "$OLD" "fail ok" ok
if expect_a; then report FAIL "negative control (a): 旧ロジックが再試行なしで (a) を満たした"; else report PASS "negative control (a): 旧ロジックは (a) で落ちる (rc=$RC cp=$CP_CALLS size=$FILE_SIZE)"; fi
run_fetch neg-c "$OLD" "short ok" ok
if expect_c; then report FAIL "negative control (c): 旧ロジックが不一致を見逃さなかった"; else report PASS "negative control (c): 旧ロジックは (c) で落ちる (rc=$RC cp=$CP_CALLS size=$FILE_SIZE)"; fi

if [ "$fail" -ne 0 ]; then
  echo "test-fetch-artifacts: FAILED"
  exit 1
fi
echo "test-fetch-artifacts: all passed"
