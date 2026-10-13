#!/usr/bin/env bash
# PY-12 (#587) ネガティブコントロール: 修正前の flpy.c (static 状態の _flhost) をビルドして subinterp_probe.mjs が FAIL (exit 2) することを確認する。
#   bash tools/python/tests/subinterp_negcontrol_old.sh [<修正前 commit>]   既定 8f55002 (PR #621 merge = PY-12 着手時の main)
#   修正前 probe が FAIL しない (= probe が _flhost 修正を検出できない) 場合は exit 1。検出できたとき exit 0。
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
REV="${1:-8f55002}"
OLD="$HERE/work/flpy_old"; mkdir -p "$OLD"
git -C "$HERE" show "$REV:tools/python/src/flpy.c" > "$OLD/flpy_old.c"
FLPY_SKIP_TABLE=1 FLPY_C="$OLD/flpy_old.c" FLPY_OUT="$OLD/dist" bash "$HERE/build_flpy.sh" >/dev/null
set +e
FLPY_DIST="$OLD/dist" node "$HERE/tests/subinterp_probe.mjs" >"$OLD/probe.out" 2>"$OLD/probe.err"
rc=$?
set -e
echo "old flpy.c ($REV) probe exit=$rc  FAIL 行: $(grep -c '^FAIL ' "$OLD/probe.err")"
grep '^FAIL ' "$OLD/probe.err" | cut -c1-160 || true
[ "$rc" -eq 2 ] || { echo "NEG-CONTROL NOT DETECTED: 修正前ビルドで probe が exit 2 にならない" >&2; exit 1; }
echo "NEG-CONTROL(old flpy.c) DETECTED"
