#!/usr/bin/env python3
"""GeneralPitchShifter vtable slot 4 (RVA 0x1aa3a0) / slot 5 (RVA 0x1aa470) の lift 差分テスト。 usage: diff_test.py <workdir> [--mutate-wasm-result]
  参照 (native): fn.bin (元の機械語) を RWX mmap し gcc の ms_abi 関数ポインタで直接実行 (native_ref.c)
  被験 (wasm)  : RetDec -> ir_normalize -> emcc の fn.wasm を node で実行 (run_wasm.mjs)
  ケース: inner (0x2f8 B) を全バイト乱数で初期化 (ポインタ 5 欄は buffer の番地、count1 [+0x28] は {0,1,2,3,7,16}、
          count2 [+0x244] は {0,1,2,5} から選ぶ)。buffer は 5 本 x 64 dword、wrapper は 16 B (+8 = inner)。
  比較: 呼出し後の inner 全バイト + wrapper 16 B + 全 buffer。ポインタ欄 5 個と wrapper+8 は両側とも 0 に正規化。
        ranges.json の ret=1 (slot 5・return 0) なら戻り値 (eax) も比べる。全バイト一致で合格。
  gate: slot 4 は count1==0 / count1>0 / count2==0 / count2>0 の各 1 件以上。不足なら exit 1。slot 5 は count を読まないため gate は無い。
  終了コード: 全ケース一致かつ gate 充足のときだけ 0。不一致・TRAP・gate 不足は 1。
  --mutate-wasm-result: ネガティブコントロール。wasm 結果 record の offset 4 (ret 欄の下位 1 バイト) を反転して FAIL (exit 1) することを確かめる。"""
import sys, os, json, random, struct, subprocess

W = sys.argv[1]; MUT = "--mutate-wasm-result" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
INNER, NB, BUFN, NCASE = 0x2F8, 5, 64, 240
PTR = [0x10, 0x18, 0x20, 0x258, 0x260]
C1_VALS, C2_VALS = [0, 1, 2, 3, 7, 16], [0, 1, 2, 5]
REC = 8 + INNER + 16 + NB * BUFN * 4
RNG = json.load(open(f"{W}/loc/ranges.json")); FN = RNG["fn_name"]; SLOT = RNG["slot"]; RETF = str(RNG["ret"])
rng = random.Random(0x2529)

def gen_case():
    c1, c2 = rng.choice(C1_VALS), rng.choice(C2_VALS)
    inner = bytearray(rng.randbytes(INNER))
    struct.pack_into("<i", inner, 0x28, c1); struct.pack_into("<i", inner, 0x244, c2)
    for o in PTR: struct.pack_into("<Q", inner, o, 0)
    return dict(c1=c1, c2=c2, inner=bytes(inner), bufs=[rng.randbytes(BUFN * 4) for _ in range(NB)], wrap=rng.randbytes(16))

def pack(c):
    return bytes(c["inner"]) + b"".join(c["bufs"]) + c["wrap"]

cases = [gen_case() for _ in range(NCASE)]
open(f"{W}/cases.bin", "wb").write(struct.pack("<I", NCASE) + b"".join(pack(c) for c in cases))

cov = {"count1=0": sum(c["c1"] == 0 for c in cases), "count1>0": sum(c["c1"] > 0 for c in cases),
       "count2=0": sum(c["c2"] == 0 for c in cases), "count2>0": sum(c["c2"] > 0 for c in cases)} if SLOT == 4 else {}
print("coverage:", cov)
holes = [k for k, v in cov.items() if v == 0]
if holes: print("FAIL: coverage hole", holes); sys.exit(1)

subprocess.run(["gcc", "-O1", "-o", f"{W}/native_ref", f"{HERE}/native_ref.c"], check=True)
subprocess.run([f"{W}/native_ref", f"{W}/loc/fn.bin", f"{W}/cases.bin", f"{W}/res_native.bin", RETF], check=True)
subprocess.run(["node", f"{HERE}/run_wasm.mjs", W, FN, RETF], check=True)

nat = open(f"{W}/res_native.bin", "rb").read(); wa = open(f"{W}/res_wasm.bin", "rb").read()
assert len(nat) == NCASE * REC and len(wa) == NCASE * REC, (len(nat), len(wa), NCASE * REC)
if MUT: wa = wa[:4] + bytes([wa[4] ^ 1]) + wa[5:]  # offset 4 = ret 欄の下位 1 バイト
recs_n = [nat[i * REC:(i + 1) * REC] for i in range(NCASE)]
recs_w = [wa[i * REC:(i + 1) * REC] for i in range(NCASE)]

groups = {"all": lambda c: True}
if SLOT == 4:
    groups.update({"count1=0": lambda c: c["c1"] == 0, "count1>0": lambda c: c["c1"] > 0,
                   "count2=0": lambda c: c["c2"] == 0, "count2>0": lambda c: c["c2"] > 0})
ok = [n == w for n, w in zip(recs_n, recs_w)]
trap = [w[:4] != b"\0\0\0\0" for w in recs_w]
first_bad = next((i for i, o in enumerate(ok) if not o), None)
print(f"{'function':32s} {'group':10s} {'pass/total':>12s} {'trap':>5s}")
tp = tt = 0
for g, pred in groups.items():
    idx = [i for i, c in enumerate(cases) if pred(c)]
    a = sum(ok[i] for i in idx); t = len(idx); tr = sum(trap[i] for i in idx)
    print(f"{FN:32s} {g:10s} {f'{a}/{t}':>12s} {tr:>5d}")
    if g == "all": tp, tt = a, t
if first_bad is not None:
    d = next((k for k in range(REC) if recs_n[first_bad][k] != recs_w[first_bad][k]), None)
    print(f"mismatch cases: {tt - tp}/{tt}  first: case#{first_bad} c1={cases[first_bad]['c1']} c2={cases[first_bad]['c2']} record byte@{d}")
print(f"TOTAL {tp}/{tt}")
json.dump({"cov": cov, "total": [tp, tt]}, open(f"{W}/difftable.json", "w"), indent=1)
print("RESULT:", "PASS" if tp == tt else "FAIL")
sys.exit(0 if tp == tt else 1)
