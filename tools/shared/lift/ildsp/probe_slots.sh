#!/usr/bin/env bash
# CreateInstance → vtable の slot 0–5 を全部呼ぶ版を、元の機械語 (native) だけで実行し、落ちる case を数える (T-SH-52 / #3216 の REPORT_APPENDIX_3216.md §7-5)。
# wasm も emcc も使わない。生成物は work/ (gitignore)。
# usage: FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/ildsp/probe_slots.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$HERE/../.."
source "$ROOT/env.sh"
DLL="${ILDSP_DLL:-$FL_WIN64_DIR/extracted/block24360_PE.bin}"
[ -f "$DLL" ] || { echo "[probe-slots] DLL not found: $DLL"; exit 2; }
W="$ROOT/work/lift/ildsp-probe-slots"; rm -rf "$W"; mkdir -p "$W"
WC_CALL_SLOTS=6 python3 "$HERE/wc_image.py" "$DLL" "$W"
python3 "$HERE/wc_cases.py" "$W" "${WC_CASES:-64}"
gcc -O1 -w -I "$W" -o "$W/native_ref" "$HERE/wc_native_ref.c"
set +e; timeout 300 "$W/native_ref" "$W/image_native.bin" "$W/cases.bin" "$W/res_native.bin" 2> "$W/native.log"; RC=$?; set -e
cat "$W/native.log"
echo "[probe-slots] native rc=$RC crashed_cases=$(grep -c '\[native\] crash' "$W/native.log" || true) (slot 0-5 全呼出)"
