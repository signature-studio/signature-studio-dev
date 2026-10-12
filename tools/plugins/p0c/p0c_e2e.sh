#!/usr/bin/env bash
# CAB-196 P0c (kernel 表妥当性検証 + f80 assessment) 1 コマンド再現
#   bash tools/plugins/p0c/p0c_e2e.sh
# 構成:
#   [1] kernel_table.py 再実行        — Balance 0x5e19f0 から 45 変数/80 実装を機械語から復元 (決定的)
#   [2] kernel_matrix.py (条件付き)   — 141 plugin 走査 → per-DLL kernel 表一致 + 呼出 site 抽出 (~数分, work JSON があれば skip)
#   [3] verify_table.py               — 修正版正規化で 130 DLL の kernel 実装を 80/80 再検証
#   [4] k80 lift (条件付き)           — 80 kernel の RetDec lift (IR f80 計数用, work/k80.lift.ll があれば skip)
#   [5] f80_assess.py                 — 28 x87 kernel の分類 + IR f80 計数
#   [6] f80_micro.c build+run         — long double(x87) vs double(f64 lowering) bit 差分 + 実機械語 4 本で検証
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../../shared/env.sh"
ROOT="$(cd "$HERE/.." && pwd)"                      # tools/plugins
REPO="$(cd "$ROOT/.." && pwd)"                      # webstudio
PE="$FL_WIN64_DIR/extracted/block18983_PE.bin"
mkdir -p "$HERE/work"

echo "== [1] kernel_table.py =="
python3 "$ROOT/inventory/kernel_table.py" "$PE"
git -C "$REPO" diff --quiet -- tools/plugins/lift/kernel_ranges_balance.txt \
  || { echo "[e2e] WARN: lift/kernel_ranges_balance.txt が再生成で変化した"; git -C "$REPO" diff --stat -- tools/plugins/lift/kernel_ranges_balance.txt | cat; }

echo "== [2] kernel_matrix.py (work/kernel_matrix.json が無い場合のみ, 数分) =="
if [ ! -f "$HERE/work/kernel_matrix.json" ]; then
  python3 "$HERE/kernel_matrix.py" 12
else
  echo "skip (work/kernel_matrix.json 存在)"
fi

echo "== [3] verify_table.py =="
python3 "$HERE/verify_table.py"

echo "== [4] k80 lift (work/k80.lift.ll が無い場合のみ) =="
if [ ! -f "$HERE/work/k80.lift.ll" ]; then
  if [ ! -f "$HERE/work/k80_ranges.txt" ]; then
    python3 - "$HERE/work" <<'PY'
import json, sys, os
kt = json.load(open(os.path.join(sys.argv[1], '..', 'work', 'kernel_table.json')))
ranges = ','.join('0x%x-0x%x' % (int(k['va'], 16), int(k['va'], 16) + k['size'] - 1) for k in kt['kernels'])
open(os.path.join(sys.argv[1], 'k80_ranges.txt'), 'w').write(ranges + '\n')
print('ranges written: %d kernels' % len(kt['kernels']))
PY
  fi
  bash "$ROOT/lift/lift_ranges.sh" "$PE" "$HERE/work/k80_ranges.txt" "$HERE/work" k80 2400
else
  echo "skip (work/k80.lift.ll 存在)"
fi

echo "== [5] f80_assess.py =="
python3 "$HERE/f80_assess.py"

echo "== [6] f80_micro =="
cc -O2 -ffp-contract=off -o "$HERE/work/f80_micro" "$HERE/f80_micro.c" -lm
"$HERE/work/f80_micro" "$PE" 2000000

echo "== e2e OK =="
