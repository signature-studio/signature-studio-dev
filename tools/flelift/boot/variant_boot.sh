#!/usr/bin/env bash
# variant_boot.sh — PERF-P14 (#970): boot closure の variant 別 実行時間と出力署名。
#   bash tools/flelift/boot/variant_boot.sh plain o2 o2lto
# 前提: build.sh で $W/fleboot_<label>.cjs を作成済み (plain = fle6_measure.sh の -O0, o2 / o2lto = FLE_CC_OPT・FLE_LABEL 付き)。
# 各 label の boot を N 回 (FLE_BOOT_N, 既定 3) 実行し、node の壁時計秒・FLEBOOT_RESULT・IPP 判定・署名を
# $W/variant/summary.tsv に追記する。FLE_IPP=1 (shim 有 = fle6_measure.sh と同じ経路)。判定 NG (rc=3) は記録して続行する。
# 署名 = boot と ipp を JSON 正規化して sha256 の先頭 16 桁 (同一なら変種間で boot の出力が一致)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
W="${FLE_BOOT_WORK:-$FLE/work/boot}"
NODE="$(command -v node)"
N="${FLE_BOOT_N:-3}"
OUT="$W/variant"
mkdir -p "$OUT"
TSV="$OUT/summary.tsv"
[ -f "$TSV" ] || printf 'label\twasm_bytes\trun\twall_sec\trc\tFLEBOOT_RESULT\tipp_check\tsignature\n' > "$TSV"
for L in "$@"; do
  CJS="$W/fleboot_$L.cjs"
  [ -f "$CJS" ] || { echo "[variant] missing $CJS"; exit 2; }
  WASM_B=$(stat -c%s "$CJS.wasm")
  for i in $(seq 1 "$N"); do
    J="$OUT/boot_${L}_r$i.json"; LOG="$OUT/run_${L}_r$i.log"; rc=0
    T=$(date +%s.%N)
    FLE_IPP=1 FLE_BOOT_VARIANT="$L" "$NODE" "$HERE/fle_boot.mjs" "$CJS" "$J" --boot-only > "$LOG" 2>&1 || rc=$?
    SEC=$(echo "$(date +%s.%N) - $T" | bc)
    RES=$(grep '^FLEBOOT_RESULT' "$LOG" | cut -d' ' -f2- || true)
    IPP=$(grep '^FLEBOOT_IPP_CHECK' "$LOG" | grep -o '"ok":[a-z]*' || echo none)
    SIG=$(python3 -c 'import json,hashlib,sys; d=json.load(open(sys.argv[1])); print(hashlib.sha256(json.dumps({"boot":d["boot"],"ipp":d["ipp"]},sort_keys=True).encode()).hexdigest()[:16])' "$J")
    printf '%s\t%s\t%s\t%.1f\t%s\t%s\t%s\t%s\n' "$L" "$WASM_B" "$i" "$SEC" "$rc" "$RES" "$IPP" "$SIG" | tee -a "$TSV"
  done
done
