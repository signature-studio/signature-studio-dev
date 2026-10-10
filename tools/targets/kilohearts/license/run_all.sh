#!/usr/bin/env bash
# KH-9 ライセンス stub — 1 コマンド E2E 検証 (tools/targets/kilohearts/license/)
#   bash tools/targets/kilohearts/license/run_all.sh
#
# 内容:
#   [1] stub モジュール A (stub 14 関数 + 実 IR マージ) / B (対照: getStatus のみ stub, 分類 thunk+マージは実 IR) を lift→stub pass→emcc
#   [2] lic_check.mjs: A/B 70 項目の実行検証 (定数返し・メモリ形状・実 thunk@9 ≡ stub 定数・実マージの優先度テーブル)
#   [3] snapin 6 種 (Channel Mixer/Gain/Haas/Clipper/Gate/3-Band EQ) を base (stub 無し) / lic (stub 適用) の
#       2 系で lift→emcc→ctx-fuzz 200 trial (実機機械語と bit 突合) + ライセンス関数参照数の census
#   [4] まとめ表
#
# snapins/ 側は参照のみ (run_all.sh の本体実行は別途: bash tools/targets/kilohearts/snapins/run_all.sh)。
# 成果物は license/work/ (gitignore)。
set -euo pipefail
cd "$(dirname "$0")"
TRIALS=${TRIALS:-200}; SEED=${SEED:-1}
CORE=../work/winpkg/HeartCore.core_64
if [ ! -f "$CORE" ]; then echo "== HeartCore 未抽出: installer 抽出 (../scripts/extract_installer.sh)"; bash ../scripts/extract_installer.sh; fi
export PATH=/opt/emsdk/node/24.19.0_64bit/bin:$PATH

echo "== [1] license stub モジュール A/B の lift → stub pass → emcc"
python3 lic_build.py --module A
python3 lic_build.py --module B

echo "== [2] stub モジュール実行検証 (lic_check.mjs)"
node lic_check.mjs work

echo "== [3] snapin 6 種: base (stub 無し) / lic (stub 適用) で lift → wasm → 実機と bit 突合"
for n in matrix gain haas clipper gate quickeq; do
  echo "--- $n base"
  python3 lic_build.py --dsp "$n" --tag base --no-stub --trials "$TRIALS" --seed "$SEED" | tail -1
  echo "--- $n lic"
  python3 lic_build.py --dsp "$n" --tag lic --trials "$TRIALS" --seed "$SEED" | tail -1
done

echo "== [4] まとめ"
node -e '
const fs = require("fs");
for (const n of ["matrix","gain","haas","clipper","gate","quickeq"]) {
  const r = [];
  for (const t of ["base","lic"]) {
    const s = JSON.parse(fs.readFileSync("work/"+n+"/"+t+"/stat.json","utf8"));
    r.push(`${t}: ${s.trials_ok}/${s.trials} trial bit-exact (${s.calls_ok}/${s.calls} call), wasm ${s.wasm_bytes}B, licFn参照 ${s.lic_va_hits_total}`);
  }
  console.log(n.padEnd(9), r.join(" | "));
}'
echo "ALL DONE"
