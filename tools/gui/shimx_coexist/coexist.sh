#!/usr/bin/env bash
# shimx × gui 共存リンクテスト (#172 SHX-T5)。1 コマンド: bash tools/gui/shimx_coexist/coexist.sh
#   1. gui 全 obj (IR 署名 adapter 付き, 到達ログ有効) と shimx 全 obj を同一 wasm にリンク (-Wl,--fatal-warnings: 警告があれば失敗)
#   2. 重複/警告の件数、shimx weak 9 本の「どちらが勝ったか」を静的 (llvm-nm + wasm-ld -Map) と動的 (adapter 到達計数) で確認
#   3. node 上で HostCallBridge (src/runtime/gui_hostcall.ts) を host に wasm を実行: MsgWait / Char* / ShellExecute / OpenFileName / Drop
#   env: M11_IR = adapter 生成に使う m11 IR (既定 tools/m11/work/boot_final3.ll。無ければ integ/fixtures の GUI declare 抜粋)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; GUI="$HERE/.."; SX="$GUI/../shimx"; REPO="$(cd "$GUI/../.." && pwd)"
W="${COEXIST_WORK:-$HERE/work}"; mkdir -p "$W"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
command -v emcc >/dev/null || { echo "[coexist] emcc が無い"; exit 2; }
source "$SX/flags.sh"
IR="${M11_IR:-$REPO/tools/m11/work/boot_final3.ll}"
[ -f "$IR" ] || { echo "[coexist] M11_IR 無し → fixture を使用"; IR="$GUI/integ/fixtures/boot_final_gui_declares.ll"; }
echo "[coexist] IR=$(realpath --relative-to="$REPO" "$IR" 2>/dev/null || echo "$IR") sha1=$(sha1sum "$IR" | cut -c1-10)"

rm -rf "$W/gui_obj" "$W/sx_obj"; mkdir -p "$W/gui_obj" "$W/sx_obj"
bash "$GUI/integ/build_objs.sh" "$W/gui_obj" --reach --ir "$IR" | tail -2
for f in "$SX"/src/*.c; do emcc -c "${SHIMX_CLANG_FLAGS[@]}" -pthread -I "$SX/src" "$f" -o "$W/sx_obj/$(basename "$f" .c).o"; done
CF=(-O1 -fwrapv -w -fno-strict-aliasing -pthread -I "$GUI/include" -I "$GUI/src" -I "$GUI/build")
emcc -c "${CF[@]}" "$HERE/t_gui.c" -o "$W/t_gui.o"
emcc -c "${SHIMX_CLANG_FLAGS[@]}" -pthread -I "$SX/src" "$HERE/t_main.c" -o "$W/t_main.o"

# ---- 静的: 9 本の定義元 ----
WEAK9="CharLowerBuffW CharLowerW CharNextExA CharNextW CharToOemBuffW CharUpperBuffW CharUpperW MsgWaitForMultipleObjects MsgWaitForMultipleObjectsEx"
llvm-nm --defined-only -g "$W"/gui_obj/gui_adapt_w32.o | awk '$2=="T"{print $3}' | sort -u > "$W/gui_public.txt"
llvm-nm --defined-only -g "$W"/gui_obj/*.o | awk '$2=="T"||$2=="W"{print $3}' | sort -u > "$W/gui_defs_all.txt"
llvm-nm --defined-only -g "$W"/sx_obj/*.o | awk '$2=="T"{print $3}' | sort -u > "$W/sx_strong.txt"
llvm-nm --defined-only -g "$W"/sx_obj/*.o | awk '$2=="W"{print $3}' | sort -u > "$W/sx_weak.txt"
comm -12 "$W/gui_defs_all.txt" "$W/sx_strong.txt" > "$W/dup_strong_x_strong.txt"
comm -12 "$W/gui_defs_all.txt" "$W/sx_weak.txt" > "$W/dup_gui_x_sxweak.txt"
echo "[coexist] shimx weak 定義 $(wc -l < "$W/sx_weak.txt") 本 / うち gui が公開名で強定義 $(wc -l < "$W/dup_gui_x_sxweak.txt") 本 / shimx 強 × gui 定義の重複 $(wc -l < "$W/dup_strong_x_strong.txt") 本"
for n in $WEAK9; do
  if grep -qx "$n" "$W/gui_public.txt"; then o="gui(adapter, IR 宣言あり)"; else o="shimx weak (IR 宣言なし: gui は公開名を出さない)"; fi
  printf '[coexist]   %-30s -> %s\n' "$n" "$o"
done | tee "$W/winner_static.txt"

# ---- リンク ----
EXPORTS=_main,_gui_headless_attach,_gui_hostcall_ptr,_gui_stage_dir_posix,_gui_drop_files,_gui_shimx_attach,_malloc,_free
set +e
emcc "${SHIMX_EMCC_COMMON[@]}" -pthread -sPTHREAD_POOL_SIZE=8 -sPROXY_TO_PTHREAD=1 -sMODULARIZE=1 -sEXPORT_NAME=coexist -sSTACK_SIZE=1MB \
  -sEXPORTED_RUNTIME_METHODS=FS,UTF8ToString,HEAPU8,wasmMemory -sEXPORTED_FUNCTIONS=$EXPORTS -Wno-pthreads-mem-growth -Wl,--fatal-warnings -Wl,-Map="$W/link.map" -Wl,--error-limit=0 \
  "$W"/gui_obj/*.o "$W"/sx_obj/*.o "$W/t_gui.o" "$W/t_main.o" -o "$W/coexist.js" > "$W/link.log" 2>&1
RC=$?; set -e
DUP=$(grep -c 'duplicate symbol' "$W/link.log" || true); WARN=$(grep -ci 'warning' "$W/link.log" || true); UND=$(grep -c 'undefined symbol' "$W/link.log" || true)
echo "[coexist] link rc=$RC duplicate symbol=$DUP warning=$WARN undefined symbol=$UND (log: $(realpath --relative-to="$REPO" "$W/link.log"))"
[ "$RC" -eq 0 ] || { head -30 "$W/link.log"; exit 1; }
mv "$W/coexist.js" "$W/coexist.cjs"
[ "$DUP" -eq 0 ] && [ "$WARN" -eq 0 ] && [ "$UND" -eq 0 ] || { echo "[coexist] FAIL: 重複/警告/未解決が 0 でない"; exit 1; }

# ---- 動的 ----
node --experimental-strip-types --no-warnings "$HERE/run.mjs" "$W/coexist.cjs"

# ---- ネガティブコントロール ----
NCOUT="$W/nc.txt"; : > "$NCOUT"
# NC1: shimx の SHIMX_WEAK を外したコピーをリンク → gui 強定義と衝突して duplicate symbol が出る (= 本検査が重複を検出できる証拠)
rm -rf "$W/sx_nc_src" "$W/sx_nc_obj"; mkdir -p "$W/sx_nc_src" "$W/sx_nc_obj"; cp "$SX"/src/* "$W/sx_nc_src/"
sed -i 's/SHIMX_WEAK //' "$W"/sx_nc_src/*.c
for f in "$W"/sx_nc_src/*.c; do emcc -c "${SHIMX_CLANG_FLAGS[@]}" -pthread -I "$W/sx_nc_src" "$f" -o "$W/sx_nc_obj/$(basename "$f" .c).o"; done
set +e
emcc "${SHIMX_EMCC_COMMON[@]}" -pthread -sPTHREAD_POOL_SIZE=8 -sPROXY_TO_PTHREAD=1 -sMODULARIZE=1 -sSTACK_SIZE=1MB -Wno-pthreads-mem-growth -Wl,--error-limit=0 \
  "$W"/gui_obj/*.o "$W"/sx_nc_obj/*.o "$W/t_gui.o" "$W/t_main.o" -o "$W/nc1.js" > "$W/nc1.log" 2>&1
NC1RC=$?; set -e
NC1N=$(grep -c 'duplicate symbol' "$W/nc1.log" || true)
echo "[coexist] NC1 (shimx から weak を除去): link rc=$NC1RC duplicate symbol=$NC1N (期待: rc!=0, 重複 = gui 公開名 ∩ shimx weak = $(wc -l < "$W/dup_gui_x_sxweak.txt"))" | tee -a "$NCOUT"
[ "$NC1RC" -ne 0 ] && [ "$NC1N" -eq "$(wc -l < "$W/dup_gui_x_sxweak.txt")" ] || { echo "[coexist] NC1 FAIL"; exit 1; }
# NC2: host (HostCallBridge) を起動しない → C 側の ShellExecute / ダイアログ検査が落ちる
set +e
COEXIST_NC=nohost node --experimental-strip-types --no-warnings "$HERE/run.mjs" "$W/coexist.cjs" > "$W/nc2.log" 2>&1
NC2RC=$?; set -e
NC2F=$(grep -o 'RESULT pass=[0-9]* fail=[0-9]*' "$W/nc2.log" | head -1 | sed 's/.*fail=//')
echo "[coexist] NC2 (host 無し): exit=$NC2RC C 側 fail=${NC2F:-?} (期待: exit!=0, fail>0)" | tee -a "$NCOUT"
[ "$NC2RC" -ne 0 ] && [ "${NC2F:-0}" -gt 0 ] || { echo "[coexist] NC2 FAIL"; exit 1; }
# NC3 (#958): handles.c の CloseHandle から file close hook 呼出しを外す → 閉じた save 先が自動では反映されない
rm -rf "$W/sx_nc3_src" "$W/sx_nc3_obj"; mkdir -p "$W/sx_nc3_src" "$W/sx_nc3_obj"; cp "$W"/sx_obj/*.o "$W/sx_nc3_obj/"; cp "$SX/src/handles.c" "$W/sx_nc3_src/"
sed -i 's/if (g_file_close_hook \&\& /if (0 \&\& /' "$W/sx_nc3_src/handles.c"
grep -q 'if (0 && o->type == OBJ_FILE' "$W/sx_nc3_src/handles.c" || { echo "[coexist] NC3 の sed が当たらない"; exit 1; }
emcc -c "${SHIMX_CLANG_FLAGS[@]}" -pthread -I "$SX/src" "$W/sx_nc3_src/handles.c" -o "$W/sx_nc3_obj/handles.o"
set +e
emcc "${SHIMX_EMCC_COMMON[@]}" -pthread -sPTHREAD_POOL_SIZE=8 -sPROXY_TO_PTHREAD=1 -sMODULARIZE=1 -sEXPORT_NAME=coexist -sSTACK_SIZE=1MB \
  -sEXPORTED_RUNTIME_METHODS=FS,UTF8ToString,HEAPU8,wasmMemory -sEXPORTED_FUNCTIONS=$EXPORTS -Wno-pthreads-mem-growth \
  "$W"/gui_obj/*.o "$W"/sx_nc3_obj/*.o "$W/t_gui.o" "$W/t_main.o" -o "$W/nc3.js" > "$W/nc3.log" 2>&1
NC3LINK=$?
mv "$W/nc3.js" "$W/nc3.cjs" 2>/dev/null
node --experimental-strip-types --no-warnings "$HERE/run.mjs" "$W/nc3.cjs" > "$W/nc3-run.log" 2>&1
NC3RC=$?; set -e
NC3F=$(grep -c '^FAIL host: save: FL が閉じた' "$W/nc3-run.log" || true)
echo "[coexist] NC3 (CloseHandle の file close hook を外す): link rc=$NC3LINK run exit=$NC3RC 自動反映の検査 FAIL=$NC3F (期待: 全て非 0 / FAIL=1)" | tee -a "$NCOUT"
[ "$NC3LINK" -eq 0 ] && [ "$NC3RC" -ne 0 ] && [ "$NC3F" -eq 1 ] || { echo "[coexist] NC3 FAIL"; exit 1; }
echo "[coexist] ALL PASS"
