#!/usr/bin/env bash
# P8 実 OTT: 相対化 lift の PIC 税 (LIFTLIB-15 / #1201)。同じ相対化 lift を
#   static_reloc     = lift_build.sh (OTT_RELOC=1, MODULARIZE, 非 PIC)  … bench_real.mjs で駆動
#   side_reloc_hidden = side_build.sh (SIDE_VIS=hidden, -fPIC -fvisibility=hidden, SIDE_MODULE) … side_bench.mjs で dlopen 駆動
# で N=1 の定常 µs/block を交互に RUNS 回ずつ測り、比 (side/static) を出す。
#   bash tools/perf/p8/real/pic_tax.sh            (既定 RUNS=5)
# 前提: tools/ott/work/lift_reloc/ottl.cjs と tools/ott/work/side_reloc/{side.wasm,host.cjs}。
# 結果 = tools/perf/p8/results/real_ott_pic.jsonl (各行に variant・run・cpu・負荷を付す)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
OTT="$HERE/../../../ott/work"
RUNS="${RUNS:-5}"
CPU="$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')"
RES="$HERE/../results"; mkdir -p "$RES"; OUT="$RES/real_ott_pic.jsonl"; : > "$OUT"
for r in $(seq 1 "$RUNS"); do
  la="$(cut -d' ' -f1-3 /proc/loadavg)"
  node "$HERE/bench_real.mjs" "$OTT/lift_reloc/ottl.cjs" 1 \
    | sed "s/^{/{\"variant\":\"static_reloc\",\"run\":$r,\"cpu\":\"$CPU\",\"loadavg_before\":\"$la\",/" >> "$OUT"
  la="$(cut -d' ' -f1-3 /proc/loadavg)"
  node "$HERE/side_bench.mjs" "$OTT/side_reloc" \
    | sed "s/^{/{\"variant\":\"side_reloc_hidden\",\"run\":$r,\"cpu\":\"$CPU\",\"loadavg_before\":\"$la\",/" >> "$OUT"
  tail -2 "$OUT" | cut -c1-200
done
python3 - "$OUT" <<'PYEOF'
import json, statistics as st, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
s = [r for r in rows if r['variant'] == 'static_reloc']; d = [r for r in rows if r['variant'] == 'side_reloc_hidden']
fmt = lambda rs: '%.2f (%.2f–%.2f)' % (st.median(r['us_per_block_p50'] for r in rs), min(r['us_per_block_p50'] for r in rs), max(r['us_per_block_p50'] for r in rs))
ok = sum(1 for r in rows if r['sig'] == ['6b1696f0'])
pairs = [b['us_per_block_p50'] / a['us_per_block_p50'] for a, b in zip(s, d)]
print('| 構成 (N=1) | µs/block p50 (run 中央, min–max) | 署名 |')
print('|---|--:|---|')
print('| 静的 (非 PIC) 相対化 lift `static_reloc` | %s | 6b1696f0 |' % fmt(s))
print('| SIDE_MODULE `-fPIC -fvisibility=hidden` `side_reloc_hidden` | %s | 6b1696f0 |' % fmt(d))
print('PIC 税 = side / static の中央値比 ×%.3f (run 対ごとの比 min–max ×%.3f–×%.3f, %d 対)' % (st.median(b['us_per_block_p50'] for b in d) / st.median(a['us_per_block_p50'] for a in s), min(pairs), max(pairs), len(pairs)))
print('署名一致 %d/%d プロセス' % (ok, len(rows)))
PYEOF
echo "done: $OUT"
