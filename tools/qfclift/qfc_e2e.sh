#!/usr/bin/env bash
# qfc_e2e.sh — QuickFontCache_x64.dll lift 1 コマンド検証 (T-SH-12 #154)。
#   [1] pdata 全 6347 関数 roots → x64c lift: unsup 0 / unlifted callees 0 を assert (違えば exit 1)
#   [2] emcc → wasm   [3] native vs wasm spot diff (qfc_diff.py, 不一致は exit 1)
#   [4] ネガコン 4 本 (SSSE3 handler 無効 / pmulhrsw・pshufb・phaddw を壊す): 全て FAIL 検出が必要
# 前提: python3 (capstone, pefile), emsdk, node, setarch, gcc。 FL_WIN64_DIR 必須。
set -euo pipefail
source "$(cd -- "$(dirname -- "$0")" && pwd)/env.sh"
cd "$QFC"
[ -f "$QFC_PE" ] || { echo "[qfc_e2e] PE not found: $QFC_PE (FL_WIN64_DIR=$FL_WIN64_DIR)"; exit 2; }
T0=$(date +%s)
echo "load: $(cut -d' ' -f1-3 /proc/loadavg)  nproc: $(nproc)"
mkdir -p work
source "$QFC/qfc_lift.sh"   # lift_build <out-dir> <QFC_NEGCTL>

echo "== [1,2] lift + wasm build =="
lift_build work/lift ""
"$QFC_PY" - <<'PY'
import json
m = json.load(open('work/lift/lift_meta.json'))
n = sum(m['unsup'].values())
print('[qfc_e2e] functions %d / insns %d / unsupported sites %d / unlifted callees %d / imports %d' % (
    len(m['functions']), m['ninsn'], n, len(m['unlifted_callees']), len(m['imports_used'])))
assert len(m['functions']) == 6347, 'function count != .pdata count'
assert n == 0 and not m['unlifted_callees'], 'unsupported / unlifted remain'
PY

echo "== [3] native vs wasm spot diff =="
gcc -O1 -g -w -D_GNU_SOURCE -fPIE -pie -o work/qfc_natdrv qfc_natdrv.c ../flelift/fle_ms_call.S -lm
"$QFC_PY" qfc_diff.py --pe "$QFC_PE" --cjs work/lift/qfcl.cjs

echo "== [4] negative controls (全て FAIL 検出が PASS 条件) =="
for neg in none_ssse3 pmulhrsw pshufb phaddw; do
  echo "-- QFC_NEGCTL=$neg"
  if [ "$neg" = none_ssse3 ]; then
    # handler 無効 → lift が unsup を報告 (gate [1] が落ちる) ことを確認
    QFC_NEGCTL=none_ssse3 "$QFC_PY" x64c_qfc.py --pe "$QFC_PE" --entries work/lift/entries.json --out work/neg_none --closure 0 \
      --img 0x400000 --shift 0 --img-size 0x20e000 | tail -1 | tee work/neg_none.log
    grep -q "unsup {'" work/neg_none.log || { echo "[qfc_e2e] negctl none_ssse3 NOT detected"; exit 1; }
  else
    lift_build "work/neg_$neg" "$neg" >/dev/null
    "$QFC_PY" qfc_diff.py --pe "$QFC_PE" --cjs "work/neg_$neg/qfcl.cjs" --out "work/diff_neg_$neg" --expect-fail | tail -3
  fi
done
echo "[qfc_e2e] PASS ($(( $(date +%s) - T0 )) s, load: $(cut -d' ' -f1-3 /proc/loadavg))"
