#!/usr/bin/env bash
# qfc_boot.sh — QuickFontCache_x64.dll の boot 実行 (T-SH-60 / #3289)。
#   lift (qfc_lift.sh = qfc_e2e.sh と同一) → emcc wasm → qfc_boot.mjs で DllMain(PROCESS_ATTACH) → FontCache_GetStats → FontCache_CleanUp。
#   [strict] 実装済み import だけで実行 (rt の stub のみ)。[soft] rt に無い import を soft stub (呼出し記録 + 0 返し) で埋めて実行。
#   PASS = strict で 3 段とも ok かつ DllMain が 1 を返し、soft stub の呼出し 0 件。SOFT = 3 段 ok だが soft stub に当たった。
#   FAIL は止まった段と停止理由を JSON に残す。 exit 0 は PASS のみ。
# 前提: python3 (capstone, pefile), emsdk, node。 FL_WIN64_DIR 必須 (`tar --zstd -xf fl-win64.tar.zst -C <dir>` の <dir>)。
# 出力: work/boot/boot_strict.json, work/boot/boot_soft.json。 InitDll は QuickFontCache の export ではない (VST3 モジュール側。REPORT 参照) ため対象外。
set -euo pipefail
source "$(cd -- "$(dirname -- "$0")" && pwd)/env.sh"
cd "$QFC"
[ -f "$QFC_PE" ] || { echo "[qfc_boot] PE not found: $QFC_PE (FL_WIN64_DIR=$FL_WIN64_DIR)"; exit 2; }
T0=$(date +%s)
echo "load: $(cut -d' ' -f1-3 /proc/loadavg)  nproc: $(nproc)"
mkdir -p work/boot
source "$QFC/qfc_lift.sh"
if [ ! -f work/boot/lift/lift_meta.json ] || [ -n "${QFC_BOOT_REBUILD:-}" ]; then
  echo "== lift + wasm build =="
  lift_build "$QFC/work/boot/lift" ""
fi
python3 gen_soft_imp.py work/boot/lift/lift_meta.json ../flelift/rt work/boot/lift/soft_imp.c qfc_imp.c
wasm_build "$QFC/work/boot/lift" "$QFC/work/boot/lift/qfcl_soft.cjs" "$QFC/work/boot/lift/soft_imp.c" "$QFC/qfc_imp.c"
echo "== boot strict (実装済み import のみ) =="
rc_strict=0
QFC_CJS="$QFC/work/boot/lift/qfcl.cjs" QFC_OUT="$QFC/work/boot/boot_strict.json" node "$QFC/qfc_boot.mjs" || rc_strict=$?
echo "== boot soft (rt に無い import を soft stub で埋める) =="
rc_soft=0
QFC_CJS="$QFC/work/boot/lift/qfcl_soft.cjs" QFC_OUT="$QFC/work/boot/boot_soft.json" node "$QFC/qfc_boot.mjs" || rc_soft=$?
echo "[qfc_boot] strict rc=$rc_strict soft rc=$rc_soft real=$(( $(date +%s) - T0 )) s load: $(cut -d' ' -f1-3 /proc/loadavg)"
[ "$rc_strict" -eq 0 ] && [ "$rc_soft" -eq 0 ] && exit 0
exit 1
