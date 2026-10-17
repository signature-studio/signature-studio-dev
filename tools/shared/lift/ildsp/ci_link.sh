#!/usr/bin/env bash
# CreateInstance (0x1aa290) の ci_lift.sh 出力 (ci.rs_norm.ll・ci_helpers.c) を wasm にリンクし、未解決シンボルを数える (T-SH-152 #5748)。
# 入力: ci_lift.sh の出力 (tools/shared/work/lift/ci/)。census FAIL で ci_lift.sh が rc 1 のとき ci.rs_norm.ll・ci_helpers.c は無いので、REPORT_CI.md §9-1 の 2 行 (ir_normalize.py・gen_helpers.py) を先に流す。emsdk は EMSDK_ENV (既定は [EMSDK] の emsdk_env.sh。docs/REFERENCES.md §1)。
# 処理: uselistorder 行を除く (emcc の LLVM が読めない) -> @global_var_1803f6610 を画像内の絶対アドレス化 -> ci.o -> helpers.o -> 検査用 shim (@0 のみ) -> wasm-ld。
# 出力: tools/shared/work/lift/ci-link/ (gitignore)。
# 注意: @0 (__unnamed_1) の shim は「リンクが通るための仮置き」。画像上の意味は未検証 (REPORT_CI.md §9-2)。絶対アドレスの値 (0x303f6610) の画像上の意味確認は #3320。
# usage: bash tools/shared/lift/ildsp/ci_link.sh   (exit 0 = 未解決の集合が期待集合と一致 / exit 1 = 想定外の未解決 / exit 2 = 入力が無い)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
source "$ROOT/env.sh"
IN="$ROOT/work/lift/ci"
W="$ROOT/work/lift/ci-link"; mkdir -p "$W"
[ -f "$IN/ci.rs_norm.ll" ] && [ -f "$IN/ci_helpers.c" ] || { echo "[ci-link] ci_lift.sh の出力が無い: $IN"; exit 2; }
source "${EMSDK_ENV:?EMSDK_ENV を設定 ([EMSDK] の emsdk_env.sh)}" >/dev/null 2>&1

# global_var_1803f6610 は画像内の cell (RVA 0x3f6610・wc_image.py の BASE 0x30000000 基準) に敷設する (REPORT_CI §9-2)。
IMG_BASE=0x30000000; CELL_RVA=0x3f6610
grep -v -e '^  uselistorder' -e '^@global_var_1803f6610 = external global i64$' "$IN/ci.rs_norm.ll" | sed "s/@global_var_1803f6610/inttoptr (i64 $((IMG_BASE + CELL_RVA)) to ptr)/g" > "$W/ci.ll"
cat > "$W/shim.c" <<'EOF'
#include <stdint.h>
/* 検査用の仮置き (意味は未検証)。ret 値用の cell (@0 = __unnamed_1) のみ。画像敷設は未決 (REPORT_CI §9-2)。 */
int32_t __unnamed_1;
EOF
emcc -c -O1 -w "$W/ci.ll" -o "$W/ci.o"
emcc -c -O1 -w "$IN/ci_helpers.c" -o "$W/helpers.o"
emcc -c -O1 -w "$W/shim.c" -o "$W/shim.o"
set +e
emcc -O1 -w "$W/ci.o" "$W/helpers.o" "$W/shim.o" -sSTANDALONE_WASM=1 --no-entry -sERROR_ON_UNDEFINED_SYMBOLS=1 \
  -Wl,--no-gc-sections -Wl,--error-limit=0 -Wl,--export=GeneralPitchShifter_CreateInstance -o "$W/ci.wasm" > "$W/link.log" 2>&1
RC=$?
set -e
grep -o 'undefined symbol: [A-Za-z_0-9]*' "$W/link.log" | sed 's/undefined symbol: //' | sort | uniq -c > "$W/undefined.txt" || true
echo "[ci-link] wasm-ld rc=$RC / 未解決シンボル (種, 件数 = リンクエラー行数)"
cat "$W/undefined.txt"
EXPECT='EnterCriticalSection|FlsGetValue|FlsSetValue|GetLastError|HeapAlloc|HeapFree|LeaveCriticalSection|RaiseException|RtlPcToFileHeader|SetLastError|function_1801aef40|function_1801cb600'
BAD=$(sed -E 's/^ *[0-9]+ //' "$W/undefined.txt" | grep -Ev "^($EXPECT)$" || true)
if [ -n "$BAD" ]; then echo "[ci-link] 想定外の未解決: $BAD"; exit 1; fi
echo "[ci-link] 未解決は期待集合 (IAT 10 種・直接/画像内の呼び出し先 2 種) のみ。global_var_1803f6610 と __stack_pointer は解決済み (@0 は shim)"
exit 0
