#!/usr/bin/env bash
# h6_e2e.sh — HB-H6 (G1) 1 コマンド検収: OTT .rsrc PNG 抽出 → 別算法検算 → host wasm build → 結線検査.
#   前提: emsdk (clang 同梱), python3, node ≥ 22, OTT_vst2_win64.dll ($OTT_DLL か $PLUGINS_DIR/ott/binaries/)。
#   抽出物は work/ (gitignore, 非再配布素材).
set -euo pipefail
H6="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$H6/../../shared/env.sh"
OTT_DLL="${OTT_DLL:-$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll}"
[ -f "$OTT_DLL" ] || { echo "OTT_vst2_win64.dll が無い: $OTT_DLL (oc_artifacts: plugins-ott analysis-ott-binaries)"; exit 3; }
mkdir -p "$H6/work"
echo "[1/4] rsrc 抽出";       node "$H6/rsrc_extract.mjs" "$OTT_DLL" "$H6/work/rsrc"
echo "[2/4] 別算法 (python)"; python3 "$H6/verify_rsrc.py" "$OTT_DLL" "$H6/work/py_scan.json"
echo "[3/4] host wasm build"; bash "$H6/../poc/build_host.sh" >/dev/null
echo "[4/4] 結線検査";        node "$H6/h6_check.mjs" "$OTT_DLL" "$H6/work/py_scan.json"
