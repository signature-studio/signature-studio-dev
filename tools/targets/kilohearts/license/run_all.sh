#!/usr/bin/env bash
# KH-9 ライセンス stub — 1 コマンド E2E 検証 (tools/targets/kilohearts/license/)
#   bash tools/targets/kilohearts/license/run_all.sh
#
# 内容:
#   [1] stub モジュール A (stub 14 関数 + 実 IR マージ) / B (対照: getStatus のみ stub, 分類 thunk+マージは実 IR) を lift→stub pass→emcc
#   [2] lic_check.mjs: A/B 70 項目の実行検証 (定数返し・メモリ形状・実 thunk@9 ≡ stub 定数・実マージの優先度テーブル)
#   [3] snapin 6 種 (Channel Mixer/Gain/Haas/Clipper/Gate/3-Band EQ) を base (stub 無し) / lic (stub 適用) の
#       2 系で lift→emcc→ctx-fuzz 200 trial (実機機械語と bit 突合) + ライセンス関数参照数の census
#   [4] KH-10 (CAB-247): EditorModel 層部分 lift (module E: ctor+poll1/poll2+EventSlot+writer) の
#       lift→emcc→native oracle ctx-fuzz (ctor/poll 200 + 1000 trial, 状態注入込み) + 47 製品「編集可能」デモ
#   [5] まとめ表
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

echo "== [4] KH-10/KH-11 (CAB-247): EditorModel 層部分 lift (module E: ctor+poll1+poll2+EventSlot+writer)
    + subscribe 経路 (0x1800526f0 等) の実 IR 化 → native oracle ctx-fuzz + 47 製品「編集可能」デモ"
python3 lic_build.py --module E | tail -1
if [ ! -x work/native_ref ]; then
  cc -O1 -Wall -o work/native_ref harness/native_ref.c harness/scenarios.c -Iharness
fi
./work/native_ref "$CORE" em 200 1 work/em_200_1.bin
node harness/compare.mjs work/em_200_1.bin work/licE/mod.cjs work/licE/sigs.json --json work/em_200_1.json | tail -1
./work/native_ref "$CORE" empoll 1000 7 work/empoll_1000_7.bin
node harness/compare.mjs work/empoll_1000_7.bin work/licE/mod.cjs work/licE/sigs.json --json work/empoll_1000_7.json | tail -1
node em_check.mjs | tail -1
# emfire (manager EventSlot 起火 E2E、CAB-247 残スコープ): native oracle は完走するが wasm 側の
# vector-compact ctrl vtable delete thunk (0x180003360・尾 `jmp rax`) が未 lift のため bit 不一致
# = 未解決 (KH-11 REPORT に root cause と起票先を記載)。exit code には影響させない (情報提供)。
echo "--- emfire (manager slot 起火 E2E / 参考実行・未解決)"
./work/native_ref "$CORE" emfire 200 1 work/emfire_200_1.bin && \
node harness/compare.mjs work/emfire_200_1.bin work/licE/mod.cjs work/licE/sigs.json --json work/emfire_200_1.json | tail -1 || \
  echo "WARN emfire: wasm 側の未 lift thunk (0x180003360) により bit 不一致 (KH-11 REPORT 未解決・起票先: 親 CAB-13)"

echo "== [4b] KH-11b (#249): snap-in ブラウザ分類 0x180ef7fc0 の lift (module F) → 分類ゲート/カテゴリ実行検証 + 47 ctor の RTTI 同定"
python3 lic_build.py --module F | tail -1
node kh249_check.mjs | tail -1
[ -f work/xref_kh11.json ] || python3 scripts/xrefscan.py 180051af0,180d5f190,180d52990,180ef7fc0,180d5e820 --json work/xref_kh11.json > /dev/null
python3 scripts/kh249_ctor_ids.py --json work/ctor_ids.json | tail -1
python3 scripts/kh249_id_scan.py --json work/id_scan.json | tail -1

echo "== [5] まとめ"
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
