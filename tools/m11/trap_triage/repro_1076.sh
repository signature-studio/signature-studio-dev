#!/usr/bin/env bash
# #1076: M2p ON survey の停止位置の二分探索 (REPORT_1076.md §3 の再現)。
# 前提: FL_WIN64_DIR (fl-win64 展開先) / [RETDEC] / [EMSDK] (docs/REFERENCES.md) / tools/m11/work (work-m11 展開) が要る。
set -u
cd "$(dirname "$0")/.."
export FL_WIN64_DIR="${FL_WIN64_DIR:?FL_WIN64_DIR を指定}"
export ANALYSIS_DIR="${ANALYSIS_DIR:-$FL_WIN64_DIR/..}"
mkdir -p work/trap_triage

run() { # $1=ラベル $2=SV_ONLY の unit 列
  local out="work/trap_triage/$1.json"
  SV_ONLY="$2" timeout 60 node trap_triage/survey_units.mjs "$out" > "work/trap_triage/$1.log" 2>&1
  echo "$1 rc=$? $(tail -1 "work/trap_triage/$1.log")"
}

# OFF / ON の build は m11_gen_ir2.sh と m11_build.sh を M11_M2P の有無で切り替えて行う (REPORT_1076 §1)
run u880_alone      "880"
run skip880         "$(seq -s, 0 941 | tr ',' '\n' | grep -vx 880 | paste -sd, -)"
run prefix_0_830_880 "$(seq -s, 0 830),880"
run prefix_0_829_880 "$(seq -s, 0 829),880"
run only_830_880    "830,880"
run prefix_0_830    "$(seq -s, 0 830)"
