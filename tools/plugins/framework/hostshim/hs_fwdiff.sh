#!/usr/bin/env bash
# hs_fwdiff.sh — CAB-195 検収: framework build 挙動不変の独立照合 (規則 41 ネガティブコントロール)。
#
# 主張 (REPORT §1): 「fw_stage2.sh に hostshim.c を追加リンクのみし (動作不変)。
#   fw_rt.c の fail-soft 化・fw_table.py の hs slot 登録/return 値伝達/decode-miss fail-soft は
#   CAB-195 連鎖到達のためで framework build の挙動を変えない」。
#
# 検証方法:
#   A (HEAD)      : fw_stage2.sh (HEAD) の emcc 行と同一構成 (hostshim.c リンク, HEAD fw_table.py 生成表)
#   B (b8e762d^)  : 親 commit の fw_stage2.sh emcc 行と同一構成 (hostshim.c 無し, 親 fw_table.py/rt.c)
#   同一 IR (work/fw/fw_flat4_canon3.ll) ・同一 image から A/B を組み、framework smoke を回して
#   exit パス・dispatch・ff・va・alloc・dispatch site ヒストグラムが一致することを確認する。
#   trap が出たら FAIL (exit 2)。
#
# 書込は tools/plugins/framework/hostshim/ と tools/plugins/work/hs/ のみ (work/fw は読取のみ)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../../../shared/env.sh"
T="$REPO_ROOT"
FW="$T/tools/plugins/framework"
WFW="$T/tools/plugins/work/fw"
W="$T/tools/plugins/work/hs/fwdiff"
U="$W/under"           # 親 commit 版の素材 (git show で展開)

mkdir -p "$W" "$U"
cd "$W"

# ---- 素材存在確認 (work/fw は読取のみ) ----
for f in fw_flat4_canon3.ll fw_simd.c fw_image.bin fw_imports.json fw_boot.c; do
  [ -f "$WFW/$f" ] || { echo "[fwdiff] 前提不足: $WFW/$f" >&2; exit 1; }
done

# ---- 親 commit (b8e762d^) の fw_table.py / fw_rt.c / fw_rt.h を展開 ----
for f in fw_table.py fw_rt.c fw_rt.h; do
  git -C "$T" show "b8e762d^:tools/plugins/framework/$f" > "$U/$f"
done
[ -s "$U/fw_table.py" ] || { echo "[fwdiff] git show に失敗" >&2; exit 1; }

# ---- dispatch 表を A/B それぞれで再生成 (同一 IR・同一 imports) ----
python3 "$FW/fw_table.py" --ir "$WFW/fw_flat4_canon3.ll" --imports "$WFW/fw_imports.json" \
  --out table_head.c --blk 0x8A1000
python3 "$U/fw_table.py" --ir "$WFW/fw_flat4_canon3.ll" --imports "$WFW/fw_imports.json" \
  --out table_base.c --blk 0x8A1000
echo "[fwdiff] table_head.c $(stat -c%s table_head.c) / table_base.c $(stat -c%s table_base.c) bytes"
if diff -q table_head.c table_base.c >/dev/null; then
  echo "[fwdiff] 注意: dispatch 表が A/B で同一 (fw_table.py 変更が表に影響しない)"; FCMP=same
else FCMP=differ; fi
echo "[fwdiff] table compare: $FCMP"

source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
export TMPDIR="$W/tmp"; mkdir -p "$TMPDIR"

COMMON=(-w -O0 -g -ffp-contract=off -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB
        -sGLOBAL_BASE=$((0x10000000)) -sENVIRONMENT=node -sMODULARIZE=1 -sEXIT_RUNTIME=1
        -sERROR_ON_UNDEFINED_SYMBOLS=0
        -I"$WFW" -I"$T/tools/liftlib/liftlib/simd")

# A: HEAD 構成 (hostshim.c 追加リンク + HEAD fw_rt.c/h + HEAD fw_table.c)
emcc "$WFW/fw_flat4_canon3.ll" "$WFW/fw_simd.c" table_head.c "$FW/fw_rt.c" "$WFW/fw_boot.c" \
  "$FW/hostshim/hostshim.c" -I"$FW/hostshim" "${COMMON[@]}" \
  -sEXPORTED_FUNCTIONS=_function_6c13a0,_fw_dispatch_count,_fw_last_site,_fw_last_target,_fw_ff_count,_fw_ff_msg,_fw_va_calls,_fw_va_used,_fw_alloc_count,_fw_alloc_bytes \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64,wasmExports \
  -Wl,--initial-memory=$((0x14000000)) -Wl,--max-memory=$((0x80000000)) \
  -o fwchk_head.cjs 2> emcc_head.log || { grep -v 'warning\|>>>\|^$' emcc_head.log | head -20; exit 1; }

# B: 親 commit 構成 (hostshim.c 無し・親 fw_rt.c/h と親 dispatch 表)
emcc "$WFW/fw_flat4_canon3.ll" "$WFW/fw_simd.c" table_base.c "$U/fw_rt.c" "$WFW/fw_boot.c" \
  -I"$U" "${COMMON[@]}" \
  -sEXPORTED_FUNCTIONS=_function_6c13a0,_fw_dispatch_count,_fw_last_site,_fw_last_target,_fw_ff_count,_fw_ff_msg,_fw_va_calls,_fw_va_used,_fw_alloc_count,_fw_alloc_bytes \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64,wasmExports \
  -Wl,--initial-memory=$((0x14000000)) -Wl,--max-memory=$((0x80000000)) \
  -o fwchk_base.cjs 2> emcc_base.log || { grep -v 'warning\|>>>\|^$' emcc_base.log | head -20; exit 1; }

ls -la fwchk_head.cjs fwchk_base.cjs
node "$HERE/hs_fwdiff.mjs" "$WFW/fw_image.bin" "$W/fwchk_head.cjs" "$W/fwchk_base.cjs"
