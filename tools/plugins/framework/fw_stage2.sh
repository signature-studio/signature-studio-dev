#!/usr/bin/env bash
# fw_stage2.sh — P0a (CAB-194) framework lift stage 2: 修復 pass → wasm → headless smoke。
#   bash fw_stage2.sh            # 増分 (既存成果物をスキップ)
#   bash fw_stage2.sh --fresh    # stage-2 生成物を全部作り直し (stage-1 の RetDec lift は再利用)
# 前提: stage-1 (fw_lift.sh) 済み = work/fw/{fw_icall.dll,fw_map.json,fw[0-7].restored.ll}
# 経路: merge (無名番号衝突 Fix + fn-ptr 戻り型正規化) → decode 漏れ round2/3 → fnptr → f80
#       → liftlib base.normalize → cleanup → cefix (事前 hoist) → ir5_patch (8 way 並列)
#       → cefix (残留型補完) → sigfix → entry_fix → cab129 → flatten → rep/cpuid/ymm/fldenv 正規化
#       → liftlib simd gen (TAG 拡張) → ovpass → fw_table (dispatch 表 + override) → emcc → smoke
#
# 再現性 (CAB-269): W は FW_W で差し替え可能 (既定は tools/plugins/work/fw)。共有 work/fw を
# 触らず独立再現するときは `FW_W=<空dir> bash fw_stage2.sh` (dir に stage-1 成果物を置く)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../../shared/env.sh"
T="$REPO_ROOT"
W="${FW_W:-$HERE/../work/fw}"
PE="$W/fw_icall.dll"
FRESH=0
for a in "$@"; do case "$a" in --fresh) FRESH=1 ;; esac; done
cd "$W"
mkdir -p tmp
export TMPDIR="$W/tmp"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
# runner は emsdk に llvm-as が無く Ubuntu の llvm-as-18 だけ入っている (IR 検証 llvm-as 用)
command -v llvm-as >/dev/null 2>&1 || llvm-as() { llvm-as-18 "$@"; }

# ---- emcc 入力 (相対参照) と hs_e2e.sh の前提ファイルを W に揃える ----
# S1 (CAB-269): fw_rt.h/fw_rt.c は cp していたが fw_boot.c は漏れていた
#   → `emcc: error: fw_boot.c: No such file or directory`
stage_inputs() {
  local f
  for f in fw_rt.h fw_rt.c fw_boot.c; do
    [ -f "$HERE/$f" ] || { echo "[s2] 入力欠落: $HERE/$f" >&2; exit 1; }
    cp -f "$HERE/$f" .
  done
}

# ---- 1. 8 chunk merge (無名番号衝突 Fix + fn-ptr 戻り define 取り込み) ----
if [ $FRESH = 1 ] || [ ! -f fw_all8.ll ]; then
  python3 "$HERE/fw_merge.py" fw[0-7].restored.ll -o fw_all8.ll
fi
if [ $FRESH = 1 ] || [ ! -f fw_all.restored.ll ]; then
  # fn-ptr 戻り型正規化
  python3 "$HERE/fw_fnptr.py" fw_all8.ll fw_all8n.ll
  python3 "$HERE/fw_merge.py" fw_all8n.ll r2.restored.ll r3.restored.ll -o fw_all.restored.ll
fi

# ---- 2. decode 漏れ関数の第二/三ラウンド ----
if [ $FRESH = 1 ] || [ ! -f r2.restored.ll ]; then
  python3 "$HERE/fw_round2.py" --ir fw_all8.ll --map fw_map.json --ranges-out r2.ranges
  /opt/retdec/bin/retdec-decompiler "$PE" -o r2.drc.c --select-ranges "$(cat r2.ranges)" --select-decode-only --timeout 1800 > r2.retdec.log 2>&1
  python3 "$T/tools/icall/ir_icall_restore.py" --ir r2.drc.ll --map fw_map.json --out r2.restored.ll --report r2.restore.json
fi
if [ $FRESH = 1 ] || [ ! -f r3.restored.ll ]; then
  python3 "$HERE/fw_merge.py" fw_all8.ll r2.restored.ll -o fw_all2.ll
  python3 "$HERE/fw_round2.py" --ir fw_all2.ll --map fw_map.json --ranges-out r3.ranges
  /opt/retdec/bin/retdec-decompiler "$PE" -o r3.drc.c --select-ranges "$(cat r3.ranges)" --select-decode-only --timeout 1200 > r3.retdec.log 2>&1
  python3 "$T/tools/icall/ir_icall_restore.py" --ir r3.drc.ll --map fw_map.json --out r3.restored.ll --report r3.restore.json
fi
if [ $FRESH = 1 ] || [ ! -f fw_all.restored.ll ]; then
  python3 "$HERE/fw_fnptr.py" fw_all8.ll fw_all8n.ll
  python3 "$HERE/fw_merge.py" fw_all8n.ll r2.restored.ll r3.restored.ll -o fw_all.restored.ll
fi

# ---- 3. f80 → f64 ----
# FW_EXT_FUNCS (P0c-8 / #311): 指定すると fw_f80.py --ext-funcs で ext (dd) emulation を適用する。
# 未指定なら従来どおり (fw_f80.ll は byte 一致)。FW_CHOP_FUNCS / FW_CHOP_RANGES は fldcw chop 区間。
EXT_ARGS=()
if [ -n "${FW_EXT_FUNCS:-}" ]; then
  EXT_ARGS=(--ext-funcs "$FW_EXT_FUNCS" --chop-funcs "${FW_CHOP_FUNCS:-}" --chop-ranges "${FW_CHOP_RANGES:-}")
fi
[ -f fw_f80.ll ] || python3 "$HERE/fw_f80.py" fw_all.restored.ll fw_f80.ll --report fw_f80.json "${EXT_ARGS[@]}"

# ---- 4. liftlib base normalize ----
if [ ! -f fw_norm.ll ]; then
  python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ['REPO_ROOT'] + '/tools/liftlib')
from liftlib.passes import base
text = open('fw_f80.ll', errors='replace').read()
open('fw_norm.ll', 'w').write(base.normalize(text))
PY
fi

# ---- 5. cleanup ----
[ -f fw_clean.ll ] || python3 "$HERE/fw_cleanup.py" fw_norm.ll fw_clean.ll

# ---- 6. 事前 hoist ----
[ -f fw_clean2.ll ] || python3 "$HERE/fw_cefix.py" fw_clean.ll fw_clean2.ll

# ---- 7. ir5_patch (8 way 並列) ----
if [ ! -f fw_lift.ll ]; then
  rm -rf slice && mkdir -p slice
  python3 - <<'PY'
lines = open('fw_clean2.ll', errors='replace').read().split('\n')
starts = [i for i, l in enumerate(lines) if l.startswith('define ')]
first = starts[0]
header = [l for l in lines[:first] if not l.startswith('declare ')]
declares = [l for l in lines[:first] if l.startswith('declare ')]
blocks = []
for si, s in enumerate(starts):
    e = starts[si + 1] if si + 1 < len(starts) else len(lines)
    blocks.append('\n'.join(lines[s:e]).rstrip() + '\n')
for k in range(8):
    part = blocks[k::8]
    open('slice/fw_slice%d.ll' % k, 'w').write('\n'.join(header) + '\n' + '\n'.join(part) + '\n' + '\n'.join(declares) + '\n')
print('[slice] %d defines -> 8' % len(blocks))
PY
  pids=()
  for k in 0 1 2 3 4 5 6 7; do
    ( python3 "$T/tools/m5/ir5_patch.py" slice/fw_slice$k.ll slice/fw_slice$k.lift.ll --keep-all > slice/ir5_$k.log 2>&1 ) &
    pids+=($!)
  done
  fail=0
  for p in "${pids[@]}"; do wait "$p" || fail=1; done
  [ $fail = 0 ] || { echo "[s2] ir5 slice 失敗: slice/ir5_*.log を確認" >&2; exit 1; }
  python3 "$HERE/fw_merge.py" slice/fw_slice0.lift.ll slice/fw_slice1.lift.ll slice/fw_slice2.lift.ll slice/fw_slice3.lift.ll \
    slice/fw_slice4.lift.ll slice/fw_slice5.lift.ll slice/fw_slice6.lift.ll slice/fw_slice7.lift.ll -o fw_lift.ll
fi

# ---- 8. A9L 残留の型補完 ----
[ -f fw_lift2.ll ] || python3 "$HERE/fw_cefix.py" fw_lift.ll fw_lift2.ll

# ---- 9. sigfix (cross-chunk 署名整合) ----
[ -f fw_lift3.ll ] || python3 "$HERE/fw_sigfix.py" fw_lift2.ll fw_lift3.ll --report sigfix.json

# ---- 10. entry spill 修復 ----
[ -f fw_lift4.ll ] || python3 "$HERE/fw_entry_fix.py" fw_lift3.ll fw_lift4.ll --report entry_fix.json

# ---- 11. alloca 縮退修復 (CAB-129) ----
[ -f fw_lift5.ll ] || python3 "$HERE/fw_cab129.py" fw_lift4.ll fw_lift5.ll --report cab129_fix.json

# ---- 12. flatten ----
[ -f fw_flat.ll ] || python3 "$T/tools/icall/ir_flatten.py" fw_lift5.ll fw_flat.ll \
  --base 0x400000 --newbase 0x400000 --limit 0xd02000

# ---- 13. rep/cpuid/ymm/fldenv 正規化 ----
[ -f fw_flat2.ll ] || python3 "$HERE/fw_rep.py" fw_flat.ll fw_flat2.ll
[ -f fw_flat3.ll ] || python3 "$HERE/fw_cpuid.py" fw_flat2.ll fw_flat3.ll

# ---- 14. ymm store 正規化 + simd gen + canon 正規化 (CAB-269: fw_canon.py に集約) ----
stage_inputs
if [ ! -f fw_flat4_canon2.ll ]; then
  # 旧実装は 3 つのインライン heredoc に重複実装され, S2 (ceclone 採番の衝突)・S3 (declare 欠落) の
  # 原因だった。正規化は fw_canon.py の 1 実装に統一し, stage で差分 (i256 identity / fldenv) を切替える。
  python3 "$HERE/fw_canon.py" fw_flat3.ll fw_flat4.ll --stage flat4 --report fw_canon_flat4.json
fi
if [ ! -f fw_simd.c ]; then
  # liftlib simd gen (TAG 拡張)
  python3 - <<'PY'
import os, sys, re
sys.path.insert(0, os.environ['REPO_ROOT'] + '/tools/liftlib')
from liftlib.simd import gen as G
class DynTag(dict):
    def get(self, k, d=None):
        if k in self: return dict.__getitem__(self, k)
        m = re.match(r'^i(\d+)$', k)
        if m: return 'g%s' % m.group(1)
        return d or '?'
G.TAG = DynTag({'i128':'x','i64':'q','i32':'d','i16':'w','i8':'b','i256':'y','void':'v','ptr':'p','float':'f','double':'F'})
G.CT.update({'p':'void*','f':'float','F':'double','g224':'u64'})
sys.argv = ['gen', 'fw_flat4.ll', '-o', 'fw_simd.c', '--canon', 'fw_flat4_canon.ll']
G.main(sys.argv[1:])
PY
fi
if [ ! -f fw_flat4_canon2.ll ]; then
  # gen 後のみ __asm_fldenv__vg224(i224) が現れるので, rename + declare 置き換えはここ (S3)
  python3 "$HERE/fw_canon.py" fw_flat4_canon.ll fw_flat4_canon2.ll --stage canon --report fw_canon_canon.json
fi

# ---- 15. ovpass (_StartLib/_InitLib/RestoreContext override) ----
if [ ! -f fw_flat4_canon3.ll ]; then
  python3 "$HERE/fw_ovpass.py" fw_flat4_canon2.ll fw_flat4_canon3.ll
  python3 - <<'PY'
t = open('fw_flat4_canon3.ll').read().split('\n')
seen = set(); out = []
for l in t:
    if l.startswith('declare ') and 'fw_ov_' in l:
        if l in seen: continue
        seen.add(l)
    out.append(l)
open('fw_flat4_canon3.ll','w').write('\n'.join(out))
PY
fi

# ---- 16. dispatch 表 ----
[ -f fw_image.bin ] || python3 "$HERE/fw_image.py" --pe "$PE" --map fw_map.json --out fw_image.bin --imports fw_imports.json
[ -f fw_table.c ] || python3 "$HERE/fw_table.py" --ir fw_flat4_canon3.ll --imports fw_imports.json --out fw_table.c --blk 0x8A1000

# ---- 16.5 plugin 連鎖用の IR 修復は hostshim/hs_e2e.sh に分離 (CAB-195) ----
# 本 stage-2 の成果物 (canon3) は CAB-194 の headless smoke と同一挙動を保つ。
# CreatePlugInstance 連鎖の検証 (hs_irfix → fw_retw → fw_hostfix → emcc → e2e) は
# hostshim/hs_e2e.sh が canon3 から派生ビルドを作って実施する (framework build に
# 戻り値 store / mosaic override を混入させると unit init #16 経路の分岐が変わり
# smoke が OOB trap する — 実測のため分離)。

# ---- 17. emcc ----
if [ ! -f fw_route.cjs ]; then
  # S2/S3/S4 回帰ガード (CAB-269): clang/emcc が落とす IR エラーは llvm-as で 3 s で再現できる
  #   (multiple definition of local value / use of undefined value '@fw_fldenv' /
  #    invalid cast opcode for cast from 'i64' to 'i128' — 実測は REPORT §参照)
  # llvm-as は runner に無いため、emsdk 同梱 clang の .ll 入力で同等の検証を行う (CAB-195 #195 run)
  clang -x ir -c fw_flat4_canon3.ll -o tmp/fw_canon3.bc -w || { echo "[s2] IR 検証失敗 (clang -x ir)" >&2; exit 1; }
  # EXIT_RUNTIME=0: RestoreContext の exit(0) の後も fw_*_count 等の情報関数を呼べるようにする (#3186)。
  #   1 だと exit 後の呼出しが "called after runtime exit" で assert し、情報値が 0 になる。
  emcc fw_flat4_canon3.ll fw_simd.c fw_table.c fw_rt.c fw_boot.c "$HERE/hostshim/hostshim.c" \
    -I. -I"$HERE/hostshim" -I"$T/tools/liftlib/liftlib/simd" \
    -w -O0 -g -ffp-contract=off -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB \
    -sGLOBAL_BASE=$((0x10000000)) -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
    -sEXIT_RUNTIME=0 -sERROR_ON_UNDEFINED_SYMBOLS=0 \
    -sEXPORTED_FUNCTIONS=_function_6c13a0,_function_4189c0,_function_6bdde0,_fw_dispatch_count,_fw_last_site,_fw_last_target,_fw_ff_count,_fw_ff_msg,_fw_va_calls,_fw_va_used,_fw_alloc_count,_fw_alloc_bytes,_fw_call_cur,_fw_hs_host,_fw_hs_host_va,_fw_hs_install,_fw_hs_fold_cell,_fw_hs_trace,_fw_hs_reset,_fw_hs_count,_fw_hs_records,_fw_hs_installed,_fw_hs_fle_impl \
    -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64,wasmExports \
    -Wl,--initial-memory=$((0x14000000)) -Wl,--max-memory=$((0x80000000)) \
    -o fw_route.cjs 2> emcc.log || { grep -v 'warning\|>>>\|^$' emcc.log | head -20; exit 1; }
fi
ls -la fw_route.cjs fw_route.wasm

# ---- 18. smoke (CAB-269: 期待値を独立に再計算して検証) ----
node "$HERE/fw_run.mjs" "$W/fw_image.bin" "$W/fw_route.cjs" 2>&1 | tee smoke.log
# 注: size の既定 14,828,623 B は **77cde78 (CAB-194 vintage) ツリー** の再ビルド実測値。
# HEAD のツリーは CAB-195 以降 hostshim.c の追加リンク・fw_table.py/fw_rt.c の fail-soft 化で
# 別ビルドになるため、サイズ差は FW_SIZE 環境変数で期待値を差し替えて確認する (REPORT §13.6)。
# 注: wasm サイズの照合は FW_SIZE 指定時のみ (既定はスキップ)。HEAD で実測した 15,061,227 B と
# 77cde78 (CAB-194 vintage) ツリーの 14,828,623 B は別ビルド (CAB-195 以降 hostshim.c の追加
# リンク・fw_table.py/fw_rt.c の fail-soft 化) なので、既定で FAIL にはしない (REPORT §13.6)。
python3 "$HERE/fw_smoke_check.py" --log smoke.log --wasm "$W/fw_route.wasm" --size "${FW_SIZE:-0}"
