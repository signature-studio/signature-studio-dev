#!/usr/bin/env bash
# #3482: unit 別の probe trace ([probe_free] / [probe_list] / [probe_grow]) を取る。
# m11_survey.mjs は printErr を errs に溜めるだけで stderr に出さないため、printErr を stderr に流し、
# 各 unit の直前に "[UNIT] <i>" を出す複製 (work/m11_survey_trace.mjs) で survey を回す。
# 前提: 直前に M11_PROBE_LIST=1 で m11_build.sh を走らせ、work/m11_boot.cjs が probe 入りであること。
# 使い方: cd tools/m11 && bash trap_triage/probe_trace.sh > $RUNNER_TEMP/trace.out 2> $RUNNER_TEMP/trace.err
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'PY'
import os
src = open('m11_survey.mjs').read()
here = os.getcwd()
def rep(a, b):
    global src
    assert src.count(a) == 1, a
    src = src.replace(a, b)
rep("const M11 = new URL('./', import.meta.url).pathname.replace(/\\/$/, '');", "const M11 = %r;" % here)
rep("from './m11_ptrcheck.mjs'", "from %r" % (here + '/m11_ptrcheck.mjs'))
rep("errs.push(String(s)); }", "errs.push(String(s)); process.stderr.write(String(s) + '\\n'); }")
rep("  const va = hex(i);\n", "  process.stderr.write('[UNIT] ' + i + '\\n');\n  const va = hex(i);\n")
open('work/m11_survey_trace.mjs', 'w').write(src)
PY
node work/m11_survey_trace.mjs
