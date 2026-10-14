#!/usr/bin/env bash
# frame_slot_2394.sh — REPORT_APPENDIX_2394.md (ICALL-75 #2394) の 1 コマンド再現。
#   前提: 素材 work-icall を展開済み (tools/icall/work/rt_freshair-core)・RetDec は [RETDEC] (RETDEC_ROOT)・emsdk は [EMSDK] (fa_route_build.sh が source する)。
#   plugins-freshair は不要: 元 PE の decode 結果 (before.0.drc.dsm) と、元 PE + .icall section の rw.dll を使う。
#   FA_CORE (data 敷設・native 実行用 DLL) は既定で rw.dll。SWEEP=1 で fa_sweep.sh 8 60 を base / fixed の両方で走らせる (各 75 秒前後)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
RT="$HERE/work/rt_freshair-core"; EXP="$HERE/work/fa_exp"; mkdir -p "$EXP"
export TMPDIR="${TMPDIR:-${RUNNER_TEMP:-/tmp}}"
export FA_CORE="${FA_CORE:-$RT/rw.dll}"
RETDEC="${RETDEC_ROOT:-/opt/retdec}"
P="python3 $HERE/frame_slot_probe.py"
for f in "$RT/before.0.drc.dsm" "$RT/before.0.drc.ll" "$RT/rw.dll" "$RT/after.0.restored.ll"; do
  [ -f "$f" ] || { echo "[2394] $f が無い: 素材 work-icall を展開 (tools/icall/work)" >&2; exit 2; }
done
echo "## 1. 元の機械語 (before.0.drc.dsm を capstone で再 decode・rw.dll の同 VA と bytes 比較)"
$P mc --dsm "$RT/before.0.drc.dsm" --va 0x181057b38 --pe "$RT/rw.dll"
echo "## 2. RetDec の段ごとの stack_var (rw.dll の元 VA 0x181057b38-0x181057c05 を --print-after-all)"
"$RETDEC/bin/retdec-decompiler" "$RT/rw.dll" -o "$EXP/b38.c" --select-ranges 0x181057b38-0x181057c05 --select-decode-only --print-after-all > /dev/null 2> "$EXP/b38.err"
$P phase --err "$EXP/b38.err" --func function_181057b38
echo "## 3. 脱落 store の census (F.ranges 131 関数)"
$P census --dsm "$RT/before.0.drc.dsm" --ll "$RT/before.0.drc.ll" --ranges "$RT/F.ranges"
drive() {  # $1 label
  bash "$HERE/diff/fa_wc_build.sh" 2>&1 | tail -1
  node "$HERE/diff/fa_wc_drv.cjs" "$HERE/work/fa_wc/fa_wc.cjs" 181057b38 > "$EXP/drv_$1.out" 2> "$EXP/drv_$1.err" || true
  echo "[$1] 181057b38 8 入力: OK $(grep -c '^OK' "$EXP/drv_$1.out") / TRAP $(grep -c '^TRAP' "$EXP/drv_$1.out") | WC 行 $(grep -c '^WC line=' "$EXP/drv_$1.err") | 値 63736d65 (emsc) の WC 行 $(grep -c 'val=63736d65' "$EXP/drv_$1.err") | BLK+0 (addr=36319008) への emsc $(grep 'addr=36319008' "$EXP/drv_$1.err" | grep -c 'val=63736d65')"
  if [ "${SWEEP:-0}" = 1 ]; then
    bash "$HERE/diff/fa_sweep.sh" 8 60 | tail -1 | sed "s/^/[$1] /"; cp "$HERE/work/fa_route/sweep.jsonl" "$EXP/sweep_$1.jsonl"
  fi
}
echo "## 4. 回復実験 (base = 現 IR / fixed = 脱落した 2 store を戻した IR)"
bash "$HERE/fa_route_build.sh" > /dev/null 2>&1
drive base
$P restore --src "$RT/after.0.restored.ll" --out "$EXP/after.0.restored.fixed.ll"
FA_SRC="$EXP/after.0.restored.fixed.ll" bash "$HERE/fa_route_build.sh" > /dev/null 2>&1
drive fixed
echo "## 5. 負の対照 (2 store を戻すが [rbp-0x10] と [rbp-8] を別 alloca のままにする)"
$P restore --separate --src "$RT/after.0.restored.ll" --out "$EXP/after.0.restored.sep.ll"
FA_SRC="$EXP/after.0.restored.sep.ll" bash "$HERE/fa_route_build.sh" > /dev/null 2>&1
SWEEP=0 drive sep
if [ "${SWEEP:-0}" = 1 ]; then
  python3 - "$EXP/sweep_base.jsonl" "$EXP/sweep_fixed.jsonl" <<'PY'
import json, sys
def load(p):
    rows = [json.loads(l) for l in open(p) if l.strip()]
    return {r.get('va'): r for r in (x[0] if isinstance(x, list) else x for x in rows)}
def cls(r):
    if r.get('status') or r.get('native_err', 0) > 0: return 'native crash/timeout'
    if r.get('wasm_err', 0) > 0: return 'wasm のみ err'
    if r.get('mismatch', 0) > 0 or not r.get('n'): return '値の不一致'
    return 'bit一致'
b, f = load(sys.argv[1]), load(sys.argv[2])
keys = ('n', 'match', 'mismatch', 'wasm_err', 'native_err')
d = [va for va in b if any(b[va].get(k) != f[va].get(k) for k in keys) or cls(b[va]) != cls(f[va])]
print('base と fixed で行が異なる関数: %d 件' % len(d))
for va in d:
    print(' ', va, cls(b[va]), {k: b[va].get(k) for k in keys}, '->', cls(f[va]), {k: f[va].get(k) for k in keys})
PY
fi
echo "## 6. 後始末: 負の対照の route と wc を base (現 IR) で作り直す (後続の fa_sweep.sh が負の対照の route を拾わないように)"
bash "$HERE/fa_route_build.sh" > /dev/null 2>&1
bash "$HERE/diff/fa_wc_build.sh" > /dev/null 2>&1
echo "[2394] work/fa_route と work/fa_wc を base で作り直した"
