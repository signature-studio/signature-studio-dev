#!/usr/bin/env bash
# #2456: RetDec drc.ll の uselistorder 並びの非決定の起点を切り分ける (REPORT_APPENDIX_960 §20)。
# 同一 PE・同一 150 range で RetDec を流し、群ごとに drc.ll / drc.bc / lift.ll の md5 と差分を集計する。
#   on  : ASLR 有効 (既定)
#   off : ASLR 無効 (setarch x86_64 -R)
#   tc  : ASLR 無効 + glibc.malloc.tcache_count=0 (ヒープ上の割り当て先だけをずらす。アドレス依存の検査)
# 使い方: bash tools/m11/uselist_origin_2456.sh [on 試行数=4] [off 試行数=3] [tc 試行数=2]
# 前提: FL_WIN64_DIR (block00031_PE.bin)・RetDec (RETDEC_ROOT か PATH)・work/boot_ranges.txt (work-m11)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
source ../shared/env.sh   # FL_WIN64_DIR
PE="${M11_PE:-${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}}"
RETDEC_BIN="${RETDEC:-$(command -v retdec-decompiler || true)}"
[ -n "$RETDEC_BIN" ] || RETDEC_BIN="${RETDEC_ROOT:-}/bin/retdec-decompiler"
[ -x "$RETDEC_BIN" ] || { echo "FAIL: retdec-decompiler 無し (RETDEC か PATH・RETDEC_ROOT で指定)" >&2; exit 1; }
[ -f "$PE" ] || { echo "FAIL: PE 無し: $PE" >&2; exit 1; }
[ -f work/boot_ranges.txt ] || { echo "FAIL: work/boot_ranges.txt 無し (work-m11 を展開)" >&2; exit 1; }
N_ON="${1:-4}"; N_OFF="${2:-3}"; N_TC="${3:-2}"; N_PASS="${4:-2}"
OUT="$HERE/work/uselist_2456"
rm -rf "$OUT"; mkdir -p "$OUT/tmp"
export TMPDIR="$OUT/tmp"
RANGES="$(tr ',' '\n' < work/boot_ranges.txt | sed -n '1,150p' | paste -sd, -)"
SUM="$OUT/summary.tsv"
printf 'label\tmode\trc\tsec\tload1\n' > "$SUM"

run() { # run <label> <mode: on|off|tc>
  local label="$1" mode="$2" wrap="" tun="" rc=0 t0 t1
  case "$mode" in
    off) wrap="setarch x86_64 -R" ;;
    tc)  wrap="setarch x86_64 -R"; tun="glibc.malloc.tcache_count=0" ;;
  esac
  local load; load="$(cut -d' ' -f1 /proc/loadavg)"
  t0="$(date +%s.%N)"
  env ${tun:+GLIBC_TUNABLES=$tun} $wrap "$RETDEC_BIN" "$PE" -o "$OUT/$label.drc.c" \
    --select-ranges "$RANGES" --select-decode-only --timeout 250 > "$OUT/$label.retdec.log" 2>&1 || rc=$?
  t1="$(date +%s.%N)"
  if [ -f "$OUT/$label.drc.ll" ]; then
    python3 ../m2/ir_normalize.py "$OUT/$label.drc.ll" "$OUT/$label.norm0.ll" > /dev/null 2>&1 || true
    python3 ../m5/ir5_patch.py "$OUT/$label.norm0.ll" "$OUT/$label.lift.ll" --report "$OUT/$label.ir5.json" > /dev/null 2>&1 || true
  fi
  printf '%s\t%s\t%s\t%s\t%s\n' "$label" "$mode" "$rc" "$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.1f", b-a}')" "$load" >> "$SUM"
}

for i in $(seq 1 "$N_ON");  do run "on$i"  on;  done
for i in $(seq 1 "$N_OFF"); do run "off$i" off; done
for i in $(seq 1 "$N_TC");  do run "tc$i"  tc;  done

# pass 単位の切り分け: --print-after-all の stderr (pass ごとの IR 全文) を ASLR 有効で取り、run 間で比べる。
# テキストダンプは use-list の順序を載せないため、ここで差が無くても「順序が変わらない」根拠にはならない (REPORT §20)。
for i in $(seq 1 "$N_PASS"); do
  t0="$(date +%s.%N)"; rc=0
  "$RETDEC_BIN" "$PE" -o "$OUT/pass$i.drc.c" --select-ranges "$RANGES" --select-decode-only --timeout 250 \
    --print-after-all > /dev/null 2> "$OUT/pass$i.stderr" || rc=$?
  t1="$(date +%s.%N)"
  printf 'pass%s\tprint-after-all\t%s\t%s\t%s\n' "$i" "$rc" "$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.1f", b-a}')" "$(cut -d' ' -f1 /proc/loadavg)" >> "$SUM"
done

python3 uselist_origin_2456.py "$OUT"
