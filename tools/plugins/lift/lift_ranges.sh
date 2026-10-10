#!/usr/bin/env bash
# プラグイン 1 PE の選択関数群を lift する汎用ドライバ (tools/m6_lift.sh / m11_lift.sh を一般化)
#   RetDec --select-ranges --select-decode-only → ir_normalize → ir5_patch → fix_regparam_alloca(新規) → fix_asm_stores(新規) → fix_orcond_xnor(opt-in) → fix_dup_decls(新規) → fix_ptr_params(新規) → m11_asmfix → m11_passes (global→linear VA) → m11_simd2 (__asm_* helper C 生成)
#
# 使い方: bash lift_ranges.sh <PE> <ranges(file|"0xA-0xB,...")> <outdir> <name> [timeout_sec]
#   例: bash lift_ranges.sh /.../block18983_PE.bin ranges.txt work/balance bal
# 出力: <outdir>/<name>.drc.ll, .norm0.ll, .lift.ll, .final.ll, <name>_simd.c と各 .report.json
# 環境変数: PLUG_IMG_HI (対象 PE の ImageBase+SizeOfImage; 省略時は PE から自動算出)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
P="$HERE/passes"
PE="$1"; RANGES="$2"; OUT="$3"; NAME="$4"; TMO="${5:-1800}"
mkdir -p "$OUT/tmp"
export TMPDIR="$OUT/tmp"
if [ -f "$RANGES" ]; then RANGES="$(cat "$RANGES")"; fi
NFN="$(echo "$RANGES" | tr ',' '\n' | wc -l)"
if [ -z "${PLUG_IMG_HI:-}" ]; then
  PLUG_IMG_HI="$(python3 - "$PE" <<'PY'
import sys, pefile
pe = pefile.PE(sys.argv[1], fast_load=True)
print(hex(pe.OPTIONAL_HEADER.ImageBase + pe.OPTIONAL_HEADER.SizeOfImage))
PY
)"
fi
export PLUG_IMG_HI
echo "[lift] $NAME: ranges=$NFN imghi=$PLUG_IMG_HI timeout=$TMO"
/opt/retdec/bin/retdec-decompiler "$PE" -o "$OUT/$NAME.drc.c" \
  --select-ranges "$RANGES" --select-decode-only --timeout "$TMO" > "$OUT/$NAME.retdec.log" 2>&1
[ -f "$OUT/$NAME.drc.ll" ] || { echo "[lift] FAIL: RetDec 出力なし" >&2; tail -20 "$OUT/$NAME.retdec.log"; exit 1; }
python3 "$P/ir_normalize.py" "$OUT/$NAME.drc.ll" "$OUT/$NAME.norm0.ll"
python3 "$P/ir5_patch.py" "$OUT/$NAME.norm0.ll" "$OUT/$NAME.lift.ll" --report "$OUT/$NAME.ir5.json" 2>&1 | tail -3
python3 "$P/fix_regparam_alloca.py" "$OUT/$NAME.lift.ll" "$OUT/$NAME.rp.ll" --report "$OUT/$NAME.rp.json"
python3 "$P/fix_asm_stores.py" "$OUT/$NAME.rp.ll" "$OUT/$NAME.st.ll"
# opt-in: 差分試験で検出した RetDec or.cond XNOR 化の修復 (PLUG_ORCOND_FUNCS="function_5dee90 ...")
OC_ARGS=""
for f in ${PLUG_ORCOND_FUNCS:-}; do OC_ARGS="$OC_ARGS --func $f"; done
python3 "$P/fix_orcond_xnor.py" "$OUT/$NAME.st.ll" "$OUT/$NAME.oc.ll" $OC_ARGS
python3 "$P/fix_dup_decls.py" "$OUT/$NAME.oc.ll" "$OUT/$NAME.dd.ll"
python3 "$P/fix_ptr_params.py" "$OUT/$NAME.dd.ll" "$OUT/$NAME.pp.ll"
python3 "$P/m11_asmfix.py" "$OUT/$NAME.pp.ll" "$OUT/$NAME.asmfix.ll"
python3 "$P/m11_passes.py" "$OUT/$NAME.asmfix.ll" "$OUT/$NAME.final.ll" --report "$OUT/$NAME.passes.json"
python3 "$P/m11_simd2.py" "$OUT/$NAME.final.ll" 2> "$OUT/$NAME.simd.log" | sed 's#"\.\./msimd11_core\.h"#"msimd11_core.h"#' > "$OUT/${NAME}_simd.c"
echo "[lift] OK: $OUT/$NAME.final.ll ($(wc -l < "$OUT/$NAME.final.ll") lines), $(grep -c '^define' "$OUT/$NAME.final.ll") defines, helpers: $(tail -3 "$OUT/$NAME.simd.log" | tr '\n' ' ')"
