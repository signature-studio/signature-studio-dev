#!/usr/bin/env bash
# #513: 巨大 VirtualAlloc 2 件 (unit 368 = 981000 の n / unit 888 = 129f140 の count) の原因を、IR を 1 箇所ずつ直した build で確かめる.
#   fix368: function_980ed0 の `inttoptr i64 22954112` (VA 0x15e4080) を LVA 18759808 (RVA 0x11e4080) に直す (= VA→LVA remap 漏れの 1 件)
#   fix888: function_129f140 の `ptrtoint(inttoptr 18683649)` (= 変数 [0x11d1700] のアドレス+1) を load [0x11d1700] + 1 に直す (= load 脱落の 1 件)
#   構成 base / 888 / 368 / both ごとに build → m11_vabig_probe.mjs で unit 368 / 888 の 64MB 以上の要求数 (va_big) を出す. base が NC (両方出る)。
# 前提: m11_e2e.sh を 1 回実行済み (work/boot_final3.ll, work/m11_image.bin). 作業は $TMPDIR 配下の複製で行い, work/ は変更しない.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
T=${TMPDIR:-/tmp}/m11_vabig_verify
rm -rf "$T"; mkdir -p "$T/tools"
cp -a "$HERE/../shim" "$T/tools/shim"; cp -a "$HERE" "$T/tools/m11"
cd "$T/tools/m11"
cp work/boot_final3.ll work/boot_final3.orig.ll
patch_ir() { # patch_ir <fix368:0|1> <fix888:0|1>
  FIX368=$1 FIX888=$2 python3 - <<'PY'
import os
s = open('work/boot_final3.orig.ll').read()
if os.environ['FIX368'] == '1':
    old = '%ce0n11_function_980ed0 = inttoptr i64 22954112 to ptr'
    assert s.count(old) == 1; s = s.replace(old, '%ce0n11_function_980ed0 = inttoptr i64 18759808 to ptr')
if os.environ['FIX888'] == '1':
    old = '  %ce0n11_function_129f140 = ptrtoint ptr inttoptr (i64 18683649 to ptr) to i64\n'
    assert s.count(old) == 1
    s = s.replace(old, '  %vv_fix = load i32, ptr inttoptr (i64 18683648 to ptr), align 4\n  %vv1_fix = add i32 %vv_fix, 1\n  %ce0n11_function_129f140 = zext i32 %vv1_fix to i64\n')
open('work/boot_final3.ll', 'w').write(s)
PY
  touch work/boot_final3.ll   # m11_build.sh は boot_final3.ll が boot_final.ll / m11_post.py より新しければ post を再実行しない
}
probe() { node m11_vabig_probe.mjs "$1" --pre=0-$(($1 - 1)) 2>&1 | grep -E '^UNIT|VA-big' | tr '\n' ' '; echo; }
for cfg in "base 0 0" "888 0 1" "368 1 0" "both 1 1"; do
  set -- $cfg
  patch_ir "$2" "$3"
  bash m11_build.sh > "work/vabig_build_$1.log" 2>&1 || { echo "build FAILED ($1)"; exit 1; }
  echo "== config $1 (fix368=$2 fix888=$3)"
  echo -n "unit 368: "; probe 368
  echo -n "unit 888: "; probe 888
done
echo "== survey (both)"
M11_SURVEY_UNITS="$T/units_both.json" node m11_survey.mjs 2>&1 | grep -o '"ok":[0-9]*\|"trap":[0-9]*\|"clobber":[0-9]*\|"big_units":\[[^]]*\]\|"va_big":[0-9]*' | tr '\n' ' '; echo
