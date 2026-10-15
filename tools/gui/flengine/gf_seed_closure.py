#!/usr/bin/env python3
"""GUI-3 (#2715 / WIN-4): 指定 seed VA (既定 CreateFruityInstance = 0x1375990) から call/jmp 即値を辿る閉包を求め、
現在の lift closure (最終 IR の `define @function_<VA>`) に無い関数を列挙する。
  python3 gf_seed_closure.py --pe <PE> --ir <boot_final3.ll> [--seed 0x1375990] [--json-out F] [--ranges-out F]
  --ranges-out: 閉包外の関数の RetDec --select-ranges 形式 (m11_lift.sh の ranges 入力)。
規則は tools/m11/m11_wndclass_scan.py の閉包と同じ (境界は .pdata のみ・import thunk は 6B・直接 call/jmp 即値のみ)。
"""
import argparse, json, os, re, struct, sys
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'm6'))
from ottlib import Bin, Dis  # capstone 必須

ap = argparse.ArgumentParser()
ap.add_argument('--pe', required=True)
ap.add_argument('--ir', required=True)
ap.add_argument('--seed', default='0x1375990')
ap.add_argument('--json-out')
ap.add_argument('--ranges-out')
ap.add_argument('--max-depth', type=int, default=10**9)
a = ap.parse_args()

pe = pefile.PE(a.pe, fast_load=True)
IB = pe.OPTIONAL_HEADER.ImageBase
fn_size = {}
for s in pe.sections:
    if s.Name.rstrip(b'\0').decode() == '.pdata':
        d = s.get_data()
        for i in range(len(d) // 12):
            b, e, _ = struct.unpack_from('<III', d, i * 12)
            if b and e > b:
                fn_size[b] = e - b
thunk_rvas = set()
for ent in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
    for imp in ent.imports:
        if imp.address:
            thunk_rvas.add(imp.address - IB)

DEF = re.compile(r'^define [^@]*@function_([0-9a-f]+)\(', re.M)
defined = set(int(x, 16) for x in DEF.findall(open(a.ir).read()))

bin_ = Bin(a.pe)
dis = Dis(bin_)


def fsize(va):
    rva = va - IB
    return fn_size.get(rva) or (6 if rva in thunk_rvas else 0)


def edges(va):
    sz = fsize(va)
    code = bin_.read_at(va - IB, sz) if sz else None
    out = []
    if code is None:
        return out
    for ins in dis.cs.disasm(code, va):
        if ins.mnemonic in ('jmp', 'call') and ins.operands and ins.operands[0].type == 2:
            t = ins.operands[0].imm
            if not (va <= t < va + sz) and fsize(t):
                out.append(t)
    return out


seed = int(a.seed, 16)
seen, depth = {}, {seed: 0}
q = [seed]
while q:
    f = q.pop()
    if f in seen:
        continue
    seen[f] = fsize(f)
    if depth[f] >= a.max_depth:
        continue
    for t in edges(f):
        if t not in depth:
            depth[t] = depth[f] + 1
        q.append(t)

new = {k: v for k, v in seen.items() if k not in defined}
hit = {k: v for k, v in seen.items() if k in defined}
summary = {
    'seed': '0x%x' % seed,
    'seed_defined_in_ir': seed in defined,
    'seed_fsize': fsize(seed),
    'closure_reachable_functions': len(seen),
    'closure_reachable_bytes': sum(seen.values()),
    'reachable_already_in_ir': len(hit),
    'reachable_new_not_in_ir': len(new),
    'reachable_new_bytes': sum(new.values()),
    'final_ir_defined_functions': len(defined),
}
print(json.dumps(summary, indent=1))
if a.json_out:
    os.makedirs(os.path.dirname(os.path.abspath(a.json_out)), exist_ok=True)
    json.dump({'summary': summary, 'new_functions': {'0x%x' % k: v for k, v in sorted(new.items())}}, open(a.json_out, 'w'), indent=1)
if a.ranges_out:
    open(a.ranges_out, 'w').write(','.join('0x%x-0x%x' % (k, k + v) for k, v in sorted(new.items())))
