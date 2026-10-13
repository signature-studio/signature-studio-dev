#!/usr/bin/env python3.12
"""MCPTools.pyc の flapi への kw 呼出しを抽出 (3.12 の dis)。PY-15 #653。
  python3.12 tests/mcp_kwcalls_extract.py <MCPTools.pyc (win64 block25159_DATA.bin)> <out.json>
"""
import marshal, dis, json, sys, types, os
data = open(sys.argv[1], "rb").read()
code = marshal.loads(data[16:])
HERE = os.path.dirname(os.path.abspath(__file__))
t = json.load(open(os.path.join(HERE, "..", "analysis/flapi/flapi_table.json")))
allnames = {}
for m, fs in t["modules"].items():
    for n, e in fs.items():
        allnames[(m, n)] = set(p["name"] for p in (e.get("sig") or {}).get("params", [])) | set((e.get("kwsig") or {}).get("kwlist") or [])
mods = set(t["modules"])
found = []
def walk(co):
    ins = list(dis.get_instructions(co))
    cand = None
    kw = None
    for i, x in enumerate(ins):
        if x.opname in ("LOAD_ATTR", "LOAD_METHOD") and i and ins[i-1].opname in ("LOAD_GLOBAL", "LOAD_NAME") and ins[i-1].argval in mods and (ins[i-1].argval, x.argval) in allnames:
            cand = (ins[i-1].argval, x.argval)
        elif x.opname == "KW_NAMES":
            kw = x.argval
        elif x.opname == "CALL" and kw is not None:
            if cand and set(kw) <= allnames[cand]:
                found.append((cand[0], cand[1], x.arg - len(kw), list(kw), co.co_name, x.starts_line))
            kw = None
    for c in co.co_consts:
        if isinstance(c, types.CodeType):
            walk(c)
walk(code)
json.dump(found, open(sys.argv[2], "w"))
for f in found: print(f)
print("total", len(found), "distinct", len(set((a,b,c,tuple(d)) for a,b,c,d,_,_ in found)))
