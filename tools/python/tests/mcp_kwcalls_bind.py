"""MCPTools の flapi kw 呼出し (mcp_kwcalls_extract.py の出力) を fl_api.bind に通す。PY-15 #653。
  python3 tests/mcp_kwcalls_bind.py <src DIR> <calls.json>
"""
import json, sys, types, os
src = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
calls = []
fake = types.ModuleType("_flhost"); fake.HostError = type("HostError", (Exception,), {})
fake.call = lambda fid, a: calls.append((fid, a)) or 0
sys.modules["_flhost"] = fake
sys.path.insert(0, os.path.abspath(src))
import fl_api
fl_api.install(os.path.join(HERE, "..", "analysis/flapi/flapi_table.json"))
rows = json.load(open(sys.argv[2]))
seen = {}
ok = bad = 0
for mod, name, npos, kw, caller, _ in rows:
    f = getattr(sys.modules[mod], name)
    pos = tuple(100000 + i for i in range(npos))
    K = {k: 200000 + i for i, k in enumerate(kw)}
    calls.clear()
    try:
        f(*pos, **K)
        res = calls[-1][1]
        outc = "ok"
    except TypeError as e:
        res, outc = None, "TypeError: " + str(e)[:80]
    except Exception as e:
        res, outc = None, type(e).__name__ + ": " + str(e)[:80]
    key = (mod, name, npos, tuple(kw))
    if key in seen: continue
    seen[key] = outc
    if outc == "ok": ok += 1
    else: bad += 1
    print(f"{mod}.{name}(pos={npos}, kw={kw}) -> {outc} {res if res is None else res}")
print(f"distinct patterns {len(seen)}: pass {ok}, fail {bad}")
