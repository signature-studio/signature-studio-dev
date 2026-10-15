#!/usr/bin/env bash
# プラグイン 1 PE の選択関数群を lift する汎用ドライバ (tools/m6_lift.sh / m11_lift.sh を一般化)
#   RetDec --select-ranges --select-decode-only → ir_normalize → ir5_patch → fix_regparam_alloca(新規) → fix_asm_stores(新規) → fix_orcond_xnor(opt-in) → fix_dup_decls(新規) → fix_ptr_params(新規) → fix_icmp_ptr(新規) → m11_asmfix → m11_passes (global→linear VA) → fix_avx256(新規; ymm/VEX → IR 命令) → vex_comis_flags (#1774; VEX comis の flag 反映) → m11_simd2 (__asm_* helper C 生成)
#
# 使い方: bash lift_ranges.sh <PE> <ranges(file|"0xA-0xB,...")> <outdir> <name> [timeout_sec]
#   例: bash lift_ranges.sh /.../block18983_PE.bin ranges.txt work/balance bal
# 出力: <outdir>/<name>.drc.ll, .norm0.ll, .lift.ll, .final.ll, <name>_simd.c と各 .report.json
# 環境変数: PLUG_IMG_HI (対象 PE の ImageBase+SizeOfImage; 省略時は PE から自動算出)
#           PLUG_REUSE_DRC=1 (既定 0): RetDec を再実行せず、既存の <name>.drc.ll から後段の pass 鎖だけを再開 (pass の修復の検証用)
#           PLUG_NO_STATIC_DETECT (既定 1): RetDec に --disable-static-code-detection を渡す。 既定の静的検出だと定数 libc 系の関数を「statically linked function」として define を出さない (#1486)。 0 で従来 (静的検出あり) に戻す
#           PLUG_F80_LOWER=1 (既定 0): m11_passes の後に p0c/f80_lower.py (x86_fp80 → f64) を適用。 lowering 前は <name>.pre_f80.ll
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
if [ "${PLUG_REUSE_DRC:-0}" = "1" ] && [ -f "$DRC_LL" ]; then
  echo "[lift] PLUG_REUSE_DRC=1: RetDec を再実行せず既存の $DRC_LL から後段を再開"
else
NOSD_ARGS=""
[ "${PLUG_NO_STATIC_DETECT:-1}" = 1 ] && NOSD_ARGS="--disable-static-code-detection"
/opt/retdec/bin/retdec-decompiler "$DEC_PE" -o "$OUT/$NAME.drc.c" \
  --select-ranges "$DEC_RANGES" --select-decode-only $NOSD_ARGS --timeout "$TMO" > "$OUT/$NAME.retdec.log" 2>&1
fi
[ -f "$OUT/$NAME.drc.ll" ] || { echo "[lift] FAIL: RetDec 出力なし" >&2; tail -20 "$OUT/$NAME.retdec.log"; exit 1; }
if [ "${PLUG_ICALL:-0}" = "1" ]; then
  python3 "$IC/ir_icall_restore.py" --ir "$OUT/$NAME.drc.ll" --map "$OUT/$NAME.icall.map.json" --out "$OUT/$NAME.drc.restored.ll" --report "$OUT/$NAME.icall.restore.json" > /dev/null
  DRC_LL="$OUT/$NAME.drc.restored.ll"
fi
python3 "$P/ir_normalize.py" "$DRC_LL" "$OUT/$NAME.norm0.ll"
python3 "$P/ir5_patch.py" "$OUT/$NAME.norm0.ll" "$OUT/$NAME.lift.ll" --report "$OUT/$NAME.ir5.json" 2>&1 | tail -3
# opt-in (PLUG_NAME_DEFS=1): RetDec が名前 (export 名 / entry_point) で出した define を function_<VA> に改名 (#1537)。 既定 0 のため他の lift の出力は変わらない
if [ "${PLUG_NAME_DEFS:-0}" = "1" ]; then
  python3 "$P/name_defs_to_va.py" "$OUT/$NAME.lift.ll" "$PE" "$RANGES"
fi
# opt-in (PLUG_CANON_ALLOCA=1; p0c_e2e.sh が立てる): RetDec の alloca 並び非決定を正規化 (LIFTLIB-11 / #887)。
# 既定 0 のため他の lift の出力は変わらない。uselistorder は ir5_patch (A7) で除去済みの後に掛ける。
if [ "${PLUG_CANON_ALLOCA:-0}" = "1" ]; then
  python3 "$P/canon_alloca.py" "$OUT/$NAME.lift.ll" "$OUT/$NAME.ca.ll"
  mv "$OUT/$NAME.ca.ll" "$OUT/$NAME.lift.ll"
fi
python3 "$P/fix_regparam_alloca.py" "$OUT/$NAME.lift.ll" "$OUT/$NAME.rp.ll" --report "$OUT/$NAME.rp.json"
python3 "$P/fix_asm_stores.py" "$OUT/$NAME.rp.ll" "$OUT/$NAME.st.ll"
# opt-in: 差分試験で検出した RetDec or.cond XNOR 化の修復 (PLUG_ORCOND_FUNCS="function_5dee90 ...")
OC_ARGS=""
for f in ${PLUG_ORCOND_FUNCS:-}; do OC_ARGS="$OC_ARGS --func $f"; done
python3 "$P/fix_orcond_xnor.py" "$OUT/$NAME.st.ll" "$OUT/$NAME.oc.ll" $OC_ARGS
# opt-in: fistp qword の上位 dword store 欠落の復元 (#982; PLUG_FISTP_HI_FUNCS="function_5de3e0 ...")
FH_ARGS=""
for f in ${PLUG_FISTP_HI_FUNCS:-}; do FH_ARGS="$FH_ARGS --func $f"; done
if [ -n "$FH_ARGS" ]; then
  python3 "$P/fix_fistp_hi_store.py" "$OUT/$NAME.oc.ll" "$OUT/$NAME.fh.ll" $FH_ARGS
else
  cp "$OUT/$NAME.oc.ll" "$OUT/$NAME.fh.ll"
fi
# opt-in: 本体で inttoptr として使う i32 仮引数の i64 化 (#1485; PLUG_I32PTR_FUNCS="function_180049450 ...")
I3_ARGS=""
for f in ${PLUG_I32PTR_FUNCS:-}; do I3_ARGS="$I3_ARGS --func $f"; done
if [ -n "$I3_ARGS" ]; then
  python3 "$P/fix_i32_ptr_arg.py" "$OUT/$NAME.fh.ll" "$OUT/$NAME.i3.ll" $I3_ARGS
else
  cp "$OUT/$NAME.fh.ll" "$OUT/$NAME.i3.ll"
fi
python3 "$P/fix_dup_decls.py" "$OUT/$NAME.i3.ll" "$OUT/$NAME.dd.ll"
python3 "$P/fix_ptr_params.py" "$OUT/$NAME.dd.ll" "$OUT/$NAME.pp0.ll"
python3 "$P/fix_icmp_ptr.py" "$OUT/$NAME.pp0.ll" "$OUT/$NAME.pp.ll"
# opt-in (PLUG_XMMARG=1): 機械語が xmm0..3 を入力に読むのに IR 署名に無い関数へ float/double 引数を復元 ((DEFECTS.md) D5, PLG-F2-4 #547)
# opt-in (PLUG_LDFIX=1): RetDec の load 取り違え (値↔アドレス・spill_slot_deref) を機械語と突合して修復 (#232 LD-1, tools/m11/ldfix)
LD_IN="$OUT/$NAME.pp.ll"
if [ "${PLUG_LDFIX:-0}" = "1" ]; then
  python3 "$HERE/../../m11/ldfix/ldfix.py" "$LD_IN" "$OUT/$NAME.ldfix.ll" --pe "$PE" --report "$OUT/$NAME.ldfix.json"
  LD_IN="$OUT/$NAME.ldfix.ll"
fi
AF_IN="$LD_IN"
if [ "${PLUG_XMMARG:-0}" = "1" ]; then
  python3 "$P/fix_xmm_args.py" "$LD_IN" "$OUT/$NAME.xa.ll" --pe "$PE" --report "$OUT/$NAME.xa.json"
  AF_IN="$OUT/$NAME.xa.ll"
fi
python3 "$P/m11_asmfix.py" "$AF_IN" "$OUT/$NAME.asmfix.ll"
if [ "${PLUG_F80_LOWER:-0}" = "1" ]; then
  # opt-in: x86_fp80 (x87) → f64 lowering (p0c/f80_lower.py)。 wasm の LLVM backend は fp80 (fpext / frem / 算術) を legalize できず `emcc -c` が落ちる。
  # f64 化は精度を落とす (x87 の 64bit 仮数が 53bit になる) ので既定は off。 呼び出し側が到達性 (emcc -c) だけを測る時に使う。 lowering 前の IR は <name>.pre_f80.ll
  python3 "$P/m11_passes.py" "$OUT/$NAME.asmfix.ll" "$OUT/$NAME.pre_f80.ll" --report "$OUT/$NAME.passes.json"
  python3 "$HERE/../p0c/f80_lower.py" "$OUT/$NAME.pre_f80.ll" "$OUT/$NAME.mp.ll" --report "$OUT/$NAME.f80.json"
else
  python3 "$P/m11_passes.py" "$OUT/$NAME.asmfix.ll" "$OUT/$NAME.mp.ll" --report "$OUT/$NAME.passes.json"
fi
# PLUG_AVX256=0 で fix_avx256 を飛ばす (synth/cpp_lift.sh は #534 の C++ DLL 結果を変えないため 0 にする)
if [ "${PLUG_AVX256:-1}" = 1 ]; then python3 "$P/fix_avx256.py" "$OUT/$NAME.mp.ll" "$OUT/$NAME.final.ll"; else cp "$OUT/$NAME.mp.ll" "$OUT/$NAME.final.ll"; fi
# opt-in (PLUG_COMIS_FLAGS=1): 非 VEX comis/ucomis の CF/ZF/PF を flag slot を持つ関数で IR に反映する (#3242)。反映できない呼出しは残し m11_simd2 が unimpl に出す
if [ "${PLUG_COMIS_FLAGS:-0}" = "1" ]; then
  python3 "$P/comis_flags.py" "$OUT/$NAME.final.ll" "$OUT/$NAME.cflag.ll" --report "$OUT/$NAME.cflag.json"
  mv "$OUT/$NAME.cflag.ll" "$OUT/$NAME.final.ll"
fi
# VEX comis の flag を同一ブロック内の読み出しに反映 (#1774 [PLG-F3-14])。 呼び出し自体は残す (helper は stub のまま unimpl に残る)
python3 "$P/vex_comis_flags.py" "$OUT/$NAME.final.ll" "$OUT/$NAME.vcf.ll"
mv "$OUT/$NAME.vcf.ll" "$OUT/$NAME.final.ll"
python3 "$P/m11_simd2.py" "$OUT/$NAME.final.ll" 2> "$OUT/$NAME.simd.log" | sed 's#"\.\./msimd11_core\.h"#"msimd11_core.h"#' > "$OUT/${NAME}_simd.c"
echo "[lift] OK: $OUT/$NAME.final.ll ($(wc -l < "$OUT/$NAME.final.ll") lines), $(grep -c '^define' "$OUT/$NAME.final.ll") defines, helpers: $(tail -3 "$OUT/$NAME.simd.log" | tr '\n' ' ')"
