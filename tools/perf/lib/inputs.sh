#!/usr/bin/env bash
# 読取専用の既存 tools/m* 成果物を work/inputs/ へコピーする (原本は改変しない)。
# 無ければ生成元の e2e/build を案内して非0終了する。
set -euo pipefail
PERF="$(cd -- "$(dirname -- "$0")/.." && pwd)"
T="$PERF/.."
IN="$PERF/work/inputs"
mkdir -p "$IN/ott" "$IN/m5" "$IN/m3" "$IN/m11" "$IN/shim"

need() { [ -f "$1" ] || { echo "[inputs] 無い: $1  → $2" >&2; exit 2; }; }

# --- OTT (M10 最終 IR + 付随 C ソース。m10_build.sh と同一構成) ---
need "$T/m10/work/ott_m10.ll" "bash tools/m10/m10_build.sh"
for f in "$T/m10/work/ott_m10.ll" "$T/m6/msimd6.c" "$T/m6/msimd6_core.h" "$T/m6/m6_types.h" \
         "$T/m6/m6_rt.c" "$T/m6/work/m6_stubs.c" "$T/m6/work/m6_data.c" \
         "$T/m6/work/m6_stubs_hand.c" "$T/m6/work/m6_stubs_hand2.c" \
         "$T/m8/m8_rt.c" "$T/m9/m9_rt.c" "$T/m10/m10_boot.c"; do
  need "$f" "bash tools/m10/m10_build.sh"; cp -u "$f" "$IN/ott/"
done
cp -u "$T/m6/m6_types.h" "$IN/"
cp -u "$T/shim/src/"*.c "$T/shim/src/"*.h "$IN/shim/"
# --- M5 純計算 (waveshaper / distortion) ---
for f in "$T/m5/work/m5_a1.ll" "$T/m5/work/m5_a2.ll" "$T/m5/msimd.c" "$T/m5/msimd_a1.c" "$T/m5/msimd_a2.c" "$T/m5/work/a2g.c" "$T/m5/msimd_core.h"; do
  [ -f "$f" ] && cp -u "$f" "$IN/m5/" || echo "[inputs] (任意) 無し: $f" >&2
done
# --- M3 (FLAC crc 4 関数) ---
cp -u "$T/m3/work/m3_sel4.ll" "$IN/m3/" 2>/dev/null || true
cp -u "$T/m3/work/m3_sel4.wasm" "$IN/m3/" 2>/dev/null || true
# --- M11 (boot closure: 5.65MB wasm と IR/スタブ) ---
for f in boot_final2.ll m11_fwd.c m11_winstubs.c m11_fnstubs.c m11_data.c boot_ranges.txt boot_fns.json; do
  [ -f "$T/m11/work/$f" ] && cp -u "$T/m11/work/$f" "$IN/m11/" || echo "[inputs] (任意) 無し: m11/work/$f" >&2
done
for f in msimd11.c msimd11_core.h m11_rt.c; do cp -u "$T/m11/$f" "$IN/m11/" 2>/dev/null || true; done
cp -u "$T/m11/msimd11_core.h" "$IN/" 2>/dev/null || true   # m11_fwd.c が ../msimd11_core.h を include
[ -f "$T/m11/work/m11_boot.cjs.wasm" ] && cp -u "$T/m11/work/m11_boot.cjs.wasm" "$IN/m11/m11_boot.wasm"
echo "[inputs] OK → $IN"
