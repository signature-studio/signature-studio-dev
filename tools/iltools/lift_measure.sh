#!/usr/bin/env bash
# lift_measure.sh — ILTools_x64.dll (block24347_PE.bin) の .pdata 全関数 lift を測る (T-SH-12 #154)。
#   [1] gen_entries (qfclift 流用) → x64c lift → 集計を表示
#   [2] unsup / unlifted callees が 0 でなければ exit 1 (現状は x87 未対応で不合格が正しい測定結果)
# 前提: FL_WIN64_DIR (fl-win64 展開先)、QFC_PY (capstone + pefile の python)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
QFCLIFT="$HERE/../qfclift"
: "${FL_WIN64_DIR:?FL_WIN64_DIR を設定}"
QFC_PY="${QFC_PY:-python3}"
PE="${ILT_PE:-$FL_WIN64_DIR/extracted/block24347_PE.bin}"
OUT="$HERE/work/lift"
T0=$(date +%s)
[ -f "$PE" ] || { echo "[iltools] PE not found: $PE"; exit 2; }
mkdir -p "$OUT"
echo "load: $(cut -d' ' -f1-3 /proc/loadavg)  nproc: $(nproc)"
"$QFC_PY" "$QFCLIFT/gen_entries.py" "$PE" "$OUT/entries.json" || exit 2
"$QFC_PY" "$QFCLIFT/x64c_qfc.py" --pe "$PE" --entries "$OUT/entries.json" --out "$OUT" --closure 0 \
  --img 0x400000 --shift 0 --img-size 0x394000 --impbase 0x1D80000 | tail -1 | tee "$OUT/lift.log"
"$QFC_PY" - "$OUT/lift_meta.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
n = sum(m['unsup'].values())
x87 = sum(v for k, v in m['unsup'].items() if k.split(':')[0].startswith('f'))
print('[iltools] functions %d / insns %d / unsupported sites %d (x87 %d) / unlifted callees %d / imports %d' % (
    len(m['functions']), m['ninsn'], n, x87, len(m['unlifted_callees']), len(m['imports_used'])))
ok = n == 0 and not m['unlifted_callees'] and len(m['functions']) == 11747
print('[iltools] %s' % ('PASS' if ok else 'FAIL'))
sys.exit(0 if ok else 1)
PY
rc=$?
echo "[iltools] elapsed $(( $(date +%s) - T0 )) s"
exit $rc
