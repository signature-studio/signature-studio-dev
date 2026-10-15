#!/usr/bin/env bash
# 1 コマンド E2E: 復元パス → インベントリ → ブートセット → パッケージ → node/Chrome テスト → 実測
#   bash e2e.sh [--full]      既定: 小サブセット (数十秒)。--full: 全ツリー(約 100 秒の圧縮 + 全テスト)
# 前提: node >= 24 (TypeScript をそのまま実行), python3, google-chrome, npm i (esbuild)。素材は analysis/ 配下。
set -euo pipefail
cd "$(dirname "$0")"
FULL=0; [[ "${1:-}" == "--full" ]] && FULL=1
export PATH="${PATH}:$HOME/.local/share/pnpm/bin"
# shellcheck source=/dev/null
source ../shared/env.sh   # FL_WIN64_DIR (= 直下に flstudio_win64_*.exe と extracted/)
[[ -d node_modules/esbuild ]] || npm install --no-audit --no-fund --ignore-scripts >/dev/null
[[ -x ../../node_modules/.bin/tsc ]] || (cd ../.. && pnpm install --frozen-lockfile --ignore-scripts >/dev/null)
mkdir -p work
EXE="${FL_WIN_INSTALLER:-$(ls "$FL_WIN64_DIR"/flstudio_win64_*.exe 2>/dev/null | head -1)}"
[[ -n "$EXE" && -f "$EXE" ]] || EXE="$HOME/ダウンロード/flstudio_win64_26.1.7.5653.exe"
# block_manifest.json / pe_metadata.json が素材に無い環境 (Actions) では installer と extracted/ から再構成する
#   mk_manifest.py: blockNNNNN ↔ payload_off (recover_paths.py の入力) / mk_inputs.py: idx/kind/dsize/payload_off 入り manifest + pe_metadata
#   inventory.py は tracked の inventory/summary.json を上書きするので、この経路では work/ に逃がして作業ツリーを汚さない
if [[ ! -f "$FL_WIN64_DIR/block_manifest.json" ]]; then
  python3 ../startup/loadpaths/mk_manifest.py "$EXE" work/block_offsets.json >/dev/null
  python3 inventory/mk_inputs.py "$FL_WIN64_DIR/extracted" work work/block_offsets.json >/dev/null
  export WIN_INPUTS_DIR="$PWD/work" INVENTORY_SUMMARY_OUT="$PWD/work/summary.json"
fi
MANIFEST="${WIN_INPUTS_DIR:-$FL_WIN64_DIR}/block_manifest.json"
[[ -f work/win_paths.json ]] || python3 win_paths/recover_paths.py "$EXE" "$MANIFEST" work/win_paths.json
[[ -f work/inv_win.jsonl ]] || python3 inventory/inventory.py
python3 bootset/strings_scan.py >/dev/null
python3 bootset/classify_bootset.py >/dev/null
# ST-T14 §4 の tier 差分 6 点 (#592): 変更前 (8f55002) の規則との差分が表と過不足なく一致 + ネガコン (期待表を壊すと FAIL)
#   変更前の bootset.json は固定ファイル (shallow clone でも履歴に依存しない)
PRE=bootset/bootset.pre592.json
python3 bootset/verify_tier_diff.py "$PRE"
if python3 bootset/verify_tier_diff.py "$PRE" --negcon >/dev/null; then echo "FAIL: verify_tier_diff のネガコンが通った" >&2; exit 1; fi
# 再生成の決定性: コミット済み bootset.json / BOOTSET.md と一致 (生成物を人手で触っていない)
git diff --exit-code HEAD -- bootset/bootset.json bootset/BOOTSET.md >/dev/null || { echo "FAIL: bootset 生成物が未コミット/再生成と不一致" >&2; exit 1; }
../../node_modules/.bin/tsc -p tsconfig.json --noEmit
if [[ $FULL == 1 ]]; then PKG=work/pkg-full; node pack/pack.ts --out $PKG | tail -5
else PKG=work/pkg-small; node pack/pack.ts --only '^(Data/System/[^/]*$|Artwork/|System/Config/|Data/Templates/Minimal/)' --out $PKG | tail -3; fi
node test/node-test.ts --pkg $PKG --out work/results-node.json
node test/emscripten-test.ts --pkg $PKG
node test/browser-test.ts --pkg $PKG --out work/results-chrome.json
[[ $FULL == 1 ]] && node test/bench.ts --pkg $PKG --out work/bench-net.json
# 314MB 級 wasm asset (tools/perf/work/huge/k100.wasm) の二段キャッシュ + compileStreaming e2e
node test/asset-e2e.ts
echo "E2E OK"
