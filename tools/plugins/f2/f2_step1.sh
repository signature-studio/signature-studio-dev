#!/usr/bin/env bash
# PLG-F2 (#199) 手順 1 の 1 コマンド再現: eq-filter 11 本 (12 block) の固有閉包 lift → emcc -c → 閉包統計 → 間接 call 監査
#   bash tools/plugins/f2/f2_step1.sh            (前提: FL_WIN64_DIR/extracted/block*_PE.bin 全 PE, [RETDEC], [EMSDK] (docs/REFERENCES.md),
#                                                 python に pefile+capstone。`source f2/env.sh` が PATH を整える)
# 出力: work/batch/status.csv, work/f2_stats.json, work/f2/<block>.icall.json, stdout に 3 表
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"                       # tools/plugins
source "$ROOT/../shared/env.sh"
[ -f "$HERE/env.sh" ] && source "$HERE/env.sh"
cd "$ROOT"
BLOCKS="18953 18975 18979 18982 18984 19005 19006 19013 19058 19059 19145"
mkdir -p work/f2
# 前提 work/ (gitignore) が無ければ生成 (Actions 環境: NSIS block_manifest が無いので matrix から blockmap を再構成)
[ -f work/win_pe_scan.json ] || python3 inventory/win_scan.py
[ -f work/nsis_blockmap.json ] || python3 f2/mk_blockmap.py
[ -d work/winfuncs ] || python3 inventory/win_funcs.py
[ -f work/win_unique.json ] || python3 inventory/win_unique.py > /dev/null
[ -f work/win_abi.json ] || python3 inventory/win_abi.py > /dev/null
rm -f work/batch/status.csv
PLUG_ICALL=0 bash lift/batch_lift.sh $BLOCKS   # step1 = icall 復元なしの「接続前」計測 (#504 の数値の再現)。復元あり = f2_step2.sh
echo "== status.csv の突合 (PLUGIN_MATRIX.json の batch 欄と closure_funcs/closure_bytes/lift_rc/emcc_c_rc を比較)"
python3 f2/matrix_check.py $BLOCKS
echo "== 閉包統計"
python3 f2/closure_stats.py --json work/f2_stats.json $BLOCKS
echo "== 間接 call 監査 (tools/icall/audit_icall.py)"
for b in $BLOCKS; do
  tr ',' '\n' < "work/closure/block$(printf %05d $b).ranges.txt" | cut -d- -f1 | grep . > "work/f2/$b.funcs"
  python3 ../icall/audit_icall.py --pe "$FL_WIN64_DIR/extracted/block$(printf %05d $b)_PE.bin" \
    --ir "work/batch/$b/p.final.ll" --funcs "work/f2/$b.funcs" --json "work/f2/$b.icall.json" --label "$b" > /dev/null
done
python3 f2/icall_summary.py $BLOCKS
