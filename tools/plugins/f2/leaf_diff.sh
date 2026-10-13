#!/usr/bin/env bash
# PLG-F2-3 (#515) 1 コマンド再現: 「IR leaf かつ機械語にも間接 call 無し」23 関数を tools/liftdiff で native と関数単位差分する。
#   bash tools/plugins/f2/leaf_diff.sh
# 前提: `bash tools/plugins/f2/f2_step1.sh` を実行済み (work/batch/<block>/p.final.ll・p_simd.c・work/f2/<block>.icall.json)。
#       emsdk (/opt/emsdk)、python に numpy capstone pefile (`source f2/env.sh` が pefile+capstone。numpy は uv pip install numpy)
# 出力: work/f2/leaf.json, work/f2/leaf/<block>.jsonl (liftdiff 共有フォーマット = tools/liftdiff/docs/FORMAT.md §3),
#       work/f2/leaf_report.md (stdout にも出す)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"                       # tools/plugins
LD="$ROOT/../liftdiff"
source "$ROOT/../shared/env.sh"
[ -f "$HERE/env.sh" ] && source "$HERE/env.sh"
python3 -c 'import numpy' 2>/dev/null || { [ -n "${VIRTUAL_ENV:-}" ] || VIRTUAL_ENV="${PYTHON_VENV:-${RUNNER_TEMP:-/tmp}/f2venv}"; export VIRTUAL_ENV; uv pip install -q numpy; }
BLOCKS="18953 18975 18979 18982 18984 19005 19006 19013 19058 19059 19145"
SHARDS="${SHARDS:-4}"
mkdir -p "$LD/work/tmp" "$ROOT/work/f2/leaf"
t0=$(date +%s)
python3 "$HERE/leaf_list.py" --expect 23 $BLOCKS
python3 "$HERE/mk_targets.py"
# liftdiff の native ランナ (gcc)。済みなら再ビルドしない
[ -x "$LD/work/ld_native" ] || gcc -O1 -g -w -o "$LD/work/ld_native" "$LD/rt/ld_native.c" "$LD/rt/ld_ms_call.S" -lm
cd "$LD"
for vf in "$ROOT"/work/f2/targets/*.vas; do
  b="$(basename "$vf" .vas)"
  echo "== block $b"
  python3 liftdiff.py batch "$ROOT/work/f2/targets/eqf$b.json" --set "file:$vf" --shards "$SHARDS" \
    --out "$ROOT/work/f2/leaf/$b.jsonl" | tail -12
done
python3 "$HERE/leaf_report.py" --md "$ROOT/work/f2/leaf_report.md"
echo "LEAF_DIFF elapsed $(( $(date +%s) - t0 )) s (load average $(cut -d' ' -f1 /proc/loadavg))"
