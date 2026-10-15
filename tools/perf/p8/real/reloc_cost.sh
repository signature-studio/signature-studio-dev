#!/usr/bin/env bash
# P8 実 OTT: 相対化 lift (OTT_RELOC=1) と既定 lift の定常 CPU 比 (LIFTLIB-15 / #1201)。
#   bash tools/perf/p8/real/reloc_cost.sh            (既定 RUNS=3・NS="1 4 16")
# 前提: tools/ott/work/lift_def/ottl.cjs (既定 lift) と tools/ott/work/lift_reloc/ottl.cjs (OTT_RELOC=1 lift)。
#   どちらも同じ HEAD・同じ std profile で `LIFT_OUT=<dir> [OTT_RELOC=1] bash tools/ott/lift/lift_build.sh` して作る。
# 結果 = tools/perf/p8/results/real_ott_reloc.jsonl (各行に variant・run・cpu・負荷を付す)。
# 既定 lift と相対化 lift を交互に (run ごとに N の順に) 別プロセスで測る。N ごとの比は末尾の表。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
OTT="$HERE/../../../ott/work"
RUNS="${RUNS:-3}"
CPU="$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')"
RES="$HERE/../results"; mkdir -p "$RES"; OUT="$RES/real_ott_reloc.jsonl"; : > "$OUT"
for r in $(seq 1 "$RUNS"); do
  for n in ${NS:-1 4 16}; do
    for v in lift_def lift_reloc; do
      la="$(cut -d' ' -f1-3 /proc/loadavg)"
      node "$HERE/bench_real.mjs" "$OTT/$v/ottl.cjs" "$n" \
        | sed "s/^{/{\"variant\":\"$v\",\"run\":$r,\"cpu\":\"$CPU\",\"loadavg_before\":\"$la\",/" >> "$OUT"
      tail -1 "$OUT" | cut -c1-220
    done
  done
done
python3 - "$OUT" <<'PYEOF'
import json, statistics as st, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
by = {}
for r in rows:
    by.setdefault((r['N'], r['variant']), []).append(r)
print('| N | 既定 lift µs/block (run 中央, min–max) | 相対化 lift µs/block | 比 (相対化/既定, 中央値の比) | 署名 |')
print('|--:|--:|--:|--:|---|')
for n in sorted({r['N'] for r in rows}):
    d = by[(n, 'lift_def')]; x = by[(n, 'lift_reloc')]
    dm = st.median(r['us_per_block_p50'] for r in d); xm = st.median(r['us_per_block_p50'] for r in x)
    fmt = lambda rs: '%.2f (%.2f–%.2f)' % (st.median(r['us_per_block_p50'] for r in rs), min(r['us_per_block_p50'] for r in rs), max(r['us_per_block_p50'] for r in rs))
    sigs = sorted({s for r in d + x for s in r['sig']})
    ok = sum(1 for r in d + x if r['sig'] == ['6b1696f0'])
    print('| %d | %s | %s | ×%.3f | %s (プロセス %d/%d 一致) |' % (n, fmt(d), fmt(x), xm / dm, ','.join(sigs), ok, len(d + x)))
PYEOF
echo "done: $OUT"
