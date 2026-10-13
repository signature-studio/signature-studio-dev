#!/usr/bin/env bash
# reach_509.sh — #509 (LD-9): 指定した関数の「動的到達」を測る (survey 942 unit で各関数の入口を通る回数)。
#   boot_final3.ll の対象関数の入口へ `call void @m11_fnhit(i32 K)` を挿入 → emcc → reach_survey.mjs。
#   m11_ov.c が C で上書きした関数は IR 版が実行されない (hit 0) ことも、この計装で分かる。
# 使い方: bash tools/m11/ldfix/reach_509.sh VA,VA,... [OUT.json]    環境変数: M11_WORK (既定 tools/m11/work) / IR (既定 $M11_WORK/boot_final3.ll)
# 前提: /opt/emsdk, node, m11_build.sh を 1 回実行済み (work/obj/*.o)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M11="$(cd -- "$HERE/.." && pwd)"
W="${M11_WORK:-$M11/work}"
IR="${IR:-$W/boot_final3.ll}"
VAS="${1:?VA,VA,...}"
OUTJ="${2:-${RUNNER_TEMP:-/tmp}/reach_509.json}"
D="${RUNNER_TEMP:-/tmp}/reach_509_build"; rm -rf "$D"; mkdir -p "$D"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
python3 - "$IR" "$D/probe.ll" "$VAS" <<'PY'
import re, sys
src, dst, vas = sys.argv[1], sys.argv[2], sys.argv[3].split(',')
t = open(src, errors='replace').read()
n = 0
for k, va in enumerate(vas):
    m = re.search(r'(^define [^\n]*@function_%s\([^\n]*\{\n[^\n]*:[^\n]*\n)' % va, t, re.M)
    if not m:
        sys.exit('function_%s の入口が見つからない' % va)
    t = t[:m.end()] + '  call void @m11_fnhit(i32 %d)\n' % k + t[m.end():]
    n += 1
t += '\ndeclare void @m11_fnhit(i32)\n'
open(dst, 'w').write(t)
open(dst + '.n', 'w').write(str(n))
print('[reach] 計装 %d 関数' % n)
PY
cat > "$D/fnhit.c" <<C
unsigned m11_fnhit_c[256];
void m11_fnhit(int k) { m11_fnhit_c[k & 255]++; }
unsigned m11_fnhit_get(int k) { return m11_fnhit_c[k & 255]; }
void m11_fnhit_reset(void) { for (int i = 0; i < 256; i++) m11_fnhit_c[i] = 0; }
int m11_fnhit_n(void) { return $(cat "$D/probe.ll.n"); }
C
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
export TMPDIR="$D"
CF="-w -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0}"
emcc -c "$D/probe.ll" -o "$D/boot.o" $CF
emcc -c "$D/fnhit.c" -o "$D/fnhit.o" $CF
OBJS=$(ls "$W"/obj/*.o | grep -v '/boot\.o$')
EXPORTS=$(grep -o '^EXPORTS=.*' "$M11/m11_build.sh" | cut -d= -f2),_m11_fnhit_get,_m11_fnhit_reset,_m11_fnhit_n
emcc $OBJS "$D/boot.o" "$D/fnhit.o" -o "$D/m11_probe.cjs" \
  -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE="$((0x10000000))" \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=m11create -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 \
  --no-entry -Wl,--export-all \
  -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,HEAPF32,HEAP32,HEAPF64,HEAPU32,HEAP64,wasmTable,addFunction \
  -sEXPORTED_FUNCTIONS=$EXPORTS \
  -Wl,--initial-memory="$((0x12000000))" -Wl,--max-memory="$((0x72000000))" 2> "$D/link.log" || { tail -20 "$D/link.log"; exit 1; }
python3 "$M11/m11_postjs.py" "$D/m11_probe.cjs" 2>/dev/null
node "$HERE/reach_survey.mjs" "$D/m11_probe.cjs" "$W/m11_image.bin" "$OUTJ"
python3 - "$OUTJ" "$VAS" <<'PY'
import json, sys, collections
per = json.load(open(sys.argv[1])); vas = sys.argv[2].split(',')
print('| 関数 | 実行された unit 数 | 入口通過 総回数 | 実行された unit (先頭 8) |')
print('|---|--:|--:|---|')
for k, va in enumerate(vas):
    us = [(r['unit'], r['hits'][str(k)]) for r in per if str(k) in r['hits']]
    print('| %s | %d | %d | %s |' % (va, len(us), sum(h for _, h in us), ' '.join(str(u) for u, _ in us[:8])))
PY
