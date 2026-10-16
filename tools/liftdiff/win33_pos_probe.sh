#!/usr/bin/env bash
# WIN-53 (#4713) 再現: default.moe の読取り関数 (rva 0x4d85d0) の呼出元と、その Stream の Position [obj+0x18] の変化を trace で実測する。
# 素材: fl-win64 (FL_WIN64_DIR)。出力は tools/liftdiff/work/flelift/win33/ (gitignore・commit しない)。
# 前提生成物 (本 script は生成しない。先に用意する):
#   - tools/m11/work/boot_final3.ll (targets/flelift.json の ir): bash tools/m11/m11_e2e.sh --full (FL_WIN64_DIR 必要)。素材 work-m11 でも可
#   - tools/flelift/work/lift/{fle_lifted.c,fle_data.c,lift_meta.json} (clift_sources・clift_data・clift_meta): FL_WIN64_DIR=<展開先> bash tools/flelift/fle_lift.sh (emsdk 必要。EMSDK_ENV で指定)
# 使い方: FL_WIN64_DIR=<展開先> bash tools/liftdiff/win33_pos_probe.sh
# 時間: 上の前提生成を除いた本 script の実測は作者の run で約 3 分 (前提生成の時間は含まない)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
: "${FL_WIN64_DIR:?fl-win64 を展開して FL_WIN64_DIR を設定する}"
CAT="$FL_WIN64_DIR/extracted/block25158_DATA.bin"
OUT=work/flelift/win33
mkdir -p "$OUT"
TRACE_ENV=(LD_CATALOG_MO="$CAT" LD_STEP_N=80000000 LD_STEP_ID=cfi LD_STEP_OUT="$HERE/$OUT/pos" LD_RUNNER_TMO=900 LD_CASE_TMO_US=800000000)
echo "== [1/2] trace 1 回目: 読取り関数 rva 0x4d862a の rcx (Stream オブジェクト) を求める"
rm -f "$OUT/pos.cfi"
env "${TRACE_ENV[@]}" LD_STEP_MEM=7fffffffe000 python3 spike_cfi.py targets/flelift.json > /dev/null
OBJ="$(awk '$1=="4d862a"{print $3; exit}' "$OUT/pos.cfi")"
rm -f "$OUT/pos.cfi"
POS="$(printf '%x' $((0x$OBJ + 0x18)))"
echo "   Stream = 0x$OBJ / Position = 0x$POS (スタックでないヒープ。環境で変わらない想定だが再確認する)"
echo "== [2/2] trace 2 回目: LD_STEP_MEM=$POS で Position の変化を記録"
env "${TRACE_ENV[@]}" LD_STEP_MEM="$POS" python3 spike_cfi.py targets/flelift.json | grep "^\[spike\] CreateF" || true
echo "   呼出元と読取りの行 (trace 行は rva 16 進):"
awk '$1=="4e1879"||$1=="4e13f0"||$1=="4e146b"||$1=="4d85d0"||$1=="4d862a"||$1=="4d8642"||$1=="113b90"{print}' "$OUT/pos.cfi" | head -20 | cut -c1-120
echo "   Position の MEM 行:"
grep '^MEM ' "$OUT/pos.cfi" | cut -c1-160 || true
