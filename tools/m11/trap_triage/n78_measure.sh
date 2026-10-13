#!/usr/bin/env bash
# #1275 (M11-N78): ClassCreate ON/OFF で unit 304/555 の kind 遷移を測る。
# 使い方: FL_WIN64_DIR=... RETDEC_ROOT=... EMSDK=... bash tools/m11/trap_triage/n78_measure.sh
# 出力: tools/m11/work/n78/ (gitignore 対象)。判定表は標準出力に出る。
set -euo pipefail
cd "$(dirname "$0")/.."
: "${FL_WIN64_DIR:?FL_WIN64_DIR が必要 (fl-win64 の展開先)}" "${RETDEC_ROOT:?RETDEC_ROOT が必要}" "${EMSDK:?EMSDK が必要}"
mkdir -p work/n78
bash m11_gen_ir2.sh
M11_OV_CLASSCREATE=0 bash m11_build.sh
node trap_triage/survey_units.mjs work/n78/units_off.json
M11_OV_CLASSCREATE=1 bash m11_build.sh
node trap_triage/survey_units.mjs work/n78/units_on.json
M11_OV_CLASSCREATE=1 M11_FIX_535BF2=1 bash m11_build.sh
node trap_triage/survey_units.mjs work/n78/units_on_fix.json
U=304,555,101,190,291,296,923
python3 trap_triage/survey_diff.py work/n78/units_off.json work/n78/units_on.json ${U//,/ }
python3 trap_triage/survey_diff.py work/n78/units_off.json work/n78/units_on_fix.json ${U//,/ }
python3 trap_triage/check_682.py work/n78/units_off.json --units 304,555,923,291,296 || echo "check_682 rc=$? (OFF: 2/5 が期待値)"
