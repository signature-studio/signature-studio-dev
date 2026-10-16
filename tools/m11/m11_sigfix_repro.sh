#!/usr/bin/env bash
# #5481 (M11-N245): sigfix40c の 4 variant (only40c・ctlB・ctlC・sigzero) を、各回 work/obj と boot_final3.ll を消して clean build し、同じ IR で survey を 2 回取る.
# 前提: work/boot_final.ll と work/ir_conditions.json (m11_gen_ir2.sh で作る)、work/sigfix40c/<variant>.ll (m11_sigfix40c_ab.py で作る)、
#       ANALYSIS_DIR (PE は $ANALYSIS_DIR/win64/extracted/block00031_PE.bin)、emsdk、node。
# 出力: work/repro5481/ (gitignore)。1 行 RESULT を variant × 2 回ぶん出す。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
OUT=work/repro5481
mkdir -p "$OUT"
for v in "$@"; do
  for r in 1 2; do
    # m11_build.sh は xmm_args.stamp が変わると boot_final.xa.ll を全関数変換版に作り直す。stamp を先に合わせて variant を残す
    echo "1:" > work/xmm_args.stamp
    cp "work/sigfix40c/$v.ll" work/boot_final.xa.ll
    rm -rf work/obj work/boot_final3.ll
    s=$(date +%s)
    M11_XMM_ARGS=1 bash m11_build.sh > "$OUT/build_${v}_$r.log" 2>&1; brc=$?
    b=$(( $(date +%s) - s ))
    cmp -s work/boot_final.xa.ll "work/sigfix40c/$v.ll" || echo "ERROR xa.ll is not $v" >&2
    s=$(date +%s)
    M11_SURVEY_UNITS="$OUT/survey_${v}_$r.json" timeout 300 node m11_survey.mjs > "$OUT/survey_${v}_$r.out" 2>&1; src=$?
    t=$(( $(date +%s) - s ))
    python3 - "$OUT/survey_${v}_$r.json" "$v" "$r" "$brc" "$src" "$b" "$t" <<'PY'
import json, sys
from collections import Counter
p, v, r, brc, src, b, t = sys.argv[1:]
try:
    c = Counter(json.load(open(p)))
    print('RESULT variant=%s run=%s build_rc=%s survey_rc=%s build_s=%s survey_s=%s ok=%d trap=%d miss=%d noproc=%d clobber=%d' % (
        v, r, brc, src, b, t, c['ok'], c['trap'], c['miss'], c['noproc'], c['clobber']))
except Exception as e:
    print('RESULT variant=%s run=%s ERR %s' % (v, r, e))
PY
    sha256sum work/boot_final3.ll >> "$OUT/ir_sha256_${v}_$r.txt"
  done
done
