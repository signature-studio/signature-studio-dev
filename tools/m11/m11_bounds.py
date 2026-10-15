#!/usr/bin/env python3
# M11 #1: boot closure 確定 (VA 空間) → RetDec --select-ranges 用の範囲表を吐く
# 素材: m11_scan.py の索引 (call graph) + m2 ghidra 関数表 (境界 ground truth)
# 出力: work/boot_fns.json (VA,size) / work/boot_ranges.txt (全lift set)
#       work/pilot_ranges.txt (pilot: entry closure + array1 先頭60)
import sys, json, csv, struct, os
from collections import deque

SRC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SRC, '..', 'm6'))
from ottlib import Bin

HERE = os.path.join(SRC, 'work')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from paths import FL_WIN64_DIR
WINF = os.environ.get('M11_PE') or os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
EP_VA = 0x1376820
ARR1_RVA = 0xf768e0
ARR1_N = 0x3ae

b = Bin(WINF)
IDX = json.load(open(os.path.join(HERE, 'scan_index.json')))
callsC = {int(k, 16): set(int(x, 16) for x in v) for k, v in IDX['calls'].items()}
calls = {}
for k, v in callsC.items():
    calls[k + 0x400000] = set(t + 0x400000 for t in v)

gh = {}
with open(os.path.join(SRC, '..', 'm2', 'work', 'ghidra_dll', 'functions_dll.csv')) as f:
    for row in csv.DictReader(f):
        va = int(row['entry'].replace('ram:', ''), 16)
        gh[va] = int(row['size'])
pdmap = dict((va + 0x400000, sz) for (va, sz) in b.fns)

def fnsize(va):
    return gh.get(va) or pdmap.get(va) or 0
def hasbound(va):
    return bool(gh.get(va) or pdmap.get(va))

raw = b.read_at(ARR1_RVA, ARR1_N * 16)
arr1 = [struct.unpack_from('<QQ', raw, k * 16) for k in range(ARR1_N)]
inits = [a for (a, c) in arr1 if a]
finals = [c for (a, c) in arr1 if c]
# 境界ある .textVA のみ seed 化 (data/bss 参照は icall 機構 (wasm table) 側で処理)
seeds = set(x for x in (inits + finals) if x and 0x401000 <= x < 0x13a44b0 and hasbound(x))
print('[bounds] array1 seeds(.text bounded):', len(seeds), 'of', len(inits) + len(finals))

# m11_passes.py の init prologue counter 用リスト (unit の Init/FInit を array1 の並び順で)
_it = []
for (a, c) in arr1:
    for x in (a, c):
        if x in seeds:
            _it.append('function_%x' % x)
open(os.path.join(HERE, 'inits_text.txt'), 'w').write('\n'.join(_it) + '\n')
print('[bounds] inits_text.txt:', len(_it))
EP_SEEDS = {EP_VA, 0x412760, 0x41d8f0, 0x411fc0, 0x4128b0}
seen = set(seeds) | EP_SEEDS
q = deque(list(seen) + list(EP_SEEDS))
while q and len(seen) < 500000:
    f = q.popleft()
    for c in calls.get(f, ()):
        if c not in seen and hasbound(c):
            seen.add(c)
            q.append(c)
        elif c not in seen and not hasbound(c):
            pass  # data-as-code/reference: 無下限 (stub 化はビルド失敗側で観測)
sizes = {hex(va): fnsize(va) for va in seen}
print('[bounds] boot union:', len(seen), 'code bytes:', sum(sizes.values()))
sizes = {va: fnsize(va) for va in seen}
ranges = ['0x%x-0x%x' % (va, va + sizes[va]) for va in sorted(sizes)]
open(os.path.join(HERE, 'boot_ranges.txt'), 'w').write(','.join(ranges))
json.dump(sizes, open(os.path.join(HERE, 'boot_fns.json'), 'w'), indent=0)

# pilot: EP SP closure + array1 .text-bounded 先頭 60 の transitive
pil = set(EP_SEEDS)
q = deque(list(EP_SEEDS))
while q:
    f = q.popleft()
    for c in calls.get(f, ()):
        if c not in pil and hasbound(c):
            pil.add(c)
            q.append(c)
for va in sorted(seeds)[:60]:
    pil.add(va)
    q2 = deque([va])
    while q2:
        g = q2.popleft()
        for c in calls.get(g, ()):
            if c not in pil and hasbound(c):
                pil.add(c)
                q2.append(c)
psizes = {va: fnsize(va) for va in pil}
pranges = ['0x%x-0x%x' % (va, va + psizes[va]) for va in sorted(psizes)]
open(os.path.join(HERE, 'pilot_ranges.txt'), 'w').write(','.join(pranges))
json.dump(psizes, open(os.path.join(HERE, 'pilot_fns.json'), 'w'), indent=0)
print('[bounds] pilot:', len(psizes), 'code bytes:', sum(psizes.values()))
