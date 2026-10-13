"""MCPTools の flapi kw 呼出し (mcp_kwcalls_extract.py の出力) を fl_api.bind に通す。PY-15 #653。
  python3 tests/mcp_kwcalls_bind.py <src DIR> <calls.json> [--neg]
判定 (distinct パターンごと。1 件でも外れたら exit 1):
  - TypeError なしで束縛される
  - 位置引数 (100000+i) は先頭 npos 個がそのまま入る
  - kw の値 (200000+i) は、その kw 名が kwlist (無ければ stubs 署名) で最初に現れる位置に入る
  - それ以降の値は、同名 stubs の単純リテラル既定値と一致する (別の引数の既定値・未知の値は不合格)
--neg: 不合格になる呼出し channels.getChannelVolume(1, useGlobalIndex=True) を 1 件足す (途中の useDb は既定値不明で省略不可)。
  その場合 exit 1 にならなければ判定器が壊れている (ネガコン)。
"""
import ast, json, os, sys, types

argv = sys.argv[1:]
neg = "--neg" in argv
src, calls_path = [a for a in argv if a != "--neg"][:2]
HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.join(HERE, "..", "analysis/flapi/flapi_table.json")
calls = []
fake = types.ModuleType("_flhost"); fake.HostError = type("HostError", (Exception,), {})
fake.call = lambda fid, a: calls.append((fid, a)) or 0
sys.modules["_flhost"] = fake
sys.path.insert(0, os.path.abspath(src))
import fl_api
fl_api.install(TABLE)
t = json.load(open(TABLE))
rows = json.load(open(calls_path))
if neg:
    rows.append(["channels", "getChannelVolume", 1, ["useGlobalIndex"], "NEG-CONTROL", None])


def spec(mod, name):
    e = t["modules"][mod][name]
    stub = (e.get("sig") or {}).get("params", [])
    D = {}
    for p in stub:
        if p["default"] is not None and p["name"] not in D:
            try:
                D[p["name"]] = ast.literal_eval(p["default"])
            except (ValueError, SyntaxError):
                pass
    kl = ((e.get("kwsig") or {}).get("kwlist"))
    names = list(kl) if kl is not None else [p["name"] for p in stub]
    return names, D


def ident(v):
    return isinstance(v, int) and not isinstance(v, bool) and 200000 <= v < 300000


def verdict(res, npos, kw, names, D):
    errs = []
    if tuple(res[:npos]) != tuple(100000 + i for i in range(npos)):
        errs.append(f"positional {res[:npos]}")
    for i, k in enumerate(kw):
        if k not in names:
            errs.append(f"kw {k} not in kwlist"); continue
        j = names.index(k)
        if j < npos:
            errs.append(f"kw {k} at positional slot {j}")
        elif j >= len(res) or res[j] != 200000 + i:
            errs.append(f"kw {k} not at slot {j} (got {res[j:j + 1]})")
    for j in range(npos, len(res)):
        v = res[j]
        if ident(v):
            if j >= len(names) or names[j] != kw[v - 200000]:
                errs.append(f"kw id {v - 200000} ({kw[v - 200000]}) at slot {j}")
        elif j < len(names) and names[j] in D and v == D[names[j]]:
            pass
        else:
            errs.append(f"slot {j} ({names[j] if j < len(names) else '?'}) = {v!r} is not a same-name stubs literal default")
    return errs


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
        errs = verdict(res, npos, kw, *spec(mod, name))
        outc = "ok" if not errs else "NG " + "; ".join(errs)
    except TypeError as e:
        res, outc = None, "TypeError: " + str(e)[:80]
    except Exception as e:
        res, outc = None, type(e).__name__ + ": " + str(e)[:80]
    key = (mod, name, npos, tuple(kw))
    if key in seen:
        continue
    seen[key] = outc
    if outc == "ok": ok += 1
    else: bad += 1
    print(f"{mod}.{name}(pos={npos}, kw={kw}) -> {outc} {res if res is None else res}")
print(f"distinct patterns {len(seen)}: pass {ok}, fail {bad}")
print("mcp_kwcalls_bind:", "PASS" if bad == 0 else "FAIL")
sys.exit(0 if bad == 0 else 1)
