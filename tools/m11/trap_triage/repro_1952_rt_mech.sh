#!/usr/bin/env bash
# #1952: rt.o の計測 flag が getmem −4 を生む機序の切り分け (REPORT_1701 の続き)。
# 基準は C_noren (計測 ON・IR 既定同一)。rt.o 内の静的データの配置 (a) と関数の有無 (b) を対照する。
#   C_noren   : 基準 (2008 を期待)
#   R0_rtOFF  : rt.o 計測 OFF (2012 を期待。関数・データ・EXPORTS を全て外す)
#   R1_rtON   : A + rt.o だけ計測 ON
#   PRE64     : C + g_dest_h より前に 64B の静的 pad (配置だけ動く。量は rt.o の既存データと同じ)
#   PRE4096   : C + 前に 4096B (配置だけ大きく動く)
#   POST64    : C + 後ろに 64B (g_dest_h より後ろの配置は動かず、rt.o 全体の量だけ増える)
#   POST4096  : C + 後ろに 4096B
#   EMPTY     : C + m11_dest_obs の本体だけ空 (関数・静的データは残す)
#   NODATA    : C + 関数 m11_dest_obs は残し、静的データ (g_dest_h・g_rec_*・g_dest_n) を無くす (#2212 の対照)
# 直列・単発。判定は表示のみ。出力は work/split_1952/ (gitignore)。
# #2212: 各構成のリンク map を map_<tag>.txt に残し、g_dest_h・g_rec_*・pad の実アドレス (wasm 上) を表に出す。
# 前提: work/ が m11_gen_ir2.sh 生成済み、FL_WIN64_DIR 設定済み、/opt/emsdk 配置済み。
# 使い方: bash tools/m11/trap_triage/repro_1952_rt_mech.sh [N] [CONFIG...]   (N = 反復回数・既定 1)
set -u
cd "$(dirname "$0")/.."   # tools/m11 へ
export FL_WIN64_DIR="${FL_WIN64_DIR:-}"
N="${1:-1}"; shift || true
ONLY=("$@")
OUT=work/split_1952; mkdir -p "$OUT"
FAIL=0
# measure <rep> <label> <env...>: build → IR md5 → rt.o の g_dest_h 位置 → survey → M11_SURVEY を 1 行に要約
measure() {
  local rep="$1" label="$2"; shift 2
  if [ "${#ONLY[@]}" -gt 0 ]; then
    local hit=0; for o in "${ONLY[@]}"; do [ "$o" = "$label" ] && hit=1; done; [ "$hit" = 1 ] || return 0
  fi
  local tag="${label}_r${rep}"
  if ! env "$@" M11_OV_413060=0 M11_NEG_413060=0 M11_LINK_MAP="$PWD/$OUT/map_$tag.txt" timeout 300 bash m11_build.sh > "$OUT/build_$tag.log" 2>&1; then
    echo "[split_1952] build $tag FAILED"; FAIL=1; return
  fi
  cp work/boot_final3.ll "$OUT/ir_$tag.ll"
  local ir_md5; ir_md5=$(md5sum "$OUT/ir_$tag.ll" | cut -c1-8)
  local undef; undef=$(grep -c 'undefined symbol' work/link.log || true)
  local dpos; dpos=$(llvm-nm -n work/obj/rt.o 2>/dev/null | grep ' g_dest_h$' | awk '{print $1}')
  # #2212: リンク後の実アドレス (wasm 上の VA)。map の .data 内で各シンボルの行を拾う
  local laddr; laddr=$(grep -E '(g_dest_h|g_rec_st|g_rec_len|g_rec_rc|g_rec_h|g_pad_pre|g_pad_post|g_dest_n)$' "$OUT/map_$tag.txt" 2>/dev/null | awk '{printf "%s@%s ", $NF, $1}')
  echo "[split_1952][addr] $tag ${laddr:-none}" >> "$OUT/addr.txt"
  env "$@" timeout 300 node m11_survey.mjs > "$OUT/survey_$tag.out" 2>/dev/null; local rc=$?
  if [ "$rc" -ne 0 ]; then echo "[split_1952] survey $tag FAILED (rc=$rc)"; FAIL=1; return; fi
  python3 - "$OUT/survey_$tag.out" "$label" "$rep" "$ir_md5" "$undef" "${dpos:-none}" <<'PY' || FAIL=1
import json, sys
line = next((l for l in open(sys.argv[1]) if l.startswith('M11_SURVEY ')), None)
if line is None:
    print('[split_1952] M11_SURVEY 行が無い'); sys.exit(1)
d = json.loads(line[len('M11_SURVEY '):])
print('\t'.join(str(x) for x in [sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], d.get('ok'), d.get('trap'), d.get('clobber'),
                                 d.get('getmem'), d.get('fastmm_getmem_impl')]))
PY
}
TABLE="$OUT/table.tsv"
[ "${#ONLY[@]}" -gt 0 ] || { : > "$TABLE"; : > "$OUT/addr.txt"; }
BASE="M11_INSTR_413060=1 M11_PROBE_VARIANT=noren M11_DEST_READ=1"
for rep in $(seq 1 "$N"); do
  measure "$rep" A_default -u M11_INSTR_413060 -u M11_PROBE_VARIANT >> "$TABLE"
  measure "$rep" C_noren $BASE >> "$TABLE"
  measure "$rep" R0_rtOFF $BASE M11_RT_INSTR=0 M11_LINK_INSTR=0 >> "$TABLE"
  measure "$rep" R1_rtON -u M11_INSTR_413060 -u M11_PROBE_VARIANT M11_RT_INSTR=1 >> "$TABLE"
  measure "$rep" PRE64 $BASE M11_RT_PADPRE=64 >> "$TABLE"
  measure "$rep" PRE4096 $BASE M11_RT_PADPRE=4096 >> "$TABLE"
  measure "$rep" POST64 $BASE M11_RT_PADPOST=64 >> "$TABLE"
  measure "$rep" POST4096 $BASE M11_RT_PADPOST=4096 >> "$TABLE"
  measure "$rep" EMPTY $BASE M11_RT_EMPTY=1 >> "$TABLE"
  measure "$rep" NODATA $BASE M11_RT_NODATA=1 >> "$TABLE"
done
echo "構成	回	boot_final3.ll md5	undefined symbol	g_dest_h offset	ok	trap	clobber	getmem	fastmm_getmem_impl"
cat "$TABLE"
if [ "$FAIL" -ne 0 ]; then echo "[split_1952] FAIL"; exit 1; fi
echo "[split_1952] done (表: $TABLE)"
