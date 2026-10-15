#!/usr/bin/env bash
# WIN-33 (#3556) 再現: 既定 spike / 実カタログ供給 spike / cfi の命令 trace と範囲検査の値 V の履歴。
# 素材: fl-win64 (FL_WIN64_DIR)。出力は work/flelift/win33/ (gitignore・commit しない)。
# 使い方: FL_WIN64_DIR=<展開先> bash tools/liftdiff/win33_catalog.sh   (約 2 分)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
: "${FL_WIN64_DIR:?fl-win64 を展開して FL_WIN64_DIR を設定する}"
CAT="$FL_WIN64_DIR/extracted/block25158_DATA.bin"
OUT=work/flelift/win33
mkdir -p "$OUT"
echo "== [1/4] 既定 spike (LD_CATALOG_MO 未指定)"
python3 spike_cfi.py targets/flelift.json | grep "^\[spike\] CreateF\|units_run"
cp work/flelift/spike_cfi.json "$OUT/default_spike_cfi.json"
echo "== [2/4] 実カタログ spike (LD_CATALOG_MO=block25158)"
LD_CATALOG_MO="$CAT" python3 spike_cfi.py targets/flelift.json | grep "^\[spike\] CreateF\|units_run"
cp work/flelift/spike_cfi_cat.json "$OUT/catalog_spike_cfi.json"
TRACE_ENV=(LD_CATALOG_MO="$CAT" LD_STEP_N=80000000 LD_STEP_ID=cfi LD_STEP_OUT="$HERE/$OUT/step" LD_RUNNER_TMO=900 LD_CASE_TMO_US=800000000)
echo "== [3/4] cfi 命令 trace 1 回目: V のアドレス (最後の範囲検査入口の r9) を求める"
rm -f "$OUT/step.cfi"
env "${TRACE_ENV[@]}" LD_STEP_MEM=7fffffffe000 python3 spike_cfi.py targets/flelift.json > /dev/null
VADDR="$(grep '^17b70 ' "$OUT/step.cfi" | tail -1 | awk '{print $11}')"
rm -f "$OUT/step.cfi"
echo "   V = [r9] のアドレス: 0x$VADDR (スタック。環境変数長で変わる)"
echo "== [4/4] cfi 命令 trace 2 回目: LD_STEP_MEM=$VADDR で V の書込み履歴"
env "${TRACE_ENV[@]}" LD_STEP_MEM="$VADDR" python3 spike_cfi.py targets/flelift.json | grep "^\[spike\] CreateF"
python3 win33_trace.py trace "$OUT/step.cfi"
