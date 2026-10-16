#!/usr/bin/env bash
# engine 分離型 2 本 (T3: Delay 3 / Multiband Delay) の C++ engine DLL 全 .pdata 関数を RetDec+pass 鎖で lift → emcc -c (到達性のみ; 正しさは別)
#   bash tools/plugins/reverb_delay/engine_lift.sh <block> [timeout_sec]      例: 19000 (Delay 3 engine) / 19165 (Multiband Delay engine)
# 従来鎖 (PLUG_ICALL=0 を明示) で lift する。 f80 は PLUG_F80_LOWER=1 (x86_fp80 → f64、精度は 53 bit に下がる。 REPORT_APPENDIX.md §19) を既定とする。
# 出力: work/reverb_delay/engine<block>/ と 1 行サマリ (block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,
#   missing_define,missing_bytes,missing_ref,extra_inside,function_defines  ← engine_defs.py)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B="$1"; TMO="${2:-1200}"
# 環境変数 ENGINE_RANGE_ARGS (例: "--exclude IPPCODE") と ENGINE_TAG (出力 dir 接尾辞) で対象 section を絞れる
OUT="work/reverb_delay/engine$B${ENGINE_TAG:-}"; mkdir -p "$OUT/tmp"
python3 reverb_delay/engine_ranges.py "$B" ${ENGINE_RANGE_ARGS:-} > "$OUT/ranges.txt" 2> "$OUT/ranges.info"
t0=$(date +%s)
PLUG_ICALL=0 PLUG_F80_LOWER=${PLUG_F80_LOWER:-1} bash lift/lift_ranges.sh "$FL_WIN64_DIR/extracted/block$(printf %05d "$B")_PE.bin" "$OUT/ranges.txt" "$OUT" e "$TMO" > "$OUT/lift.log" 2>&1
rc=$?
t1=$(date +%s)
DEF=$(grep -c '^define' "$OUT/e.final.ll" 2>/dev/null || echo 0)
UNI=$(grep -o 'unimplemented [0-9]*' "$OUT/e.simd.log" 2>/dev/null | awk '{print $2}' | head -1)
F80=$(python3 - "$OUT/e.final.ll" <<'PY'
import re, sys
try:
    s = open(sys.argv[1]).read()
except Exception:
    print(-1); sys.exit()
print(sum(1 for f in re.split(r'\n(?=define )', s) if f.startswith('define') and 'x86_fp80' in f))
PY
)
erc=-1; erc2=-1; NP=0
emcc_c() { ( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; TMPDIR="$OUT/tmp" emcc -c "$1" -o "$OUT/e.o" -w -O0 -msimd128 > "$2" 2>&1 ); echo $?; }
if [ -f "$OUT/e.final.ll" ]; then
  erc=$(emcc_c "$OUT/e.final.ll" "$OUT/emcc.log")
  # engine-local 修復 (icmp ptr/i64 型不整合) を当てた後の再試行。 clang は最初の型エラーで止まるため、次に露見する欠陥類型を記録する
  NP=$(python3 reverb_delay/engine_fixcmp.py "$OUT/e.final.ll" "$OUT/e.fixcmp.ll" 2>&1 | sed 's/.*= //')
  erc2=$(emcc_c "$OUT/e.fixcmp.ll" "$OUT/emcc_fixcmp.log")
  { echo "[final.ll]"; grep -m1 'error' "$OUT/emcc.log" || true; echo "[fixcmp.ll]"; grep -m1 'error' "$OUT/emcc_fixcmp.log" || true; } > "$OUT/first_errors.txt"
fi
DEFS=$(python3 reverb_delay/engine_defs.py "$OUT" 2>/dev/null || echo "-1,-1,-1,-1,-1")
echo "$B,$(cut -d' ' -f1 "$OUT/ranges.info"),$rc,$DEF,$F80,${UNI:--1},$erc,$NP,$erc2,$((t1-t0)),$DEFS" | tee "$OUT/summary.csv"
