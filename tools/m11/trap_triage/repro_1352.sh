#!/usr/bin/env bash
# #1352 (#944 §4(e)): 計測 build (M11_INSTR_413060=1) の OFF が既定 build と違うか、dest 読出し (M11_DEST_READ) が集計を変えるかの再現。
# 直列・単発で 3 回測る: 既定 (計測なし) / 計測 OFF (dest 読出しあり) / 計測 OFF (dest 読出しなし, M11_DEST_READ=0)。
# 判定: 3 回とも 870/24/0 なら PASS (HEAD で 871/23 は再現せず、dest 読出しは集計を変えない)。
# 前提: work/ が m11_gen_ir2.sh で生成済み (work/boot_final.ll・work/ir_conditions.json)、FL_WIN64_DIR 設定済み。
# 使い方: bash tools/m11/trap_triage/repro_1352.sh
set -u
cd "$(dirname "$0")/.."   # tools/m11 へ
export FL_WIN64_DIR="${FL_WIN64_DIR:-}"
OUT=work/repro_1352; mkdir -p "$OUT"
FAIL=0
measure() {  # measure <label> <env...>: build して survey し、判定用の計数を 1 行出す
  local label="$1"; shift
  if ! env "$@" M11_OV_413060=0 M11_NEG_413060=0 timeout 300 bash m11_build.sh > "$OUT/build_$label.log" 2>&1; then
    echo "[repro_1352] build $label FAILED"; FAIL=1; return
  fi
  env "$@" timeout 300 node m11_survey.mjs > "$OUT/survey_$label.out" 2>/dev/null; rc=$?
  if [ "$rc" -ne 0 ]; then echo "[repro_1352] survey $label FAILED (rc=$rc)"; FAIL=1; return; fi
  python3 - "$OUT/survey_$label.out" "$label" <<'PY' || FAIL=1
import json, sys
line = next((l for l in open(sys.argv[1]) if l.startswith('M11_SURVEY ')), None)
if line is None:
    print('[repro_1352] M11_SURVEY 行が無い'); sys.exit(1)
d = json.loads(line[len('M11_SURVEY '):])
ok = d.get('ok') == 870 and d.get('trap') == 24 and d.get('clobber') == 0
print(f"[repro_1352] {sys.argv[2]}: ok={d.get('ok')} trap={d.get('trap')} clobber={d.get('clobber')} "
      f"noproc={d.get('noproc')} miss={d.get('miss')} f413060_calls={d.get('f413060_calls')} "
      f"dest_obs_n={d.get('dest_obs_n')} dest_obs_hash={d.get('dest_obs_hash')} -> {'870/24/0 一致' if ok else '不一致'}")
sys.exit(0 if ok else 1)
PY
}
measure default -u M11_INSTR_413060
measure instr_off M11_INSTR_413060=1 M11_DEST_READ=1
measure instr_off_noread M11_INSTR_413060=1 M11_DEST_READ=0
if [ "$FAIL" -ne 0 ]; then echo "[repro_1352] FAIL"; exit 1; fi
echo "[repro_1352] PASS"
