#!/bin/bash
# LD-18 (#865): trace_head 外の 27 件 (function_414ad0 系 OOB) を trace_head=200 (-v) で単体再走する。
# 入力: 既存 batch jsonl から抽出した "<va> <pattern>" 列 (引数 1、既定 work/m11_414ad0_27/list.txt)。
# 出力: work/m11_414ad0_27/<va>.json (gitignore。集計は tests/oob_414ad0_27.py)。
# 前提: FL_WIN64_DIR (PE は LD_M11_PE)・ANALYSIS_DIR・venv の python (PY) が必要。
set -u
cd "$(dirname "$0")/.."
PY="${PY:-python3}"
OUT=work/m11_414ad0_27
mkdir -p "$OUT"
LIST="${1:-$OUT/list.txt}"
while read -r va pat; do
  timeout 120 "$PY" liftdiff.py run targets/m11.json --fn "$va" --pattern "$pat" --nobuild --state auto --json "$OUT/$va.json" -v >/dev/null 2>&1
  echo "$va $pat rc=$?"
done < "$LIST"
