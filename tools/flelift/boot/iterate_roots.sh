#!/usr/bin/env bash
# iterate_roots.sh — 実行時に発見される unlifted target と lifted C 即値 (address-taken) を
# boot_roots.json に累積し、lift → build → boot 実行を収束まで反復する (FLE-2 開発用)。
#
#   bash tools/flelift/boot/iterate_roots.sh [max_rounds]
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
W="$FLE/work/boot"
PE="${FLE_PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
MAX="${1:-6}"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
set +u; source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1; set -u
mkdir -p "$W/obj" "$W/tmp" "$HERE/results"
export TMPDIR="$W/tmp"

EXPORTS=_fle_boot_enter,_fle_boot_set_strict,_fle_units_run,_fle_units_total,_fle_units_empty,_fle_boot_stage,_fle_n_getmem,_fle_n_freemem,_fle_n_longjmp,_fle_n_exit,_fle_n_getproc,_fle_n_soft,_fle_n_soft_uniq,_fle_soft_name,_fle_soft_count,_fle_va_calls,_fle_va_bytes,_fle_n_cb,_fle_unit_proc,_fle_run,_fle_rget,_fle_data_install,_fle_init,_fle_reset,_shimx_set_trace,_shimx_init,_fle_test_throw,_fle_n_dispatch,_fle_n_disp_getmem,_fle_n_disp_freemem,_fle_n_disp_realloc,_fle_n_disp0,_fle_ring_at,_fle_n_loadstr,_fle_boot_set_ipp,_fle_boot_set_diag_nullfill,_fle_diag_skip_n,_fle_diag_pass_n,_fle_ipp_total,_fle_ipp_names,_fle_ipp_name,_fle_ipp_count

# FLE-5: root 化すると survey が破裂する address の blocklist。
# lift すると f_6c7900 の fill ループが未初期化幅 (1,048,570 回) で暴走 → ExitProcess
# → survey が成立しなくなる (§3-4 参照)。unlifted で止める方が survey は functional。
BLOCKLIST="${FLE_ROOT_BLOCKLIST:-0x6a7b70}"

for round in $(seq 1 "$MAX"); do
  echo "==== round $round ===="
  python3 "$HERE/gen_boot.py" --pe "$PE" --out "$W" >/dev/null
  T0=$(date +%s)
  python3 "$FLE/x64c.py" --pe "$PE" --entries "$W/fle_entries_boot.json" --out "$W/lift" --closure ${FLE_LIFT_CLOSURE:-2} \
    --img 0x400000 --shift 0 --img-size 0x18c0000 --impbase 0x1D80000 \
    --override 0x4126f0=fle_ov_longjmp --override 0x409410=fle_ov_getmem \
    --override 0x409440=fle_ov_freemem --override 0x4120c0=fle_ov_initunits 2>&1 | tail -1
  echo "[iter] lift $(( $(date +%s) - T0 ))s"
  python3 "$FLE/fle_data_gen.py" "$PE" "$W/lift/fle_data.c" "$W/lift/lift_meta.json" >/dev/null
  python3 "$HERE/gen_boot.py" --pe "$PE" --meta "$W/lift/lift_meta.json" --out "$W" >/dev/null

  # lifted C の即値 → .pdata 開始点 → 未 lift のものを boot_roots.json へ累積 (address-taken 収束)
  python3 - "$W" "$HERE" "$PE" <<'PYEOF'
import re, struct, pefile, json, sys
W, HERE, PE = sys.argv[1], sys.argv[2], sys.argv[3]
pe = pefile.PE(PE)
raw = None
for s in pe.sections:
    if s.Name.startswith(b'.pdata'):
        raw = s.get_data(); break
starts = set()
for i in range(0, len(raw)//12*12, 12):
    b, e, u = struct.unpack_from('<III', raw, i)
    if b == 0 and e == 0: break
    starts.add(0x400000 + b)
src = open(W + '/lift/fle_lifted.c').read()
imm = set(int(x, 16) for x in re.findall(r'0x(4[0-9a-f]{5})ULL', src))
cand = sorted(imm & starts)
meta = json.load(open(W + '/lift/lift_meta.json'))
fns = set('0x' + x for x in meta['functions'])
new = [hex(x) for x in cand if hex(x) not in fns]
old = json.load(open(HERE + '/boot_roots.json'))
merged = sorted(set(old) | set(new))
json.dump(merged, open(HERE + '/boot_roots.json', 'w'), indent=1)
print('[iter] address-taken 未 lift: %d 件 (boot_roots %d -> %d)' % (len(new), len(old), len(merged)))
PYEOF

  T0=$(date +%s)
  emcc -c "$W/lift/fle_lifted.c" -o "$W/obj/t_lifted.o" -O0 -w -I"$FLE/rt" -I"$HERE"
  emcc -c "$W/lift/fle_data.c" -o "$W/obj/t_data.o" -O0 -w -I"$FLE/rt"
  emcc -c "$W/fle_imp_bridge.c" -o "$W/obj/t_bridge.o" -O0 -w -Wno-error=int-conversion -I"$FLE/rt" -I"$HERE"
  echo "[iter] compile $(( $(date +%s) - T0 ))s"
  T0=$(date +%s)
  emcc $W/obj/t_lifted.o $W/obj/t_data.o $W/obj/t_cpu.o $W/obj/t_glue.o $W/obj/t_bridge.o $W/obj/t_tw.o $W/obj/t_boot.o $W/obj/sx_*.o \
    -o "$W/fleboot_plain.cjs" -O0 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 \
    -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=flebootcreate -sEXIT_RUNTIME=1 \
    -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,HEAPU32 \
    -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) 2> "$W/link_plain.log"
  echo "[iter] link $(( $(date +%s) - T0 ))s errors=$(grep -ci error "$W/link_plain.log" || true) wasm=$(stat -c%s "$W/fleboot_plain.wasm")"

  # boot 実行 (unlifted target を収集)
  set +e
  FLE_BOOT_VARIANT=plain timeout 900 node "$HERE/fle_boot.mjs" "$W/fleboot_plain.cjs" "$HERE/results/boot_summary.json" --boot-only > "$W/run_plain.log" 2>&1
  RC=$?
  set -e
  grep 'FLEBOOT_RESULT' "$W/run_plain.log" | tail -1 || true
  grep '\[fleboot\]\[ff\]' "$W/run_plain.log" | grep -v 'dispatch(0)' | tail -5 || true
  if [ "$RC" = 0 ] && grep -q '"boot_threw":null' "$W/run_plain.log"; then
    echo "[iter] boot 完走 (round $round) — 収束"
    break
  fi
  # unlifted target を boot_roots.json へ (実行時発見分)
  python3 - "$W" "$HERE" "$BLOCKLIST" <<'PYEOF'
import json, re, sys
W, HERE, BLOCK = sys.argv[1], sys.argv[2], sys.argv[3]
block = {x.strip() for x in BLOCK.split(',') if x.strip()}
log = open(W + '/run_plain.log', errors='replace').read()
targets = set(int(m, 16) for m in re.findall(r'\[fleboot\]\[ff\] unlifted 0x([0-9a-f]+)', log))
old = list(json.load(open(HERE + '/boot_roots.json')))
new = sorted(set(old) | (set(hex(t) for t in targets) - block))
if len(new) > len(old):
    json.dump(new, open(HERE + '/boot_roots.json', 'w'), indent=1)
    print('[iter] runtime unlifted %d 件を追加 (boot_roots -> %d)' % (len(new) - len(old), len(new)))
else:
    print('[iter] runtime unlifted 追加なし (blocked: %s)' % sorted(block))
PYEOF
done
echo "[iter] done"
