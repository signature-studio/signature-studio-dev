#!/usr/bin/env bash
# Kilohearts 事前解析 1 コマンド E2E: 抽出 → PE/RTTI/call graph/closure/SIMD census → 表 → Gain lift PoC (wasm bit-exact)
#   bash tools/targets/kilohearts/run_all.sh            (RUN_GHIDRA=1 で Ghidra headless 範囲限定 decompile クロスチェックも実行)
set -euo pipefail
cd "$(dirname "$0")"
CORE=work/winpkg/HeartCore.core_64
echo "== [1] installer 抽出 (dmg/zip → payload → windows.zip/mac.zip → 製品)"
bash scripts/extract_installer.sh
echo "== [2] PE メタ (stub / HeartCore / Installer.exe)"
{ python3 scripts/pe_info.py "work/winpkg/kHs Gain.vst2_64" "work/winpkg/kHs Gain.aaxplugin/Contents/x64/kHs Gain.aaxplugin" "$CORE" "work/win/Kilohearts Installer.exe" | cut -c1-400; } > work/pe_info.txt
echo "== [3] RTTI vtable → .pdata/leaf sweep (全 .text) → snap-in closure → SIMD census → 表"
python3 scripts/rtti_walk.py "$CORE" work/rtti_vtables.json
python3 scripts/callgraph.py "$CORE" work/rtti_vtables.json work/callgraph.pkl 14
python3 scripts/closures.py work/callgraph.pkl work/rtti_vtables.json work/closures.json
python3 scripts/simd_census.py "$CORE" work/callgraph.pkl work/closures_sets.pkl ../../m6/msimd6.c work/simd_census.json
python3 scripts/make_tables.py > work/tables.log
if [ "${RUN_GHIDRA:-0}" = 1 ]; then
  echo "== [3b] Ghidra headless (-noanalysis, 範囲限定 decompile)"
  rm -rf work/ghidra/proj; mkdir -p work/ghidra/proj
  JAVA_TOOL_OPTIONS="-Xmx16g" /opt/ghidra/ghidra_12.1.4_PUBLIC/support/analyzeHeadless work/ghidra/proj kh -import "$CORE" -noanalysis \
    -scriptPath scripts/ghidra -postScript DecompAt.java work/ghidra/gain_decomp.txt 0x1804b0380 0x1802ed7f0 -deleteProject > work/ghidra/run.log 2>&1
fi
echo "== [4] Gain snap-in lift PoC"
bash poc_gain/poc_gain.sh
bash poc_gain/poc_gain_negctl.sh
echo "ALL DONE"
