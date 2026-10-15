#!/bin/bash
# test-title-collision.sh — check-title-collision.sh の検出と誤検知 0 を fake gh で検証する (CI-197, #4721)。
# 実行: bash .github/scripts/tests/test-title-collision.sh   (全て通れば exit 0、1 件でも落ちれば exit 1)
# CI: .github/workflows/scripts-test.yaml が .github/scripts/** の変更ごとに実行する。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/../check-title-collision.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export OC_REPO=o/r GH_TOKEN=x

# fake gh: `gh issue view N ... --jq .title` は $FIX/view-N、`gh issue list` は $FIX/list を返す。
# FAKE_LIST_FAILS=1 なら list を失敗させる。
mkdir -p "$TMP/bin" "$TMP/fix"
cat > "$TMP/bin/gh" << 'EOF'
#!/bin/bash
if [ "$1" = issue ] && [ "$2" = view ]; then
  cat "$FAKE_FIX/view-$3"
  exit 0
fi
if [ "$1" = issue ] && [ "$2" = list ]; then
  [ -n "${FAKE_LIST_FAILS:-}" ] && { echo "fake gh: list failed" >&2; exit 1; }
  cat "$FAKE_FIX/list"
  exit 0
fi
echo "fake gh: unexpected: $*" >&2
exit 1
EOF
chmod +x "$TMP/bin/gh"
export PATH="$TMP/bin:$PATH" FAKE_FIX="$TMP/fix"

# 一覧 (番号 TAB 題名)。
printf '%s\t%s\n' \
  10 '[PY-217] old issue' \
  15 '[HB-H2] legacy prefix' \
  20 '[PY-336] first' \
  21 'no tag at all' \
  22 '[PY-217a] suffixed' \
  30 '[PY-217] new collision' \
  31 '[PY-217] later, must not be reported' \
  > "$TMP/fix/list"

fails=0
check() { # check <名前> <issue番号> <期待する出力 (空可)>
  local name="$1" n="$2" want="$3" got
  got="$(bash "$CHECK" "$n" 2>/dev/null)"
  if [ "$got" = "$want" ]; then
    echo "PASS $name"
  else
    echo "FAIL $name: want [$want] got [$got]"
    fails=$((fails + 1))
  fi
}

# 1) 重複: #30 の [PY-217] は先行の #10 と重複する。後続の #31 は報告しない。
echo '[PY-217] new collision' > "$TMP/fix/view-30"
check "collision detected (先行のみ報告)" 30 "#10 [PY-217] old issue"

# 2) 誤検知 0: 同じ AREA でも n が違う / 非数値の接頭辞 / サフィックス違い / タグ無しは何も出さない。
echo '[PY-336] first' > "$TMP/fix/view-20"
check "no collision for different n" 20 ""
echo '[PY-217a] suffixed' > "$TMP/fix/view-22"
check "suffixed tag is a distinct tag" 22 ""
echo 'no tag at all' > "$TMP/fix/view-21"
check "no tag -> nothing" 21 ""

# 3) 非数値の接頭辞 ([HB-H2]) は対象外。同じ文字列でも検出しない。
echo '[HB-H2] legacy prefix' > "$TMP/fix/view-16"
printf '%s\t%s\n' 15 '[HB-H2] legacy prefix' 16 '[HB-H2] legacy prefix' > "$TMP/fix/list"
check "non-numeric prefix [HB-H2] is not checked" 16 ""

# 4) 取得失敗は検査できなかったことを終了コード 2 で返す (黙って成功扱いにしない)。
printf '%s\t%s\n' 30 '[PY-217] new collision' > "$TMP/fix/list"
echo '[PY-217] new collision' > "$TMP/fix/view-30"
FAKE_LIST_FAILS=1 bash "$CHECK" 30 >/dev/null 2>&1
rc=$?
if [ "$rc" -eq 2 ]; then echo "PASS list failure -> exit 2"; else echo "FAIL list failure: exit $rc (want 2)"; fails=$((fails + 1)); fi

# 5) 使い方の誤り。
bash "$CHECK" >/dev/null 2>&1
rc=$?
if [ "$rc" -eq 2 ]; then echo "PASS usage error -> exit 2"; else echo "FAIL usage: exit $rc (want 2)"; fails=$((fails + 1)); fi

if [ "$fails" -gt 0 ]; then
  echo "$fails test(s) failed"
  exit 1
fi
echo "all title-collision tests passed"
