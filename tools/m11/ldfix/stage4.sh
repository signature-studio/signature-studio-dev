#!/usr/bin/env bash
# stage4.sh — ldfix 修復 IR で m11_e2e.sh 相当の stage4 (FastMM4 実行) 回帰を自 dir 内で再現する。
#   既存 tools/m11 のファイルは一切変更しない (ソースは読み込むのみ、成果物は ldfix/work/stage4/ に出す)。
#   使い方: bash stage4.sh <IR.ll> <name>   (name: base|fix など。work/stage4/<name>/ に成果物)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M11="$HERE/.."
IR="${1:?IR.ll required}"
IR="$(readlink -f "$IR")"
NAME="${2:?name required}"
S4="$HERE/work/stage4"
W="$S4/$NAME"
mkdir -p "$W/obj" "$W/tmp" "$S4"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
export TMPDIR="$W/tmp"
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} ${S4_EXTRA_CF:-}"

# 署名 header (m11_post.py と同一規約: IR の define 署名から C prototype を生成)
python3 - "$IR" "$W/boot_final3_sigs.h" <<'PYEOF'
import re, sys
src, dst = sys.argv[1], sys.argv[2]
CT = {'i64': 'unsigned long long', 'i32': 'unsigned int', 'i16': 'unsigned int', 'i8': 'unsigned int', 'i1': 'unsigned int',
      'ptr': 'void*', 'void': 'void', 'i128': 'unsigned __int128', 'double': 'double', 'float': 'float'}
out = ['/* auto-gen by ldfix stage4.sh: IR function_* の C 署名 (m11_post.py 規約と同一) */']
ptypes_re = re.compile(r'^define (?P<ret>[^@]*?)@(?P<nm>function_[0-9a-f]+)\((?P<args>[^)]*)\)', re.M)
for m in ptypes_re.finditer(open(src, errors='replace').read()):
    ret = m.group('ret').strip().split()[0] if m.group('ret').strip() else 'void'
    args = [a.strip().split()[0] for a in m.group('args').split(',') if a.strip()]
    ats = ', '.join(CT.get(t, 'unsigned long long') for t in args) or 'void'
    out.append('extern %s %s(%s);' % (CT.get(ret, 'unsigned long long'), m.group('nm'), ats))
open(dst, 'w').write('\n'.join(out) + '\n')
print('[stage4] sigs header: %d' % (len(out) - 1))
PYEOF

cc() { # cc <src> <obj> [extra deps...]
  local src="$1" obj="$2"; shift 2
  local need=0
  [ ! -f "$obj" ] && need=1
  [ "$src" -nt "$obj" ] && need=1
  for d in "$@"; do [ "$d" -nt "$obj" ] && need=1; done
  if [ $need = 1 ]; then
    echo "[stage4/$NAME] cc $src"
    case "$src" in
      *.ll) emcc -c "$src" -o "$obj" $CF ;;
      *)    emcc -c "$src" -o "$obj" $CF -I"$W" -I. ;;
    esac
  fi
}

# shim / m11 共通ソース (読込のみ)
for f in heap failfast file timer sync; do cc "$M11/../shim/src/$f.c" "$W/obj/shim_$f.o"; done
cc "$M11/m11_rt.c" "$W/obj/rt.o"
cc "$M11/m11_win.c" "$W/obj/win.o"
llvm-nm --defined-only "$W"/obj/shim_*.o "$W/obj/rt.o" "$W/obj/win.o" 2>/dev/null | awk '$2 ~ /^[TtWwDd]$/ {print $3}' | sort -u > "$W/defined_c.txt"
if [ ! -f "$W/m11_winstubs.c" ] || [ "$W/defined_c.txt" -nt "$W/m11_winstubs.c" ] || [ "$IR" -nt "$W/m11_winstubs.c" ]; then
  (cd "$M11" && M11_EXCLUDE="$W/defined_c.txt" python3 m11_genstubs.py "$IR" "$W" > "$W/genstubs.log") || { echo genstubs failed; tail -5 "$W/genstubs.log"; exit 1; }
fi
cc "$IR" "$W/obj/boot.o"
# SIMD helper (m11_simd2.py は tools/m11 のスクリプトを実行するだけ; 出力は自 dir)
if [ ! -f "$W/m11_simd.c" ] || [ "$IR" -nt "$W/m11_simd.c" ]; then
  (cd "$M11" && python3 m11_simd2.py "$IR" > "$W/m11_simd.c" 2> "$W/simd2.log") || { echo simd2 failed; tail -5 "$W/simd2.log"; exit 1; }
fi
cp "$M11/msimd11_core.h" "$S4/msimd11_core.h"
cc "$W/m11_simd.c" "$W/obj/simd.o" "$M11/msimd11_core.h"
cc "$W/m11_winstubs.c" "$W/obj/winstubs.o"
cc "$W/m11_fnstubs.c" "$W/obj/fnstubs.o"
cc "$M11/m11_ov.c" "$W/obj/ov.o" "$W/boot_final3_sigs.h"
[ -f "$M11/work/m11_data.c" ] || { echo "[stage4] m11_data.c 無し (m11_e2e.sh を先に)"; exit 2; }
cc "$M11/work/m11_data.c" "$W/obj/data.o"

INITMEM="$((0x12000000))"
MAXMEM="$((0x72000000))"
EXPORTS=_m11_boot_enter,_entry_point,_m11_init_count,_m11_boot_stage,_m11_va_used,_m11_va_calls,_m11_set_trace,_m11_icall_ok,_m11_icall_miss,_m11_icall_miss_uniq,_m11_icall_miss_at,_m11_disp_count,_m11_units_run,_m11_units_total,_m11_units_skipped,_m11_stub_total,_m11_stub_uniq,_m11_stub_name,_m11_stub_count,_m11_probe_count,_m11_longjmp_hit,_m11_set_survey,_m11_call_unit,_m11_unit_va,__emscripten_stack_restore,_emscripten_stack_get_current
echo "[stage4/$NAME] link"
emcc "$W"/obj/*.o -o "$W/m11_boot.cjs.tmp" \
  -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE="$((0x10000000))" \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=m11create \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 \
  --no-entry -Wl,--export-all \
  -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,HEAPF32,HEAP32,HEAPF64,HEAPU32,HEAP64,wasmTable,addFunction \
  -sEXPORTED_FUNCTIONS=$EXPORTS \
  -Wl,--initial-memory="$INITMEM" -Wl,--max-memory="$MAXMEM" 2> "$W/link.log" || { tail -30 "$W/link.log"; exit 1; }
mv "$W/m11_boot.cjs.tmp" "$W/m11_boot.cjs"
python3 "$M11/m11_postjs.py" "$W/m11_boot.cjs" > /dev/null 2>&1
echo "[stage4/$NAME] build OK: wasm-ld signature mismatch: $(grep -c 'signature mismatch' "$W/link.log" || true), undefined symbol: $(grep -c 'undefined symbol' "$W/link.log" || true)"

# 実行 (イメージは tools/m11/work の既存物を読込のみで使用)
export S4_NAME="$NAME"
export S4_IMAGE="$M11/work/m11_image.bin"
cp "$M11/work/boot_final3_probes.json" "$W/boot_final3_probes.json"
M11_TRACE=${M11_TRACE:-0} timeout 300 node "$HERE/run_stage4.mjs" > "$W/e2e_full.out" 2> "$W/e2e_full.err" || true
grep -o 'M11_RESULT {.*}' "$W/e2e_full.out" | head -1 > "$W/result.jsonline"
python3 - "$W/result.jsonline" <<'PYEOF'
import json, sys
try:
    r = json.loads(open(sys.argv[1]).read().strip().replace('M11_RESULT ', '', 1))
except Exception as e:
    print('STAGE4_RESULT {"error": "no M11_RESULT"}'); sys.exit(0)
pr = r.get('probes') or {}
stage = 0
if r.get('image_bytes'): stage = 1
if (r.get('icall_ok') or 0) >= 1: stage = 2
if (r.get('units_total') or 0) >= 1: stage = 3
if (r.get('va_calls') or 0) >= 1 and (pr.get('GetMem') or 0) >= 1: stage = 4
out = {'name': r.get('wasm_size') and 'ok', 'stage4': stage >= 4, 'reached_stage_probe': stage,
       'wasm_size': r.get('wasm_size'), 'boot_stage': r.get('boot_stage'), 'init_count': r.get('init_count'),
       'units_run': r.get('units_run'), 'units_total': r.get('units_total'),
       'getmem': pr.get('GetMem'), 'freemem': pr.get('FreeMem'),
       'fastmm_getmem_impl': pr.get('FastMM_GetMem(407a50)'),
       'va_calls': r.get('va_calls'), 'va_used': r.get('va_used'),
       'icall_ok': r.get('icall_ok'), 'icall_miss': r.get('icall_miss'),
       'disp_entries': r.get('disp_entries'), 'stub_uniq': r.get('stub_uniq'),
       'dllmain_done': r.get('dllmain_done'), 'threw': r.get('threw'), 'boot_rc': r.get('boot_rc')}
print('STAGE4_RESULT ' + json.dumps(out))
PYEOF
