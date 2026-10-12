#!/usr/bin/env bash
# #131: sigfix 0 詰め site の計測・機械語分類・定数復元の独立検算 (1 コマンド再現; emcc/wasm は不要)
# 前提: work/boot_final.ll (work-m11), capstone/pefile (python), FL_WIN64_DIR (extracted/block00031_PE.bin)
# 使い方: bash tools/m11/m11_sigfix_stats.sh [OUTDIR]     (既定 work/sigfix_stats)
set -euo pipefail
cd "$(dirname "$0")"
source ../shared/env.sh
PE="${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
OUT="${1:-work/sigfix_stats}"
mkdir -p "$OUT" results
python3 m11_post.py work/boot_final.ll "$OUT/final3_base.ll" --report "$OUT/post_base.json" --pads "$OUT/pads.json"
cmp "$OUT/final3_base.ll" work/boot_final3.ll 2>/dev/null && echo "[stats] 既定出力は work/boot_final3.ll と byte 一致" || echo "[stats] (work/boot_final3.ll は復元モード or 未生成: 比較スキップ)"
python3 m11_argrecover.py "$OUT/pads.json" --pe "$PE" --out "$OUT/fixes.json" | tee "$OUT/argrecover.txt"
python3 m11_argrecover_verify.py "$OUT/fixes.json" --pe "$PE"
python3 - "$OUT" > results/sigfix_zeropad_remaining.tsv <<'EOF2'
import json, sys
d = json.load(open(sys.argv[1] + '/fixes.json'))
print('caller\tcallee\tk\thave\twant\tstatus\tpos:class')
for r in d['site_detail']:
    print('\t'.join(map(str, [r['caller'], r['callee'], r['k'], r['have'], r['want'], r['status'], ','.join('%s:%s' % (k, v) for k, v in r['args'].items())])))
EOF2
python3 m11_post.py work/boot_final.ll "$OUT/final3_rec.ll" --report "$OUT/post_rec.json" --fixes "$OUT/fixes.json"
python3 - "$OUT" <<'EOF'
import json, sys
o = sys.argv[1]
b = json.load(open(o + '/post_base.json')); r = json.load(open(o + '/post_rec.json'))
print('[stats] zeropad sites %d / args %d; const recovered %d (base %d)' % (b['sigfix_zeropad_sites'], b['sigfix_zeropad_args'], r['sigfix_const_recovered'], b['sigfix_const_recovered']))
EOF
