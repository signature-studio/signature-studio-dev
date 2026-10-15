#!/usr/bin/env bash
# build_ctrl.sh — FA-2c: FreshAirDsp 制御層 (0x1803dfc10, vtable 17 slot) + 子 snapin 仮想 dispatch 鎖を mlift → wasm。
#   制御層 17 slot + 子 wrapper (Compressor/Filter/Gain) ctor + slot 群 + 子 process 3 種を 1 モジュールに統合。
#   vtable 間接 call / 間接 tail-jmp は fa_icall switch (--icall) で解決 (native は実機 vtable VA をそのまま実行)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
W="$HERE/work/ctrl"; mkdir -p "$W"; cd "$W"; source "$HERE/env.sh"
POKES=(); while read -r va sz val; do [[ "$va" == \#* || -z "$va" ]] && continue; POKES+=(--poke "$va:$sz:$val"); done < "$HERE/pokes.txt"

# ---- roots: 制御層 17 slot (FreshAirDsp vtable 0x1810cab70) ----
ROOTS=(
  --root 0x1803dfc10:'void(i64,i64)'      # slot12 process (本チケット本体)
  --root 0x1803ba840:'i64(i64,i64)'       # FreshAirDspModel ctor (base 0x180c95fd0 + cell ctor 0x1803ba800 群; M を実機で構築)
  --root 0x1803dee20:'i64(i64,i64)'       # ctor (harness が実機 ctor でオブジェクト構築)
  --root 0x1803defa0:'void(i64,i64)'      # slot0 dtor
  --root 0x1803e01a0:'void(i64)'          # slot3 (→ slot13 へ間接 tail-jmp)
  --root 0x1803e0380:'void(i64,f32)'      # slot4 samplerate/tempo (→ slot13 へ間接 tail-jmp)
  --root 0x1803df580:'void(i64,i64)'      # slot5
  --root 0x1803df050:'i32(i64)'           # slot7 meter
  --root 0x1803df030:'i32(i64)'           # slot8
  --root 0x1803df060:'i32(i64)'           # slot9
  --root 0x1803df810:'void(i64,i64)'      # slot10
  --root 0x1803e01d0:'void(i64)'          # slot13
  --root 0x1803df040:'i32(i64,i64)'       # slot16
  --root 0x1803b4070:'void(i64)'          # vtable 共有 no-op (ret 0) — ctrl block 解放先としても使用
)
# ---- roots: 子 snapin wrapper (SnapinDsp<T>) ctor と vtable slot 群 ----
ROOTS+=(
  --root 0x180774cd0:'i64(i64,i64,i64,i64)'  # Compressor wrapper ctor
  --root 0x180b6ed50:'i64(i64,i64,i64,i64)'  # Filter wrapper ctor
  --root 0x180afde00:'i64(i64,i64,i64,i64)'  # Gain wrapper ctor
  --root 0x1807750a0:'void(i64,i64)'      # comp slot10 (param flush → 0x1803de4d0)
  --root 0x1807750e0:'void(i64,i64)'      # comp slot11 (tail process)
  --root 0x1807758b0:'void(i64,i64)'      # comp slot13 (tail reset)
  --root 0x1807758a0:'void(i64,i64)'      # comp slot15
  --root 0x180774ee0:'i64(i64,i64)'       # comp slot16 (tail active?)
  --root 0x180775930:'void(i64,f32)'      # comp slot4 (sr)
  --root 0x180774e80:'void(i64,i64)'      # comp slot0 dtor
  --root 0x1808e2280:'void(i64,f32)'      # filter slot4
  --root 0x180460e60:'void(i64,i64)'      # filter/gain slot10
  --root 0x180b6efb0:'void(i64,i64)'      # filter slot11
  --root 0x180b6f390:'void(i64,i64)'      # filter slot13
  --root 0x180b6ef40:'void(i64,i64)'      # filter slot0
  --root 0x180afe2b0:'void(i64,f32)'      # gain slot4
  --root 0x180afdfd0:'void(i64,i64)'      # gain slot11
  --root 0x180afe260:'void(i64,i64)'      # gain slot13
  --root 0x180afe250:'void(i64,i64)'      # gain slot15
  --root 0x180afdf70:'void(i64,i64)'      # gain slot0
)
# ---- roots: 子 process 本体 (vtable slot12 経由で間接 call される) ----
ROOTS+=(
  --root 0x180775220:'void(i64,i64)'      # Compressor process (FA-2/2b 済み, 制御層からは slot12 経由)
  --root 0x180b6f050:'void(i64,i64)'      # Filter process
  --root 0x180afe090:'void(i64,i64)'      # Gain process
  --root 0x18103fd60:'f32(f32,f32)'       # 共有数学 helper (macro 変換 / sr 時定数)
)

# ---- fa_icall switch: vtable 間接 call/tail-jmp の解決先 (実機 vtable VA をそのまま登録) ----
ICALLS=(
  # FreshAirDsp vtable 0x1810cab70 (17 slot)
  --icall 1803defa0 --icall 1803b4070 --icall 1803e01a0 --icall 1803e0380 --icall 1803df580
  --icall 1803df050 --icall 1803df030 --icall 1803df060 --icall 1803df810 --icall 1803dfc10
  --icall 1803e01d0 --icall 1803df040
  # ctor 経由の lea 関数ポインタ (0x1804e7d10 repeat-call helper の r9: filter wrapper ctor が
  # 子 voice 6 個の配置 ctor として渡す — 表に存在しないゆえ --icall 登録が必須)
  --icall 1809917d0 --icall 1806aff20
  # Compressor wrapper vtable 0x1810e1be8
  --icall 180774e80 --icall 180775930 --icall 1803df070 --icall 1803df010 --icall 1807750a0
  --icall 1807750e0 --icall 180775220 --icall 1807758b0 --icall 1807758a0 --icall 180774ee0
  # Filter wrapper vtable 0x1810faad0
  --icall 180b6ef40 --icall 1808e2280 --icall 180460e60 --icall 180b6efb0 --icall 180b6f050 --icall 180b6f390
  # Gain wrapper vtable 0x1810f8870
  --icall 180afdf70 --icall 180afe2b0 --icall 180afdfd0 --icall 180afe090 --icall 180afe260 --icall 180afe250
  # CFG ディスパッチ stub (jmp rax): 実先着は rax → fa_icall が rax0 で再ディスパッチ (FA-2c 追加)
  --icall 1810806a0
  # closure 内 lea 参照の関数ポインタ (FA-2c 追加: モデル基本 ctor 0x180c95fd0 が r9 に載せて渡す)
  --icall 1803e0650 --icall 1803ddb60 --icall 1803ddba0 --icall 18105d9dc
  # harness グラフの vtable slot (FA-2c: 実測で未解決だった slot を追加)。
  # 0x1803de9b0 は pdata 非登録の小関数 (func_extent は線形走査で 0x1803de9b0..0x1803de9c7 を返す)。
  --icall 1803dea00 --icall 1803de9b0
)

# ---- FA-2c: 2 段 lift。closure 内の `lea r64,[rip+X]` 関数ポインタ (引数受け回し) を icall seed に追加する。
#      1 回目で closure (ctrl_rep.json) を確定 → icall_extra.py で seed を抽出 → 2 回目で本 lift。
TRACE9=(); TRACE_EXP=""
[ -n "${FA_TRACE9:-}" ] && { TRACE9=(--trace 180c9d700:180c9d760); TRACE_EXP=",_fa_trace_ptr,_fa_trace_count"; }   # #1789: setter 入口〜出口の命令前レジスタ (既定 OFF)
python3 "$HERE/mlift/mlift.py" "$CORE" ctrl_full.ll \
  "${ROOTS[@]}" "${ICALLS[@]}" \
  --map 0x181030490=fa_memmove --map 0x18106a3a0=fa_mxcsr_get --map 0x18106a3ba=fa_mxcsr_set \
  --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}" "${TRACE9[@]}" --report ctrl_rep.json
ICALL_EXTRA=$(python3 "$HERE/icall_extra.py" "$CORE" "$W/ctrl_rep.json")
echo "icall_extra: $ICALL_EXTRA"

python3 "$HERE/mlift/mlift.py" "$CORE" ctrl_full.ll \
  "${ROOTS[@]}" "${ICALLS[@]}" $ICALL_EXTRA \
  --map 0x181030490=fa_memmove --map 0x18106a3a0=fa_mxcsr_get --map 0x18106a3ba=fa_mxcsr_set \
  --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}" "${TRACE9[@]}" --report ctrl_rep.json

python3 -c "
import json; r=json.load(open('ctrl_rep.json')); open('iat_slots.txt','w').write('\n'.join('%s %s'%(k[2:],v) for k,v in r['iat_slots'].items())+'\n')"
cp "$HERE/pokes.txt" pokes.txt

EXPORTS=$(python3 -c "
roots = '''0x1803dfc10 0x1803ba840 0x1803dee20 0x1803defa0 0x1803e01a0 0x1803e0380 0x1803df580 0x1803df050
0x1803df030 0x1803df060 0x1803df810 0x1803e01d0 0x1803df040 0x1803b4070
0x180774cd0 0x180b6ed50 0x180afde00
0x1807750a0 0x1807750e0 0x1807758b0 0x1807758a0 0x180774ee0 0x180775930 0x180774e80
0x1808e2280 0x180460e60 0x180b6efb0 0x180b6f390 0x180b6ef40
0x180afe2b0 0x180afdfd0 0x180afe260 0x180afe250 0x180afdf70
0x180775220 0x180b6f050 0x180afe090 0x18103fd60'''.split()
print(','.join('_fa_root_%s' % v.replace('0x','') for v in roots))")

python3 "$HERE/gen_win_stubs.py" "$CORE" > win_stubs.c
emcc -w -O1 -ffp-contract=off -frounding-math -fno-fast-math ctrl_full.ll "$HERE/shim/host_wasm.c" win_stubs.c \
  -sERROR_ON_UNDEFINED_SYMBOLS=1 -sMODULARIZE=1 -sENVIRONMENT=node -sALLOW_MEMORY_GROWTH=1 \
  -sEXPORTED_FUNCTIONS="${EXPORTS},_fa_va2ptr,_malloc,_free,_fa_heap_zero${TRACE_EXP}" -sEXPORTED_RUNTIME_METHODS=HEAPU8,stackSave,stackRestore --no-entry -o ctrl_full.js
cp ctrl_full.js ctrl_full.cjs
clang -O1 -ffp-contract=off -frounding-math -w -o native_ctrl "$HERE/native/native_ctrl.c" || { echo "ERROR: native_ctrl の clang が失敗 (build_ctrl.sh)" >&2; exit 1; }
[ -x native_ctrl ] && [ -f ctrl_full.cjs ] || { echo "ERROR: ctrl build の成果物 (native_ctrl / ctrl_full.cjs) が無い" >&2; exit 1; }
echo "ctrl build ok"
