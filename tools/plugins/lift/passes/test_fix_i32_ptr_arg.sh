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

# 6. 伝播 (#1509): 呼出元 C の i32 仮引数 %arg1 を、C 自身を --func に指定して i64 化する。
#    C の %arg1 は変換済み callee へ渡すだけ。C の呼出は i32 0 / trunc 定義 / 定数の 3 形を含む。
cat > "$W/propagate.ll" <<EOF
$callee

define i64 @function_180056120(i32 %arg1, i64 %arg2) {
  %p = inttoptr i64 %arg2 to ptr
  %r = call i64 @function_180049450(i64 %arg2, i32 %arg1)
  ret i64 %r
}

define i64 @outer(i64 %a) {
  %W = add i64 %a, 1
  %V = trunc i64 %W to i32
  %r1 = call i64 @function_180056120(i32 0, i64 %a)
  %r2 = call i64 @function_180056120(i32 %V, i64 %a)
  ret i64 %r1
}
EOF
python3 "$PASS" "$W/propagate.ll" "$W/propagate.out.ll" --func function_180049450 --func function_180056120 2>"$W/propagate.err" || { echo "FAIL propagate" >&2; exit 1; }
"$CLANG" -x ir -fsyntax-only "$W/propagate.out.ll"
grep -q 'define i64 @function_180056120(i64 %arg1' "$W/propagate.out.ll" || { echo "FAIL propagate: 仮引数が i64 化されていない" >&2; exit 1; }
echo "PASS propagate: $(cat "$W/propagate.err")"

# 7. --func の順序が逆 (呼出元を先に処理) → 失敗 (受け先が処理前で伝播できない)。
if python3 "$PASS" "$W/propagate.ll" "$W/prop_rev.out.ll" --func function_180056120 --func function_180049450 2>"$W/prop_rev.err"; then
  echo "FAIL prop_rev: 失敗すべきだが成功した" >&2
  exit 1
fi
if [ -e "$W/prop_rev.out.ll" ]; then
  echo "FAIL prop_rev: 失敗時に出力を書いた" >&2
  exit 1
fi
echo "PASS prop_rev (expected fail): $(cat "$W/prop_rev.err")"
echo "ALL PASS"
