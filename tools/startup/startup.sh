#!/bin/bash
# startup.sh — H startup-process 解析の 1 コマンド再現 (E2E)。 usage: bash tools/startup/startup.sh [FORCE=1 で全再計算]
# 入力 (読取専用): analysis/win64/extracted/block00031 (FLEngine_x64.dll) / block00037 (FL64.exe), analysis/mac/... (OsxFL, libwinbridge),
#                  tools/m2/work/ghidra_dll (FLEngine の Ghidra 解析済プロジェクト: 複製して使用, 元は触らない)
# 出力: REGISTRY.csv PROCESSES.csv (+ work/ の中間物)。最後に verify.py (実バイナリ照合) が exit 0 で全 OK
set -euo pipefail
cd "$(dirname "$0")"
W=work; mkdir -p $W
GH=/opt/ghidra/ghidra_12.1.4_PUBLIC/support/analyzeHeadless
source ../shared/env.sh
EXT="$FL_WIN64_DIR/extracted"
APP="$FL_MAC_DIR/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents"
M2="$REPO_ROOT/tools/m2/work"
F=${FORCE:-0}
step() { echo "[startup] $*"; }
need() { [ "$F" = 1 ] || [ ! -s "$1" ]; }
step "1/7 入力複製"
[ -s $W/FL64.exe ] || cp $EXT/block00037_PE.bin $W/FL64.exe
[ -s $W/FLEngine_x64.dll ] || cp $EXT/block00031_PE.bin $W/FLEngine_x64.dll
need $W/OsxFL_x86_64 && python3 scripts/fat_slice.py "$APP/MacOS/OsxFL" x86_64 $W/OsxFL_x86_64 >/dev/null
need $W/libwinbridge_x86_64.dylib && python3 scripts/fat_slice.py "$APP/Resources/FL/Shared/libwinbridge_x64.dylib" x86_64 $W/libwinbridge_x86_64.dylib >/dev/null
step "2/7 FL64.exe Ghidra decompile (WinMain / engine 解決 / trust 検証)"
if need $W/fl64_decomp.c; then
  rm -rf $W/ghidra_fl64; mkdir -p $W/ghidra_fl64
  $GH $W/ghidra_fl64 p -import $W/FL64.exe -overwrite -scriptPath ghidra_scripts -postScript DecompileFuncs.java $W/fl64_decomp.c 140007560,1400062a0,140005000,140005480,140005d80,140004b60,140002940,1400014f0,140002bc0 > $W/ghidra_fl64.log 2>&1
fi
step "3/7 FLEngine Ghidra プロジェクト複製 (m2 解析済 → work/ghidra_eng)"
if [ ! -d $W/ghidra_eng/ghproj_dll.rep ]; then mkdir -p $W/ghidra_eng; cp -r $M2/ghidra_dll/ghproj_dll.* $W/ghidra_eng/; fi
step "4/7 全関数 index (strings/imports/callees) = func_index.tsv"
if need $W/func_index.tsv; then
  python3 - <<'PY'
import csv, os
rows=list(csv.DictReader(open(os.path.join(os.environ['REPO_ROOT'], 'tools/m2/work/ghidra_dll/functions_dll.csv'))))
open('work/all_roots.txt','w').write('\n'.join(r['entry'].split(':')[-1] for r in rows)+'\n')
PY
  $GH $W/ghidra_eng ghproj_dll -process -noanalysis -readOnly -scriptPath ghidra_scripts -postScript CallTree.java $W/func_index.tsv 0 100000 @$W/all_roots.txt > $W/ct_all.log 2>&1
fi
step "5/7 TRegistry 呼出点の文字列引数抽出 + 在庫化"
need $W/reg_sites.tsv && $GH $W/ghidra_eng ghproj_dll -process -noanalysis -readOnly -scriptPath ghidra_scripts -postScript CallSiteStrings.java $W/reg_sites.tsv 5ae000 5b4000 > $W/rs.log 2>&1
python3 scripts/reg_inventory.py $W/reg_sites.tsv $W/func_index.tsv > $W/reg_raw.csv
step "6/7 REGISTRY.csv / PROCESSES.csv 生成"
( cd $W && python3 ../scripts/build_registry.py && python3 ../scripts/build_processes.py && python3 ../scripts/build_seed.py )
step "7/7 実バイナリ照合 (verify.py)"
python3 scripts/verify.py | tail -3
