#!/usr/bin/env bash
# fle_e2e.sh — flelift (CAB-226) 1 コマンド検証:
#   (1) FLEngine 全関数 lift (x64c flelift fork) + 未対応 site 計上
#   (2) emcc → wasm build
#   (3) smoke: _UStrAsg (lock xadd 経路) + Move (M11 unit#18 leaf, 0x188 record size)
#   (4) spot diff (native 実機械語 vs wasm, FORMAT.md v1 準拠 verdict JSONL)
#   (5) D9 検証 (capstone rip-rel × 手動 modrm 全件突合)
# 前提: python3 (capstone, pefile), emsdk 6.0.12, node, setarch, gcc
#   emsdk は EMSDK_ENV で emsdk_env.sh の場所を指定 (既定 /opt/emsdk/emsdk_env.sh = [EMSDK])。
# 編集禁止 dir (tools/ott, tools/liftdiff, tools/liftlib, tools/icall) には書かない。
set -euo pipefail
FLE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$FLE"
EMSDK_SH="${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
[ -f "$EMSDK_SH" ] || { echo "[fle_e2e] emsdk_env.sh not found: $EMSDK_SH (EMSDK_ENV で指定)" >&2; exit 2; }
source "$EMSDK_SH" >/dev/null 2>&1
export EMSDK_ENV="$EMSDK_SH"
source "$FLE/../shared/env.sh"
PE="${FLE_PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
export FLE_PE="$PE"
ENT="${FLE_ENTRIES:-$FLE/work/fle_entries.json}"
# entries が無ければコミット済み fle_entries.json (M11 closure F 集合 7,421 roots) から生成
mkdir -p "$FLE/work"
[ -f "$ENT" ] || python3 -c "
import json
d = json.load(open('$FLE/fle_entries.json'))
json.dump(d, open('$ENT', 'w'))"
export FLE_ENTRIES="$ENT"
FAIL=0

echo "== [1] lift =="
bash fle_lift.sh 2>&1 | grep -E "\[fle_lift\]|\[flelift" | tail -3
python3 - <<'PY'
import json
m = json.load(open('work/lift/lift_meta.json'))
n = sum(m['unsup'].values())
print('[e2e] lifted %d functions / %d insns / unsupported %d sites / unlifted-callees %d' % (
    len(m['functions']), m['ninsn'], n, len(m['unlifted_callees'])))
assert n == 0, 'unsupported sites remain'
PY

echo "== [2] smoke (UStrAsg lock xadd + Move) =="
node t_ustrasg.mjs || FAIL=1

echo "== [3a] build fle_natdrv (native 参照 driver) =="
gcc -O1 -g -w -D_GNU_SOURCE -fPIE -pie -o work/fle_natdrv fle_natdrv.c fle_ms_call.S -lm

echo "== [3] spot diff (native vs wasm, FORMAT.md v1) =="
python3 fle_diff.py 2>&1 | tail -10 || FAIL=1
cp work/verdict.jsonl results/verdict_flelift.jsonl
cp work/verdict_summary.json results/verdict_summary.json

echo "== [4] D9 (capstone rip-rel × manual modrm) =="
python3 probe_d9_disp.py || FAIL=1

echo
if [ "$FAIL" = 0 ]; then echo "[fle_e2e] PASS"; else echo "[fle_e2e] FAIL"; exit 1; fi
