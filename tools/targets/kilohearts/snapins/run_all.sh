#!/usr/bin/env bash
# Kilohearts snap-in 10 本 (Channel Mixer / Gain / Haas / Clipper / Gate / 3-Band EQ / Resonator / Stereo / Disperser / Formant Filter) の
# lift → wasm → 実機機械語と ctx-fuzz 突合 (既存 6 本 + Disperser + Formant = bit-exact, Resonator/Stereo = 許容誤差 (CAB-224))。
#   bash tools/targets/kilohearts/snapins/run_all.sh                 本編 (Path B: RetDec stage-0 + kh_lower) 10 本 + Path A 対照 (matrix/gain/haas) + libm 単体 (qemath + qebig) + 一覧表
#   ABLATE=1 bash .../run_all.sh                                     + 修復 pass を 1 本ずつ外す ablation (数分)
#   TRIALS=1000 SEED=7 bash .../run_all.sh                           試行数 / seed 変更 (既定 200 / 1)
# 初回は RetDec (stage-0 取得 ≈ 7s/本, Path A ≈ 20s/本) と installer 抽出 (HeartCore 無ければ) が走る。2 回目以降は work/ のキャッシュで 1 分程度。
set -euo pipefail
cd "$(dirname "$0")"
TRIALS=${TRIALS:-200}; SEED=${SEED:-1}
CORE=../work/winpkg/HeartCore.core_64
if [ ! -f "$CORE" ]; then echo "== HeartCore 未抽出: installer 抽出 (../scripts/extract_installer.sh)"; bash ../scripts/extract_installer.sh; fi
mkdir -p work
echo "== [1] native 参照 (ctx-fuzz; 実機機械語を ImageBase に VA 敷設して ms_abi 直接実行)"
cc -O1 -Wall -o work/native_ref harness/native_ref.c harness/scenarios.c -Iharness -lm
echo "== [2] Path B (RetDec stage-0 IR → kh_lower → emcc → wasm) × 10 → 実機と突合 (7 本 bit-exact / resonator+stereo 許容誤差)"
for n in matrix gain haas clipper gate quickeq resonator stereo disperser formant; do
  echo "--- $n"; python3 lift/build.py $n --path s0 --tag s0 --trials "$TRIALS" --seed "$SEED" | python3 -c "import sys,json; l=sys.stdin.readline(); d=json.loads(l); print(' ', d['passes'][:160]); print(' ', d.get('compare'), '| wasm', d['wasm_bytes'], 'B | undefined import', len(d['undefined_imports']))"
done
echo "== [3] Path A (RetDec 最終 IR + kh_passes) 対照: matrix gain haas (clipper は消失コードで不可能 = 負の対照)"
for n in matrix gain haas clipper; do
  echo "--- $n (path a)"; python3 lift/build.py $n --path a --tag main --trials "$TRIALS" --seed "$SEED" | python3 -c "import sys,json; l=sys.stdin.readline(); d=json.loads(l); print(' ', d.get('compare'))"
done
echo "== [4] libm 部品の単体差分 (3-Band EQ: sin/cos FMA3, exp 系)"
./work/native_ref "$CORE" qemath 50 3 work/quickeq/qemath.bin
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
node harness/compare.mjs work/quickeq/qemath.bin work/quickeq/s0/mod.cjs work/quickeq/s0/sigs.json | tail -1
echo "== [4b] libm 部品の単体差分 (KH-2b D14: sincos_a / k_dfdb0 大引数 Payne-Hanek, |x| ∈ [5e5, 1e9], 4800 call)"
./work/native_ref "$CORE" qebig 200 3 work/quickeq/qebig.bin
node harness/compare.mjs work/quickeq/qebig.bin work/quickeq/s0/mod.cjs work/quickeq/s0/sigs.json | tail -1
echo "== [4c] KH-4 共通基盤 lift (khbase: powf FMA3 / allocator / vector push / shared_ptr icall (D15) / probe)"
python3 lift/build.py khbase --path s0 --tag s0 --trials "$TRIALS" --seed "$SEED" | python3 -c "import sys,json; l=sys.stdin.readline(); d=json.loads(l); print(' ', d['passes'][:160]); print(' ', d.get('compare'), '| wasm', d['wasm_bytes'], 'B | undefined import', len(d['undefined_imports']))"
echo "== [5] 一覧表"
python3 scripts/make_table.py s0
if [ "${ABLATE:-0}" = 1 ]; then echo "== [6] ablation"; python3 scripts/ablate.py; fi
echo "ALL DONE"
