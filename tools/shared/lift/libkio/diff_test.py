#!/usr/bin/env python3
"""libkio lift の差分テスト。 usage: diff_test.py <workdir>
  参照 (native) : libkio x86_64 slice を mmap(RWX) し ctypes で *元の機械語* を直接実行 (SysV ABI は Linux と同一)
  被験 (wasm)   : RetDec lift -> emcc wasm を node で実行 (run_wasm.mjs)
  同一ベクタで戻り値ビット列と書込バッファを比較し、関数×(small/wide) ごとの PASS/FAIL を表にする。"""
import sys, os, json, struct, random, mmap, ctypes, subprocess, re
W = sys.argv[1]; HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "../..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from macho_util import MachO
from sig import params

# SIG は funcs.txt (戻り値型) と demangle 署名 (sig.py) から生成する。関数名の手書き表は持たない。
# テスト用の引数種別: i64 f32 str16 str32 str8 buf ref64 ref64v f64ref
# 参照引数は 1 つ目を「オフセット (0..47)」、2 つ目以降を「値 (ref64v)」として生成する (従来の SIG と同じ分布)。
def _targs(kinds):
    out = []; refs = 0
    for k in kinds:
        if k == "ref64":
            out.append("ref64" if refs == 0 else "ref64v"); refs += 1
        elif k == "i64": out.append("i64")
        else: out.append(k)
    return out
SIG = {}
for row in (l.split() for l in open(os.path.join(HERE, "funcs.txt")) if not l.startswith("#") and l.strip()):
    name, ret = row[0], row[3]
    kinds = params(name)
    if kinds is None or any(k in ("f64",) for k in kinds): raise SystemExit(f"[diff_test] 未対応の署名: {name} {kinds}")
    SIG[name] = (ret, _targs(kinds))
rng = random.Random(0xF1)
def rbytes(n): return bytes(rng.randrange(256) for _ in range(n))
def i64v(wide):
    if not wide: return rng.choice([0, 1, -1, 2, 100, -100, 12345, -12345, 2**31 - 1, -2**31, rng.randrange(-2**31, 2**31), rng.randrange(-1000, 1000)])
    return rng.choice([2**31, -2**31 - 1, 2**40, -2**40, 2**62, -2**62, 2**63 - 1, -2**63, rng.randrange(-2**63, 2**63), 0x1_0000_0001])
def f32v():
    return struct.unpack("<f", struct.pack("<f", rng.choice([0.0, 1.0, -1.0, 0.5, 3.75, -3.75, 1e10, -1e10, 1e30, -1e30, 123456.789, -0.0001, rng.uniform(-1000, 1000), rng.uniform(-1, 1)])))[0]
def gen(fn, wide):
    ret, args = SIG[fn]; case = []
    for a in args:
        if a == "i64":
            v = i64v(wide)
            case.append({"t": "i64", "v": v})
        elif a == "f32": case.append({"t": "f32", "v": f32v()})
        elif a in ("str16", "str32"):
            w = 2 if a == "str16" else 4; n = rng.randrange(0, 12)
            chars = [rng.randrange(1, 0x7f) for _ in range(n)]
            case.append({"t": "buf", "hex": b"".join(c.to_bytes(w, "little") for c in chars + [0]).hex(), "chars": chars})
        elif a == "str8": case.append({"t": "buf", "hex": b"".join(bytes([c]) for c in ([rng.randrange(1, 0x7f) for _ in range(rng.randrange(0, 12))] + [0])).hex(), "copy_prev": rng.random() < 0.5})
        elif a == "buf": case.append({"t": "buf", "hex": rbytes(64).hex(), "dump": True})
        elif a == "ref64": case.append({"t": "ref", "v": rng.randrange(0, 48 if True else 0)})
        elif a == "ref64v": case.append({"t": "ref", "v": i64v(wide)})
        elif a == "f64ref": case.append({"t": "f64ref", "v": rng.choice([0.0, 1.5, -2.25, 1e300, -1e-300, rng.uniform(-1e6, 1e6)])})
    # str2compare/str4compare: 半数は同一内容にして真経路も踏む
    if fn in ("__Z11str2comparePKtPKc", "__Z11str4comparePKwPKc") and case[1].pop("copy_prev"):
        case[1]["hex"] = bytes(c for c in case[0]["chars"]).hex() + "00"
    for c in case: c.pop("chars", None); c.pop("copy_prev", None)
    if fn == "__Z9FixHi_RCSll" and case[1]["v"] == 0: case[1]["v"] = 7
    if fn == "__Z9FixHi_RCSll" and case[0]["v"] == -2**63 and case[1]["v"] == -1: case[1]["v"] = 3
    return case
cases = []
for fn in SIG:
    for wide in (False, True):
        if wide and not any(a in ("i64", "ref64v") for a in SIG[fn][1]): continue
        for _ in range(40): cases.append({"fn": fn, "group": "wide" if wide else "small", "args": gen(fn, wide)})
def jsonable(c):  # 64bit 整数は JS の Number に潰れる (2^53 超で丸め) ため文字列で渡す
    return {**c, "args": [({**a, "v": str(a["v"])} if a["t"] in ("i64", "ref") else a) for a in c["args"]]}
json.dump({"sig": SIG, "cases": [jsonable(c) for c in cases]}, open(f"{W}/cases.json", "w"))

# ---- native: 元の機械語を ctypes で実行 ----
m = MachO(f"{W}/kio.dylib")
size = max(vm + vs for _, vm, vs, _, _ in m.segs if vs) 
mm = mmap.mmap(-1, (size + 4095) & ~4095, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
for n, vm, vs, fo, fs in m.segs:
    if fs and n != "__LINKEDIT": mm[vm:vm + fs] = m.d[fo:fo + fs]
base = ctypes.addressof(ctypes.c_char.from_buffer(mm))
addrs = {r[0]: int(r[1], 16) for r in (l.split() for l in open(f"{HERE}/funcs.txt") if not l.startswith("#") and l.strip())}
CT = {"i64": ctypes.c_int64, "f32": ctypes.c_float, "buf": ctypes.c_void_p}
RT = {"u64": ctypes.c_uint64, "i64": ctypes.c_int64, "u32": ctypes.c_uint32, "f32": ctypes.c_float, "f64": ctypes.c_double, "void": None}
def bits(rt, v):
    if rt == "f32": return struct.pack("<f", v).hex()
    if rt == "f64": return struct.pack("<d", v).hex()
    if rt == "void": return ""
    return format(v & (2**64 - 1 if rt in ("u64", "i64") else 2**32 - 1), "x")
nat = []
for c in cases:
    ret, args = SIG[c["fn"]]
    f = ctypes.CFUNCTYPE(RT[ret], *[ctypes.c_int64 if a["t"] == "i64" else ctypes.c_float if a["t"] == "f32" else ctypes.c_void_p for a in c["args"]])(base + addrs[c["fn"]])
    keep = []; cargs = []; dump = None
    for a in c["args"]:
        if a["t"] == "i64": cargs.append(a["v"])
        elif a["t"] == "f32": cargs.append(a["v"])
        elif a["t"] == "buf": b = ctypes.create_string_buffer(bytes.fromhex(a["hex"]), len(a["hex"]) // 2); keep.append(b); cargs.append(ctypes.addressof(b)); 
        elif a["t"] == "ref": r = ctypes.c_int64(a["v"]); keep.append(r); cargs.append(ctypes.addressof(r))
        elif a["t"] == "f64ref": r = ctypes.c_double(a["v"]); keep.append(r); cargs.append(ctypes.addressof(r))
    r = f(*cargs)
    out = {"ret": bits(ret, r)}
    for a, k in zip(c["args"], [None] * 0): pass
    bi = [i for i, a in enumerate(c["args"]) if a["t"] == "buf" and a.get("dump")]
    if bi: out["buf"] = bytes(keep[0]).hex() if c["args"][0]["t"] == "buf" else ""
    nat.append(out)
json.dump(nat, open(f"{W}/res_native.json", "w"))

# ---- wasm ----
subprocess.run([__import__("shutil").which("node") or os.path.expanduser("~/.local/share/pnpm/bin/node"), f"{HERE}/run_wasm.mjs", W], check=True)
wa = json.load(open(f"{W}/res_wasm.json"))
tab = {}
for c, n, w in zip(cases, nat, wa):
    key = (c["fn"], c["group"]); ret = SIG[c["fn"]][0]
    ok = (n["ret"] == w["ret"]) if ret != "void" else True
    if ret in ("u32",): ok = int(n["ret"], 16) & 0xffffffff == int(w["ret"], 16) & 0xffffffff if w["ret"] and not w["ret"].startswith("ERR") else False
    if "buf" in n and n.get("buf") != w.get("buf"): ok = False
    t = tab.setdefault(key, [0, 0]); t[0] += ok; t[1] += 1
print(f"{'function':44s} {'group':6s} pass/total")
tp = tt = 0
for (fn, g), (p, t) in sorted(tab.items()):
    print(f"{fn:44s} {g:6s} {p}/{t}"); tp += p; tt += t
print(f"TOTAL {tp}/{tt}")
json.dump({f"{fn}|{g}": v for (fn, g), v in tab.items()}, open(f"{W}/difftable.json", "w"), indent=1)
