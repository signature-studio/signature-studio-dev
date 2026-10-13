#!/usr/bin/env bash
# fix_fistp_hi_store.py (#982 P-S2) の回帰テスト。llvm-as で支配関係を検査する (clang -x ir は forward reference を通すため使わない)。
#   ok:   正常形 → 上位 dword store が挿入され llvm-as rc=0
#   dom:  %H の定義が下位 store より後 (支配違反を生む形) → pass は書き換えず、入出力とも llvm-as rc=0
#         (修正前の pass はここで %H を先に使う store を挿入し llvm-as rc=1 になっていた)
#   name: 挿入名 %fhi_s が既存 → pass は書き換えない
# どれかが期待と違えば exit 1。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
LLVM_AS="${LLVM_AS:-/usr/lib/llvm-18/bin/llvm-as}"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

cat > "$T/ok.ll" <<'EOF'
define void @function_ok(i64 %x, i64 %arg2, i64 %arg3) {
  %p = inttoptr i64 %arg3 to ptr
  %h = inttoptr i64 %arg2 to ptr
  %f = fptosi double 1.0 to i64
  %l = trunc i64 %f to i32
  store i32 %l, ptr %p, align 4
  ret void
}
EOF
cat > "$T/dom.ll" <<'EOF'
define void @function_dom(i64 %x, i64 %arg2, i64 %arg3) {
  %p = inttoptr i64 %arg3 to ptr
  store i32 0, ptr %p, align 4
  %f = fptosi double 1.0 to i64
  %l = trunc i64 %f to i32
  store i32 %l, ptr %p, align 4
  %h = inttoptr i64 %arg2 to ptr
  ret void
}
EOF
cat > "$T/name.ll" <<'EOF'
define void @function_name(i64 %arg2, i64 %arg3) {
  %p = inttoptr i64 %arg3 to ptr
  %h = inttoptr i64 %arg2 to ptr
  %fhi_s = add i64 0, 0
  %f = fptosi double 1.0 to i64
  %l = trunc i64 %f to i32
  store i32 %l, ptr %p, align 4
  ret void
}
EOF

fail=0
check() { # name fn expect_rc_after expect_pass_changed
  local name="$1" fn="$2" want_rc="$3" want_changed="$4"
  python3 "$HERE/fix_fistp_hi_store.py" "$T/$name.ll" "$T/$name.out.ll" --func "function_$fn" > "$T/$name.log" 2>&1 || { echo "test_fix_fistp_hi_store: $name pass 失敗"; cat "$T/$name.log"; fail=1; return; }
  "$LLVM_AS" "$T/$name.out.ll" -o /dev/null > "$T/$name.as.log" 2>&1; local rc=$?
  local changed=0; cmp -s "$T/$name.ll" "$T/$name.out.ll" || changed=1
  echo "test_fix_fistp_hi_store: $name llvm-as rc=$rc (期待 $want_rc) / 書換え=$changed (期待 $want_changed)"
  [ "$rc" = "$want_rc" ] && [ "$changed" = "$want_changed" ] || fail=1
}
check ok ok 0 1
check dom dom 0 0
check name name 0 0
# ネガティブ: 旧 pass (支配チェック無し) は dom 形で llvm-as を落とすこと (テストが欠陥を検出できる証明)
if git -C "$HERE" show 1297643d:tools/plugins/lift/passes/fix_fistp_hi_store.py > "$T/old.py" 2>/dev/null; then
  python3 "$T/old.py" "$T/dom.ll" "$T/old.out.ll" --func function_dom >/dev/null 2>&1
  if "$LLVM_AS" "$T/old.out.ll" -o /dev/null >/dev/null 2>&1; then echo "test_fix_fistp_hi_store: 旧 pass も dom を通した (欠陥を検出できていない)"; fail=1; else echo "test_fix_fistp_hi_store: 旧 pass dom llvm-as rc!=0 (期待どおり)"; fi
fi
[ "$fail" = 0 ] && { echo "test_fix_fistp_hi_store: OK"; exit 0; }
echo "test_fix_fistp_hi_store: FAIL" >&2; exit 1
