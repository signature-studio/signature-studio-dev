#!/usr/bin/env bash
# link_d17_e2e.sh — #1740 (LD-61) 1:1 対応付け pass の 1 コマンド再現。work-m11 と fl-win64 不要 (image は work-m11 の m11_image.bin)。
#   1/6 audit (修復前) → 2/6 fix_d17.py (単一 load) → 3/6 link_d17.py (複数 load・1:1 のみ)
#   → 4/6 audit (fix_d17 のみ = ネガコン) → 5/6 audit (fix + link) → 6/6 emcc 構文検証 (fix + link)
# 使い方: bash tools/m11/ldfix/link_d17_e2e.sh     環境変数: M11_WORK (既定 tools/m11/work) / PY / RUNNER_TEMP
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
W="${M11_WORK:-$REPO/tools/m11/work}"
OUT="${RUNNER_TEMP:-/tmp}/link_d17_e2e"; mkdir -p "$OUT"
PY="${PY:-python3}"
IR="$W/boot_final3.ll"; IMG="$W/m11_image.bin"; CFG="$W/boot*.drc.config.json"
step() { echo "[link_d17_e2e] $*"; }

step "1/6 audit (修復前)"
"$PY" "$HERE/audit_lsf_ssa.py" "$IR" "$IMG" "$CFG" --json "$OUT/ssa_base.json" | head -1 || exit 1
step "2/6 fix_d17.py (単一 load)"
"$PY" "$HERE/fix_d17.py" "$IR" "$OUT/ssa_base.json" "$OUT/boot_d17.ll" --report "$OUT/d17_report.json" || exit 1
step "3/6 link_d17.py (複数 load・1:1 のみ)"
"$PY" "$HERE/link_d17.py" "$OUT/boot_d17.ll" "$OUT/ssa_base.json" "$IMG" "$CFG" "$OUT/boot_link.ll" --report "$OUT/link_report.json" || exit 1
step "4/6 audit (ネガコン: fix_d17 のみ)"
"$PY" "$HERE/audit_lsf_ssa.py" "$OUT/boot_d17.ll" "$IMG" "$CFG" --json "$OUT/ssa_neg.json" | head -1 || exit 1
step "5/6 audit (fix_d17 + link)"
"$PY" "$HERE/audit_lsf_ssa.py" "$OUT/boot_link.ll" "$IMG" "$CFG" --json "$OUT/ssa_link.json" | head -1 || exit 1
step "6/6 emcc 構文検証 (修復 IR)"
if ! source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1 || ! command -v emcc > /dev/null 2>&1; then
  echo "[link_d17_e2e] FAIL: emsdk が無い (/opt/emsdk/emsdk_env.sh の source か emcc の検出に失敗)" >&2
  exit 2
fi
export TMPDIR="$OUT/tmp"; mkdir -p "$TMPDIR"
emcc -c "$OUT/boot_link.ll" -o "$OUT/boot_link.o" -w -Wno-error=int-conversion -O0 -g1 || { echo "[link_d17_e2e] FAIL: emcc rc!=0" >&2; exit 1; }
echo "[link_d17_e2e] emcc rc=0"
"$PY" - "$OUT" <<'EOF'
import json, sys, collections
O = sys.argv[1]
for name in ('ssa_base', 'ssa_neg', 'ssa_link'):
    a = json.load(open('%s/%s.json' % (O, name)))
    c = collections.Counter(); fns = set()
    for va, v in a['functions'].items():
        for s in v['sites']:
            cc = s.get('cell')
            if cc and not s['frame']:
                c[cc['verdict']] += 1
                if cc['verdict'] == 'CELL_COLLAPSED':
                    fns.add(va)
    print('[link_d17_e2e] %s store_CC_site=%d store_CC_fn=%d store_CELL_DEEP=%d' % (name, c['CELL_COLLAPSED'], len(fns), c['CELL_DEEP']))
EOF
