#!/usr/bin/env bash
# KH-5 (#58): Ghidra decompile→C→emcc ルート と RetDec→kh_lower ルートを Gain / Haas / Gate で比較する 1 コマンド。
#   bash tools/targets/kilohearts/ghidra_route/run_all.sh [trials=1000] [seed=7]
# 前提: HeartCore.core_64 が work/winpkg に有る (scripts/extract_installer.sh)・/opt/retdec・/opt/emsdk・
#       GHIDRA_HOME (既定 /opt/ghidra/ghidra_12.1.4_PUBLIC)・JDK 21・python に pefile/capstone。
# 出力: 各段の実測秒 (wall) と load average。結果の正本は REPORT.md §10。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; KH="$HERE/.."
TR=${1:-1000}; SEED=${2:-7}
GHIDRA_HOME=${GHIDRA_HOME:-/opt/ghidra/ghidra_12.1.4_PUBLIC}
CORE="$KH/work/winpkg/HeartCore.core_64"
[ -f "$CORE" ] || { echo "HeartCore.core_64 が無い: bash $KH/scripts/extract_installer.sh" >&2; exit 2; }
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
T() { local t0; t0=$(date +%s.%N); "$@"; printf '   [wall %.1f s | load %s]\n' "$(echo "$(date +%s.%N) - $t0" | bc)" "$(cut -d' ' -f1-3 /proc/loadavg)"; }

echo "== [1] native 参照 + 共通 ctx-fuzz ベクタ (snapins/harness, $TR trial / seed $SEED)"
mkdir -p "$KH/snapins/work"
cc -O1 -Wall -o "$KH/snapins/work/native_ref" "$KH/snapins/harness/native_ref.c" "$KH/snapins/harness/scenarios.c" -I"$KH/snapins/harness" -lm
for n in gain haas gate; do
  [ -f "$KH/snapins/work/$n/vec_${TR}_${SEED}.bin" ] || { mkdir -p "$KH/snapins/work/$n"; "$KH/snapins/work/native_ref" "$CORE" $n $TR $SEED "$KH/snapins/work/$n/vec_${TR}_${SEED}.bin"; }
done

echo "== [2] Ghidra route: import (-noanalysis) + 範囲指定 decompile (3 snap-in の lift 対象 10 関数)"
rm -rf "$KH/work/ghidra/proj" "$KH/work/ghidra/out"; mkdir -p "$KH/work/ghidra/proj"
export JAVA_HOME=${JAVA_HOME:-/usr/lib/jvm/temurin-21-jdk-amd64}; export PATH="$JAVA_HOME/bin:$PATH"
T env JAVA_TOOL_OPTIONS="-Xmx10g" "$GHIDRA_HOME/support/analyzeHeadless" "$KH/work/ghidra/proj" kh -import "$CORE" -noanalysis \
  -scriptPath "$KH/scripts/ghidra" -postScript DecompEach.java "$KH/work/ghidra/out" \
  0x1804b0380 0x18004cf20 0x1804d0280 0x1804d0180 0x1804cff00 0x1804cff90 0x1804d0720 0x1804c2f50 0x180295f20 0x180020e70 \
  -deleteProject > "$KH/work/ghidra/run.log" 2>&1
cat "$KH/work/ghidra/out/summary.tsv"

echo "== [3] Ghidra route: C 化 + emcc + 突合 (fix 全部 / 構成別 ablation)"
for n in gain haas gate; do echo "--- $n (all fixes)"; T bash "$HERE/build_cmp.sh" $n $TR $SEED bitcast,intload,stackpair,assoc,concat; done
echo "--- ablation (1 つ外し / fix なし)"
bash "$HERE/ablate.sh" $TR $SEED

echo "== [4] RetDec route (Path B: stage-0 IR → kh_lower → emcc) 同一ベクタ"
for n in gain haas gate; do
  rm -rf "$KH/snapins/work/$n/s0" "$KH/snapins/work/$n/retdec0"   # RetDec 取得も含めて冷間で測る
  echo "--- $n"; T python3 "$KH/snapins/lift/build.py" $n --path s0 --tag s0 --trials $TR --seed $SEED | python3 -c "
import sys,json
for l in sys.stdin:
    if l.startswith('{'):
        d=json.loads(l); print(' ', d.get('compare'), '| wasm', d['wasm_bytes'], 'B | undefined import', len(d['undefined_imports']), '| retdec', d.get('retdec_sec'), 's | emcc', d.get('emcc_sec'), 's')"
done

echo "== [5] SIMD / 128bit / レジスタ渡し の C 化障害 (Tier-M 7 関数 + libm 3 関数 + Channel Mixer)"
rm -rf "$KH/work/ghidra/proj"; mkdir -p "$KH/work/ghidra/proj"
T env JAVA_TOOL_OPTIONS="-Xmx10g" "$GHIDRA_HOME/support/analyzeHeadless" "$KH/work/ghidra/proj" kh -import "$CORE" -noanalysis \
  -scriptPath "$KH/scripts/ghidra" -postScript DecompEach.java "$KH/work/ghidra/out_simd" \
  0x180743390 0x18080d4d0 0x1802ed7f0 0x180fbc1f4 0x180fcd690 0x180fdfdb0 0x1807270d0 0x1804e8500 0x18035fb10 0x1804f41a0 \
  -deleteProject > "$KH/work/ghidra/run2.log" 2>&1
bash "$HERE/census.sh"
echo "ALL DONE"
