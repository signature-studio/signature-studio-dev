#!/usr/bin/env bash
# license_obs の 1 コマンド e2e (#107)。 usage: bash tools/startup/license_obs/license_obs.sh
#   1) venv 準備 (pefile capstone unicorn; 作成済みなら省略)  2) 登録フラグの全サイト走査 + gradeChar の連続形/レジスタ追跡形の走査  3) unit 初期化節 (VM ハンドラ表) → 0x10c7cd0 の実機械語実行  4) 検算 (verify.py; ilreg reader.mjs の judge() と突合するため node が要る)
# 前提: FL_WIN64_DIR/extracted/block00031_PE.bin が在る (素材 fl-win64)。
set -euo pipefail
cd "$(dirname "$0")"
. ./env.sh
command -v node >/dev/null || { echo "[license_obs] node が無い (verify.py の judge 突合に必要)" >&2; exit 2; }
PE="$FL_WIN64_DIR/extracted/block00031_PE.bin"
[ -f "$PE" ] || { echo "[license_obs] $PE が無い (fl-win64 を展開して FL_WIN64_DIR を設定)" >&2; exit 2; }
step() { echo "[license_obs] $*"; }
if [ ! -x "$LICENSE_OBS_VENV/bin/python" ]; then
  step "1/4 venv"; uv venv -q "$LICENSE_OBS_VENV"; uv pip install -q --python "$LICENSE_OBS_VENV/bin/python" pefile capstone unicorn
fi
PY="$LICENSE_OBS_VENV/bin/python"
step "2/4 scan_consumers";  "$PY" scan_consumers.py
step "3/4 run_cases";       "$PY" run_cases.py
step "4/5 verify";          "$PY" verify.py
step "5/5 escaped (#1220)";   "$PY" probe_1220.py --write
step "ALL OK"
