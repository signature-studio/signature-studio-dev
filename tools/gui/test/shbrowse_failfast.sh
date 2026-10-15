#!/usr/bin/env bash
# SHX-T34 (#2917): gui 側の node + mock 検査。gui の全 obj と shimx の全 obj を同一 wasm にリンクし (coexist.sh と同じ構成)、
# SHBrowseForFolderA/W を GetProcAddress で解決すると名前を出して fail-fast (非 0 終了) することを検査する。
# 1 コマンド: bash tools/gui/test/shbrowse_failfast.sh
#   env: SHBROWSE_WORK = 生成物の作業先 (既定 tools/gui/test/work/shbrowse。gitignore 対象)
#        M11_IR        = adapter 生成に使う IR (既定 tools/m11/work/boot_final3.ll。無ければ integ/fixtures の GUI declare 抜粋)
# 検査: ① A/W: rc≠0 かつ stderr に "FAIL-FAST: unimplemented Win32 API: SHBrowseForFolder" ② 対照 ShellExecuteW は解決され rc=0
#       ③ ネガティブコントロール: shimx の SHBrowseForFolder の fail-fast 行を外すと ① が 2 件とも FAIL になる (検査が効く証拠)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; GUI="$HERE/.."; SX="$GUI/../shimx"; REPO="$(cd "$GUI/../.." && pwd)"
W="${SHBROWSE_WORK:-$HERE/work/shbrowse}"; mkdir -p "$W"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
command -v emcc >/dev/null || { echo "[shbrowse] emcc が無い"; exit 2; }
# emsdk 6.x は llvm-nm を upstream/bin に置き、emsdk_env.sh は載せない。2 回目の source (build_objs.sh 内) で補正が消えるため EMSDK_ENV=/dev/null で再 source を止める
command -v llvm-nm >/dev/null || export PATH="$(cd "$(dirname "$(readlink -f "$(command -v emcc)")")/.." && pwd)/bin:$PATH"
command -v llvm-nm >/dev/null || { echo "[shbrowse] llvm-nm が無い"; exit 2; }
export EMSDK_ENV=/dev/null
source "$SX/flags.sh"
IR="${M11_IR:-$REPO/tools/m11/work/boot_final3.ll}"
[ -f "$IR" ] || { echo "[shbrowse] M11_IR 無し → fixture を使用"; IR="$GUI/integ/fixtures/boot_final_gui_declares.ll"; }
echo "[shbrowse] IR=$(realpath --relative-to="$REPO" "$IR" 2>/dev/null || echo "$IR") sha1=$(sha1sum "$IR" | cut -c1-10)"

rm -rf "$W/gui_obj" "$W/sx_obj"; mkdir -p "$W/gui_obj" "$W/sx_obj"
bash "$GUI/integ/build_objs.sh" "$W/gui_obj" --reach --ir "$IR" | tail -1
for f in "$SX"/src/*.c; do emcc -c "${SHIMX_CLANG_FLAGS[@]}" -pthread -I "$SX/src" "$f" -o "$W/sx_obj/$(basename "$f" .c).o"; done
emcc -c "${SHIMX_CLANG_FLAGS[@]}" -pthread -I "$SX/src" "$HERE/shbrowse_probe.c" -o "$W/probe.o"

LINKF=("${SHIMX_EMCC_COMMON[@]}" -pthread -sPTHREAD_POOL_SIZE=8 -sSTACK_SIZE=1MB -Wno-pthreads-mem-growth -Wl,--fatal-warnings)
emcc "${LINKF[@]}" "$W"/gui_obj/*.o "$W"/sx_obj/*.o "$W/probe.o" -o "$W/probe.js" > "$W/link.log" 2>&1 \
  || { head -30 "$W/link.log"; echo "[shbrowse] FAIL: link"; exit 1; }
mv "$W/probe.js" "$W/probe.cjs"

N_PASS=0; N_FAIL=0
ok() { N_PASS=$((N_PASS+1)); echo "[shbrowse] PASS $*"; }
ng() { N_FAIL=$((N_FAIL+1)); echo "[shbrowse] FAIL $*"; }
run() {  # $1=cjs $2=mode → RC / stderr は $W/err_<tag>.txt
  RC=0; node "$1" "$2" > "$W/out_$3.txt" 2> "$W/err_$3.txt" || RC=$?
}
MSG="[shim] FAIL-FAST: unimplemented Win32 API: SHBrowseForFolder"

# ① SHBrowseForFolderA/W → 名前を出して fail-fast
for m in a w; do
  api="SHBrowseForFolder$(echo "$m" | tr a-z A-Z)"
  run "$W/probe.cjs" "$m" "$m"
  if [ "$RC" -ne 0 ] && grep -qxF "$MSG" "$W/err_$m.txt"; then ok "$api: rc=$RC fail-fast (stderr に API 名)"; else ng "$api: rc=$RC (fail-fast 無し)"; fi
done
# ② 対照: ShellExecuteW は解決され rc=0 (probe と handle が正しいことの確認)
run "$W/probe.cjs" ok ok
if [ "$RC" -eq 0 ] && grep -qF "ShellExecuteW resolved" "$W/err_ok.txt"; then ok "control ShellExecuteW: rc=0 resolved"; else ng "control ShellExecuteW: rc=$RC"; fi

# ③ ネガティブコントロール: shimx の SHBrowseForFolder の fail-fast 行を外した wasm では ① が落ちる
NCS="$W/sx_nc_src"; NCO="$W/sx_nc_obj"
rm -rf "$NCS" "$NCO"; mkdir -p "$NCS" "$NCO"; cp "$SX"/src/* "$NCS/"
sed -i 's/shim_unimplemented("SHBrowseForFolder");/(void)0;/' "$NCS/module.c"
grep -q 'shim_unimplemented("SHBrowseForFolder")' "$NCS/module.c" && { echo "[shbrowse] NC の sed が当たらない"; exit 1; }
cp "$W"/sx_obj/*.o "$NCO/"
emcc -c "${SHIMX_CLANG_FLAGS[@]}" -pthread -I "$NCS" "$NCS/module.c" -o "$NCO/module.o"
emcc "${LINKF[@]}" "$W"/gui_obj/*.o "$NCO"/*.o "$W/probe.o" -o "$W/nc.js" > "$W/nc_link.log" 2>&1 \
  || { head -30 "$W/nc_link.log"; echo "[shbrowse] NC link FAIL"; exit 1; }
mv "$W/nc.js" "$W/nc.cjs"
NC_DETECT=0
for m in a w; do
  api="SHBrowseForFolder$(echo "$m" | tr a-z A-Z)"
  run "$W/nc.cjs" "$m" "nc_$m"
  if ! { [ "$RC" -ne 0 ] && grep -qxF "$MSG" "$W/err_nc_$m.txt"; }; then NC_DETECT=$((NC_DETECT+1)); ok "NC $api: fail-fast 行を外すと FAIL を検出 (rc=$RC)"; else ng "NC $api: 外しても fail-fast が残った (rc=$RC)"; fi
done
echo "[shbrowse] RESULT pass=$N_PASS fail=$N_FAIL (NC 検出 $NC_DETECT/2)"
[ "$N_FAIL" -eq 0 ] && [ "$NC_DETECT" -eq 2 ] || { echo "[shbrowse] FAIL"; exit 1; }
echo "[shbrowse] ALL PASS"
