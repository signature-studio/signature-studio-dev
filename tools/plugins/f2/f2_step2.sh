#!/usr/bin/env bash
# PLG-F2-2 (#514) の 1 コマンド再現: batch_lift 鎖に tools/icall の復元を接続した eq-filter 11 閉包の lift → emcc -c → 回帰ゲート → 別算法検算
#   bash tools/plugins/f2/f2_step2.sh            (前提: f2_step1.sh と同じ。 work/ の前提 JSON が無ければ再生成する)
# 出力: work/batch/<block>/ (p.final.ll ほか。 icall 中間物は p.icall.dll / p.icall.map.json / p.drc.restored.ll), work/batch/status.csv, work/f2/gate.json
# 終了コード: matrix 突合 DIFF / 回帰ゲート FAIL / 別算法検算 DIFF のいずれかで非 0
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"                       # tools/plugins
source "$ROOT/../shared/env.sh"
[ -f "$HERE/env.sh" ] && source "$HERE/env.sh"
cd "$ROOT"
BLOCKS="${F2_BLOCKS:-18953 18975 18979 18982 18984 19005 19006 19013 19058 19059 19145}"
mkdir -p work/f2
[ -f work/win_pe_scan.json ] || python3 inventory/win_scan.py
[ -f work/nsis_blockmap.json ] || python3 f2/mk_blockmap.py
[ -d work/winfuncs ] || python3 inventory/win_funcs.py
[ -f work/win_unique.json ] || python3 inventory/win_unique.py > /dev/null
[ -f work/win_abi.json ] || python3 inventory/win_abi.py > /dev/null
rm -f work/batch/status.csv
PLUG_ICALL=1 bash lift/batch_lift.sh $BLOCKS
echo "== status.csv の突合 (PLUGIN_MATRIX.json の lift 欄: closure_funcs/closure_bytes/lift_rc/emcc_c_rc)"
python3 f2/matrix_check.py $BLOCKS
echo "== 閉包統計 (defines = closure の assert を含む)"
python3 f2/closure_stats.py --json work/f2_stats.json $BLOCKS
echo "== 回帰ゲート: IR の間接 call が機械語の非 IAT 間接 call site を全て覆う (f2/icall_gate.py)"
python3 f2/icall_gate.py --json work/f2/gate.json $BLOCKS
echo "== waiver 18979 0x741035 の機械検証 (f2/waiver_proof.py。窓モード。全数検査は --domain full)、そのネガコン"
python3 f2/waiver_proof.py
python3 f2/nc_waiver_proof.py
echo "== 別算法検算: 機械語の線形 sweep vs icall_rewrite.py (recursive descent) の dispatch 化 site"
python3 f2/xcheck_rewriter.py $BLOCKS
