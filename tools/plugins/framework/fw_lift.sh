#!/usr/bin/env bash
# fw_lift.sh — P0a (CAB-194) framework lift stage 1: PE 敷設 → icall_rewrite → RetDec (chunk 並列) → 復元 → merge
#   bash fw_lift.sh [--full] [--chunks N]
#   入力: $FL_WIN64_DIR/extracted/block18983_PE.bin (Fruity Balance = framework 正本)
#         work/fw/F.ranges (fw_prep.py)
#   出力: work/fw/fw_all.ll (merge 済み raw RetDec IR, insn.addr 保持)
#   教訓 (tools/icall, 稼働中): RetDec は間接 call/jmp を IR から全て落とすため,
#   decode 専用に PE を書換え (icall_rewrite.py: 間接 call → memory-ABI + stub, 関数を新 section に再配置,
#   closure 内 direct call も memory-ABI 仮想化) してから RetDec に掛け, 後で ir_icall_restore.py で
#   元 VA 体系に戻す。これで IR に間接 call が残る (M11 では 0 件だった)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../../shared/env.sh"
ICALL="$REPO_ROOT/tools/icall"
W="$HERE/../work/fw"
PE="$FL_WIN64_DIR/extracted/block18983_PE.bin"
CHUNKS=8
FULL=0
for a in "$@"; do case "$a" in --full) FULL=1 ;; --chunks) CHUNKS="$2"; shift ;; esac; done
mkdir -p "$W/tmp"
export TMPDIR="$W/tmp"
cd "$W"

[ -f F.ranges ] || { echo "[fw] F.ranges 無し: python3 fw_prep.py を先に" >&2; exit 2; }

# ---- 1. PE 書換え (間接 call 復元 + ABI 仮想化) --------------------------------
if [ $FULL = 1 ] || [ ! -f fw_icall.dll ] || [ ! -f fw_map.json ]; then
  echo "[fw] icall_rewrite (11,736 funcs)..."
  python3 "$ICALL/icall_rewrite.py" --pe "$PE" --funcs F.ranges \
    --out fw_icall.dll --map fw_map.json 2>&1 | tail -5
fi

# ---- 2. RetDec decode-only (chunk 並列) ---------------------------------------
if [ $FULL = 1 ] || [ ! -f fw_all.ll ]; then
  python3 - "$CHUNKS" <<'PY'
import json, sys
n = int(sys.argv[1])
m = json.load(open('fw_map.json'))
r = open('fw_map.json.ranges').read().strip()
rng = r.split(',')
# stub / comis_stub も decode 対象に加える (map.json.ranges には既に含まれるが保険で確認)
extra = []
for k in ('stub', 'comis_stub'):
    if k in m:
        extra.append('0x%x-0x%x' % (m[k], m[k] + 128))
rng += [e for e in extra if e not in rng]
for i in range(n):
    open('fw.ranges.%d' % i, 'w').write(','.join(rng[i::n]))
print('[fw] ranges %d -> %d chunks' % (len(rng), n))
PY
  pids=()
  for i in $(seq 0 $((CHUNKS-1))); do
    ( /opt/retdec/bin/retdec-decompiler fw_icall.dll -o "fw$i.drc.c" \
        --select-ranges "$(cat fw.ranges.$i)" --select-decode-only --timeout 3600 \
        > "fw$i.retdec.log" 2>&1 ) &
    pids+=($!)
  done
  fail=0
  for p in "${pids[@]}"; do wait "$p" || fail=1; done
  [ $fail = 0 ] || { echo "[fw] RetDec chunk 失敗: fw*.retdec.log を確認" >&2; exit 1; }
  for i in $(seq 0 $((CHUNKS-1))); do
    [ -f "fw$i.drc.ll" ] || { echo "[fw] fw$i.drc.ll 無し" >&2; exit 1; }
  done
  echo "[fw] RetDec decode 完了 ($CHUNKS chunks)"
fi

# ---- 3. 復元 (new→orig VA, stub → __icall_dispatch) + merge -------------------
if [ $FULL = 1 ] || [ ! -f fw_all.restored.ll ]; then
  for i in $(seq 0 $((CHUNKS-1))); do
    python3 "$ICALL/ir_icall_restore.py" --ir "fw$i.drc.ll" --map fw_map.json \
      --out "fw$i.restored.ll" --report "fw$i.restore.json"
  done
  IN=""
  for i in $(seq 0 $((CHUNKS-1))); do IN="$IN fw$i.restored.ll"; done
  python3 "$HERE/fw_merge.py" $IN -o fw_all.restored.ll
fi
echo "[fw] OK: fw_all.restored.ll ($(wc -l < fw_all.restored.ll) lines, $(grep -c '^define' fw_all.restored.ll) defines)"
