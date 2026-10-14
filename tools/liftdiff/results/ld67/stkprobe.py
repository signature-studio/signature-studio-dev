import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from ldlib.session import Session
from ldlib import cases

target, out = sys.argv[1], sys.argv[2]
FNS = [0x1801c5e84, 0x1801c621c]
sess = Session(target, build=False, trace=False)
nat, was = sess.make_runners()
res = []
try:
    for va in FNS:
        name = sess.fn_name(va)
        sig = sess.sigs[name]
        for fill in (0x00, 0xa5, 0xff):
            line = cases.case_line(va, name, 'vm0', sig, trace=False, stkfill=fill)
            r = was.run_cases([line], [0])[0]
            res.append({'va': hex(va), 'stkfill': hex(fill), 'status': r.get('status'), 'rax': r.get('rax'), 'x0': r.get('x0')})
            print(hex(va), hex(fill), r.get('status'), r.get('rax'), flush=True)
finally:
    nat.close(); was.close()
json.dump(res, open(out, 'w'), indent=1)
