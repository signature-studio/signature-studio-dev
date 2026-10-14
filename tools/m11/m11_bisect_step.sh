#!/usr/bin/env bash
# M11 sigfix 0 詰め site 数の二分探索 1 段 (#2045): 指定 commit の IR を RetDec から再生成し (m11_e2e.sh --full の IR 段まで)、
# m11_sigfix_stats.sh の終端行を出す。build と node 実行は省く (0 詰め数は work/boot_final.ll から出るため)。1 段 約 6.5 分 (REPORT_N2045.md)。
# 前提: FL_WIN64_DIR (extracted/block00031_PE.bin 入り)、M11_BISECT_GHIDRA_CSV (Ghidra 12.1.4 + JDK 21 で作る functions_dll.csv。
#       作り方は tools/m2/README.md「重い解析」)、python3 (capstone・pefile 入り)、RetDec ([RETDEC]・docs/REFERENCES.md §1)。
# 使い方: bash tools/m11/m11_bisect_step.sh <commit>   (作業は $M11_BISECT_WORK/w-<commit>、既定 $RUNNER_TEMP/m11b)
set -euo pipefail
SHA="${1:?usage: m11_bisect_step.sh <commit>}"
REPO="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
W="${M11_BISECT_WORK:-${RUNNER_TEMP:?RUNNER_TEMP か M11_BISECT_WORK を指定}/m11b}/w-$SHA"
CSV="${M11_BISECT_GHIDRA_CSV:?M11_BISECT_GHIDRA_CSV (functions_dll.csv) を指定}"
export FL_WIN64_DIR="${FL_WIN64_DIR:?FL_WIN64_DIR (fl-win64 の展開先) を指定}"
export PE="$FL_WIN64_DIR/extracted/block00031_PE.bin" M11_PE="$FL_WIN64_DIR/extracted/block00031_PE.bin"
rm -rf "$W"; mkdir -p "$W"
git -C "$REPO" archive "$SHA" | tar -x -C "$W"
mkdir -p "$W/tools/m2/work/ghidra_dll"
cp "$CSV" "$W/tools/m2/work/ghidra_dll/functions_dll.csv"
cd "$W/tools/m11"
mkdir -p work/tmp
L="$W/step.log"
: > "$L"
run() {
  local t0=$SECONDS
  if "$@" >> "$L" 2>&1; then echo "[bisect $SHA] ok ($((SECONDS - t0)) s): $*"; return 0; fi
  echo "[bisect $SHA] FAILED ($((SECONDS - t0)) s): $*"; tail -20 "$L"; exit 1
}
run python3 m11_scan.py
run python3 m11_bounds.py
run bash m11_lift_all.sh
for it in 1 2 3; do
  run python3 m11_tail.py
  run bash m11_lift.sh work/boot_ranges_extra.txt boot4 600
  run bash m11_gen_ir2.sh
done
if [ -f m11_extra_ranges5.txt ]; then
  run bash m11_lift.sh m11_extra_ranges5.txt boot5 600
  run bash m11_gen_ir2.sh
fi
run bash m11_sigfix_stats.sh
echo "[bisect $SHA] $(grep '^\[stats\] zeropad' "$L" | tail -1)"
