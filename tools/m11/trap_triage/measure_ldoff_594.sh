#!/usr/bin/env bash
# #1041 受入 1: ldfix=disabled の IR で 8cc190 系 (unit 56, 58-63) の状態を測る測定専用手順.
#   m11_build.sh は ldfix!=applied を既定で拒否する (#680)。拒否は外さず、既存の opt-in M11_ALLOW_LDFIX_DISABLED=1 (#1165) だけで build する.
#   usage: FL_WIN64_DIR=<fl-win64 の展開先> bash trap_triage/measure_ldoff_594.sh
#   前提: work/ に work-m11 の展開 (boot_final.ll), PE ($FL_WIN64_DIR/extracted/block00031_PE.bin), capstone/pefile.
#   生成物は work/negctl_594/ldoff_* のみ。work/boot_final.ll は ldfix=disabled のままになる (negctl_594.sh は冒頭で IR を作り直す).
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
OUT=work/negctl_594; mkdir -p "$OUT"
PE="${PE:-${FL_WIN64_DIR:-}/extracted/block00031_PE.bin}"; export PE FL_WIN64_DIR
[ -n "${FL_WIN64_DIR:-}" ] && [ -f "$PE" ] || { echo "FAIL: 前提 PE 無し ($PE)" >&2; exit 1; }
python3 -c 'import capstone, pefile' 2>/dev/null || { echo "FAIL: 前提 capstone/pefile 無し" >&2; exit 1; }
M11_LDFIX=0 bash m11_gen_ir2.sh > "$OUT/ldoff_gen.log" 2>&1 || { echo "FAIL: m11_gen_ir2.sh (M11_LDFIX=0) rc!=0 ($OUT/ldoff_gen.log)" >&2; exit 1; }
[ "$(python3 m11_cond.py --get ldfix)" = disabled ] || { echo "FAIL: ir_conditions.json ldfix が disabled でない" >&2; exit 1; }
M11_ALLOW_LDFIX_DISABLED=1 M11_QSTORE=0 bash m11_build.sh > "$OUT/ldoff_build.log" 2>&1 || { echo "FAIL: m11_build.sh (ldfix=disabled, qstore 無し) rc!=0" >&2; tail -3 "$OUT/ldoff_build.log" >&2; exit 1; }
s=$(date +%s.%N)
SV_TRACE_AT=99999 node trap_triage/survey_units.mjs "$OUT/ldoff.json" > "$OUT/ldoff.out" 2> "$OUT/ldoff.err"
e=$(date +%s.%N)
printf 'survey %.1fs load=%s %s\n' "$(echo "$e - $s" | bc)" "$(cut -d' ' -f1-3 /proc/loadavg)" "$(grep -a SURVEY_UNITS "$OUT/ldoff.out" | head -1)"
python3 - "$OUT/ldoff.json" <<'PY'
import json, sys
d = {r['unit']: r for r in json.load(open(sys.argv[1]))}
kinds = {u: d[u]['kind'] if u in d else 'missing' for u in range(56, 64)}
print('ldfix=disabled kinds 56..63 =', kinds)
print('58..63 all ok:', all(kinds[u] == 'ok' for u in range(58, 64)))
PY
