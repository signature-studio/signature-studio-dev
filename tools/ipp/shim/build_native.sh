#!/usr/bin/env bash
# native (x86-64 Linux) 検証バイナリをビルド: work/shim/bin/{shim_selftest,shim_ref}
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; IPP="$(dirname "$HERE")"; W="$IPP/work/shim"; mkdir -p "$W/bin"
python3 "$HERE/gen_shim.py" > "$W/gen_shim.log"
gcc -std=gnu11 -Wall -Werror -fsyntax-only "$HERE/test/proto_check.c"          # 署名検査 (ipp_min.h vs 生成プロトタイプ)
CF="-std=gnu11 -O2 -ffp-contract=off -fno-fast-math -Wall -Wno-unused-function -Wno-stringop-overflow -Wno-array-bounds -Wno-maybe-uninitialized -Wno-misleading-indentation -I$IPP/src"
SH="$HERE/src/ipp_shim.c $HERE/gen/ipp_shim_tab.c $HERE/test/tramp_x86_64.c"
IMPL="$IPP/src/ipp_min.c $(ls "$HERE"/fft/*.c "$HERE"/fft/pffft/*.c 2>/dev/null || true) $(ls "$HERE"/impl/*.c 2>/dev/null || true)"
gcc $CF -o "$W/bin/shim_selftest" $HERE/test/shim_selftest.c $HERE/test/gen/probe_thunks.c $SH $IMPL -lm
gcc $CF -o "$W/bin/shim_ref" $HERE/test/shim_ref.c $IPP/ref/pe_load.c $SH $IMPL -lm
IPP="$IPP" python3 - <<'PY' > "$W/names.txt"
import json,os
print('\n'.join(n for n in json.load(open(os.environ.get('IPP','..')+'/work/flengine_ipp_names.json'))['x86_64'] if n.startswith('ipp')))
PY
echo "built: $W/bin"
