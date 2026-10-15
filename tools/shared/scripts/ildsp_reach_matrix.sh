#!/bin/bash
# 間接 call 4 件と helper 入口の到達実測 (#4230 / T-SH-103)。
# 用途: ildsp_native の正の対照 (0x1ac9ce・0x1aedc0・0x1b6f6c) と間接 call 4 件の発火を、slot ごとに 1 表で出す。
# 使い方: FL_WIN64_DIR=<展開先> bash tools/shared/scripts/ildsp_reach_matrix.sh [出力先]
#   出力先の既定は tools/shared/work/reach (gitignore)。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
PE="${FL_WIN64_DIR:?FL_WIN64_DIR を設定する}/extracted/block24360_PE.bin"
OUT="${1:-$ROOT/tools/shared/work/reach}"
BIN="$ROOT/tools/shared/work/native/ildsp_native"
mkdir -p "$OUT" "$(dirname "$BIN")"
[ -x "$BIN" ] || gcc -O1 -g -Wall -Wno-unused-function -o "$BIN" "$HERE/ildsp_native.c" || exit 2

run() { # run <tag> <args...>
  local tag="$1"; shift
  timeout 15 "$BIN" "$PE" "$@" > "$OUT/$tag.txt" 2>&1
  local rc=$?
  local hits
  hits="$(grep -oE 'hook_hit site=0x[0-9a-f]+' "$OUT/$tag.txt" | sort | uniq -c | awk '{printf "%s×%s ", $3, $1}')"
  echo "$tag rc=$rc hits: ${hits:-none}"
}

echo "# A. 既定入力 (注入なし・rdx 4 種)"
for k in 1 2 3 4 5; do nv=1; [ $k -le 3 ] && nv=4
  for v in $(seq 0 $((nv-1))); do run "A_k${k}v${v}" --slot $k $v; done; done

echo "# B. 1 回目の HeapAlloc 失敗 (--heap-fail-from 0 --heap-fail-n 1 --newh-zero)"
for k in 1 2 3 4 5; do nv=1; [ $k -le 3 ] && nv=4
  for v in $(seq 0 $((nv-1))); do run "B_k${k}v${v}" --slot $k $v --heap-fail-from 0 --heap-fail-n 1 --newh-zero; done; done

echo "# C. 巨大 rdx (注入なし・--newh-zero)"
for r in 0x100000 0x4000000; do run "C_rdx${r}" --slot 1 0 --rdx $r --newh-zero; done
