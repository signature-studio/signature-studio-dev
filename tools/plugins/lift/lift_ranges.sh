#!/usr/bin/env bash
# プラグイン 1 PE の選択関数群を lift する汎用ドライバ (tools/m6_lift.sh / m11_lift.sh を一般化)
#   RetDec --select-ranges --select-decode-only → ir_normalize → ir5_patch → fix_regparam_alloca(新規) → fix_asm_stores(新規) → fix_orcond_xnor(opt-in) → fix_dup_decls(新規) → fix_ptr_params(新規) → m11_asmfix → m11_passes (global→linear VA) → m11_simd2 (__asm_* helper C 生成)
#
# 使い方: bash lift_ranges.sh <PE> <ranges(file|"0xA-0xB,...")> <outdir> <name> [timeout_sec]
#   例: bash lift_ranges.sh /.../block18983_PE.bin ranges.txt work/balance bal
# 出力: <outdir>/<name>.drc.ll, .norm0.ll, .lift.ll, .final.ll, <name>_simd.c と各 .report.json
# 環境変数: PLUG_IMG_HI (対象 PE の ImageBase+SizeOfImage; 省略時は PE から自動算出)
#           PLUG_ICALL=1 (既定 0; batch_lift.sh は既定 1): RetDec の前に tools/icall/icall_rewrite.py で PE を decode 専用に書換え (間接 call/jmp → memory-ABI + 共有 stub)、
#             RetDec の後に ir_icall_restore.py で stub 呼出し → `call void @__icall_dispatch(i64 <元 site VA>)` へ戻す。RetDec は間接 call を decoder 段で捨てる ((icall §4) D1)。
#             追加出力: <name>.icall.dll / .icall.map.json / .icall.restore.json / .drc.restored.ll。 runtime (BLK, __icall_dispatch) は tools/icall/rt/icall_rt.c 側
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
DEC_PE="$PE"; DEC_RANGES="$RANGES"; DRC_LL="$OUT/$NAME.drc.ll"
if [ "${PLUG_ICALL:-0}" = "1" ]; then
  IC="$HERE/../../icall"
  echo "$RANGES" > "$OUT/$NAME.icall.funcs"
  python3 "$IC/icall_rewrite.py" --pe "$PE" --funcs "$OUT/$NAME.icall.funcs" --out "$OUT/$NAME.icall.dll" --map "$OUT/$NAME.icall.map.json" > "$OUT/$NAME.icall.rewrite.txt"
  DEC_PE="$OUT/$NAME.icall.dll"
  DEC_RANGES="$(python3 - "$OUT/$NAME.icall.map.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print(open(sys.argv[1] + '.ranges').read() + ',0x%x-0x%x,0x%x-0x%x' % (m['stub'], m['stub'] + m.get('stub_len', 78), m['comis_stub'], m['comis_stub'] + m.get('comis_stub_len', 29)))
PY
)"
  echo "[lift] icall: $(cat "$OUT/$NAME.icall.rewrite.txt")"
fi
/opt/retdec/bin/retdec-decompiler "$DEC_PE" -o "$OUT/$NAME.drc.c" \
  --select-ranges "$DEC_RANGES" --select-decode-only --timeout "$TMO" > "$OUT/$NAME.retdec.log" 2>&1
[ -f "$OUT/$NAME.drc.ll" ] || { echo "[lift] FAIL: RetDec 出力なし" >&2; tail -20 "$OUT/$NAME.retdec.log"; exit 1; }
if [ "${PLUG_ICALL:-0}" = "1" ]; then
  python3 "$IC/ir_icall_restore.py" --ir "$OUT/$NAME.drc.ll" --map "$OUT/$NAME.icall.map.json" --out "$OUT/$NAME.drc.restored.ll" --report "$OUT/$NAME.icall.restore.json" > /dev/null
  DRC_LL="$OUT/$NAME.drc.restored.ll"
fi
python3 "$P/ir_normalize.py" "$DRC_LL" "$OUT/$NAME.norm0.ll"
python3 "$P/ir5_patch.py" "$OUT/$NAME.norm0.ll" "$OUT/$NAME.lift.ll" --report "$OUT/$NAME.ir5.json" 2>&1 | tail -3
python3 "$P/fix_regparam_alloca.py" "$OUT/$NAME.lift.ll" "$OUT/$NAME.rp.ll" --report "$OUT/$NAME.rp.json"
python3 "$P/fix_asm_stores.py" "$OUT/$NAME.rp.ll" "$OUT/$NAME.st.ll"
# opt-in: 差分試験で検出した RetDec or.cond XNOR 化の修復 (PLUG_ORCOND_FUNCS="function_5dee90 ...")
OC_ARGS=""
for f in ${PLUG_ORCOND_FUNCS:-}; do OC_ARGS="$OC_ARGS --func $f"; done
python3 "$P/fix_orcond_xnor.py" "$OUT/$NAME.st.ll" "$OUT/$NAME.oc.ll" $OC_ARGS
python3 "$P/fix_dup_decls.py" "$OUT/$NAME.oc.ll" "$OUT/$NAME.dd.ll"
python3 "$P/fix_ptr_params.py" "$OUT/$NAME.dd.ll" "$OUT/$NAME.pp.ll"
# opt-in (PLUG_XMMARG=1): 機械語が xmm0..3 を入力に読むのに IR 署名に無い関数へ float/double 引数を復元 ((DEFECTS.md) D5, PLG-F2-4 #547)
AF_IN="$OUT/$NAME.pp.ll"
if [ "${PLUG_XMMARG:-0}" = "1" ]; then
  python3 "$P/fix_xmm_args.py" "$OUT/$NAME.pp.ll" "$OUT/$NAME.xa.ll" --pe "$PE" --report "$OUT/$NAME.xa.json"
  AF_IN="$OUT/$NAME.xa.ll"
fi
python3 "$P/m11_asmfix.py" "$AF_IN" "$OUT/$NAME.asmfix.ll"
python3 "$P/m11_passes.py" "$OUT/$NAME.asmfix.ll" "$OUT/$NAME.final.ll" --report "$OUT/$NAME.passes.json"
python3 "$P/m11_simd2.py" "$OUT/$NAME.final.ll" 2> "$OUT/$NAME.simd.log" | sed 's#"\.\./msimd11_core\.h"#"msimd11_core.h"#' > "$OUT/${NAME}_simd.c"
echo "[lift] OK: $OUT/$NAME.final.ll ($(wc -l < "$OUT/$NAME.final.ll") lines), $(grep -c '^define' "$OUT/$NAME.final.ll") defines, helpers: $(tail -3 "$OUT/$NAME.simd.log" | tr '\n' ' ')"
