#!/usr/bin/env python3
"""Delphi framework 初期化 (Fruity Balance 0x5e19f0) が作る SIMD kernel 表を機械語から復元する (検収で追加)。

`lea reg,[rip+kernel]; mov [rip+var],reg` の組を数え、変数 (関数ポインタ .bss) ↔ 実装関数 の表と
lift 用 ranges (.pdata 境界) を出力する。 lift 実績の work/balance/dsp80_ranges.txt と同一。
出力: work/kernel_table.json, lift/kernel_ranges_balance.txt (RetDec --select-ranges 形式)
usage: kernel_table.py [PE=block18983] [init_VA=0x5e19f0]
"""
import json, os, re, struct, sys, collections
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_REG, X86_REG_RIP

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402
PE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(FL_WIN64_DIR, 'extracted', 'block18983_PE.bin')
INIT = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x5e19f0
X87 = re.compile(r'^f(ld|st|stp|add|mul|sub|div|ild|ist|istp|xch|sqrt|sin|cos|abs|chs|comp|ucom|ucomi|ldcw|nclex|rndint|scale|2xm1|ld\w+|imul|isub|cmov\w+|\w*p)$')

d = open(PE, 'rb').read()
pe = pefile.PE(data=d, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
funcs = {}
for k in range(len(pdata) // 12):
    b, e, u = struct.unpack_from('<III', pdata, 12 * k)
    if b and not u & 1:
        funcs[base + b] = base + e


def code(va, n):
    for s in pe.sections:
        a = base + s.VirtualAddress
        if a <= va < a + s.Misc_VirtualSize:
            return s.get_data()[va - a:va - a + n]
    return b''


md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
regv, assigns = {}, []
for i in md.disasm(code(INIT, funcs[INIT] - INIT), INIT):
    ops = i.operands
    if i.mnemonic == 'lea' and len(ops) == 2 and ops[0].type == X86_OP_REG and ops[1].type == X86_OP_MEM and ops[1].mem.base == X86_REG_RIP:
        regv[ops[0].reg] = i.address + i.size + ops[1].mem.disp
    elif i.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == X86_OP_MEM and ops[0].mem.base == X86_REG_RIP and ops[1].type == X86_OP_REG and ops[1].reg in regv:
        assigns.append((i.address + i.size + ops[0].mem.disp, regv[ops[1].reg]))

vars_ = collections.defaultdict(set)
for v, t in assigns:
    vars_[v].add(t)
targets = sorted({t for _, t in assigns})
kern = []
for t in targets:
    n = funcs[t] - t
    mn = {x.mnemonic for x in md.disasm(code(t, n), t)}
    kern.append({'va': hex(t), 'size': n, 'x87': sorted(m for m in mn if m.startswith('f') and X87.match(m))})
res = {
    'init': hex(INIT), 'init_size': funcs[INIT] - INIT, 'assignments': len(assigns),
    'variables': len(vars_), 'implementations': len(targets), 'bytes': sum(k['size'] for k in kern),
    'impl_per_var': dict(collections.Counter(len(s) for s in vars_.values())),
    'kernels_with_x87_asm': sum(1 for k in kern if k['x87']),
    'vars': {hex(v): sorted(hex(x) for x in s) for v, s in sorted(vars_.items())},
    'kernels': kern,
}
os.makedirs(os.path.join(HERE, '..', 'work'), exist_ok=True)
json.dump(res, open(os.path.join(HERE, '..', 'work', 'kernel_table.json'), 'w'), indent=1)
ranges = ','.join('0x%x-0x%x' % (t, funcs[t] - 1) for t in targets)
open(os.path.join(HERE, '..', 'lift', 'kernel_ranges_balance.txt'), 'w').write(ranges + '\n')
print({k: v for k, v in res.items() if k not in ('vars', 'kernels')})
