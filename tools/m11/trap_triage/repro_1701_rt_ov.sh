#!/usr/bin/env bash
# #1701: 計測 build の getmem −4 (REPORT_1542) を C 側の計測 flag ごとに帰属させる。
# 同じ IR (C = M11_PROBE_VARIANT=noren 系で A と IR 同一) を土台に、rt.o / ov.o / リンク時 EXPORTS の計測 flag を 1 つずつ既定 (OFF) に戻す。
#   A_default : 計測 OFF (既定)
#   C_noren   : 計測 ON・IR を既定と同一 (REPORT_1542 の C。基準 2008)
#   R0_rtOFF  : C + rt.o を計測 OFF。rt.o の m11_dest_obs_* が無くなるので EXPORTS も外す (外さないと emcc が未定義 export で失敗する)
#   O0_ovOFF  : C + ov.o だけ計測 OFF
#   L0_lnkOFF : C + リンク時 EXPORTS (_m11_dest_obs_* 等) だけ外す
#   R1_rtON   : A + rt.o だけ計測 ON (post は既定のまま)
# 直列・単発。判定は表示のみ。出力は work/split_1701/ (gitignore)。
# 前提: work/ が m11_gen_ir2.sh で生成済み、FL_WIN64_DIR 設定済み、[EMSDK] 配置済み。
# 使い方: bash tools/m11/trap_triage/repro_1701_rt_ov.sh [N]   (N = 反復回数・既定 1)
set -u
cd "$(dirname "$0")/.."   # tools/m11 へ
export FL_WIN64_DIR="${FL_WIN64_DIR:-}"
N="${1:-1}"
OUT=work/split_1701; mkdir -p "$OUT"
FAIL=0
# measure <rep> <label> <env...>: build → IR md5 → survey → M11_SURVEY を 1 行に要約
measure() {
  local rep="$1" label="$2"; shift 2
  local tag="${label}_r${rep}"
  if ! env "$@" M11_OV_413060=0 M11_NEG_413060=0 timeout 300 bash m11_build.sh > "$OUT/build_$tag.log" 2>&1; then
    echo "[split_1701] build $tag FAILED"; FAIL=1; return
  fi
  cp work/boot_final3.ll "$OUT/ir_$tag.ll"
  local ir_md5; ir_md5=$(md5sum "$OUT/ir_$tag.ll" | cut -c1-8)
  local undef; undef=$(grep -c 'undefined symbol' work/link.log || true)
  env "$@" timeout 300 node m11_survey.mjs > "$OUT/survey_$tag.out" 2>/dev/null; rc=$?
  if [ "$rc" -ne 0 ]; then echo "[split_1701] survey $tag FAILED (rc=$rc)"; FAIL=1; return; fi
  python3 - "$OUT/survey_$tag.out" "$label" "$rep" "$ir_md5" "$undef" <<'PY' || FAIL=1
import json, sys
line = next((l for l in open(sys.argv[1]) if l.startswith('M11_SURVEY ')), None)
if line is None:
    print('[split_1701] M11_SURVEY 行が無い'); sys.exit(1)
d = json.loads(line[len('M11_SURVEY '):])
print('\t'.join(str(x) for x in [sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], d.get('ok'), d.get('trap'), d.get('clobber'),
                                 d.get('getmem'), d.get('fastmm_getmem_impl')]))
PY
}
TABLE="$OUT/table.tsv"
: > "$TABLE"
for rep in $(seq 1 "$N"); do
  measure "$rep" A_default -u M11_INSTR_413060 -u M11_PROBE_VARIANT >> "$TABLE"
  measure "$rep" C_noren M11_INSTR_413060=1 M11_PROBE_VARIANT=noren M11_DEST_READ=1 >> "$TABLE"
  measure "$rep" R0_rtOFF M11_INSTR_413060=1 M11_PROBE_VARIANT=noren M11_DEST_READ=1 M11_RT_INSTR=0 M11_LINK_INSTR=0 >> "$TABLE"
  measure "$rep" O0_ovOFF M11_INSTR_413060=1 M11_PROBE_VARIANT=noren M11_DEST_READ=1 M11_OV_INSTR=0 >> "$TABLE"
  measure "$rep" L0_lnkOFF M11_INSTR_413060=1 M11_PROBE_VARIANT=noren M11_DEST_READ=1 M11_LINK_INSTR=0 >> "$TABLE"
  measure "$rep" R1_rtON -u M11_INSTR_413060 -u M11_PROBE_VARIANT M11_RT_INSTR=1 >> "$TABLE"
done
echo "構成	回	boot_final3.ll md5	undefined symbol	ok	trap	clobber	getmem	fastmm_getmem_impl"
cat "$TABLE"
if [ "$FAIL" -ne 0 ]; then echo "[split_1701] FAIL"; exit 1; fi
echo "[split_1701] done (表: $TABLE)"
