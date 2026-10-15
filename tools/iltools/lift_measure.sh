#!/usr/bin/env bash
# lift_measure.sh — ILTools_x64.dll (block24347_PE.bin) の export 閉包 lift gate (T-SH-12 #154)。
#   [1,2] roots = PE export 6 本 → x64c --closure 50 (直接 call 閉包 824 関数)。閉包外の x87 関数 45 本は
#         x64c --trap で trap stub にする (lift しない)。closure_gate.py が 824 / unsup 0 / unlifted 0 / trap 45 を assert (違えば exit 1)
#   [3]   陰性対照 (a): 閉包 root に x87 関数 1 本を trap 無しで混ぜると gate が FAIL すること
#   [4]   陰性対照 (b): 全 trap stub を native で呼び、いずれも abort (stderr に "trap stub") すること
# 前提: FL_WIN64_DIR (fl-win64 展開先)、QFC_PY (capstone + pefile の python)、gcc。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLELIFT="$HERE/../flelift"
: "${FL_WIN64_DIR:?FL_WIN64_DIR を設定}"
QFC_PY="${QFC_PY:-python3}"
PE="${ILT_PE:-$FL_WIN64_DIR/extracted/block24347_PE.bin}"
OUT="$HERE/work"
T0=$(date +%s)
ulimit -c 0
[ -f "$PE" ] || { echo "[iltools] PE not found: $PE"; exit 2; }
mkdir -p "$OUT/lift" "$OUT/neg"
echo "load: $(cut -d' ' -f1-3 /proc/loadavg)  nproc: $(nproc)"
"$QFC_PY" "$HERE/gen_entries.py" "$PE" "$OUT/entries.json" || exit 2
"$QFC_PY" "$HERE/x87_traps.py" "$PE" "$OUT/traps.txt" || exit 2

lift() {  # lift <out dir> <entries.json> <traps.txt>
  local -a tr=()
  while read -r v; do tr+=(--trap "$v"); done < "$3"
  "$QFC_PY" "$FLELIFT/x64c.py" --pe "$PE" --entries "$2" --out "$1" --closure 50 \
    --img 0x400000 --shift 0 --img-size 0x394000 --impbase 0x1D80000 "${tr[@]}" | tail -1
}

echo "== [1,2] export closure lift + gate =="
lift "$OUT/lift" "$OUT/entries.json" "$OUT/traps.txt" || { echo "[iltools] x64c failed"; exit 1; }
"$QFC_PY" "$HERE/closure_gate.py" "$OUT/lift/lift_meta.json" || { echo "[iltools] lift_measure FAIL"; exit 1; }

echo "== [3] negative control (a): x87 関数を閉包 root に混ぜると gate が FAIL すること =="
X87_ONE="$(head -n1 "$OUT/traps.txt")"
"$QFC_PY" "$HERE/gen_entries.py" "$PE" "$OUT/neg/entries.json" --extra-root "$X87_ONE" || exit 2
grep -v -x -F "$X87_ONE" "$OUT/traps.txt" > "$OUT/neg/traps.txt"
lift "$OUT/neg/lift" "$OUT/neg/entries.json" "$OUT/neg/traps.txt" > /dev/null
if "$QFC_PY" "$HERE/closure_gate.py" "$OUT/neg/lift/lift_meta.json"; then
  echo "[iltools] negctl (a) NOT detected (gate PASS on x87 root $X87_ONE)"; exit 1
fi
echo "[iltools] negctl (a) detected (gate FAIL as expected)"

echo "== [4] negative control (b): trap stub が実際に発火すること =="
gcc -O0 -w -I "$FLELIFT/rt" -o "$OUT/lift/trap_harness" "$HERE/trap_harness.c" "$OUT/lift/fle_lifted.c" \
  "$FLELIFT/rt/fle_cpu.c" -lm || { echo "[iltools] harness build failed"; exit 1; }
fired=0; total=0
while read -r v; do
  total=$((total + 1))
  "$OUT/lift/trap_harness" "$v" > /dev/null 2> "$OUT/trap.err"; rc=$?
  if [ "$rc" -ne 0 ] && grep -q "trap stub" "$OUT/trap.err"; then fired=$((fired + 1)); else echo "[iltools] trap NOT fired: $v rc=$rc"; fi
done < "$OUT/traps.txt"
echo "[iltools] trap stubs fired $fired / $total"
[ "$total" -eq 45 ] && [ "$fired" -eq "$total" ] || { echo "[iltools] negctl (b) FAIL"; exit 1; }
echo "[iltools] PASS (elapsed $(( $(date +%s) - T0 )) s)"
