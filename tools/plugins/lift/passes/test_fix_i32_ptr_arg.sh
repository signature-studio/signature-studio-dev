#!/usr/bin/env bash
# [P-T2] fix_i32_ptr_arg.py の回帰テスト (#1485 レビュー指摘への対応)。
# 4 ケース: 定数 / trunc 定義 (定義と呼出が 30 行以上離れる) / 仮引数の受け渡し (失敗すること) / 本体が i32 を別用途にも使う (失敗すること)。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PASS="$HERE/fix_i32_ptr_arg.py"
W="${TMPDIR:-/tmp}/t_i32ptr.$$"
mkdir -p "$W"
trap 'rm -rf "$W"' EXIT

CLANG="${CLANG:-clang}"

callee='define i64 @function_180049450(i64 %arg1, i32 %arg2) {
entry:
  %p = inttoptr i64 %arg2 to ptr
  %c = icmp eq i32 %arg2, 0
  %v = load i64, ptr %p
  ret i64 %v
}'

# 1. 定数
cat > "$W/const.ll" <<EOF
$callee

define i64 @caller(i64 %a) {
  %r = call i64 @function_180049450(i64 %a, i32 0)
  ret i64 %r
}
EOF

# 2. trunc 定義 (定義と呼出の間に 30 行以上離れる)
{
  echo "$callee"
  echo ""
  echo "define i64 @caller(i64 %a) {"
  echo "  %W = add i64 %a, 1"
  echo "  %V = trunc i64 %W to i32"
  for i in $(seq 1 30); do echo "  %pad$i = add i64 %a, $i"; done
  echo "  %r = call i64 @function_180049450(i64 %a, i32 %V)"
  echo "  ret i64 %r"
  echo "}"
} > "$W/trunc.ll"

# 3. 仮引数の受け渡し (レビューの再現入力。失敗させる)
cat > "$W/argpass.ll" <<EOF
$callee

define i64 @function_180056120(i64 %arg0, i32 %arg1) {
  %r = call i64 @function_180049450(i64 %arg0, i32 %arg1)
  ret i64 %r
}
EOF

# 4. 本体が i32 仮引数を inttoptr / icmp 以外にも使う (失敗させる)
cat > "$W/body_i32.ll" <<EOF
define i64 @function_180049450(i64 %arg1, i32 %arg2) {
entry:
  %p = inttoptr i64 %arg2 to ptr
  %x = add i32 %arg2, 1
  %v = load i64, ptr %p
  ret i64 %v
}

define i64 @caller(i64 %a) {
  %r = call i64 @function_180049450(i64 %a, i32 0)
  ret i64 %r
}
EOF

check_ok() {
  local in="$1" name="$2"
  python3 "$PASS" "$in" "$W/$name.out.ll" --func function_180049450 2>"$W/$name.err"
  "$CLANG" -x ir -fsyntax-only "$W/$name.out.ll"
  echo "PASS $name: $(cat "$W/$name.err")"
}

check_fail() {
  local in="$1" name="$2"
  if python3 "$PASS" "$in" "$W/$name.out.ll" --func function_180049450 2>"$W/$name.err"; then
    echo "FAIL $name: 失敗すべきだが成功した" >&2
    exit 1
  fi
  if [ -e "$W/$name.out.ll" ]; then
    echo "FAIL $name: 失敗時に出力を書いた" >&2
    exit 1
  fi
  echo "PASS $name (expected fail): $(cat "$W/$name.err")"
}

check_ok "$W/const.ll" const
check_ok "$W/trunc.ll" trunc
check_fail "$W/argpass.ll" argpass
check_fail "$W/body_i32.ll" body_i32

# 5. 本体が i32 仮引数を変数と比較する (icmp の被演算子が定数でない) (失敗させる)
cat > "$W/icmp_var.ll" <<EOF
define i64 @function_180049450(i64 %arg1, i32 %arg2) {
entry:
  %p = inttoptr i64 %arg2 to ptr
  %c = icmp eq i32 %arg2, %arg1
  %v = load i64, ptr %p
  ret i64 %v
}

define i64 @caller(i64 %a) {
  %r = call i64 @function_180049450(i64 %a, i32 0)
  ret i64 %r
}
EOF
check_fail "$W/icmp_var.ll" icmp_var
echo "ALL PASS"
