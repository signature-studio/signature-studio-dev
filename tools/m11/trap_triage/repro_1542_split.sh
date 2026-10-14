#!/usr/bin/env bash
# #1542: 計測 build (M11_INSTR_413060=1) の getmem −4 の 3 点切り分け表 (REPORT_1542 §1 の A〜D) を 1 コマンドで再現する。
# 直列・単発で 4 構成を build → survey し、M11_SURVEY 行と boot_final3.ll の md5 を 1 表に集計する。
#   A 既定 (計測 OFF) / B noprobe / C noren / D nodecl (いずれも M11_INSTR_413060=1 + 変種)
# 判定は表示のみ (870/24/0 の一致は各行に出す)。出力は work/split_1542/ (gitignore)。
# 前提: work/ が m11_gen_ir2.sh で生成済み (work/boot_final.ll・work/ir_conditions.json)、FL_WIN64_DIR 設定済み。
# 使い方: bash tools/m11/trap_triage/repro_1542_split.sh [N]   (N = 反復回数・既定 1。決定性の確認は N=3)
set -u
cd "$(dirname "$0")/.."   # tools/m11 へ
export FL_WIN64_DIR="${FL_WIN64_DIR:-}"
N="${1:-1}"
OUT=work/split_1542; mkdir -p "$OUT"
FAIL=0
# measure <rep> <label> <env...>: build → IR md5 → survey → M11_SURVEY を 1 行に要約
measure() {
  local rep="$1" label="$2"; shift 2
  local tag="${label}_r${rep}"
  if ! env "$@" M11_OV_413060=0 M11_NEG_413060=0 timeout 300 bash m11_build.sh > "$OUT/build_$tag.log" 2>&1; then
    echo "[split_1542] build $tag FAILED"; FAIL=1; return
  fi
  cp work/boot_final3.ll "$OUT/ir_$tag.ll"
  local ir_md5; ir_md5=$(md5sum "$OUT/ir_$tag.ll" | cut -c1-8)
  env "$@" timeout 300 node m11_survey.mjs > "$OUT/survey_$tag.out" 2>/dev/null; rc=$?
  if [ "$rc" -ne 0 ]; then echo "[split_1542] survey $tag FAILED (rc=$rc)"; FAIL=1; return; fi
  python3 - "$OUT/survey_$tag.out" "$label" "$rep" "$ir_md5" <<'PY' || FAIL=1
import json, sys
line = next((l for l in open(sys.argv[1]) if l.startswith('M11_SURVEY ')), None)
if line is None:
    print('[split_1542] M11_SURVEY 行が無い'); sys.exit(1)
d = json.loads(line[len('M11_SURVEY '):])
print('\t'.join(str(x) for x in [sys.argv[2], sys.argv[3], sys.argv[4], d.get('ok'), d.get('trap'), d.get('clobber'),
                                 d.get('getmem'), d.get('fastmm_getmem_impl')]))
PY
}
TABLE="$OUT/table.tsv"
: > "$TABLE"
for rep in $(seq 1 "$N"); do
  measure "$rep" A_default -u M11_INSTR_413060 -u M11_PROBE_VARIANT >> "$TABLE"
  measure "$rep" B_noprobe M11_INSTR_413060=1 M11_PROBE_VARIANT=noprobe M11_DEST_READ=1 >> "$TABLE"
  measure "$rep" C_noren M11_INSTR_413060=1 M11_PROBE_VARIANT=noren M11_DEST_READ=1 >> "$TABLE"
  measure "$rep" D_nodecl M11_INSTR_413060=1 M11_PROBE_VARIANT=nodecl M11_DEST_READ=1 >> "$TABLE"
done
echo "構成	回	boot_final3.ll md5	ok	trap	clobber	getmem	fastmm_getmem_impl"
cat "$TABLE"
if [ "$FAIL" -ne 0 ]; then echo "[split_1542] FAIL"; exit 1; fi
echo "[split_1542] done (表: $TABLE)"
