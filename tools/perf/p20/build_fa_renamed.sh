#!/usr/bin/env bash
# #4732 (PERF-P27): Fresh Air を OTT と分かれる impbase で再 lift し、関数名・imp_ 名を fa_ prefix にした単独 wasm を作る。
#   usage: bash tools/perf/p20/build_fa_renamed.sh
#   入力: build_fa_gain.sh と同じ (tools/targets/freshair/work/win)。emcc は PATH か EMSDK の emsdk_env.sh。
#   出力: tools/perf/p20/work/fa2/fa.cjs・fa.wasm (gitignore の work/。commit しない)
#   署名: node tools/perf/p20/fa_gain_sig.mjs tools/perf/p20/work/fa2/fa.cjs  (基準 5e5287b5)
#   改名: fle_lifted.c・fle_data.c と rt の複製 (work/fa2/rt) に sed をかける。rt 原本は変えない。
#     f_<va> → fa_f_<va>、ott_dispatch → fa_dispatch、imp_<名> → fa_imp_<名>、IMP_VA_BASE → 0x1F00000 (= --impbase)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd -- "$HERE/../../.." && pwd)"
FLE="$ROOT/tools/flelift"
RT="$FLE/rt"
CORE="$ROOT/tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
OUT="$HERE/work/fa2"
LIFT="$OUT/lift"
RTW="$OUT/rt"
IMP_VA=0x1F00000
IMG=0x180000000
SHIFT=0x17E000000
SIZE=0x2319000
GAIN_VA=0x180afe090
[ -f "$CORE" ] || { echo "[build_fa_renamed] 入力が無い: $CORE (bash tools/targets/freshair/fetch.sh を先に)" >&2; exit 2; }
if ! command -v emcc >/dev/null 2>&1 && [ -n "${EMSDK:-}" ]; then source "$EMSDK/emsdk_env.sh" >/dev/null 2>&1; fi
rm -rf "$OUT"
mkdir -p "$LIFT" "$RTW"
python3 -c "import json,sys; json.dump({'roots': [int(sys.argv[1], 16)]}, open(sys.argv[2], 'w'))" "$GAIN_VA" "$OUT/entries.json"
python3 "$FLE/x64c.py" --pe "$CORE" --entries "$OUT/entries.json" --out "$LIFT" --closure 60 \
  --img "$IMG" --shift "$SHIFT" --img-size "$SIZE" --impbase "$IMP_VA" | tail -c 300
python3 "$FLE/fle_data_gen.py" "$CORE" "$LIFT/fle_data.c" "$LIFT/lift_meta.json" "$SHIFT"
cp -r "$RT"/. "$RTW"/
cp "$LIFT/fle_lifted.c" "$LIFT/fle_data.c" "$RTW"/
sed -i -E \
  -e 's/\bimp_([A-Za-z_])/fa_imp_\1/g' \
  -e 's/\bf_([0-9a-f]{5,9})\b/fa_f_\1/g' \
  -e 's/\bott_dispatch\b/fa_dispatch/g' \
  -e 's/#define IMP_VA_BASE[[:space:]]+0x1D80000ULL/#define IMP_VA_BASE   0x1F00000ULL/' \
  "$RTW"/*.c "$RTW"/*.h "$RTW"/*.inc
grep -q '#define IMP_VA_BASE   0x1F00000ULL' "$RTW/fle_cpu.h" || { echo "[build_fa_renamed] IMP_VA_BASE の置換に失敗" >&2; exit 3; }
# OTT runtime と定義が重なるもの (R/X/flags/ott_*) を改名する。重なりは overlap check で 0 を確かめる。
cat > "$RTW/fa_rename.h" <<'EOF'
#define R fa_R
#define X fa_X
#define fCF fa_fCF
#define fDF fa_fDF
#define fOF fa_fOF
#define fPF fa_fPF
#define fSF fa_fSF
#define fZF fa_fZF
#define ott_badjump fa_ott_badjump
#define ott_missing_import fa_ott_missing_import
#define ott_unlifted fa_ott_unlifted
#define ott_unsup fa_ott_unsup
#define ott_xrip fa_ott_xrip
EOF
RENAME="-include $RTW/fa_rename.h"
emcc -c -O0 -ffp-contract=off -fno-fast-math $RENAME -I "$RTW" "$RTW/fle_lifted.c" -o /dev/null > "$OUT/compile.log" 2>&1
echo "compile: warnings=$(grep -c 'warning:' "$OUT/compile.log") errors=$(grep -c 'error:' "$OUT/compile.log")"
for tu in fle_data.c fle_cpu.c fle_glue.c; do
  emcc -c -O0 -ffp-contract=off -fno-fast-math $RENAME -I "$RTW" "$RTW/$tu" -o "$OUT/${tu%.c}.o" > "$OUT/compile_$tu.log" 2>&1 || { echo "[build_fa_renamed] emcc -c 失敗: $tu" >&2; cat "$OUT/compile_$tu.log" >&2; exit 4; }
done
EXPORTS=_fle_run,_fle_xmm0,_fle_xmm1,_fle_rget,_fle_mget,_fle_set_stackarg,_fle_data_install,_fle_init,_fle_reset,_malloc
emcc -O0 -ffp-contract=off -fno-fast-math $RENAME -I "$RTW" "$RTW/fle_lifted.c" "$RTW/fle_data.c" \
  "$RTW/fle_cpu.c" "$RTW/fle_glue.c" -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) -o "$OUT/fa.cjs" > "$OUT/link.log" 2>&1
ls -la "$OUT/fa.wasm" | awk '{print "wasm bytes:", $5}'
