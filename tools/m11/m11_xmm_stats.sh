#!/usr/bin/env bash
# #954 (M11-N54): xmm 署名復元 (fix_xmm_args.py) の内訳・検査なし複製との差・0 詰め 48 引数の内訳を 1 コマンドで出す (emcc/wasm は不要)
# 前提: work/boot_final.ll (work-m11)、capstone/pefile (python)、PE (既定 $FL_WIN64_DIR/extracted/block00031_PE.bin)
# 使い方: bash tools/m11/m11_xmm_stats.sh [OUTDIR]     (既定 work/xmm_stats)
set -euo pipefail
cd "$(dirname "$0")"
source ../shared/env.sh
PE="${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
OUT="${1:-work/xmm_stats}"
FX=../plugins/lift/passes/fix_xmm_args.py
mkdir -p "$OUT"
python3 m11_post.py work/boot_final.ll "$OUT/final3_base.ll" --report "$OUT/post_base.json" --pads "$OUT/pads.json" > /dev/null
python3 m11_argrecover.py "$OUT/pads.json" --pe "$PE" --out "$OUT/fixes.json" > "$OUT/argrecover.txt"
python3 "$FX" work/boot_final.ll "$OUT/xa.ll" --pe "$PE" --report "$OUT/xa_report.json"
# 検査なし複製: arity 検査 (3 行) だけ外す。p0c は元の fix_xmm_args.py と同じ場所を指す
python3 - "$FX" "$OUT/fix_noarity.py" "$(cd ../plugins/p0c && pwd)" <<'EOF'
import sys
src, dst, p0c = sys.argv[1:4]
t = open(src).read()
a = "sys.path.insert(0, os.path.join(HERE, '..', '..', 'p0c'))"
b = ("                    elif any(c != len(plist) for c in arity.get(fname, ())):\n"
     "                        rep['skipped'][fname] = 'call_arity_mismatch(sites=%s, params=%d)' % (\n"
     "                            ','.join(str(c) for c in sorted(arity[fname])), len(plist))\n")
assert t.count(a) == 1 and t.count(b) == 1
open(dst, 'w').write(t.replace(a, "sys.path.insert(0, %r)" % p0c).replace(b, ''))
EOF
python3 "$OUT/fix_noarity.py" work/boot_final.ll "$OUT/xa_noarity.ll" --pe "$PE" --report "$OUT/xa_noarity_report.json"
python3 - "$OUT" <<'EOF'
import collections, json, sys
O = sys.argv[1]
wr = json.load(open(O + '/xa_report.json'))
nr = json.load(open(O + '/xa_noarity_report.json'))
fx = json.load(open(O + '/fixes.json'))


def why(rep, n):
    if n in rep['fixed']:
        return 'fixed'
    r = rep['skipped'].get(n)
    return 'not_in_report' if r is None else r.split('(')[0]


print('[表2] 検査あり: fixed=%d skipped=%d callsite_zero_args=%d' % (len(wr['fixed']), len(wr['skipped']), wr['callsite_zero_args']))
for k, v in collections.Counter(r.split('(')[0] for r in wr['skipped'].values()).most_common():
    print('  skip %-22s %d' % (k, v))
print('[表3] 検査なし: fixed=%d skipped=%d' % (len(nr['fixed']), len(nr['skipped'])))
ar = sorted(n for n in wr['skipped'] if wr['skipped'][n].startswith('call_arity_mismatch'))
print('[arity] 検査あり call_arity_mismatch=%d: 検査なしでの判定 %s' % (
    len(ar), dict(collections.Counter(why(nr, n) for n in ar))))
xs = set(nr['fixed']) - set(wr['fixed'])
print('[arity] 検査なしで復元される arity skip 件数 (= 49 - 34 の内訳) = %d' % len(xs))
rows = fx['site_detail']
args = [(r['callee'], v) for r in rows for v in r['args'].values() if v == 'set_const_xmm_callee']
print('[0詰め48] set_const_xmm_callee 引数 = %d (callee %d 件)' % (len(args), len(set(c for c, _ in args))))
g = {k: [0, set()] for k in ('fixed', 'call_arity_mismatch', 'slot_occupied')}
for c, _ in args:
    k = why(wr, c)
    g.setdefault(k, [0, set()])
    g[k][0] += 1
    g[k][1].add(c)
for k, (n, cs) in sorted(g.items(), key=lambda x: -x[1][0]):
    print('  %-22s 引数 %3d / callee %3d' % (k, n, len(cs)))
EOF
