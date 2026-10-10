import sys,json
t=sys.stdin.read(); i=t.index('[\n'); print(t[:i].strip())
for r in json.loads(t[i:]):
    print(r['fn'].ljust(26),'elems',str(r['elems']).rjust(7),'exact',str(r['bit_exact']).rjust(7),'nanpl',str(r['nan_payload_diff']).rjust(4),'diff',str(r['differ']).rjust(6),'stmis',str(r['status_mismatch']).rjust(3),'maxulp',r['max_ulp'],'maxrel',r['max_rel'],r['first_ref_bits'],r['first_ours_bits'])
