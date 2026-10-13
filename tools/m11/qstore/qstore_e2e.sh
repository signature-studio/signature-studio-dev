#!/usr/bin/env bash
# qstore e2e (#516, 1 コマンド再現): 64bit スタック局所の即値 store が 4B に縮む欠陥 (D17 案) の検出 + 修復 + ネガコン
#   使い方: bash tools/m11/qstore/qstore_e2e.sh     (所要は REPORT.md §4. 前提は m11_e2e.sh と同じ + capstone/pefile)
#   1. gen_ir2 で IR を作り直し → 検出のみ (qstore/results/qstore_detect.json, qstore_sites.tsv)
#   2. ネガコン: M11_QSTORE=0 で build → idx 87/898 の unit probe (survey と同手順, 101/144 を skip) + survey 全体
#   3. 修復   : gen_ir2 から作り直し M11_QSTORE=1 で build → 同じ測定
#   最後に 3. の状態を work/ に残す。常に exit 0。
set -u
cd "$(dirname "$0")/.."
source ../shared/env.sh   # FL_WIN64_DIR (既定は従来どおり /home/ubuntu/work/analysis/win64)
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
PE="${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
mkdir -p work qstore/results
say() { echo "[qstore_e2e] $*"; }
survey() { # survey <label>
  M11_SURVEY_UNITS="$PWD/work/survey_units_$1.json" timeout 600 node m11_survey.mjs > "work/qstore_survey_$1.out" 2>&1
  python3 - "$1" <<'PY'
import json, re, sys
t = open('work/qstore_survey_%s.out' % sys.argv[1]).read()
d = json.loads(re.search(r'M11_SURVEY (\{.*\})', t).group(1))
u = json.load(open('work/survey_units_%s.json' % sys.argv[1]))
print('[qstore_e2e] survey %s: ok=%d trap=%d miss=%d noproc=%d; idx87=%s idx898=%s' % (sys.argv[1], d['ok'], d['trap'], d['miss'], d['noproc'], u[87], u[898]))
PY
}
probe() { M11_PROBE_UNITS=87,898 M11_PROBE_SKIP=101,144 node qstore/unit_probe.mjs 2>&1 | grep -E '^unit' | sed 's/^/[qstore_e2e] probe(skip 101,144) /'; }

say "gen_ir2 (IR 作り直し)"; bash m11_gen_ir2.sh > work/qstore_gen_ir2.log 2>&1 || say "gen_ir2 FAILED"
say "検出のみ (pre-pass IR)"
python3 qstore/m11_qstore.py work/boot_final.ll work/qstore_detect.tmp.ll --pe "$PE" --detect-only \
  --report qstore/results/qstore_detect.json --sites qstore/results/qstore_sites.tsv && rm -f work/qstore_detect.tmp.ll
awk -F'\t' 'NR>1{c[$4]++} END{for(k in c) print "[qstore_e2e] verdict " k "=" c[k]}' qstore/results/qstore_sites.tsv | sort

say "NC: M11_QSTORE=0"
M11_QSTORE=0 bash m11_build.sh > work/qstore_build_nc.log 2>&1 || say "build(nc) FAILED"
probe; survey nc

say "修復: gen_ir2 から作り直し M11_QSTORE=1"
bash m11_gen_ir2.sh > work/qstore_gen_ir2.log 2>&1 || say "gen_ir2 FAILED"
M11_QSTORE=1 bash m11_build.sh > work/qstore_build_fix.log 2>&1 || say "build(fix) FAILED"
cat work/qstore.log
probe; survey fix
exit 0
