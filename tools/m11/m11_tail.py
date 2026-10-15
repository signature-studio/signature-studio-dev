#!/usr/bin/env python3
# M11 closure 補完: `jmp imm` 末尾呼出 (tail call) 辺を追う.
# m11_bounds.py の closure は `call imm` 辺のみ → 412760 -> `jmp 0x412680` (setjmp) 型の取りこぼしがある.
# 出力: work/tail_extra.json (追加 fn VA→size), work/boot_ranges2.txt (boot_ranges + 追加)
import sys, json, csv, os
from collections import deque
SRC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SRC, '..', 'm6'))
from ottlib import Bin, Dis

HERE = os.path.join(SRC, 'work')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from paths import FL_WIN64_DIR
WINF = os.environ.get('M11_PE') or os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
b = Bin(WINF)
d = Dis(b)
gh = {}
with open(os.path.join(SRC, '..', 'm2', 'work', 'ghidra_dll', 'functions_dll.csv')) as f:
    for row in csv.DictReader(f):
        gh[int(row['entry'].replace('ram:', ''), 16)] = int(row['size'])
pd = dict((va + 0x400000, sz) for (va, sz) in b.fns)
def size(va): return gh.get(va) or pd.get(va) or 0

fns = {int(k): v for k, v in json.load(open(os.path.join(HERE, 'boot_fns.json'))).items()}
IDX = json.load(open(os.path.join(HERE, 'scan_index.json')))
calls = {int(k, 16) + 0x400000: set(int(x, 16) + 0x400000 for x in v) for k, v in IDX['calls'].items()}

# 間接 call 先 (RetDec は indirect call を落とすので data table から手動 seed 化)
#   0xfa9410 の _InitLib hook 表 (rbx[reason*8]): TLS 初期化 hook 4 本
EXTRA_SEEDS = [0x41d0e0, 0x41d050, 0x41d000, 0x41d090]
# RetDec が .data の静的初期値から解決した間接 call (例: 0x40a140 Random の `call [RandomPtr]` → function_40a120) は
# IR 上で直接 call になるが call graph 索引 (disasm の即値のみ) には現れない → IR の「宣言のみ・未定義 function_*」を seed に追加
import re as _re
_irp = os.path.join(HERE, 'boot_final.ll')
if os.path.exists(_irp):
    _t = open(_irp).read()
    _defd = set(_re.findall(r'^define [^@]*@(function_[0-9a-f]+)', _t, _re.M))
    for _n in sorted(set(_re.findall(r'^declare [^@]*@(function_[0-9a-f]+)', _t, _re.M)) - _defd):
        EXTRA_SEEDS.append(int(_n.split('_')[1], 16))
# 累積 seed (単調増加; 反復で振動しないよう m11_extra_seeds.txt に保持, コミット対象)
_sf = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'm11_extra_seeds.txt')
if os.path.exists(_sf):
    EXTRA_SEEDS += [int(x, 16) for x in open(_sf).read().split()]
EXTRA_SEEDS = sorted(set(EXTRA_SEEDS))
open(_sf, 'w').write('\n'.join('0x%x' % x for x in EXTRA_SEEDS) + '\n')
seen = set(fns)
extra = {}
q = deque(seen)
for sv in EXTRA_SEEDS:
    if sv not in seen and size(sv):
        seen.add(sv); extra[sv] = size(sv); q.append(sv)
tail_edges = []
def jmps(va):
    # closure 内関数を直接 disasm し call/jmp の即値先を全て拾う.
    # (m11_scan.py の索引は .pdata 関数しか走査しないため, unwind 情報の無い leaf 関数 (例: 0x40a140/0x40a160) の
    #  呼出し先 (0x40a120 System.Random の LCG 等) が closure から漏れていた)
    sz = size(va)
    code = b.read_at(va - 0x400000, sz)
    out = []
    if code is None: return out
    for ins in d.cs.disasm(code, va):
        if ins.mnemonic in ('jmp', 'call') and ins.operands and ins.operands[0].type == 2:
            t = ins.operands[0].imm
            if not (va <= t < va + sz) and size(t) and (t in gh or t in pd):
                out.append(t)
    return out
while q:
    f = q.popleft()
    for t in list(jmps(f)) + list(calls.get(f, ())):
        if t not in seen and size(t):
            seen.add(t)
            extra[t] = size(t)
            tail_edges.append((f, t))
            q.append(t)
json.dump({hex(k): v for k, v in extra.items()}, open(os.path.join(HERE, 'tail_extra.json'), 'w'), indent=0)
rs = open(os.path.join(HERE, 'boot_ranges.txt')).read().split(',')
rs += ['0x%x-0x%x' % (va, va + sz) for va, sz in sorted(extra.items())]
open(os.path.join(HERE, 'boot_ranges2.txt'), 'w').write(','.join(rs))
# chunk4 用 ranges (base に含まれない追加分のみ)
open(os.path.join(HERE, 'boot_ranges_extra.txt'), 'w').write(','.join('0x%x-0x%x' % (va, va + sz) for va, sz in sorted(extra.items())))
print('[tail] base closure %d fns; tail-call extra %d fns (%d bytes); first: %s' % (
    len(fns), len(extra), sum(extra.values()), ', '.join(hex(k) for k in sorted(extra)[:12])))
