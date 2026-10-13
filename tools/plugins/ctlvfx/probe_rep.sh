#!/usr/bin/env bash
# 候補修復の到達性だけを見る探針: framework 側の fw_rep.py (rep string 命令 helper を fw_rep_* へ正規化) を plugin の final.ll に当てると、
# 未実装 helper `__asm_rep_*` の宣言が消え、`emcc -c` が通るか。 正しさ (fw_rt.c の実装との意味一致) は見ていない。
#   bash tools/plugins/ctlvfx/probe_rep.sh [block=21206]    (事前: ctlvfx_e2e.sh 実行済み)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B="${1:-21206}"; T=work/ctlvfx/probe_rep; rm -rf "$T"; mkdir -p "$T/tmp"
IN="work/batch/$B/p.final.ll"
python3 framework/fw_rep.py "$IN" "$T/rep.ll" > "$T/fw_rep.log" 2>&1
cnt() { grep -c "$1" "$2" || true; }
echo "block=$B  @__asm_rep_ の出現: before=$(cnt '@__asm_rep_' "$IN") after=$(cnt '@__asm_rep_' "$T/rep.ll")  @fw_rep_ の出現: before=$(cnt '@fw_rep_' "$IN") after=$(cnt '@fw_rep_' "$T/rep.ll")"
( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; TMPDIR="$T/tmp" emcc -c "$T/rep.ll" -o "$T/rep.o" -w -O0 -msimd128 > "$T/emcc.log" 2>&1 ); echo "emcc -c rc=$?"
tail -n 3 "$T/fw_rep.log"
