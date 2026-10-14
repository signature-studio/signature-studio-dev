#!/usr/bin/env bash
# lowbase_e2e.sh — CAB-90 (HB-H1) 1 コマンド再現: lift 済み OTT の VA 敷設 base を低位へ再配置し、initial memory 864MiB → 数十 MiB で全試験が通ることを示す.
#   bash tools/hostbridge/lowbase/lowbase_e2e.sh [--no-chrome] [--quick]
#   前提 (全て既存成果物; 無ければ指示を出して終了): tools/m10/work/ott_m10.ll (bash tools/m10/m10_e2e.sh), tools/hostbridge/work/ott_hb.cjs (bash tools/hostbridge/hostbridge.sh; 「再配置前」基準),
#         tools/plugins/work/balance/{k.final.ll,k_simd.c} (bash tools/plugins/lift/t0_balance/t0_e2e.sh), python: capstone pefile (libottnative.so は毎回 build.sh で作り直す。素材 work-m6-ott 同梱の版は ott_enc_slots を欠く)
#   所要: ビルド/試験すべて合わせて約 1〜2 分 (キャッシュ不要; 全ビルドは数秒)。tools/m6..m10, ott, plugins, shim, hostbridge の既存ファイルは読取のみ (生成物は lowbase/work).
set -uo pipefail
LB="$(cd -- "$(dirname -- "$0")" && pwd)"; T="$LB/../.."; HB="$LB/.."
export PATH="$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH"
NODE="$(command -v node || ls /opt/emsdk/node/*/bin/node 2>/dev/null | head -1)"; [ -n "$NODE" ] || { echo "node 無し" >&2; exit 2; }
export NODE; export PATH="$(dirname "$NODE"):$PATH"
CHROME=1; QUICK=""; for a in "$@"; do [ "$a" = "--no-chrome" ] && CHROME=0; [ "$a" = "--quick" ] && QUICK="--quick"; done
source "$T/shared/env.sh"
DLL="$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll"
W="$LB/work"; mkdir -p "$W"; : > "$W/e2e.log"
bash "$T/ott/native/build.sh" > "$W/build_native.log" 2>&1 || { echo "[lowbase_e2e] libottnative.so のビルド失敗: $W/build_native.log" >&2; exit 2; }
need() { [ -e "$1" ] || { echo "[lowbase_e2e] 前提無し: $1  → $2" >&2; exit 2; }; }
need "$DLL" "素材"; need "$T/m10/work/ott_m10.ll" "bash tools/m10/m10_e2e.sh"; need "$HB/work/ott_hb.cjs" "bash tools/hostbridge/hostbridge.sh"
need "$T/plugins/work/balance/k.final.ll" "bash tools/plugins/lift/t0_balance/t0_e2e.sh"; need "$T/ott/work/libottnative.so" "bash tools/ott/native/build.sh"
python3 -c "import capstone, pefile" 2>/dev/null || { echo "python: capstone/pefile が必要" >&2; exit 2; }
FAIL=0; step() { echo; echo "== $*"; }; chk() { if [ "$1" = 0 ]; then echo "   -> PASS: $2"; else echo "   -> FAIL: $2"; FAIL=1; fi; }
SUM="$W/summary.txt"; : > "$SUM"; say() { echo "$*" | tee -a "$SUM"; }

step "[0] 静的監査: VA 整数の取りこぼし (reloc DIR64 / IAT / LB_BASE>=64KiB)"
python3 "$LB/audit_va.py" "$DLL" 0x10000 > "$W/audit_va.json"; chk $? "audit_va.py (dir64 先 image 外 0 / IAT に VA 0 / base>=0x10000)"
python3 -c "
import json; a=json.load(open('$W/audit_va.json'))
print('   reloc DIR64 %d (全て image 内), data 内 image 範囲 qword %d (うち reloc 外の非ポインタ類似 %d), IAT %d スロット (VA を持つもの %d)' % (a['reloc_dir64_total'], sum(s['image_range_qwords'] for s in a['sections'].values()), a['non_pointer_lookalikes_not_in_reloc'], a['iat_slots'], a['iat_slots_holding_image_VA']))"

step "[1] x64c (tools/ott の bit-exact lifter) を低位 base で再 lift/ビルド → native 機械語 89 scenario と全 bit 一致"
for spec in "0x10000 16" "0x1230000 40"; do set -- $spec; B=$1; MI=$2
  LB_BASE=$B LB_INIT_MIB=$MI bash "$LB/x64c/build_x64c.sh" > "$W/build_x64c_$B.log" 2>&1; chk $? "build base=$B init=${MI}MiB"
  eval "$(cat "$W/x64c_$B/layout.sh")"
  LB_BASE=$B LB_ARENA=$LB_ARENA LB_ARENA_SIZE=$LB_ARENA_SIZE python3 "$LB/x64c/diff/matrix.py" "$W/x64c_$B/ottl.cjs" $QUICK > "$W/matrix_$B.log" 2>&1; RC=$?
  chk $RC "matrix base=$B : $(tail -1 "$W/matrix_$B.log")"
  say "x64c base=$B initial_memory=${MI}MiB (旧 864MiB) vs native: $(tail -1 "$W/matrix_$B.log" | sed 's/^\[matrix\] //')"
done
LB_BASE=0x10000 LB_INIT_MIB=8 LB_OUT="$W/x64c_min8" bash "$LB/x64c/build_x64c.sh" > "$W/build_x64c_min8.log" 2>&1; eval "$(cat "$W/x64c_min8/layout.sh")"
LB_BASE=0x10000 LB_ARENA=$LB_ARENA LB_ARENA_SIZE=$LB_ARENA_SIZE python3 "$LB/x64c/diff/matrix.py" "$W/x64c_min8/ottl.cjs" $QUICK > "$W/matrix_min8.log" 2>&1; chk $? "probe: initial memory 8MiB でも $(tail -1 "$W/matrix_min8.log")"
eval "$(cat "$W/x64c_0x10000/layout.sh")"
LB_BASE=0x10000 LB_ARENA=$LB_ARENA MOD="$W/x64c_0x10000/ottl.cjs" SPEC='{"params":[0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5]}' OUT="$W/std_ref.json" node "$LB/x64c/diff/scen2_wasm.mjs" >/dev/null
A0=$LB_ARENA; eval "$(cat "$W/x64c_0x1230000/layout.sh")"; A1=$LB_ARENA
node "$LB/x64c/multi_x64c.mjs" --ref "$W/std_ref.json" --out "$W/multi_x64c.json" --mods "$W/x64c_0x10000/ottl.cjs:65536:$A0,$W/x64c_0x10000/ottl.cjs:65536:$A0,$W/x64c_0x10000/ottl.cjs:65536:$A0,$W/x64c_0x1230000/ottl.cjs:$((0x1230000)):$A1" | tee -a "$W/e2e.log"; chk ${PIPESTATUS[0]} "x64c 4 module 同時ロード (base 混在)"

step "[1b] 同居: 同一 DLL を base A=0x10000 / B=0x400000 + prefix a_/b_ で 1 wasm・1 linear memory に載せ交互駆動 (per-plugin base + module prefix の実証)"
bash "$LB/x64c/build_x64c_coresident.sh" > "$W/build_co.log" 2>&1; chk $? "build co-resident (関数名 a_f_*/b_f_*, a_dispatch/b_dispatch)"
node "$LB/x64c/coresident_test.mjs" --mod "$W/coresident/co.cjs" --layout "$W/coresident/layout.sh" --ref "$W/std_ref.json" | tee -a "$W/e2e.log" "$SUM"; chk ${PIPESTATUS[0]} "co-resident 2 DLL (1 memory 24MiB) bit 一致"

step "[2] RetDec chain (hostbridge の OTT module) を低位 base で再ビルド → hostbridge 検収 65 項目 (PoC 28 を lowbase module で実行)"
LB_BASE=0x10000 bash "$LB/retdec/build_m10_lb.sh" > "$W/build_m10_lb.log" 2>&1; chk $? "build m10 chain base=0x10000 : $(tail -1 "$W/build_m10_lb.log" | cut -c1-200)"
LB_BASE=0x10000 bash "$LB/retdec/build_bal_lb.sh" > "$W/build_bal_lb.log" 2>&1; chk $? "build Balance kernel module"
bash "$LB/retdec/build_host_lb.sh" > "$W/build_host_lb.log" 2>&1; chk $? "build host_vst2.wasm"
eval "$(cat "$W/m10_0x10000/layout.sh")"
rm -rf "$W/hb_0x10000"; mkdir -p "$W/hb_0x10000"; cp "$W/m10_0x10000/ott_hb.cjs" "$W/m10_0x10000/ott_hb.wasm" "$W/hb_0x10000/"; cp "$W/host_vst2.wasm" "$W/hb_0x10000/"
python3 "$LB/hb/derive_poc.py" "$W/hb_0x10000/run_poc_lb.mjs"
( cd "$HB" && python3 analysis/verify_evidence.py > "$W/ev.log" 2>&1 ); EV=$?; chk $EV "evidence $(grep -c '^OK' "$W/ev.log")/21 項目 (module 非依存)"
node "$HB/poc/pe_stub.mjs" "$W/OTT_x64.stub.dll" VSTPluginMain main > /dev/null && python3 "$HB/analysis/check_pe_stub.py" "$W/OTT_x64.stub.dll" > "$W/stub.log" 2>&1; chk $? "PE スタブ $(grep -c '^OK' "$W/stub.log")/3 項目"
node "$HB/poc/test_marshal.mjs" > "$W/marshal.log" 2>&1; chk $? "marshal 単体 $(grep -c '^OK' "$W/marshal.log")/13 項目"
LB_INIT_MIB=24 LB_WORK="$W/hb_0x10000" LB_ARENA=$LB_ARENA node "$W/hb_0x10000/run_poc_lb.mjs" > "$W/run_poc_lb.log" 2>&1; chk $? "PoC (lowbase module): $(tail -1 "$W/run_poc_lb.log")"
grep -E "^FAIL" "$W/run_poc_lb.log" | head -5
say "hostbridge 検収相当 (lowbase module): evidence $(grep -c '^OK' "$W/ev.log") + stub $(grep -c '^OK' "$W/stub.log") + marshal $(grep -c '^OK' "$W/marshal.log") + PoC $(grep -c '^OK' "$W/run_poc_lb.log") = $(( $(grep -c '^OK' "$W/ev.log") + $(grep -c '^OK' "$W/stub.log") + $(grep -c '^OK' "$W/marshal.log") + $(grep -c '^OK' "$W/run_poc_lb.log") )) / 65"

step "[3] 複数同時ロード (node): OTT×4 (各専用 memory) + Balance kernel を同一 hostbridge ホストへ → 再配置前 (864MiB×4) と比較"
node "$LB/multi/multi_load.mjs" --ott "$W/m10_0x10000/ott_hb.cjs" --bal "$W/bal_lb/bal_hb.cjs" --nmod 4 --label lb --out "$W/ml_lb.json" --dump "$W/d_lb.bin" --host "$W/host_vst2.wasm" | tee -a "$W/e2e.log"; chk ${PIPESTATUS[0]} "multi_load lowbase"
node "$LB/multi/multi_load.mjs" --ott "$HB/work/ott_hb.cjs" --nmod 4 --label orig --out "$W/ml_orig.json" --dump "$W/d_orig.bin" --host "$W/host_vst2.wasm" | tee -a "$W/e2e.log"; chk ${PIPESTATUS[0]} "multi_load 再配置前 (参照)"
python3 "$LB/multi/compare_dumps.py" "$W/d_orig.bin" "$W/d_lb.bin" "$W/ml_orig.json" "$W/ml_lb.json" | tee -a "$SUM"; chk ${PIPESTATUS[0]} "再配置前 vs lowbase 出力比較 (RetDec chain 自然経路)"

step "[3b] 切り分け: image/arena だけ低位化し heap/stack 位置は元 (GLOBAL_BASE=256MiB, 864MiB) のまま → 再配置前と 0 cell 差か"
LB_BASE=0x10000 LB_X_ARENA=$((0x320000)) LB_X_GB=$((0x10000000)) LB_X_INIT_MIB=864 LB_MAX_MIB=864 LB_OUT="$W/x_E3" bash "$LB/retdec/build_m10_lb.sh" > "$W/build_E3.log" 2>&1; chk $? "build (image=0x10000, arena=0x320000, heap/stack 位置は旧)"
node "$LB/multi/multi_load.mjs" --ott "$W/x_E3/ott_hb.cjs" --nmod 1 --label E3 --out "$W/ml_E3.json" --dump "$W/d_E3.bin" --host "$W/host_vst2.wasm" > /dev/null; chk $? "multi_load E3"
python3 - "$W/d_orig.bin" "$W/d_E3.bin" <<'PYEOF' | tee -a "$SUM"
import sys, struct
ld = lambda p: struct.unpack('<%dI' % (len(open(p, 'rb').read()) // 4), open(p, 'rb').read())
a, b = ld(sys.argv[1]), ld(sys.argv[2]); d = sum(1 for x, y in zip(a, b) if x != y)
print('切り分け E3 (image+arena のみ低位化): 再配置前との差分 %d / %d cell' % (d, len(a))); sys.exit(1 if d else 0)
PYEOF
chk ${PIPESTATUS[0]} "image/arena 再配置のみなら RetDec chain 出力は再配置前と完全一致 (差分は heap/stack 位置依存の junk のみ)"

step "[3c] module prefix (RetDec chain): function_<VA>/global_var_<VA> を ott_ 接頭にして再ビルドしても hostbridge ホストで動く"
LB_BASE=0x10000 LB_PREFIX=ott LB_OUT="$W/m10_pfx" bash "$LB/retdec/build_m10_lb.sh" > "$W/build_pfx.log" 2>&1; chk $? "build prefix=ott"
read NPF NPL < <(node -e "const m=new WebAssembly.Module(require('fs').readFileSync('$W/m10_pfx/ott_hb.wasm'));const e=WebAssembly.Module.exports(m).map(x=>x.name);console.log(e.filter(n=>n.startsWith('ott_function_')).length, e.filter(n=>/^function_/.test(n)).length)")
[ "$NPF" -gt 100 ] && [ "$NPL" = 0 ]; chk $? "wasm 名前空間: ott_function_* ${NPF} 件 / 無接頭 function_* export ${NPL} 件"
node "$LB/multi/multi_load.mjs" --ott "$W/m10_pfx/ott_hb.cjs" --nmod 1 --label pfx --out "$W/ml_pfx.json" --dump "$W/d_pfx.bin" --host "$W/host_vst2.wasm" > /dev/null; chk $? "prefix 版 module が hostbridge で LoadLibrary/process"
python3 - "$W/d_lb.bin" "$W/d_pfx.bin" <<'PYEOF' | tee -a "$SUM"
import sys, struct
ld = lambda p: struct.unpack('<%dI' % (len(open(p, 'rb').read()) // 4), open(p, 'rb').read())
f = lambda u: struct.unpack('<f', struct.pack('<I', u))[0]
a, b = ld(sys.argv[1]), ld(sys.argv[2]); d = [i for i in range(len(a)) if a[i] != b[i]]
mx = max([max(abs(f(a[i])), abs(f(b[i]))) for i in d] or [0])
print('prefix 版 vs 無接頭版 (同一 base): 差分 %d / %d cell (|v|max %.3g)' % (len(d), len(a), mx)); sys.exit(0 if mx < 1e-30 else 1)
PYEOF
chk ${PIPESTATUS[0]} "prefix 版出力 = 無接頭版 (差分は junk-tiny のみ許容)"

if [ "$CHROME" = 1 ]; then
  step "[4] headless Chrome (dedicated Worker): 同 module を Web 環境でロード → node と bit 一致 + Memory 個数"
  S="$W/chrome_stage"; rm -rf "$S"; mkdir -p "$S"; cp "$HB/poc/hb_bridge.mjs" "$LB/multi/chrome_worker.mjs" "$W/host_vst2.wasm" "$W/m10_0x10000/ott_hb.cjs" "$W/m10_0x10000/ott_hb.wasm" "$W/bal_lb/bal_hb.cjs" "$W/bal_lb/bal_hb.wasm" "$S/"
  node "$LB/multi/run_chrome.mjs" --stage "$S" --node-json "$W/ml_lb.json" --nmod 4 --nspawn 100 --out "$W/chrome_result.json" 2>&1 | tee -a "$W/e2e.log"; chk ${PIPESTATUS[0]} "Chrome Worker"

  step "[5] (#1174) SAB ring → AudioWorklet の消費量・総和と、Worker の SAB + Atomics.wait RPC による VSTPluginMain 往復を node 参照と照合"
  RS="$W/ring/stage"; rm -rf "$RS"; mkdir -p "$RS"; cp "$HB/poc/hb_bridge.mjs" "$LB/multi/ring_common.mjs" "$LB/multi/ring_rpc_worker.mjs" "$LB/multi/ring_worklet.js" "$W/hb_0x10000/host_vst2.wasm" "$W/hb_0x10000/ott_hb.cjs" "$W/hb_0x10000/ott_hb.wasm" "$RS/"
  node "$LB/multi/ring_node_ref.mjs" --ott "$W/hb_0x10000/ott_hb.cjs" --host "$W/hb_0x10000/host_vst2.wasm" --out "$W/ring/ring_ref.json" > "$W/ring/ref.log" 2>&1; chk $? "node 参照 (ring/RPC): $(cat "$W/ring/ref.log")"
  node "$LB/multi/ring_rpc_run.mjs" --stage "$RS" --ref "$W/ring/ring_ref.json" --out "$W/ring/ring_result.json" 2>&1 | tee -a "$W/e2e.log"; chk ${PIPESTATUS[0]} "Chrome: RPC 往復 (Atomics.wait) + AudioWorklet ring 消費 = node 参照"
fi
echo; echo "================ SUMMARY"; cat "$SUM"
[ $FAIL = 0 ] && echo "[lowbase_e2e] ALL PASS" || echo "[lowbase_e2e] FAIL (上の FAIL 行を参照)"
exit $FAIL
