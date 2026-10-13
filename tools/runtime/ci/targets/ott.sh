# wasm64_check.sh の target 定義: OTT DSP (M10 lifted IR)。source 専用。
# 入力 IR は tools/m10/m10_build.sh の産物 (tools/m10/work/ott_m10.ll)。無ければ先に m10_build.sh を実行する。
_R="$REPO_ROOT/tools"
TARGET_CWD="$_R/m6"
EXPECT_HASHES="824c6c48,cdd4ee04"   # setup(0.5), setup(0.1) の出力 FNV-1a (tools/runtime/REPORT.md)
ir_path() { echo "$_R/m10/work/ott_m10.ll"; }
build_inputs() {
  printf '%s\n' msimd6.c work/m6_stubs.c work/m6_data.c ../shim/src/heap.c ../shim/src/failfast.c m6_rt.c \
    work/m6_stubs_hand.c work/m6_stubs_hand2.c "$_R/m8/m8_rt.c" "$_R/m9/m9_rt.c" "$_R/m10/m10_boot.c"
}
build_flags() {
  printf '%s\n' -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 -sENVIRONMENT=web,worker,node
  python3 - "$_R/m6/m6_build.sh" <<'PY'
import re,sys
print(re.search(r'-sEXPORTED_FUNCTIONS=\S+', open(sys.argv[1]).read()).group(0))
PY
}
driver_path() { echo "$REPO_ROOT/tools/runtime/bench/ott_driver.mjs"; }
