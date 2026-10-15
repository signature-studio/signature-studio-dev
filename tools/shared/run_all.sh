#!/usr/bin/env bash
# tools/shared e2e: 分類 + IPP 実測インベントリ + OSS wasm 再ビルド PoC 3 本 + プロプラ lift PoC を一括再現
#   bash tools/shared/run_all.sh [--skip-oss]    (素材は FL_WIN64_DIR / PLUGINS_DIR を読むのみ; 既定値は tools/shared/env.sh)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; cd "$HERE"
# shellcheck source=/dev/null
source "$HERE/env.sh"
step() { echo; echo "=== $* ==="; }
step "1/6 カタログ (win PE 313 本 / mac Mach-O 222 本) + strings"
python3 scripts/win_catalog.py; python3 scripts/mac_catalog.py; bash scripts/dump_strings.sh
step "2/6 IPP 実測: win/mac ローダ表 + 直接参照 + 静的 IPP + 独立検証 (capstone)"
python3 scripts/ipp_win_all.py; python3 scripts/ipp_mac_scan.py; python3 scripts/ipp_static_mac.py
python3 scripts/ipp_win_validate.py "$FL_WIN64_DIR/extracted/block00031_PE.bin" work/ipp_validate_flengine.json | head -3
python3 scripts/ipp_mac_validate.py
step "3/6 SIMD/命令統計 (llvm-objdump, 並列)"
mkdir -p work/simd
for f in work/slices/*.x86_64.dylib; do b=$(basename "$f" .x86_64.dylib); [ "$b" = FLEngine_x64 ] && continue; [ -s "work/simd/$b.json" ] || python3 scripts/simd_stats.py "$f" "work/simd/$b.json" >/dev/null & done; wait
python3 scripts/ipp_summary.py | head -4
python3 scripts/classify.py | head -1
if [ "${1:-}" != "--skip-oss" ]; then
  step "4/6 OSS wasm 再ビルド PoC: FreeType 2.7"; bash oss/freetype/build.sh 2>&1 | grep -E "PASS|FAIL|sizes"; python3 oss/freetype/export_diff.py
  step "5/6 OSS wasm 再ビルド PoC: libogg 1.3.2 + libvorbis 1.3.5"; bash oss/ogg/build.sh 2>&1 | grep -E "PASS|FAIL|ENC|sizes|wasm size"
  step "5b/6 OSS wasm 再ビルド PoC: Blend2D (pre-v0.20) no-JIT"; bash oss/blend2d/build.sh 2>&1 | grep -E "PASS|FAIL|JIT vs|sizes"
fi
step "6/6 プロプラ lift PoC: libkio 純粋ユーティリティ 15 関数 (RetDec -> IR pass -> wasm; 元機械語との差分テスト)"
FIX=0 bash lift/libkio/lift.sh | tail -1; cp work/lift/libkio/difftable.json data/libkio_lift_difftable_raw.json
bash lift/libkio/lift.sh | tail -1; cp work/lift/libkio/difftable.json data/libkio_lift_difftable.json
echo; echo "[run_all] done"
