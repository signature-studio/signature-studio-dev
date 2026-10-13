#!/usr/bin/env bash
# engine / 別 DLL 全 .pdata 関数を RetDec+pass 鎖で lift → emcc -c (到達性のみ; 正しさは別)
#   bash tools/plugins/distortion/engine_lift.sh <block> [timeout_sec]      例: 18973 (Effector engine) / 19101 (Hardcore)
# 出力: work/distortion/engine<block>/ と 1 行サマリ
#   block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,f80_funcs_pre,emcc_c_rc_pre_f80,lift_s,
#   missing_define,missing_bytes,missing_ref,extra_inside,function_defines  (後半 5 列は engine_defs.py)
# lift は共有鎖 (lift/lift_ranges.sh) に PLUG_F80_LOWER=1 (x86_fp80 → f64, p0c/f80_lower.py) を付けて通す。
#   final.ll = f80 lowering 後 (f80_funcs / emcc_c_rc はこちら)、e.pre_f80.ll = lowering 前 (f80_funcs_pre / emcc_c_rc_pre_f80)。
#   lowering 前は wasm backend が fp80 を legalize できず emcc -c が落ちる (記録のため両方測る)。
# PLUG_REUSE_DRC=1 を渡すと RetDec を再実行せず既存の e.drc.ll から pass 鎖だけを再開する (pass 修復の再検証用。 判定の本番では使わない)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B="$1"; TMO="${2:-1200}"
OUT="work/distortion/engine$B"; mkdir -p "$OUT/tmp"
python3 distortion/engine_ranges.py "$B" > "$OUT/ranges.txt" 2> "$OUT/ranges.info"
t0=$(date +%s)
PLUG_F80_LOWER=1 bash lift/lift_ranges.sh "$FL_WIN64_DIR/extracted/block$(printf %05d "$B")_PE.bin" "$OUT/ranges.txt" "$OUT" e "$TMO" > "$OUT/lift.log" 2>&1
rc=$?
t1=$(date +%s)
DEF=$(grep -c '^define' "$OUT/e.final.ll" 2>/dev/null || echo 0)
UNI=$(grep -o 'unimplemented [0-9]*' "$OUT/e.simd.log" 2>/dev/null | awk '{print $2}' | head -1)
f80_count() {
  python3 - "$1" <<'PY'
import re, sys
try:
    s = open(sys.argv[1]).read()
except Exception:
    print(-1); sys.exit()
print(sum(1 for f in re.split(r'\n(?=define )', s) if f.startswith('define') and 'x86_fp80' in f))
PY
}
F80=$(f80_count "$OUT/e.final.ll")
F80PRE=$(f80_count "$OUT/e.pre_f80.ll")
erc=-1; erc2=-1
emcc_c() { ( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; TMPDIR="$OUT/tmp" emcc -c "$1" -o "$OUT/e.o" -w -O0 -msimd128 > "$2" 2>&1 ); echo $?; }
if [ -f "$OUT/e.final.ll" ]; then
  erc=$(emcc_c "$OUT/e.final.ll" "$OUT/emcc.log")
  # f80 lowering 前の IR も測る (clang は最初のエラーで止まるので first_errors.txt に最初の 1 件を残す)
  if [ -f "$OUT/e.pre_f80.ll" ]; then erc2=$(emcc_c "$OUT/e.pre_f80.ll" "$OUT/emcc_pre_f80.log"); fi
  { echo "[final.ll]"; grep -m1 'error' "$OUT/emcc.log" || true; echo "[pre_f80.ll]"; grep -m1 'error' "$OUT/emcc_pre_f80.log" || true; } > "$OUT/first_errors.txt"
fi
DEFS=$(python3 distortion/engine_defs.py "$OUT" 2>/dev/null || echo "-1,-1,-1,-1,-1")
echo "$B,$(cut -d' ' -f1 "$OUT/ranges.info"),$rc,$DEF,$F80,${UNI:--1},$erc,$F80PRE,$erc2,$((t1-t0)),$DEFS" | tee "$OUT/summary.csv"
