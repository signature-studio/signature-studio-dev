#!/usr/bin/env bash
# avx_e2e.sh — CAB-135 (OTT-T3) 1 コマンド検収: AVX/VEX lift の全 gate。
#   [1] build: VEX 有効 lift → wasm (通常 + VEXCOV probe)
#   [2] Gate A (flags=0 回帰): crt 9 scenario + entry 85 scenario を avx build で再突合
#   [3] Gate B (AVX/FMA 強制): AVX_FORCE=fma,isa で avx 9 + crt 9 + entry 85 を native/wasm 突合
#       — __isa_available 判断の実測データ (DSP 相当は entry 'proc' 経由で FMA kernel を通る)
#   [4] VEX 実行 coverage: native insn coverage vs wasm VEXCOV hit の突合 (新 scenario 分)
#   [5] fma_fuzz: native vfmadd213sd vs wasm fma() の 30 万 case bit 突合
#   [6] 既存 e2e 継続 (ott_e2e / entry_e2e / crt_e2e は最後に手動 or 回帰で)
#   出力: tools/ott/work/avx/
#   env: AVX_BUILD_SKIP=1 / AVX_A_SKIP=1 (再利用)
set -uo pipefail
OTT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
AVX="$OTT/avx"
OUT="$OTT/work/avx"
NODE="${NODE:-/opt/emsdk/node/24.19.0_64bit/bin/node}"
mkdir -p "$OUT"
FAIL=0

echo "[1/6] build (VEX lift → wasm 通常 + VEXCOV probe)"
if [ "${AVX_BUILD_SKIP:-0}" != "1" ] || [ ! -f "$OUT/ottl_avx.cjs" ]; then
  bash "$AVX/build_avx.sh" 2>&1 | grep -E "^\[|functions" | tail -2 || FAIL=1
  AVX_OUT=ottl_avx_cov AVX_VEXCOV=1 bash "$AVX/build_avx.sh" 2>&1 | tail -1 || FAIL=1
else
  echo "  再利用 ($OUT/ottl_avx.cjs)"
fi

echo "[2/6] Gate A: flags=0 回帰 (crt 9 + entry 85, avx build)"
if [ "${AVX_A_SKIP:-0}" != "1" ] || [ ! -f "$OUT/matrix/summary.json" ]; then
  python3 -u "$AVX/../crtinit/run_matrix.py" "$OUT/ottl_avx.cjs" "$OUT/matrix" --scen "$OUT/../crtlift/scen_crt.json" 2>&1 | tail -1
  python3 -u "$OTT/entry/cmp_entries.py" "$OUT/matrix/nat_result.json" "$OUT/matrix/wasm_result.json" --out "$OUT/matrix/summary.json" || FAIL=1
  python3 -u "$AVX/../crtinit/run_matrix.py" "$OUT/ottl_avx.cjs" "$OUT/matrix85" --scen "$OUT/../entrylift/scen.json" 2>&1 | tail -1
  python3 -u "$OTT/entry/cmp_entries.py" "$OUT/matrix85/nat_result.json" "$OUT/matrix85/wasm_result.json" --out "$OUT/matrix85/summary.json" || FAIL=1
else
  echo "  再利用 ($OUT/matrix)"
fi

echo "[3/6] Gate B: AVX/FMA 強制 (AVX_FORCE=fma,isa) — avx 9 + crt 9 + entry 85"
python3 "$AVX/avx_scen.py" "$OUT/scen_avx.json" >/dev/null
python3 -u "$AVX/avx_matrix.py" "$OUT/ottl_avx.cjs" "$OUT/mavx" --scen "$OUT/scen_avx.json" --force fma,isa 2>&1 | tail -1
python3 -u "$OTT/entry/cmp_entries.py" "$OUT/mavx/nat_result.json" "$OUT/mavx/wasm_result.json" --out "$OUT/mavx/summary.json" || FAIL=1
python3 -u "$AVX/avx_matrix.py" "$OUT/ottl_avx.cjs" "$OUT/mcrt" --scen "$OUT/../crtlift/scen_crt.json" --force fma,isa 2>&1 | tail -1
python3 -u "$OTT/entry/cmp_entries.py" "$OUT/mcrt/nat_result.json" "$OUT/mcrt/wasm_result.json" --out "$OUT/mcrt/summary.json" || FAIL=1
python3 -u "$AVX/avx_matrix.py" "$OUT/ottl_avx.cjs" "$OUT/m85" --scen "$OUT/../entrylift/scen.json" --force fma,isa 2>&1 | tail -1
python3 -u "$OTT/entry/cmp_entries.py" "$OUT/m85/nat_result.json" "$OUT/m85/wasm_result.json" --out "$OUT/m85/summary.json" || FAIL=1

echo "[4/6] VEX 実行 coverage (native vs wasm probe) — 新 scenario"
python3 -u "$AVX/avx_matrix.py" "$OUT/ottl_avx_cov.cjs" "$OUT/mavx_cov" --scen "$OUT/scen_avx.json" --force fma,isa --cov "$OUT/cov_avx_fma.json" 2>&1 | tail -1
python3 -u "$OTT/entry/cmp_entries.py" "$OUT/mavx_cov/nat_result.json" "$OUT/mavx_cov/wasm_result.json" --out "$OUT/mavx_cov/summary.json" || FAIL=1
python3 - <<'PYEOF' || FAIL=1
import json
cov = set(json.load(open('work/avx/cov_avx_fma.json'))['insn'])
vx = json.load(open('work/avx/mavx_cov/wasm_vexcov.json'))
wset = set()
for v in vx.values(): wset |= set(v)
bad = sorted(x for x in wset if x not in cov)
print('[vexcov] native 実行 insn %d / wasm VEX hit %d 種 / hit⊆native実行: %s' % (
    len(cov), len(wset), 'OK' if not bad else 'NG (%d 例: %s)' % (len(bad), ['%x' % x for x in bad[:5]])))
raise SystemExit(1 if bad else 0)
PYEOF

echo "[5/6] fma_fuzz (native vfmadd213sd vs wasm fma(), 30 万 case)"
gcc -O2 -mavx2 -mfma -o "$OUT/fma_fuzz_nat" "$AVX/fma_fuzz.c" -lm
"$OUT/fma_fuzz_nat" 300000 12345 > "$OUT/fma_nat.txt" 2> "$OUT/fma_nat.err" || { echo "  native internal NG"; cat "$OUT/fma_nat.err" | head -3; FAIL=1; }
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
emcc -O1 -ffp-contract=off -fno-fast-math "$AVX/fma_fuzz.c" -o "$OUT/fma_fuzz.cjs" -sENVIRONMENT=node -w -sEXIT_RUNTIME=1 2>/dev/null
"$NODE" "$OUT/fma_fuzz.cjs" 300000 12345 > "$OUT/fma_wasm.txt" 2>/dev/null
if diff -q "$OUT/fma_nat.txt" "$OUT/fma_wasm.txt" >/dev/null; then
  echo "  fma native/wasm bit 一致: OK ($(wc -l < "$OUT/fma_nat.txt") cases)"
else
  echo "  fma native/wasm 差分あり: NG ($(diff "$OUT/fma_nat.txt" "$OUT/fma_wasm.txt" | head -4))"; FAIL=1
fi

echo "[6/6] summary"
for f in matrix matrix85 mavx mcrt m85 mavx_cov; do
  s="$OUT/$f/summary.json"
  [ -f "$s" ] && python3 -c "
import json; d = json.load(open('$s'))
print('  %-10s %s' % ('$f', d.get('summary', d)))" 2>/dev/null || true
done
if [ $FAIL = 0 ]; then echo "[avx_e2e] PASS"; else echo "[avx_e2e] FAIL"; fi
exit $FAIL
