#!/usr/bin/env bash
# LD-101 (#2277): 候補 batch jsonl の集計と trace_diverge_418be0 の実行を 1 コマンドで行う。
#   bash tools/liftdiff/ld101_aggregate.sh [BATCH_CLOSURE.jsonl]
# 既定入力 = tools/liftdiff/work/2277/batch_closure.jsonl (work-liftdiff の展開先・commit しない)。
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
jsonl=${1:-$here/work/2277/batch_closure.jsonl}
if [ ! -f "$jsonl" ]; then
  echo "input not found: $jsonl (素材 work-liftdiff が必要)" >&2
  exit 2
fi
python3 "$here/liftdiff.py" summary "$jsonl"
python3 "$here/tests/trace_diverge_418be0.py" "$jsonl"
