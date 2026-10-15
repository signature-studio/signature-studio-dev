#!/usr/bin/env python3
"""m11_icall_audit.py: RetDec の間接 call 脱落 (ott D1) が FLEngine closure でも起きているかの独立監査.
capstone で closure (IR の定義 function_*) 内の call/jmp 間接形を数え, IR 側の間接 call 数 (callee が @name 以外) と突合する.
使い方: python3 m11_icall_audit.py [work/boot_final.ll]   -> 結果を stdout と work/icall_audit.json に出力 (常に exit 0)"""
import sys, re, json, collections, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'm6'))
from ottlib import Bin
import capstone
from capstone import x86

W = os.path.join(HERE, 'work')
BASE = 0x400000   # IR/boot_fns の VA = ottlib.Bin アドレス + 0x400000
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from paths import FL_WIN64_DIR
PE = os.environ.get('M11_PE') or os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
irp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(W, 'boot_final.ll')
b = Bin(PE)
ir = open(irp).read()
defs = sorted(set(int(x, 16) for x in re.findall(r'^define [^\n]*@function_([0-9a-f]+)\(', ir, re.M)))
fns = json.load(open(os.path.join(W, 'boot_fns.json')))
pd = dict((va + 0x400000, sz) for va, sz in b.fns)
cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
cs.detail = True
cnt = collections.Counter()
fset = collections.defaultdict(set)
nosize = 0
for v in defs:
    s = pd.get(v) or fns.get(str(v))
    code = b.read_at(v - BASE, s) if s else None
    if code is None:
        nosize += 1
        continue
    for ins in cs.disasm(code, v - BASE):
        if ins.mnemonic not in ('call', 'jmp'):
            continue
        op = ins.operands[0]
        if op.type == x86.X86_OP_IMM:
            continue
        if op.type == x86.X86_OP_REG:
            k = 'reg'
        else:
            m = op.mem
            k = 'mem_rip(IAT/静的)' if m.base == x86.X86_REG_RIP else ('mem_base+index' if m.index else 'mem_reg+off')
        cnt[(ins.mnemonic, k)] += 1
        fset[(ins.mnemonic, k)].add(v)
# IR 側: call の callee が @name でない (関数ポインタ経由) 件数
ir_ind = 0
for l in ir.split('\n'):
    if re.search(r'\bcall\b', l) and not re.match(r'\s*(declare|define|;)', l) and not re.search(r'call [^%(]*@[A-Za-z0-9_.$"-]+\(', l):
        ir_ind += 1
# __asm_* helper (struct 返し cpuid) は名前付き関数なので誤検出を除く
ir_ind -= len(re.findall(r'call %\d+ @__asm_', ir))
out = {'ir': irp, 'closure_defs': len(defs), 'defs_without_size': nosize,
       'capstone': {'%s %s' % k: {'count': c, 'fns': len(fset[k])} for k, c in sorted(cnt.items())}}
call_ind = sum(c for (m, k), c in cnt.items() if m == 'call' and not k.startswith('mem_rip'))
out['capstone_call_indirect_non_rip'] = call_ind
out['capstone_jmp_indirect_non_rip'] = sum(c for (m, k), c in cnt.items() if m == 'jmp' and not k.startswith('mem_rip'))
out['capstone_fns_with_indirect_call'] = len(set().union(*[s for (m, k), s in fset.items() if m == 'call' and not k.startswith('mem_rip')]))
out['ir_indirect_calls'] = ir_ind
json.dump(out, open(os.path.join(W, 'icall_audit.json'), 'w'), indent=1, ensure_ascii=False)
print(json.dumps(out, indent=1, ensure_ascii=False))
print('RESULT capstone 間接call(rip除く)=%d / %d 関数, IR 間接call=%d  -> 脱落率 %.1f%%' % (
    call_ind, out['capstone_fns_with_indirect_call'], ir_ind, 100.0 * (call_ind - ir_ind) / max(call_ind, 1)))
