#!/usr/bin/env bash
# PLG-G2-1 (#533) Gen_Render 差分 harness (12 shell)。
#   bash tools/plugins/synth/gr/gr_e2e.sh [--wasm-dir <dir>] [--ulp N]
# 手順: 12 shell の Gen_Render VA / instance size を実測 → native_gen (DLL を VA 敷設して ms_abi 実行) で固定 case 列を実行
#       → gr_judge.py で wasm 結果 (<wasm-dir>/<block>.bin) と bit 比較。
# exit 0 は 12 本すべて PASS のときだけ。 native が基準にならない (中断・空出力) / wasm 結果なし / 差分ありは全て exit 1。
# 素材: fl-win64 のみ (native 側)。 wasm 側 (P0a/P0b/P0c 完了後の Gen_Render 実行体) は本 repo に未存在 → 既定では MISSING になる。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../env.sh"
WORK="$HERE/../../work/synth_gr"; mkdir -p "$WORK/native"
WASM_DIR="$WORK/wasm"; ULP=0
while [ $# -gt 0 ]; do
  case "$1" in --wasm-dir) WASM_DIR="$2"; shift 2;; --ulp) ULP="$2"; shift 2;; *) echo "unknown: $1" >&2; exit 2;; esac
done
mkdir -p "$WASM_DIR"
gcc -O1 -o "$WORK/native_gen" "$HERE/native_gen.c"
python3 "$HERE/gr_targets.py" > "$WORK/targets.tsv"
python3 -c "
import sys; sys.path.insert(0,'$HERE'); import gr_lib as L
L.write_cases('$WORK/cases.bin', L.make_cases())"
while IFS=$'\t' read -r blk name va isz; do
  # native が中断しても (SIGSEGV は結果に記録される) 次へ進む。 判定は gr_judge が行う
  "$WORK/native_gen" "$FL_WIN64_DIR/extracted/block${blk}_PE.bin" "$va" "$isz" "$WORK/cases.bin" "$WORK/native/$blk.bin" \
    || { echo "[gr_e2e] native_gen rc=$? ($blk $name)" >&2; rm -f "$WORK/native/$blk.bin"; }
done < "$WORK/targets.tsv"
python3 "$HERE/gr_judge.py" "$WORK/native" "$WASM_DIR" "$WORK/targets.tsv" --ulp "$ULP"
