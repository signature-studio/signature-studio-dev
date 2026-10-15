#!/usr/bin/env python3
"""到達集合 (basic block) の native 対 wasm 比較 (T-SH-115 / #4303)。 usage: wc_cov_diff.py <workdir>
  入力: res_cov_native.bin (wc_native_ref.c・WC_COV_OUT) / res_cov_wasm.bin (wc_run_wasm.mjs・WC_COV=1)。
  case ごとに 512 byte (blocks.txt の行番号 = ブロック番号、1 = 到達)。
  出力: case 数・到達ブロック数の分布・到達集合の種類数・native と wasm の一致数。
  判定: 全 case で到達集合が一致し、到達集合の種類が 2 以上なら exit 0 (分岐の網羅に 1 経路以上の差がある)。
        native が落ちた case (res_native.bin の hits = CRASH) は比較から外す。"""
import sys, json, struct
from collections import Counter
W = sys.argv[1]
L = json.load(open(f"{W}/layout.json"))
ARENA_SZ, DATA_SZ = L["arena_sz"], L["data_sz"]
REC = 16 + ARENA_SZ + DATA_SZ
CRASH = 0xC2A5C2A5C2A5C2A5
COV = 512
nat = open(f"{W}/res_native.bin", "rb").read()
cn = open(f"{W}/res_cov_native.bin", "rb").read()
cw = open(f"{W}/res_cov_wasm.bin", "rb").read()
n = len(nat) // REC
assert len(cn) == n * COV and len(cw) == n * COV, f"size native={len(cn)} wasm={len(cw)} expect={n * COV}"
nblk = len(open(f"{W}/blocks.txt").read().split())
ok = bad = excl = 0
sets = Counter()
counts = []
for c in range(n):
    if struct.unpack_from("<Q", nat, c * REC + 8)[0] == CRASH:
        excl += 1
        continue
    a = cn[c * COV:c * COV + nblk]
    b = cw[c * COV:c * COV + nblk]
    reached = frozenset(i for i in range(nblk) if a[i])
    sets[reached] += 1
    counts.append(len(reached))
    if a == b:
        ok += 1
    else:
        bad += 1
        diff = [i for i in range(nblk) if a[i] != b[i]][:5]
        print(f"  case {c}: block diff {diff}")
print(f"[cov diff] cases={n} PASS={ok} FAIL={bad} excluded(native crash)={excl}")
print(f"[cov diff] reached blocks per case: min={min(counts) if counts else 0} max={max(counts) if counts else 0} of {nblk}")
print(f"[cov diff] distinct reached sets={len(sets)} (over {sum(sets.values())} compared cases)")
print(f"[cov diff] coverage union={len(set().union(*sets)) if sets else 0} of {nblk}")
sys.exit(0 if bad == 0 and ok >= 1 and len(sets) >= 2 else 1)
