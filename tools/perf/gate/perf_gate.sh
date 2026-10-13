#!/usr/bin/env bash
# perf 回帰ゲート (bit-exact OTT = x64c lift 対象)。 1 コマンド: bash tools/perf/gate/perf_gate.sh
#   1. tools/ott/ott_e2e.sh --quick で native 実機械語との bit-exact を確認し lift 出力 (work/lift) を作る
#   2. ott_x64c_build.sh で o0 / o2 / o3lto をビルド
#   3. ott_x64c_bench.mjs を GATE_REPS 回 (既定 3) 回し、judge.mjs で相対指標のみ判定
# 前提: toolchain-emsdk (EMSDK_DIR, 既定 /opt/emsdk) / analysis-ott-binaries (ANALYSIS_DIR) / python capstone,pefile / node
# env: GATE_REPS, GATE_SIG, GATE_MIN_O0_O2 ほか (judge.mjs 冒頭)。 exit 0 = PASS, 1 = FAIL, 2 = 前提不足
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
PERF="$HERE/.."
source "$PERF/../shared/env.sh"
[ -f "$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll" ] || { echo "[perf_gate] OTT_vst2_win64.dll 無し (analysis-ott-binaries / ANALYSIS_DIR)" >&2; exit 2; }
[ -f "${EMSDK_DIR:-/opt/emsdk}/emsdk_env.sh" ] || { echo "[perf_gate] emsdk 無し (toolchain-emsdk / EMSDK_DIR)" >&2; exit 2; }
OUT="$PERF/work/gate"; mkdir -p "$OUT"
T0=$(date +%s)
echo "[perf_gate] load(start) $(cut -d' ' -f1-3 /proc/loadavg)"
OTT_SKIP_INFO=1 bash "$PERF/../ott/ott_e2e.sh" --quick > "$OUT/ott_e2e.log" 2>&1 || { tail -15 "$OUT/ott_e2e.log"; echo "[perf_gate] FAIL: ott_e2e (bit-exact) 不合格"; exit 1; }
tail -2 "$OUT/ott_e2e.log" | sed 's/^/  /'
bash "$PERF/build/ott_x64c_build.sh" o0 o2 o3lto 2>&1 | grep '^\[x64c\]' | sort > "$OUT/build.txt"
: > "$OUT/bench.jsonl"
awk '{printf "{\"v\":\"%s\",\"bytes\":%s}\n",$2,$3}' "$OUT/build.txt" >> "$OUT/bench.jsonl"
cd "$PERF/harness"
for r in $(seq 1 "${GATE_REPS:-3}"); do   # 変種を反復内で交互に回し、負荷の時間変動を各変種へ均等に載せる
  for v in o0 o2 o3lto; do node ott_x64c_bench.mjs "../work/ott_x64c/$v.cjs" >> "$OUT/bench.jsonl"; done
done
echo "[perf_gate] load(end) $(cut -d' ' -f1-3 /proc/loadavg) / elapsed $(( $(date +%s) - T0 )) s"
RC=0; node "$HERE/judge.mjs" "$OUT/bench.jsonl" || RC=$?
exit $RC
