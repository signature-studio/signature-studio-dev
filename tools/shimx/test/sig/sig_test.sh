#!/usr/bin/env bash
# SHX-T7 (#173) 回帰: 合成 fixture (RetDec の署名揺れ再現) で
#   (a) 正規化なし → verify_sig.sh が mismatch を検出する (検出器の健全性 / 陰性対照)
#   (b) sig_normalize.py 後 → mismatch 0
#   (c) 正規化結果の adapter が値を正しく変換する (node 実行: ptr ↔ i64 の往復)
#   (d) 未対応型 (float ↔ i32) は書換えず unresolved → sig_gate が exit 1 (CI が落ちる側の確認)
#   (e) sigs.json が shimx ソースと乖離したら gen_sigs.py --check が exit 1
#   (f) 符号付きの可能性がある整数拡張 (lstrcmpA i32→i64 戻り / SetFilePointerEx i32→i64 引数) は既定で unresolved → exit 1
#   (g) --ext-policy で sext を明示した場合だけ許可され、-1 が -1 のまま届く (zext なら 4294967295 に化ける)
#   (h) 文字列定数・コメント内の @NAME は置換しない
# 使い方: bash tools/shimx/test/sig/sig_test.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
W="$HERE/work/sigtest"; mkdir -p "$W"
FX="$HERE/test/sig/retdec_drift.ll"
ok() { echo "[sig_test] OK: $*"; }
ng() { echo "[sig_test] FAIL: $*" >&2; exit 1; }
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1; set -u

# (a) 陰性対照: 正規化なし
RAW=$(bash "$HERE/scripts/verify_sig.sh" "$FX" fx_raw 2>&1 || true)
NRAW=$(echo "$RAW" | sed -n 's/.*signature mismatch = \([0-9]*\).*/\1/p')
[ "${NRAW:-0}" -eq 4 ] || ng "(a) 正規化なしの mismatch が 4 でない (=${NRAW:-?})"
ok "(a) 正規化なし mismatch = $NRAW (期待 4: midiOutShortMsg は #179 で HANDLE (i32) に統一し drift 解消)"

# (b) 正規化後
SIG_GATE_RAW=0 bash "$HERE/scripts/sig_gate.sh" "$FX" fx > "$W/gate.out" 2>&1 || { cat "$W/gate.out"; ng "(b) sig_gate が失敗"; }
grep -q "signature mismatch = 0" "$W/gate.out" || ng "(b) 正規化後 mismatch 0 が出力されていない"
ok "(b) 正規化後 mismatch = 0"

# (c) adapter の値変換 (実行)
cat > "$W/adapt.ll" <<'LL'
target triple = "wasm32-unknown-emscripten"
declare i32 @printf(ptr, ...)
declare i32 @midiOutShortMsg(ptr, i32)
declare i32 @acmMetrics(ptr, i32, ptr)
@fmt = private constant [4 x i8] c"%d\0A\00"
define i32 @main() {
  %r = call i32 @midiOutShortMsg(ptr inttoptr (i32 5 to ptr), i32 7)
  call i32 (ptr, ...) @printf(ptr @fmt, i32 %r)
  %buf = alloca i32
  store i32 99, ptr %buf
  %m = call i32 @acmMetrics(ptr null, i32 1, ptr %buf)
  %v = load i32, ptr %buf
  call i32 (ptr, ...) @printf(ptr @fmt, i32 %v)
  ret i32 0
}
LL
python3 "$HERE/scripts/sig_normalize.py" "$W/adapt.ll" "$W/adapt.norm.ll" > /dev/null
emcc "$W/adapt.norm.ll" "$HERE"/src/*.c -o "$W/adapt.cjs" -w -O0 -Wno-error=int-conversion -sALLOW_MEMORY_GROWTH=1 -sENVIRONMENT=node \
    -sEXIT_RUNTIME=1 -sGLOBAL_BASE=1048576 -sERROR_ON_UNDEFINED_SYMBOLS=0 -pthread -sPTHREAD_POOL_SIZE=2 -Wl,--allow-multiple-definition \
    > "$W/adapt.log" 2>&1 || { tail -5 "$W/adapt.log"; ng "(c) adapter のビルド失敗"; }
OUT=$(node "$W/adapt.cjs" 2>/dev/null | tr '\n' ' ')
# midiOutShortMsg(handle 無効) = MMSYSERR_INVALHANDLE(5), acmMetrics は out に 0 を書く
[ "$OUT" = "5 0 " ] || ng "(c) adapter 経由の実行結果が '5 0 ' でない ('$OUT')"
ok "(c) adapter 経由の呼出が shimx 定義へ届く (出力 '$OUT')"

# (d) 未対応型 → unresolved → exit 1
cat > "$W/bad.ll" <<'LL'
target triple = "wasm32-unknown-emscripten"
declare i32 @midiOutShortMsg(float, i32)
define void @f() { call i32 @midiOutShortMsg(float 1.0, i32 0)  ret void }
LL
if SIG_GATE_RAW=0 bash "$HERE/scripts/sig_gate.sh" "$W/bad.ll" bad > "$W/bad.out" 2>&1; then ng "(d) 未対応型で sig_gate が 0 終了した"; fi
grep -q "UNRESOLVED" "$W/bad.out" || ng "(d) UNRESOLVED が出力されていない"
ok "(d) 未対応型 (float 引数) は UNRESOLVED で exit 1"

# (e) sigs.json 乖離検出
python3 - "$HERE/data/sigs.json" "$W/sigs.broken.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1])); s['acmMetrics']['params'][0] = 'i32'
json.dump(s, open(sys.argv[2], 'w'), indent=0, sort_keys=True)
PY
if python3 "$HERE/scripts/gen_sigs.py" --check --out "$W/sigs.broken.json" > /dev/null 2>&1; then ng "(e) 乖離した sigs.json を --check が通した"; fi
ok "(e) sigs.json 乖離 (acmMetrics 第1引数 i64→i32) を --check が検出"

# (f) 符号不明の拡張 → 既定で unresolved → exit 1
cat > "$W/sext.ll" <<'LL'
target triple = "wasm32-unknown-emscripten"
declare i32 @printf(ptr, ...)
declare i64 @lstrcmpA(ptr, ptr)
@fmt = private constant [6 x i8] c"%lld\0A\00"
@a = private constant [2 x i8] c"a\00"
@b = private constant [2 x i8] c"b\00"
define i32 @main() {
  %r = call i64 @lstrcmpA(ptr @a, ptr @b)
  call i32 (ptr, ...) @printf(ptr @fmt, i64 %r)
  ret i32 0
}
LL
cat > "$W/sfp.ll" <<'LL'
target triple = "wasm32-unknown-emscripten"
declare i32 @SetFilePointerEx(i32, i32, ptr, i32)
define void @f() { call i32 @SetFilePointerEx(i32 0, i32 -1, ptr null, i32 1)  ret void }
LL
for t in sext sfp; do
    if SIG_GATE_RAW=0 bash "$HERE/scripts/sig_gate.sh" "$W/$t.ll" "$t" > "$W/$t.out" 2>&1; then ng "(f) $t: 符号不明の拡張で sig_gate が 0 終了した"; fi
    grep -q "UNRESOLVED" "$W/$t.out" || ng "(f) $t: UNRESOLVED が出力されていない"
done
ok "(f) 符号不明の拡張 (lstrcmpA 戻り i32→i64 / SetFilePointerEx 引数 i32→i64) は既定で UNRESOLVED exit 1"

# (g) sext を明示した場合だけ許可、-1 が -1 のまま届く (shimx の lstrcmpA("a","b") = -1)
echo '{"lstrcmpA": {"ret": "sext"}}' > "$W/ext_sext.json"
python3 "$HERE/scripts/sig_normalize.py" "$W/sext.ll" "$W/sext.norm.ll" --ext-policy "$W/ext_sext.json" --strict > /dev/null || ng "(g) sext 方針指定で正規化が失敗"
grep -q "sext i32" "$W/sext.norm.ll" || ng "(g) adapter に sext が出ていない"
emcc "$W/sext.norm.ll" "$HERE"/src/*.c -o "$W/sext.cjs" -w -O0 -Wno-error=int-conversion -sALLOW_MEMORY_GROWTH=1 -sENVIRONMENT=node \
    -sEXIT_RUNTIME=1 -sGLOBAL_BASE=1048576 -sERROR_ON_UNDEFINED_SYMBOLS=0 -pthread -sPTHREAD_POOL_SIZE=2 -Wl,--allow-multiple-definition \
    > "$W/sext.log" 2>&1 || { tail -5 "$W/sext.log"; ng "(g) sext adapter のビルド失敗"; }
OUT=$(node "$W/sext.cjs" 2>/dev/null | tr '\n' ' ')
[ "$OUT" = "-1 " ] || ng "(g) lstrcmpA の戻りが '-1 ' でない ('$OUT')"
ok "(g) --ext-policy sext: 負値 -1 が -1 のまま届く (出力 '$OUT')"

# (h) 文字列定数・; コメント内の @NAME は置換されない (配列長が変わり emcc が落ちる / コメント改変)
cat > "$W/str.ll" <<'LL'
target triple = "wasm32-unknown-emscripten"
declare i32 @acmMetrics(ptr, i32, ptr)
@s = private constant [24 x i8] c"see @acmMetrics ok\00"
; note @acmMetrics
define void @f() { call i32 @acmMetrics(ptr null, i32 1, ptr null)  ret void }
LL
python3 "$HERE/scripts/sig_normalize.py" "$W/str.ll" "$W/str.norm.ll" --strict > /dev/null || ng "(h) 正規化が失敗"
grep -q 'c"see @acmMetrics ok' "$W/str.norm.ll" || ng "(h) 文字列定数内の @NAME が書換えられた"
grep -q '^; note @acmMetrics' "$W/str.norm.ll" || ng "(h) コメント内の @NAME が書換えられた"
grep -q 'call i32 @__shx_sig_acmMetrics' "$W/str.norm.ll" || ng "(h) 呼出 site が adapter に向いていない"
ok "(h) 文字列定数・コメント内の @NAME は不変、呼出 site は adapter へ"
echo "[sig_test] ALL PASS"
