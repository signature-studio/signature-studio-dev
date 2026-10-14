#!/usr/bin/env bash
# #2773: unit 101 (VA 0x1de960) の halt0 (暴走) を commit 単位で再現する (REPORT_679 §9 の再現手順)。
#   使い方: bash trap_triage/unit101_2773.sh <commit> [<file> <parent-commit>]
#   - <commit> の tools/m11 と tools/shared を git archive で $RUNNER_TEMP/unit101_2773/<commit> に展開する (作業ツリーは触らない)
#   - 第 3・第 4 引数を与えると、<file> だけを <parent-commit> の版に差し替える (ablation)
#   - IR を m11_gen_ir2.sh で作り直し、ON (M11_OV_CLASSCREATE=1) で build し、unit survey を取る
#   - 出力: unit 101 の kind・0x41037d / 0x41032e の hit・halt0 の unit 数
#   前提: ${ARTIFACTS_DIR:?}/work-m11.tar.zst と fl-win64.tar.zst が実在 (WORKFLOW §11)。fl-win64 は下の FL_WIN64_DIR に展開済みであること。
set -uo pipefail
C="${1:?commit を指定}"; F="${2:-}"; P="${3:-}"
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
ROOT="${RUNNER_TEMP:-/tmp}/unit101_2773"
D="$ROOT/$C${F:+_abl}"
rm -rf "$D"; mkdir -p "$D"
git -C "$REPO" archive "$C" tools/m11 tools/shared | tar -x -C "$D" || { echo ARCHIVE_FAIL; exit 1; }
if [ -n "$F" ]; then git -C "$REPO" show "$P:$F" > "$D/$F" || { echo SHOW_FAIL; exit 1; }; fi
tar --zstd -xf "${ARTIFACTS_DIR:?}/work-m11.tar.zst" -C "$D" || { echo WORK_FAIL; exit 1; }
cd "$D/tools/m11" || exit 1
export FL_WIN64_DIR="${FL_WIN64_DIR:-$RUNNER_TEMP/fl-win64}"
export M11_PE="$FL_WIN64_DIR/extracted/block00031_PE.bin"
mkdir -p work/trap_triage
uv run --with capstone --with pefile bash m11_gen_ir2.sh > work/gen.log 2>&1 || { echo GEN_FAIL; tail -n 5 work/gen.log; exit 1; }
M11_OV_CLASSCREATE=1 uv run --with capstone --with pefile bash m11_build.sh > work/build_on.log 2>&1 || { echo BUILD_FAIL; tail -n 5 work/build_on.log; exit 1; }
timeout 600 node trap_triage/survey_units.mjs work/trap_triage/on.json > work/on_survey.out 2>&1
echo "C=$C${F:+ ablation=$F(from $P)} $(tail -n 1 work/on_survey.out)"
node -e 'const r=require("./work/trap_triage/on.json"); const u=r.find(x=>x.unit===101); const s=u.icall&&u.icall.sites||{}; console.log("unit101 kind="+u.kind+" 0x41037d="+((s["0x41037d"]||[0])[0])+" 0x41032e="+((s["0x41032e"]||[0])[0]))'
