#!/usr/bin/env bash
# FL Slayer x86 engine の結合方式 (#536): 検査 C1〜C7 → ネガコン N1〜N7 → RetDec 計測 (情報のみ)。
#   bash tools/plugins/slayer_x86/slayer_x86.sh [--skip-probe]
# 非 0 で終わる条件: C のどれかが不合格 / N のどれかが「壊したのに別検査が落ちる・落ちない」。
# 前提素材: fl-win64 (+ 計測は toolchain-retdec / toolchain-emsdk)。 docs/WORKFLOW.md §11
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../synth/env.sh"
S=$(date +%s)
python3 "$HERE/slayer_x86.py"
python3 "$HERE/slayer_x86.py" --nega
if [ "${1:-}" != "--skip-probe" ]; then
  python3 "$HERE/slayer_x86.py" --probe-retdec "${RUNNER_TEMP:-/tmp}/slayer_x86_probe"
fi
echo "[slayer_x86.sh] OK ($(( $(date +%s) - S )) s, load $(cut -d' ' -f1-3 /proc/loadavg))"
