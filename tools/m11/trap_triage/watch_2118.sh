#!/usr/bin/env bash
# #2118 (M11-N141): unit 158 (0x26d1a0) の ok/trap を分ける 2 区間 (0xfa5108-0xfa5c68, 0x11e69b0-0x11e6b98) への書込みを、
# OFF (M11_OV_413060=0) と ON (M11_OV_413060=1・M11_DEST_READ=1) で unit 0・1・158 の実行中に記録して比較する。
#   usage: bash trap_triage/watch_2118.sh <off|on> <out_dir>
#   - watch build: 全 store の直後に m11_sw を入れた boot (watch_store_682.py)・範囲版 m11_sw (watch_range_2118.c)・INSTR=1 (計装)
#   - clean build: 計装なし (M11_INSTR_413060=0) で unit 0,1,158 の ok/trap を見る (判定はこちら)
#   出力: <out_dir>/<label>_watch.log (`unit N` と `[rw]` 行), <out_dir>/<label>_clean.txt (unit 結果)
#   終了時に obj/boot.o と sw682.o を消し、m11_build.sh で既定 build を作り直す (trap で必ず復元)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
MODE=${1:?off|on}; OUT=${2:?out_dir}
case "$MODE" in off) GATE=0;; on) GATE=1;; *) echo "mode off|on"; exit 2;; esac
mkdir -p "$OUT"
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -I."
restore() { rm -f work/obj/sw682.o work/obj/boot.o; touch work/boot_final3.ll; M11_OV_413060=0 M11_INSTR_413060=0 M11_DEST_READ=1 bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT

cat > "$OUT/run_2118.mjs" <<'EOF'
import fs from 'fs';
const M11 = process.env.M11_DIR;
const units = process.argv[2].split(',').map(Number);
const m2 = await import(M11 + '/work/m11_boot.cjs');
const lines = [];
const mod = await m2.default({ printErr: (s) => { lines.push(String(s)); } });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
for (const u of units) {
  lines.push('unit ' + u);
  try { const r = mod._m11_call_unit(u); lines.push('RES ' + u + ' ' + (r === 1 ? 'ok' : r === 0 ? 'noproc' : 'miss:' + r)); }
  catch (e) { mod.__emscripten_stack_restore(sp0); lines.push('RES ' + u + ' trap:' + String((e && e.message) || e).split('\n')[0]); }
}
fs.writeFileSync(process.env.OUT_LOG, lines.filter((s) => s.startsWith('[rw]') || s.startsWith('[d413060]') || s.startsWith('unit ') || s.startsWith('RES ')).join('\n') + '\n');
EOF

# clean build (計装なし): unit 0,1,158 の結果と、dest 値 (M11_PRINT_DEST_2118=1 で [d413060] を出す。probe 無しなので trap しない)
M11_OV_413060=$GATE M11_INSTR_413060=0 M11_DEST_READ=1 bash m11_build.sh > "$OUT/build_clean_$MODE.log" 2>&1 || { tail -5 "$OUT/build_clean_$MODE.log"; exit 1; }
M11_DIR="$HERE" OUT_LOG="$OUT/${MODE}_clean.txt" node "$OUT/run_2118.mjs" 0,1,158 > /dev/null 2>&1; echo "[watch_2118] clean $MODE rc=$?"
# dest 観測の build (probe 無し・[d413060] のみ・M11_PRINT_DEST_2118=1)。trap せず j=12 まで届く
M11_PRINT_DEST_2118=1 M11_OV_413060=$GATE M11_INSTR_413060=0 M11_DEST_READ=1 bash m11_build.sh > "$OUT/build_dest_$MODE.log" 2>&1 || { tail -5 "$OUT/build_dest_$MODE.log"; exit 1; }
M11_DIR="$HERE" OUT_LOG="$OUT/${MODE}_dest.txt" node "$OUT/run_2118.mjs" 0,1,158 > /dev/null 2>&1; echo "[watch_2118] dest $MODE rc=$?"
cat "$OUT/${MODE}_clean.txt" 2>/dev/null | grep '^RES'

# watch build: 全 store に m11_sw を入れ、2 区間の書込みを site 単位で出す
rm -rf work/probe2118 && mkdir -p work/probe2118
python3 trap_triage/watch_store_682.py --out work/probe2118 || exit 1
emcc -c work/probe2118/boot_sw.ll -o work/obj/boot.o $CF || exit 1
emcc -c trap_triage/watch_range_2118.c -o work/obj/sw682.o $CF || exit 1
M11_KEEP_BOOT_O=1 M11_OV_413060=$GATE M11_INSTR_413060=1 M11_DEST_READ=1 bash m11_build.sh > "$OUT/build_watch_$MODE.log" 2>&1 || { tail -5 "$OUT/build_watch_$MODE.log"; exit 1; }
M11_DIR="$HERE" OUT_LOG="$OUT/${MODE}_watch.log" node "$OUT/run_2118.mjs" 0,1,158 > /dev/null 2>&1; echo "[watch_2118] watch $MODE rc=$?"
grep -c '^\[rw\]' "$OUT/${MODE}_watch.log" | sed 's/^/[rw] lines: /'
echo "[watch_2118] done $MODE"
