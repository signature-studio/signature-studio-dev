#!/usr/bin/env bash
# run_chainmap.sh — FA-4: FRAR/DUMP チェーン構成 + マクロ→子パラメタ ID 写像を native(実機機械語) 上で実測し .epf 8 本と突合する。
#   native_ctrl を FA_MAP_TRACE=1 で実行 (0x180c9d700 を観測フックに差替え) → fa4_chain_map.py で検証。
#   事前に build_ctrl.sh (または lift2_e2e.sh) で work/ctrl を生成しておくこと (iat_slots.txt / pokes.txt / ctrl_scen.txt)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
EPF="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/FACTORY Presets/Factory Bank"
W="$HERE/work/ctrl"; { [ -x "$W/native_ctrl" ] && [ -f "$W/ctrl_full.cjs" ] && [ -f "$W/iat_slots.txt" ]; } || bash "$HERE/build_ctrl.sh" >/dev/null || exit 2
cd "$W"; source "$HERE/env.sh"
python3 "$HERE/gen_ctrl_scen.py" ctrl_scen.txt 2 5 0xFA2C0001 >/dev/null
clang -O1 -ffp-contract=off -frounding-math -w -o native_ctrl_trace "$HERE/native/native_ctrl.c" || exit 2
FA_MAP_TRACE=1 FA_HEAP_ZERO=1 ./native_ctrl_trace "$CORE" ctrl_scen.txt 0 2> maptrace.err > /dev/null
grep MAPTRACE maptrace.err > maptrace.txt
python3 "$HERE/fa4_chain_map.py" "$CORE" "$EPF" maptrace.txt
