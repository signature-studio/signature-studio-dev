#!/usr/bin/env python3
"""libreverb (win Reverb.dll) lift の差分テスト。 usage: diff_test.py <workdir> [--mutate-wasm-result]
  参照 (native): locate.py が書いた image.bin を RWX mmap し、元の機械語を gcc の ms_abi 関数ポインタで直接実行 (native_ref.c)
  被験 (wasm)  : RetDec lift -> helper 生成 -> emcc の rv.wasm を node で実行 (run_wasm.mjs)
  同一ケース (this 状態 + 14 本の delay buffer + 入力) で「状態 + 全 buffer + 出力 (+aux 出力)」の全バイトを比較する。
  終了コード: 全ケース一致かつカバレッジ条件を満たす時のみ 0。1 ケースでも不一致 / TRAP / カバレッジ不足なら 1 (gate)。
  --mutate-wasm-result: ネガティブコントロール (比較器自身の検査)。wasm 結果の 1 バイトを反転して FAIL (exit 1) することを確かめる。"""
import sys, os, json, struct, random, subprocess, math

W = sys.argv[1]; MUT = "--mutate-wasm-result" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
NL, PTR0, S = 14, 0xBC, 0x260
rng = random.Random(0x26175)
F32 = lambda x: struct.unpack("<f", struct.pack("<f", x))[0]

def gen_case(fn, group):
    st = bytearray(rng.randbytes(S)) if group == "wide" else bytearray(S)
    big = group == "wide"
    n = rng.choice([0, 1, 2, 3, 7, 64, 255]) if big else rng.choice([0, 1, 2, 5, 16, 33, 64, 129])
    lens = [rng.choice([16, 24, 37, 64, 100, 128, 255, 256]) for _ in range(13)]
    len_ring = rng.choice([256, 512, 1024])             # 0x124 の buffer はマスク (len-1) 参照 → 2 の冪
    minlen = min(lens)
    cap = [4096] * NL                                    # 範囲外参照 (tap+pos が len 超) でも native/wasm とも同一領域内
    def setf(o, v): struct.pack_into("<f", st, o, F32(v))
    def seti(o, v): struct.pack_into("<i", st, o, v)
    def fl(): return F32(rng.uniform(-1, 1)) if not big else rng.choice([0.0, 1.0, -1.0, 1e-38, 1e-42, 3e4, -3e4, rng.uniform(-8, 8), rng.uniform(-1, 1)])
    for o in range(0x6C, 0xB8, 4): setf(o, fl())
    setf(0x78, rng.choice([0.0, 0.0, -0.0, 0.5, fl()]))   # ucomiss 分岐: x==0 (±0) と x!=0 の両経路
    for i in range(13): seti(0x164 + 4 * i, lens[i]); seti(0x12C + 4 * i, rng.randrange(0, lens[i]))
    seti(0x198, len_ring); seti(0x160, rng.randrange(0, len_ring))
    for o in range(0x19C, 0x214, 4): seti(o, rng.randrange(0, minlen))
    for o in range(0x214, 0x254, 4): setf(o, fl())
    for i in range(NL): struct.pack_into("<Q", st, PTR0 + 8 * i, 0)
    bufs = [[F32(rng.uniform(-1, 1)) if not big else rng.choice([0.0, 1e-30, rng.uniform(-4, 4), rng.uniform(-1, 1)]) for _ in range(cap[i])] for i in range(NL)]
    aux = 1 if fn == 1 and rng.random() < 0.6 else 0
    amp = 1.0 if not big else rng.choice([1.0, 100.0, 1e-20])
    inp = [F32(rng.uniform(-amp, amp)) for _ in range(n)]
    return dict(fn=fn, n=n, aux=aux, st=bytes(st), lens=lens + [len_ring], cap=cap, bufs=bufs, inp=inp, group=group,
                zero78=struct.unpack_from("<f", st, 0x78)[0] == 0.0)

def pack(c):
    b = struct.pack("<IIII", c["fn"], c["n"], c["aux"], S) + struct.pack("<14I", *(c["lens"] + [0] * (NL - len(c["lens"]))))[:NL * 4]
    b += struct.pack("<14I", *c["cap"]) + c["st"]
    for bf in c["bufs"]: b += struct.pack(f"<{len(bf)}f", *bf)
    return b + struct.pack(f"<{c['n']}f", *c["inp"])

cases = [gen_case(fn, g) for fn in (0, 1) for g in ("small", "wide") for _ in range(60)]
open(f"{W}/cases.bin", "wb").write(struct.pack("<I", len(cases)) + b"".join(pack(c) for c in cases))

# カバレッジ (gate の一部): 全てを踏まなければテスト自体が無効
cov = {"fruity": sum(c["fn"] == 0 for c in cases), "uf": sum(c["fn"] == 1 for c in cases),
       "uf_aux": sum(c["fn"] == 1 and c["aux"] for c in cases), "uf_noaux": sum(c["fn"] == 1 and not c["aux"] for c in cases),
       "x78_zero": sum(c["zero78"] for c in cases), "x78_nonzero": sum(not c["zero78"] for c in cases),
       "n0": sum(c["n"] == 0 for c in cases), "n>=129": sum(c["n"] >= 129 for c in cases)}
print("coverage:", cov)
need = ["uf_aux", "uf_noaux", "x78_zero", "x78_nonzero", "n0", "n>=129"]
if any(cov[k] == 0 for k in need): print("FAIL: coverage hole", [k for k in need if cov[k] == 0]); sys.exit(1)

ranges = json.load(open(f"{W}/loc/ranges.json"))
subprocess.run(["gcc", "-O1", "-o", f"{W}/native_ref", f"{HERE}/native_ref.c"], check=True)
subprocess.run([f"{W}/native_ref", f"{W}/loc/image.bin", f"{ranges['fruity']['begin']:x}", f"{ranges['uf']['begin']:x}",
                f"{W}/cases.bin", f"{W}/res_native.bin"], check=True)
subprocess.run([os.popen("command -v node").read().strip(), f"{HERE}/run_wasm.mjs", W], check=True)

def split(path):
    d = open(path, "rb").read(); p = 0; out = []
    while p < len(d):
        (l,) = struct.unpack_from("<I", d, p); p += 4; out.append(d[p:p + l]); p += l
    return out
nat_raw = open(f"{W}/res_native.bin", "rb").read(); wa = split(f"{W}/res_wasm.bin")
nat = []; p = 0
for c in cases:
    ln = S + sum(c["cap"]) * 4 + 8 * c["n"] + (8 * c["n"] if c["aux"] else 0)
    nat.append(nat_raw[p:p + ln]); p += ln
assert p == len(nat_raw) and len(wa) == len(nat), (p, len(nat_raw), len(wa), len(nat))
if MUT and wa: wa[0] = bytes([wa[0][0] ^ 1]) + wa[0][1:]

tab = {}; first_bad = None
for i, (c, n, w) in enumerate(zip(cases, nat, wa)):
    ok = (n == w); trap = w.startswith(b"TRAP:")
    key = ("Fruity" if c["fn"] == 0 else "UF", c["group"]); t = tab.setdefault(key, [0, 0, 0]); t[0] += ok; t[1] += 1; t[2] += trap
    if not ok and first_bad is None:
        d = next((k for k in range(min(len(n), len(w))) if n[k] != w[k]), None)
        first_bad = (i, c["fn"], c["group"], c["n"], d, len(n), len(w))
print(f"{'function':8s} {'group':6s} pass/total (trap)")
tp = tt = 0
for (fn, g), (a, b, tr) in sorted(tab.items()):
    print(f"{fn:8s} {g:6s} {a}/{b} ({tr})"); tp += a; tt += b
print(f"TOTAL {tp}/{tt}" + ("" if tp == tt else f"  first mismatch: case#{first_bad[0]} fn={first_bad[1]} {first_bad[2]} n={first_bad[3]} byte@{first_bad[4]} len native/wasm={first_bad[5]}/{first_bad[6]}"))
json.dump({"cov": cov, "table": {f"{k[0]}|{k[1]}": v for k, v in tab.items()}, "total": [tp, tt]}, open(f"{W}/difftable.json", "w"), indent=1)
print("RESULT:", "PASS" if tp == tt else "FAIL")
sys.exit(0 if tp == tt else 1)
