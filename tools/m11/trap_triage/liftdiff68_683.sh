#!/usr/bin/env bash
# #683: #307 (LD-7) の 68 関数について、function_414ad0 の IR 修復の A/B を liftdiff で測る。
#   A = IR 無変更の複写 (target m11_414base) / B = 修復 IR (target m11_414fix) / 突合 = cmp68_683.py
# 前提: tools/m11/work (work-m11) と tools/liftdiff/work/m11/batch_closure.jsonl (work-liftdiff) が展開済み。
#       FL_WIN64_DIR = fl-win64 の展開先。PY = capstone 入りの python (既定 python3)。
# 使い方: FL_WIN64_DIR=... PY=... bash tools/m11/trap_triage/liftdiff68_683.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
PY="${PY:-python3}"
LD="$REPO/tools/liftdiff"
cd "$REPO"
for name in m11_414base m11_414fix; do mkdir -p "$LD/work/$name"; done
# 68 関数 = 最初の wasm_trap case が OOB (wasm_detail が function_414ad0 で始まる) の関数 (tests/oob_414ad0.py と同定義)
"$PY" - "$LD/work/m11/batch_closure.jsonl" "$LD/work/m11_414fix/fn68.txt" <<'PYEOF'
import json, sys
top = []
for line in open(sys.argv[1]):
    r = json.loads(line)
    cs = [c for c in r['cases'] if c['outcome'] == 'wasm_trap']
    d = (cs[0].get('wasm_detail') or '') if cs else ''
    if d.startswith('memory access out of bounds @ ld_wasm.wasm.function_414ad0'):
        top.append(r['function']['va'])
open(sys.argv[2], 'w').write('\n'.join(top) + '\n')
print('fn68: %d' % len(top))
PYEOF
"$PY" "$HERE/ir414_fix.py" --none tools/m11/work/boot_final3.ll "$LD/work/m11_414base/boot_final3_414base.ll"
"$PY" "$HERE/ir414_fix.py" tools/m11/work/boot_final3.ll "$LD/work/m11_414fix/boot_final3_414fix.ll"
for name in m11_414base m11_414fix; do
  cp "$LD/work/m11/boot_state.json" "$LD/work/$name/boot_state.json"
  src="$LD/work/m11_414fix/fn68.txt"; dst="$LD/work/$name/fn68.txt"
  [ "$src" = "$dst" ] || cp "$src" "$dst"
done
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
for name in m11_414base m11_414fix; do
  (cd "$LD" && "$PY" liftdiff.py batch "$HERE/targets_$name.json" --set "file:$LD/work/$name/fn68.txt" --shards 4 --state auto --out "$LD/work/$name/batch_${name#m11_}68.jsonl" > "$LD/work/$name/batch_${name#m11_}68.log" 2>&1)
done
"$PY" "$HERE/cmp68_683.py" "$LD/work/m11_414base/batch_414base68.jsonl" "$LD/work/m11_414fix/batch_414fix68.jsonl" "$LD/work/m11_414fix/fn68.txt"
