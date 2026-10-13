#!/usr/bin/env bash
# SHX-T7 (#173) 回帰: 合成 fixture (RetDec の署名揺れ再現) で
#   (a) 正規化なし → verify_sig.sh が mismatch を検出する (検出器の健全性 / 陰性対照)
#   (b) sig_normalize.py 後 → mismatch 0
#   (c) 正規化結果の adapter が値を正しく変換する (node 実行: i32 → i64 零拡張, ptr ↔ i64 の往復)
#   (d) 未対応型 (float ↔ i32) は書換えず unresolved → sig_gate が exit 1 (CI が落ちる側の確認)
#   (e) sigs.json が shimx ソースと乖離したら gen_sigs.py --check が exit 1
# 使い方: bash tools/shimx/test/sig/sig_test.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
W="$HERE/work/sigtest"; mkdir -p "$W"
FX="$HERE/test/sig/retdec_drift.ll"
ok() { echo "[sig_test] OK: $*"; }
ng() { echo "[sig_test] FAIL: $*" >&2; exit 1; }

# (a) 陰性対照: 正規化なし
RAW=$(bash "$HERE/scripts/verify_sig.sh" "$FX" fx_raw 2>&1 || true)
NRAW=$(echo "$RAW" | sed -n 's/.*signature mismatch = \([0-9]*\).*/\1/p')
[ "${NRAW:-0}" -eq 5 ] || ng "(a) 正規化なしの mismatch が 5 でない (=${NRAW:-?})"
ok "(a) 正規化なし mismatch = $NRAW (期待 5)"

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
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1; set -u
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
echo "[sig_test] ALL PASS"
