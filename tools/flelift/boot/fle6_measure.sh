#!/usr/bin/env bash
# fle6_measure.sh — FLE-6: dsp_ippv2 ローダ shim 後に 0x6a7b70 を root 化して unit 進行を実測する
# 最小経路 (boot_e2e.sh の 4 variant clang を 1 variant=plain に絞った版)。
#
#   bash tools/flelift/boot/fle6_measure.sh            # gen → lift → plain clang → boot → ネガコン
#
# 工程: gen_boot (phase A) → x64c lift (closure 2) → fle_data_gen → gen_boot (phase B: imp bridge)
#       → build.sh plain (lifted C の clang -O0 1 本) → boot 実行 (--boot-only)
#       → ネガコン FLE_IPP=0 (dsp_ippv2 shim 無効) で同じ boot を再実行。
# 前提: FL_WIN64_DIR (fl-win64 展開先) / python3 (capstone, pefile) / /opt/emsdk (emcc 6.0.12) / node。
# 出力: results/boot_summary_fle6.json (shim 有), results/boot_summary_fle6_negctl.json (shim 無)。
# 生成物は work/boot/ (gitignore)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
W="$FLE/work/boot"
LIFT="$W/lift"
PE="${FLE_PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
export TMPDIR="$W/tmp"
mkdir -p "$W/tmp" "$W/obj" "$HERE/results"
set +u; source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1; set -u
NODE="$(command -v node)"

stage() { echo "[fle6] $1 start $(date -u +%H:%M:%S) load=$(cut -d' ' -f1-3 /proc/loadavg)"; }
elapsed() { echo "[fle6] $1 done in $(( $(date +%s) - $2 ))s load=$(cut -d' ' -f1-3 /proc/loadavg)"; }

T=$(date +%s); stage "gen-A"
python3 "$HERE/gen_boot.py" --pe "$PE" --out "$W" > /dev/null
elapsed "gen-A" "$T"

T=$(date +%s); stage "lift"
python3 "$FLE/x64c.py" --pe "$PE" --entries "$W/fle_entries_boot.json" --out "$LIFT" --closure "${FLE_LIFT_CLOSURE:-2}" \
  --img 0x400000 --shift 0 --img-size 0x18c0000 --impbase 0x1D80000 \
  --override 0x4126f0=fle_ov_longjmp --override 0x409410=fle_ov_getmem \
  --override 0x409440=fle_ov_freemem --override 0x4120c0=fle_ov_initunits | tail -3
python3 "$FLE/fle_data_gen.py" "$PE" "$LIFT/fle_data.c" "$LIFT/lift_meta.json" > /dev/null
python3 "$HERE/gen_boot.py" --pe "$PE" --meta "$LIFT/lift_meta.json" --out "$W" > /dev/null
elapsed "lift" "$T"

T=$(date +%s); stage "clang-plain"
bash "$HERE/build.sh" plain
elapsed "clang-plain" "$T"

T=$(date +%s); stage "boot"
FLE_BOOT_VARIANT=plain "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_plain.cjs" "$HERE/results/boot_summary_fle6.json" --boot-only > "$W/run_fle6.log" 2>&1 || true
grep 'FLEBOOT_RESULT' "$W/run_fle6.log" || true
elapsed "boot" "$T"

T=$(date +%s); stage "negctl (FLE_IPP=0)"
FLE_IPP=0 FLE_BOOT_VARIANT=plain "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_plain.cjs" "$HERE/results/boot_summary_fle6_negctl.json" --boot-only > "$W/run_fle6_negctl.log" 2>&1 || true
grep 'FLEBOOT_RESULT' "$W/run_fle6_negctl.log" || true
elapsed "negctl" "$T"
echo "[fle6] end $(date -u +%H:%M:%S)"
