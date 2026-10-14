#!/usr/bin/env bash
# lowbase_e2e.sh — CAB-220 (liftlib への lowbase 取り込み) 1 コマンド検証.
#
#   bash tools/liftlib/lowbase_e2e.sh [--quick] [--full]
#
#   [1] audit_va.py <dll> 0x10000 : DIR64 補正漏れ 0 / IAT に VA 0 / LB_BASE>=64KiB (exit code 判定)
#   [2] liftlib pipeline で OTT を低位 base で「最初から」生成 (newbase=LB_BASE) →
#       m10_e2e 相当 (checks 7/broken 0, band 係数 maxdev 0, OOB 不発) + 元 m10 成果物 (864MiB) と
#       出力 SHA 42 組合せ突合。base 0x10000 / 0x1230000 の 2 構成 = base 依存バグ (固定アドレス残存) の検出
#   [3] x64c (tools/ott bit-exact lifter) の native 実機械語 vs wasm を 3 構成
#       (0x10000/16MiB, 0x1230000/40MiB, 0x10000/8MiB) × 89 scenario = 267 run / 150,708 cell の
#       bit 一致を再現 (tools/hostbridge/lowbase の成果物と同じ水準。成果物は work/x64c_* に分離)
#   --full : 追加で tools/hostbridge/lowbase/lowbase_e2e.sh 全体 (RetDec chain + 同居 + Chrome) を走らせる
#
# 前提 (読取のみ): tools/m6/work の OTT lift 成果物, tools/m10/work/ott_m10.{ll,cjs},
#                 tools/hostbridge/lowbase (audit_va.py / build_x64c.sh / diff/matrix.py), python3 (capstone, pefile)
#                 libottnative.so は [3] で tools/ott/native/build.sh が HEAD ソースから作る (素材の .so は古い場合がある)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; T="$HERE/.."; LB="$T/hostbridge/lowbase"
source "$T/shared/env.sh"
DLL="${OTT_DLL:-$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll}"
[ -f "$DLL" ] || { echo "[lowbase_e2e] $DLL 無し (PLUGINS_DIR / OTT_DLL を確認)" >&2; exit 2; }
QUICK=""; FULL=0
for a in "$@"; do case "$a" in --quick) QUICK="--quick";; --full) FULL=1;; esac; done
export PATH="$PATH:/opt/emsdk/node/24.19.0_64bit/bin"
NODE="$(command -v node || true)"; [ -n "$NODE" ] || { echo "node 無し" >&2; exit 2; }
export NODE
# emcc の中間ファイルを tmpfs (/tmp 3.7GB, 他 session と取り合い) から担当 dir の work へ隔離
export TMPDIR="$HERE/work/tmp"; mkdir -p "$TMPDIR"
cd "$HERE"; mkdir -p work
RC=0
step() { echo; echo "== $*"; }
chk() { if [ "$1" = 0 ]; then echo "   -> PASS: $2"; else echo "   -> FAIL: $2"; RC=1; fi; }
SUM="$HERE/work/lowbase_summary.txt"; : > "$SUM"; say() { echo "$*" | tee -a "$SUM"; }

step "[1] audit_va.py: VA 整数の静的監査 (LB_BASE=0x10000)"
python3 "$LB/audit_va.py" "$DLL" 0x10000 > work/audit_va.json; chk $? "補正漏れ候補 0 (DIR64 先 image 外 0 / IAT に VA 0 / base>=64KiB)"
python3 -c "
import json; a=json.load(open('work/audit_va.json'))
print('   reloc DIR64 %d (全て image 内), image 範囲 qword %d (うち reloc 外の非ポインタ類似 %d), IAT %d slot (VA 保持 %d)' % (
  a['reloc_dir64_total'], sum(s['image_range_qwords'] for s in a['sections'].values()),
  a['non_pointer_lookalikes_not_in_reloc'], a['iat_slots'], a['iat_slots_holding_image_VA']))"

step "[2] liftlib pipeline: OTT を低位 base で最初から生成 → e2e + 元 m10 成果物と出力 SHA 突合"
for B in 0x10000 0x1230000; do
  python3 -m liftlib ott --lb-base "$B" > "work/ott_lb_$B.log" 2>&1
  chk $? "ott --lb-base $B : $(grep -o 'checks .* | trap rc=[0-9]*' "work/ott_lb_$B.log" | tail -1 | cut -c1-90) | $(grep -o '"f0_equal": [0-9]*, "f0_total": [0-9]*' "work/ott_lb_$B.log" | tail -1)"
  say "liftlib ott --lb-base $B: $(grep 'RESULT: PASS' "work/ott_lb_$B.log" >/dev/null && echo PASS || echo FAIL) / $(grep -o 'layout: {[^}]*}' "work/ott_lb_$B.log" | head -1)"
done

step "[3] x64c native bit 一致の再現: 3 構成 × 89 scenario (150,708 cell)"
bash "$T/ott/native/build.sh" > "work/build_native.log" 2>&1; chk $? "libottnative.so を HEAD ソースから再ビルド (tools/ott/native/build.sh・素材の .so は使わない)"
TOT=0
for spec in "0x10000 16" "0x1230000 40" "0x10000 8"; do
  set -- $spec; B=$1; MI=$2
  OUT="work/x64c_lb_${B}_mi${MI}"
  LB_BASE=$B LB_INIT_MIB=$MI LB_OUT="$HERE/$OUT" bash "$LB/x64c/build_x64c.sh" > "work/build_x64c_${B}_${MI}.log" 2>&1
  chk $? "build x64c base=$B init=${MI}MiB"
  eval "$(cat "$OUT/layout.sh")"
  # matrix は spec 中間ファイルを /tmp/opencode (tmpfs, 他 session と取り合い) に置く。
  # 失敗は tmpfs 一時圧力が主因のため最大 3 回リトライする (一時 dir の一括削除は
  # 並行稼働する他 session の matrix と干渉するため行わない)
  RCX=1; LOG="work/matrix_${B}_${MI}.log"
  for i in 1 2 3; do
    LB_BASE=$B LB_ARENA=$LB_ARENA LB_ARENA_SIZE=$LB_ARENA_SIZE python3 "$LB/x64c/diff/matrix.py" "$HERE/$OUT/ottl.cjs" $QUICK > "$LOG" 2>&1 && { RCX=0; break; }
    echo "   (matrix retry $i: $(tail -1 "$LOG" | cut -c1-110))"
  done
  chk $RCX "matrix base=$B init=${MI}MiB: $(tail -1 "$LOG" | sed 's/^\[matrix\] //' | cut -c1-120)"
  C=$(tail -1 "$LOG" | sed -n 's/.*total cells \([0-9]*\).*/\1/p'); C=${C:-0}
  TOT=$((TOT + C))
  say "x64c base=$B initial=${MI}MiB: $(tail -1 "$LOG" | sed 's/^\[matrix\] //' | cut -c1-120)"
done
say "x64c 合計: 3 構成 / $TOT cells (期待 150,708)"
[ "$TOT" = 150708 ]; chk $? "3 構成合計 150,708 cell bit 一致 (max_ulp 0 / state_diff 0)"

if [ "$FULL" = 1 ]; then
  step "[4] tools/hostbridge/lowbase/lowbase_e2e.sh 全体 (RetDec chain + 同居 + Chrome)"
  bash "$LB/lowbase_e2e.sh" 2>&1 | tee work/lowbase_full.log | grep -E "^== |ALL PASS|FAIL" | tail -30
  chk ${PIPESTATUS[0]} "lowbase_e2e (CAB-90 成果物の全試験)"
fi

echo; echo "================ SUMMARY"; cat "$SUM"
[ $RC = 0 ] && echo "[liftlib lowbase_e2e] ALL PASS" || echo "[liftlib lowbase_e2e] FAIL (上の FAIL 行を参照)"
exit $RC
