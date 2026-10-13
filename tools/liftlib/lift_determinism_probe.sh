#!/usr/bin/env bash
# lift_determinism_probe.sh — RetDec raw .drc.ll の非決定性の切り分け実測 (LIFTLIB-9 / #668)。
#
#   bash tools/liftlib/lift_determinism_probe.sh [N]     # 既定 N=4: ASLR 有効・無効をそれぞれ N 回
#
#   同一 PE・同一 ranges を RetDec に与え、ASLR 有効 (既定) と無効 (setarch -R) で各 N 回実行する。
#   各実行について raw .drc.ll の sha256、uselistorder 行を除いた sha256、.drc.c の sha256 を表示し、
#   モードごとに異なる値の個数 (distinct) を集計する。
# 入力 (読取のみ): $ANALYSIS_DIR/plugins/ott/binaries/OTT_vst2_win64.dll, tools/m6/work/ott_ranges.txt
# 出力: tools/liftlib/work/probe/ (gitignore)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
N="${1:-4}"
ANALYSIS_DIR="${ANALYSIS_DIR:-$HOME/analysis}"
PE="$ANALYSIS_DIR/plugins/ott/binaries/OTT_vst2_win64.dll"
RANGES_F="$HERE/../m6/work/ott_ranges.txt"
OUT="$HERE/work/probe"

need() { [ -e "$1" ] || { echo "[lift_determinism_probe] 前提が無い: $1" >&2; exit 2; }; }
need "$PE" "analysis-ott-binaries"
need "$RANGES_F" "work-m6-ott"
need /opt/retdec/bin/retdec-decompiler "toolchain-retdec"
command -v setarch >/dev/null || { echo "[lift_determinism_probe] setarch が無い" >&2; exit 2; }

rm -rf "$OUT"; mkdir -p "$OUT"
RANGES="$(cat "$RANGES_F")"
T0=$(date +%s)
for mode in on off; do
  if [ "$mode" = off ]; then PFX=(setarch x86_64 -R); else PFX=(); fi
  for i in $(seq 1 "$N"); do
    d="$OUT/$mode/r$i"; mkdir -p "$d/tmp"
    ( s=$(date +%s%N)
      TMPDIR="$d/tmp" "${PFX[@]}" /opt/retdec/bin/retdec-decompiler "$PE" -o "$d/ott.drc.c" \
        --select-ranges "$RANGES" --select-decode-only --timeout 2400 > "$d/retdec.log" 2>&1
      echo "$?" > "$d/rc"; echo $(( ($(date +%s%N) - s) / 1000000 )) > "$d/ms" ) &
    if [ $(( i % 2 )) = 0 ]; then wait; fi
  done
  wait
done

RC=0
echo "mode  run  rc  ms     raw_sha256   no_uselist_sha  c_sha256     uselist_lines"
for mode in on off; do
  for i in $(seq 1 "$N"); do
    d="$OUT/$mode/r$i"
    rc="$(cat "$d/rc" 2>/dev/null)"; [ "$rc" = 0 ] || RC=1
    [ -f "$d/ott.drc.ll" ] || { echo "$mode r$i: ott.drc.ll 無し"; RC=1; continue; }
    printf "%-5s r%-3d %-3s %-6s %-12s %-15s %-12s %s\n" "$mode" "$i" "$rc" "$(cat "$d/ms")" \
      "$(sha256sum "$d/ott.drc.ll" | cut -c1-12)" \
      "$(grep -v '^\s*uselistorder' "$d/ott.drc.ll" | sha256sum | cut -c1-12)" \
      "$(sha256sum "$d/ott.drc.c" | cut -c1-12)" \
      "$(grep -c '^\s*uselistorder' "$d/ott.drc.ll")"
  done
done
echo "--- distinct (値の種類数 / N=$N)"
for mode in on off; do
  for kind in ott.drc.ll ott.drc.c; do
    printf "%-4s %-10s distinct=%s\n" "$mode" "$kind" \
      "$(for i in $(seq 1 "$N"); do sha256sum "$OUT/$mode/r$i/$kind" | cut -c1-64; done | sort -u | wc -l)"
  done
  printf "%-4s %-10s distinct=%s\n" "$mode" "no_uselist" \
    "$(for i in $(seq 1 "$N"); do grep -v '^\s*uselistorder' "$OUT/$mode/r$i/ott.drc.ll" | sha256sum | cut -c1-64; done | sort -u | wc -l)"
done
echo "[lift_determinism_probe] 総所要 $(( $(date +%s) - T0 ))s load=$(cut -d' ' -f1-3 /proc/loadavg) rc=$RC"
exit "$RC"
