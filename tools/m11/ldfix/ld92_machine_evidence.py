#!/usr/bin/env python3
"""ld92_machine_evidence.py — #2244 (LD-92) 関数群 A の spill 宛未判定 site の機械語側の一次根拠。

入力: spill178_1161.tsv (status=未判定 かつ fn が関数群 A) / image (m11_image.bin) / config (boot*.drc.config.json)
出力: 第 2 引数の TSV (既定 results/ld92_machine_evidence.tsv)。site ごとに、同じ [rbp+disp] を後で最初に参照する命令。
  READ      = 後続の読み出し (cmp / mov レジスタ読み) がある。NO_CONSUMER の除外根拠
  OVERWRITE = 後続の mov で同じ slot を上書きする (読み出し無し)
  NONE      = 関数末尾まで同 slot の参照が無い
注意: 線形走査 (分岐を辿らない)。読み出しが実行経路で到達するかは示さない。TRUE_DROP / OK_LOAD の判定は IR 側の突合が要る。
使い方: python3 ld92_machine_evidence.py [OUT.tsv]
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '../../..'))
sys.path.insert(0, HERE)
from ldmach_img import ImageMachine  # noqa: E402

W = os.environ.get('M11_WORK', os.path.join(REPO, 'tools/m11/work'))
TARGET = {'cf3790', 'c589b0', '128f9e0'}
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'results/ld92_machine_evidence.tsv')

mach = ImageMachine(os.path.join(W, 'm11_image.bin'), os.path.join(W, 'boot*.drc.config.json'))
rows = [ln.rstrip('\n').split('\t') for ln in open(os.path.join(HERE, 'results/spill178_1161.tsv'))][1:]
targets = [r for r in rows if r[0] in TARGET and r[4] == '未判定']


def func_of(va):
    for s, (_rva, n) in mach.fns.items():
        if s <= va < s + n:
            return s, n
    return None


cache = {}
out = ['fn\tsite\tslot\tkind\tnext_ref_addr\tnext_ref_insn']
for fn, site, _src, _verdict, _status, _oracle, text in targets:
    sva = int(site, 16)
    f = func_of(sva)
    if f is None:
        out.append('\t'.join([fn, site, '-', 'NO_FUNC', '-', '-']))
        continue
    s, n = f
    if s not in cache:
        cache[s] = list(mach.cs.disasm(mach.read(s - mach.base, n), s, n))
    ins = cache[s]
    idx = next(i for i, x in enumerate(ins) if x.address == sva)
    slot = re.search(r'\[rbp \+ (0x[0-9a-f]+)\]', text).group(0)
    kind, addr, insn = 'NONE', '-', '-'
    for x in ins[idx + 1:]:
        if slot not in x.op_str:
            continue
        dst = x.op_str.split(',')[0]
        kind = 'OVERWRITE' if x.mnemonic == 'mov' and slot in dst else 'READ'
        addr, insn = '%x' % x.address, '%s %s' % (x.mnemonic, x.op_str)
        break
    out.append('\t'.join([fn, site, slot.replace('[rbp + ', '').rstrip(']'), kind, addr, insn]))

with open(OUT, 'w') as f:
    f.write('\n'.join(out) + '\n')
print('[ld92] %d site -> %s' % (len(targets), OUT))
print('[ld92] kind:', {k: sum(1 for ln in out[1:] if ln.split('\t')[3] == k) for k in ('READ', 'OVERWRITE', 'NONE', 'NO_FUNC')})
