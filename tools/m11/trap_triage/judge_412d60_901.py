#!/usr/bin/env python3
"""judge_412d60_901.py VA... : 412d60(&slot) 同型呼びの D4 判定 (#901, #705 §4)

判定 (PE の機械語。disasm_fn.py と同じ Machine 経由):
  slot  = 関数冒頭で引数レジスタ (rcx/rdx/r8/r9) を [rbp+off] に退避した slot
  addref = 冒頭で slot の値を rcx にして 412f30 (addref) を呼んでいる
  release = 末尾で lea rcx,[rbp+off] して 412d60 を呼んでいる
  addref と release が同じ slot で揃えば「slot 値は文字列ポインタ」で D4 ではない。
  addref が無く release だけ有る形は 旧値ロード脱落 (D4) の疑い。
環境変数: FL_WIN64_DIR (fl-win64 の展開先), LD_M11_PE (任意で PE を直接指定)"""
import sys, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'ldfix'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
import capstone
from ldmach import Machine
from paths import FL_WIN64_DIR  # docs/REFERENCES.md [WIN64]
PE = os.environ.get('LD_M11_PE', f'{FL_WIN64_DIR}/extracted/block00031_PE.bin')
ARG_REGS = ('rcx', 'rdx', 'r8', 'r9')
m = Machine(PE)
cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); cs.detail = False
SLOT = re.compile(r'\[rbp \+ (0x[0-9a-f]+)\]')

def judge(va):
    rva, size = m.fns[va]
    insns = list(cs.disasm(m.read(rva, size), va))
    store = {}  # slot off -> arg reg (prologue の引数退避)
    for i in insns[:24]:
        mm = re.match(r'mov (?:qword ptr )?\[rbp \+ (0x[0-9a-f]+)\], (r\w+)$', f'{i.mnemonic} {i.op_str}')
        if mm and mm.group(2) in ARG_REGS:
            store[mm.group(1)] = mm.group(2)
    addref = set()
    release = set()
    for idx, i in enumerate(insns):
        if i.mnemonic == 'call' and i.op_str == '0x412f30' and idx > 0:
            prev = insns[idx - 1]
            # rcx に slot 値を入れてから呼ぶ形 (mov rcx, qword ptr [rbp + off])
            mm = re.match(r'mov rcx, qword ptr \[rbp \+ (0x[0-9a-f]+)\]', f'{prev.mnemonic} {prev.op_str}')
            if mm and mm.group(1) in store:
                addref.add(mm.group(1))
        if i.mnemonic == 'call' and i.op_str == '0x412d60' and idx > 0:
            prev = insns[idx - 1]
            mm = re.match(r'lea rcx, \[rbp \+ (0x[0-9a-f]+)\]', f'{prev.mnemonic} {prev.op_str}')
            if mm:
                release.add(mm.group(1))
    return store, addref, release

def verdict(store, addref, release):
    hits = sorted(set(store) & release)
    if not hits:
        return 'no-match (引数退避→412d60(&slot) の形なし)'
    bad = [s for s in hits if s not in addref]
    if bad:
        return 'D4 候補 (addref 無し・release のみ): slot ' + ','.join(bad)
    return 'not D4 (addref/release が同 slot で釣り合う): slot ' + ','.join(hits)

for a in sys.argv[1:]:
    va = int(a, 16)
    store, addref, release = judge(va)
    print('function_%x: %s' % (va, verdict(store, addref, release)))
