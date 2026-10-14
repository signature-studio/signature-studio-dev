#!/usr/bin/env python3
"""callers_of.py VA... | --chain VA... : PE の直接 call / jmp を .pdata の関数区間ごとに線型 disasm して数える (#2373)

  callers_of.py VA...         VA への直接 call / jmp を持つ関数を列挙する
                              (呼出元関数 VA / 呼出し箇所の数 / 呼出し箇所 VA)。末尾に distinct な呼出元関数数と箇所の総数
  callers_of.py --chain VA... 並べた関数の隣り合う組 A B について「A から B への直接 call 箇所」を出す (呼出経路の静的確認)

間接呼出し (vtable・jump table 経由) と .pdata に無い関数 (leaf) は数えない。
"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'ldfix'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from ldmach import Machine
from paths import FL_WIN64_DIR  # docs/REFERENCES.md [WIN64]
PE = os.environ.get('LD_M11_PE', f'{FL_WIN64_DIR}/extracted/block00031_PE.bin')
chain = len(sys.argv) > 1 and sys.argv[1] == '--chain'
vas = [int(a, 16) for a in sys.argv[2 if chain else 1:]]
m = Machine(PE)
m.cs.detail = False
sites = {}   # 呼出元関数 VA -> 呼出先 VA -> [(mnemonic, 箇所 VA)]
for va in sorted(m.fns):
    rva, size = m.fns[va]
    for i in m.cs.disasm(m.read(rva, size), va):
        if i.mnemonic in ('call', 'jmp') and i.op_str.startswith('0x'):
            try:
                t = int(i.op_str, 16)
            except ValueError:
                continue
            sites.setdefault(va, {}).setdefault(t, []).append((i.mnemonic, i.address))
if chain:
    for a, b in zip(vas, vas[1:]):
        hit = sites.get(a, {}).get(b, [])
        print('%x -> %x : %s%s' % (a, b, ' '.join('%s@%x' % h for h in hit) or 'なし', '' if a in m.fns else ' (.pdata に無い)'))
else:
    hits = {}
    for va in sorted(sites):
        for t in vas:
            hits.setdefault(va, []).extend(sites[va].get(t, []))
        if not hits.get(va):
            hits.pop(va, None)
    for va in sorted(hits):
        print('function_%x n=%d %s' % (va, len(hits[va]), ' '.join('%s@%x' % h for h in hits[va])))
    print('callers=%d sites=%d' % (len(hits), sum(len(v) for v in hits.values())))
