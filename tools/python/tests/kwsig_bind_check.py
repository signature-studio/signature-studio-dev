#!/usr/bin/env python3
"""kwlist 全 103 関数の kw 束縛の誤束縛 0 検証 (PY-15 #653)。wasm 不要 (偽 _flhost で fl_api.bind を直接検証)。
  python3 tests/kwsig_bind_check.py [--src DIR]    (DIR 省略時は src/。ネガコン: --src <main の src のコピー>)

各 kwlist 関数について、positional 個数 k (0..max) と kw 名の全部分集合 S を試す。値は識別子付き
(positional = 100000+i、kw = 200000+(その名前の最初の位置)) なので、受け取った tuple の各位置の値の出所が分かる。
期待値は flapi_table.json の仕様から本ファイル内で独立に組み立てる (fl_api の実装は見ない):
  - kw は kwlist の最初の出現だけを束縛 (位置 >= k のもの)。k より前に束縛された名前・未知の名前は TypeError
  - 既定値 = stubs の同名引数の単純リテラルだけ (名前違いの同位置は引き継がない)
  - 既定値不明の引数 (非リテラル / 無し) は、required 位置より後ろなら省略 (以後の未指定は全部省略)、前なら TypeError
  - 省略の後に kw で指定した引数があれば TypeError (途中の省略は推測で埋めない)
  - kw を 1 つも渡さない呼出しは positional をそのまま通す (既定値は補わず、個数検査はホストに任せる: fl_api.bind の仕様)
判定: 実際の結果が期待と一致 (値・長さ・例外種別)。
  誤束縛 (misbind) = 位置 j >= k の値が、その位置の kw 識別子でも同名 stubs 既定値でもない (別の引数の値・既定値が入った)。
  mismatch = それ以外の不一致 (期待と違う例外・長さ・値)。misbind == 0 かつ mismatch == 0 で PASS、1 件でも違えば exit 1。
"""
import argparse
import ast
import json
import os
import sys
import types
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
ap = argparse.ArgumentParser()
ap.add_argument("--src", default=os.path.join(ROOT, "src"))
ap.add_argument("--table", default=os.path.join(ROOT, "analysis/flapi/flapi_table.json"))
args_ns = ap.parse_args()

calls = []
fake = types.ModuleType("_flhost")
fake.HostError = type("HostError", (Exception,), {})
fake.call = lambda fid, a: calls.append((fid, a)) or 0
sys.modules["_flhost"] = fake
sys.path.insert(0, args_ns.src)
import fl_api  # noqa: E402

t = json.load(open(args_ns.table))
fl_api.install(args_ns.table)
POS0, KW0 = 100000, 200000


def literal_or_none(s):
    try:
        return True, ast.literal_eval(s)
    except (ValueError, SyntaxError):
        return False, None


def spec(sig, ks):
    """期待値の仕様: (KL, req, D)。D = 同名 stubs の単純リテラル既定値。"""
    KL = list(ks["kwlist"])
    req = ks.get("required")
    stub = {}
    for p in (sig or {}).get("params", []):
        if p["default"] is not None and p["name"] not in stub:
            ok, v = literal_or_none(p["default"])
            if ok:
                stub[p["name"]] = v
    D = {n: stub[n] for n in KL if n in stub}
    return KL, req, D


def expected(KL, req, D, k, K):
    if not K:
        return "tuple", tuple(POS0 + i for i in range(k))
    first = {}
    for j, n in enumerate(KL):
        first.setdefault(n, j)
    for n in K:
        if n not in first or first[n] < k:
            return "TypeError", None
    out, gap = [], False
    for j in range(k, len(KL)):
        n = KL[j]
        if first[n] == j and n in K:
            if gap:
                return "TypeError", None
            out.append(K[n])
        elif gap:
            continue
        elif n in D:
            out.append(D[n])
        elif req is not None and j >= req:
            gap = True
        else:
            return "TypeError", None
    return "tuple", tuple(POS0 + i for i in range(k)) + tuple(out)


def actual(f, pos, K):
    calls.clear()
    try:
        f(*pos, **K)
    except TypeError:
        return "TypeError", None
    except Exception as ex:  # noqa: BLE001
        return f"ERR:{type(ex).__name__}", None
    return "tuple", calls[-1][1]


def misbound(KL, D, k, av):
    """位置 j >= k の値が、その位置の引数の kw 値 (識別子) か同名 stubs 既定値以外なら誤束縛 (別の引数の値・既定値が入った)。"""
    first = {}
    for j, n in enumerate(KL):
        first.setdefault(n, j)
    for j in range(k, len(av)):
        n = KL[j]
        allowed = [D[n]] if n in D else []
        if first[n] == j:
            allowed.append(KW0 + j)
        if not any(av[j] == a for a in allowed):
            return True
    return False


stats = dict(functions=0, cases=0, expect_tuple=0, expect_typeerror=0, ok=0, misbind=0, mismatch=0)
bad = []
for m, fs in t["modules"].items():
    for n, e in fs.items():
        ks = e.get("kwsig") or {}
        if ks.get("kwlist") is None:
            continue
        KL, req, D = spec(e.get("sig"), ks)
        f = getattr(sys.modules[m], n)
        stats["functions"] += 1
        names = list(dict.fromkeys(KL))
        for k in range(len(KL) + 1):
            pos = tuple(POS0 + i for i in range(k))
            for r in range(len(names) + 1):
                for S in combinations(names, r):
                    K = {s: KW0 + KL.index(s) for s in S}
                    ek, ev = expected(KL, req, D, k, K)
                    ak, av = actual(f, pos, K)
                    stats["cases"] += 1
                    stats["expect_tuple" if ek == "tuple" else "expect_typeerror"] += 1
                    if (ek, ev) == (ak, av):
                        stats["ok"] += 1
                        continue
                    kind = "mismatch"
                    if ak == "tuple" and misbound(KL, D, k, av):
                        kind = "misbind"
                    stats[kind] += 1
                    if len(bad) < 12:
                        bad.append((kind, f"{m}.{n}", k, S, ek, ev, ak, av))
            ek, ev = expected(KL, req, D, k, {"__unknown__": KW0})
            ak, av = actual(f, pos, {"__unknown__": KW0})
            stats["cases"] += 1
            stats["expect_typeerror"] += 1
            stats["ok" if (ek, ev) == (ak, av) else "mismatch"] += 1

print(json.dumps(stats, ensure_ascii=False))
for b in bad:
    print("FAIL", b)
ok = stats["misbind"] == 0 and stats["mismatch"] == 0 and stats["functions"] == 103 and stats["ok"] == stats["cases"]
print("kwsig_bind_check:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
