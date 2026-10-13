#!/usr/bin/env bash
# fix_icmp_ptr.py (E1: `icmp ptr %p, %i64arg`) の回帰テスト + ネガティブコントロール (PLG-F6-2 #545)
#   修復前 (pass を通さない) の IR は emcc -c が非 0 (期待 "defined with type 'i64' but expected 'ptr'")、pass を通すと 0 になること。
#   どちらかが期待と違えば exit 1 (= 欠陥を検出できないテストを合格にしない)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
T="$(mktemp -d)"
cat > "$T/t.ll" <<'EOF'
target triple = "wasm32-unknown-emscripten"
define i64 @f(i64 %arg1, ptr %p) {
  %c = icmp eq ptr %p, %arg1
  %z = zext i1 %c to i64
  ret i64 %z
}
EOF
emcc -c "$T/t.ll" -o "$T/t.o" -w > "$T/before.log" 2>&1; before=$?
python3 "$HERE/fix_icmp_ptr.py" "$T/t.ll" "$T/t2.ll" 2> "$T/pass.log"
emcc -c "$T/t2.ll" -o "$T/t2.o" -w > "$T/after.log" 2>&1; after=$?
echo "test_fix_icmp_ptr: 修復前 emcc rc=$before (期待 非0) / 修復後 emcc rc=$after (期待 0) / 修復前の理由: $(grep -m1 error "$T/before.log")"
if [ "$before" != 0 ] && [ "$after" = 0 ] && grep -q "defined with type 'i64' but expected 'ptr'" "$T/before.log"; then echo "test_fix_icmp_ptr: OK"; rm -rf "$T"; exit 0; fi
echo "test_fix_icmp_ptr: FAIL" >&2; rm -rf "$T"; exit 1
