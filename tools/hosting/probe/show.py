#!/usr/bin/env python3
# show.py <result.json>... — work/results/*.json を 1 行/run で要約
import sys, json
for f in sys.argv[1:]:
    d = json.load(open(f))
    print('##', d['name'], d['url'])
    for r in d['runs']:
        p = r.get('result') or {}
        w = p.get('worker') or {}
        m = p.get('main') or {}
        full = w.get('fullGet') or {}
        rp = w.get('rangeParallel') or {}
        ch = w.get('chunks') or {}
        rg = w.get('range') or {}
        print('   access:', r.get('accessCookie'))
        print(f"run{r['run']} wall={r['wallSec']}s err={r.get('err') or p.get('fatal') or w.get('error')} iso(main/worker)={m.get('crossOriginIsolated')}/{(w.get('worker') or {}).get('crossOriginIsolated')} sab={m.get('sabAlloc')} img={m.get('imgNoCors')}")
        print(f"   full: st={full.get('status')} {full.get('MBps')}MB/s {full.get('sec')}s bad={full.get('badPieces')} {full.get('error','')}")
        print(f"   rangePar: {rp.get('statuses')} bad={rp.get('badPieces')} {rp.get('MBps')}MB/s {rp.get('error','')}")
        print(f"   chunks: st={ch.get('statuses')} bad={ch.get('badIds')} {ch.get('MBps')}MB/s {ch.get('reqPerSec')}req/s p50={ch.get('p50ms')} p95={ch.get('p95ms')} cache={ch.get('cacheStorageHit')} {ch.get('error','')}")
        print('   range:', {k: (v.get('error') or f"{v.get('status')}{'ok' if v.get('same') else 'NG'}") for k, v in rg.items() if isinstance(v, dict) and k != 'ms'}, rg.get('error', ''))
    r = d['runs'][0]; p = r.get('result') or {}; w = p.get('worker') or {}
    print('   cond:', w.get('conditional'))
    print('   ext:', {k: (v if 'error' in v else f"{v['status']} ct={v['ct']} ce={v['ce']} {v['bytes']}/{v['expected']}") for k, v in (w.get('ext') or {}).items() if k != 'ms'})
    print('   wasmParts:', w.get('wasmParts'))
    print('   wasm:', w.get('wasmStreaming'), 'noCorsFetch:', w.get('noCorsFetch'))
    print('   headBig:', (w.get('headBig') or {}).get('headers'))
    print('   worklet:', (p.get('main') or {}).get('worklet'))
    print('   failed:', r.get('failed'), 'logs:', r.get('logs'))
