#!/usr/bin/env bash
# WaveformColouring の vtable slot 1–5 の host 前提を、元の機械語 (native) だけで確かめる (#4169 / T-SH-99)。
# CreateInstance の直後に slot を 1 回だけ呼ぶ (1 プロセス 1 実験)。結果の正本は REPORT_APPENDIX_4169.md。
# usage: FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/ildsp/slot_probe.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$HERE/../.."
source "$ROOT/env.sh"
DLL="${ILDSP_DLL:-$FL_WIN64_DIR/extracted/block24360_PE.bin}"
[ -f "$DLL" ] || { echo "[slot-probe] DLL not found: $DLL"; exit 2; }
W="$ROOT/work/lift/ildsp-slot"; rm -rf "$W"; mkdir -p "$W"
WC_CALL_SLOTS=6 python3 "$HERE/wc_image.py" "$DLL" "$W" >/dev/null
gcc -O1 -w -I "$W" -o "$W/slot_native" "$HERE/slot_native.c"
S="$W/slot_native"; IMG="$W/image_native.bin"
IN=0x30508000; OUT=0x3050C000
run() { local label="$1"; shift; printf '%-44s ' "$label"; set +e; timeout 15 "$S" "$IMG" "$@" 2>&1 | tr '\n' ' '; printf 'rc=%s\n' "${PIPESTATUS[0]}"; set -e; }
echo "# args: K RDX R8 R9 STACK5 (16 進)"
echo "## slot 1 (rdx=入力, r8=出力, r9=frame 数, 5 番目=channel フラグ)"
run "slot1 in out frames=0 flag=0"         1 $IN $OUT 0 0
run "slot1 in out frames=4 flag=0"         1 $IN $OUT 4 0
run "slot1 in out frames=4 flag=1"         1 $IN $OUT 4 1
run "slot1 r8=0 (出力 null)"               1 $IN 0 4 0
run "slot1 rdx=0 (入力 null)"              1 0 $OUT 4 0
run "slot1 rdx=0 frames=0 (入力 null)"     1 0 $OUT 0 0
run "slot1 r8=0 frames=0 (出力 null)"      1 $IN 0 0 0
echo "## slot 4 (rdx=入力, r8=frame 数, r9=channel フラグ, 5 番目=出力)"
run "slot4 in frames=0 flag=0 out"         4 $IN 0 0 $OUT
run "slot4 in frames=4 flag=0 out"         4 $IN 4 0 $OUT
run "slot4 in frames=16 flag=1 out"        4 $IN 16 1 $OUT
run "slot4 out=0 (5 番目 null)"            4 $IN 16 1 0
run "slot4 out=0 frames=0 (5 番目 null)"   4 $IN 0 0 0
run "slot4 rdx=0 frames=4 out"             4 0 4 0 $OUT
run "slot4 rdx=0 frames=0 out"             4 0 0 0 $OUT
echo "## slot 2・3・5 (全引数 0)"
run "slot2 all zero"                       2 0 0 0 0
run "slot3 all zero"                       3 0 0 0 0
run "slot5 all zero"                       5 0 0 0 0
