#!/usr/bin/env bash
# GUI-12 (#489) 検証: selftest (ASan/UBSan, native headless host) を N 回連続実行する。
#   本体 (修正入り): N 回全て exit 0 でなければ FAIL (exit 1)。
#   ネガコン (-DGUI12_NEGCTL_IMMEDIATE_FREE = 修正前の即 free): NC_N 回のうち ASan heap-use-after-free で落ちる回が 1 回以上なければ FAIL
#     (= この検査が競合を検出できない場合に exit 0 で素通りしない)。
# 使い方: bash tools/gui/test/gui12_race.sh [N=50] [NC_N=30]
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; BUILD="$ROOT/build"; mkdir -p "$BUILD"
N="${1:-50}"; NC_N="${2:-30}"
WORK="${TMPDIR:-/tmp}/gui12_race.$$"; mkdir -p "$WORK"; trap 'rm -rf "$WORK"' EXIT
python3 "$ROOT/gen_api.py" >/dev/null
build() {  # build <out> [extra gcc flags]
  local out="$1"; shift
  gcc -O1 -g -w -fsanitize=address,undefined -fno-sanitize-recover=undefined -pthread "$@" -I "$ROOT/include" -I "$ROOT/src" -I "$BUILD" \
    "$ROOT"/src/gui_platform.c "$ROOT"/src/gui_reach.c "$BUILD"/gui_reach_tab.c "$ROOT"/src/gui_core.c "$ROOT"/src/gui_gdi.c "$ROOT"/src/gui_headless.c "$BUILD"/gui_stubs.c \
    "$HERE/selftest.c" -o "$out" -lm
}
run_n() {  # run_n <bin> <n> <tag> -> echo "fail uaf"
  local bin="$1" n="$2" tag="$3" f=0 u=0
  for i in $(seq 1 "$n"); do
    if ! "$bin" >"$WORK/$tag.$i.log" 2>&1; then f=$((f+1)); grep -q "heap-use-after-free" "$WORK/$tag.$i.log" && u=$((u+1)); fi
  done
  echo "$f $u"
}
build "$WORK/st_fix"
read -r f u < <(run_n "$WORK/st_fix" "$N" fix)
echo "[gui12] fixed : exit!=0 ${f}/${N} (heap-use-after-free ${u}) loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
build "$WORK/st_nc" -DGUI12_NEGCTL_IMMEDIATE_FREE
read -r nf nu < <(run_n "$WORK/st_nc" "$NC_N" nc)
echo "[gui12] negctl: exit!=0 ${nf}/${NC_N} (heap-use-after-free ${nu}) loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
rc=0
[ "$f" -eq 0 ] || { echo "[gui12] FAIL: 修正入りビルドが ${f}/${N} 回失敗"; rc=1; }
[ "$nu" -ge 1 ] || { echo "[gui12] FAIL: ネガコンが use-after-free を 1 回も検出できない (検査が競合を捕捉していない)"; rc=1; }
[ "$rc" -eq 0 ] && echo "[gui12] PASS"
exit "$rc"
