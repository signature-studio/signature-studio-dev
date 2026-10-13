#!/usr/bin/env python3
"""g1_e2e.sh の末尾で「未解決の観測」を数える (gate ではない: 既知の未解決を件数で出し、黙らせない)。 常に exit 0。
  1. 閉包が (taint で) 発行する Dispatcher ID のうち P0b の応答表 (framework/hostshim/hs_ids.json) に無いもの
  2. 静的な間接 call があるのに lift 後 IR の間接 call が 0 の block 数 (本測定の鎖は PLUG_ICALL=0 = 復元前。 既定鎖 PLUG_ICALL=1 では復元されるので、この数は PLUG_ICALL=0 の IR に対する値)
  3. C++ DLL の `emcc -c` が rc != 0 の数 (work/g1/engines.csv があれば)
"""
import csv, json, os
W = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'work', 'g1')
F = json.load(open(os.path.join(W, 'facts.json')))
miss = {n: f['host']['ids_not_in_hs_ids'] for n, f in F.items() if f['host']['ids_not_in_hs_ids']}
print('findings 1: hs_ids.json に無い Dispatcher ID (taint 検出): %s' % (miss or 'なし'))
drop = tot = 0
sites = ir = 0
seen = set()
for f in F.values():
    b = f['block']
    if b in seen:
        continue
    seen.add(b)
    j = json.load(open(os.path.join(W, 'icall', '%d.icall.json' % b)))
    tot += 1
    sites += j['call_non_iat']
    ir += j['ir_call_ind_total']
    drop += j['call_non_iat'] > 0 and j['ir_call_ind_total'] == 0
print('findings 2: [PLUG_ICALL=0 の鎖] 間接 call が脱落した閉包 (静的>0 かつ IR 0) = %d / %d block (静的 site 計 %d、IR の間接 call 計 %d)' % (drop, tot, sites, ir))
p = os.path.join(W, 'engines.csv')
if os.path.exists(p):
    rows = list(csv.DictReader(open(p, newline='')))
    print('findings 3: C++ DLL の emcc -c rc != 0 = %d / %d 本' % (sum(int(r['emcc_c_rc']) != 0 for r in rows), len(rows)))
