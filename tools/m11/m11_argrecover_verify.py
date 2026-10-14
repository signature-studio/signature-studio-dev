#!/usr/bin/env python3
"""m11_argrecover.py の set_const fixes の独立検算 (別アルゴリズム: capstone の regs_access を使わず op_str の文字列だけで判定).
各 fix について call 直前を後ろ向きに見て、対象 reg を dest にする最初の命令が定数代入であること、
その間に call/jmp/jcc/ret が挟まらないことを確認し、定数値が一致するか比較する.
使い方: python3 m11_argrecover_verify.py FIXES.json --pe PE [--corrupt N]   (--corrupt: ネガティブコントロール, N 件の値を +1 して FAIL を確認)
"""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'ldfix'))
import ldmach

ap = argparse.ArgumentParser()
ap.add_argument('fixes'); ap.add_argument('--pe', required=True); ap.add_argument('--corrupt', type=int, default=0)
ap.add_argument('--lb', default='0')
a = ap.parse_args()
lb = int(a.lb, 0)
fx = json.load(open(a.fixes))['fixes']
for f in fx[:a.corrupt]:
    f['const'] = dict(f['const'], val=f['const']['val'] + 1)
m = ldmach.Machine(a.pe)
ALIAS = {0: ('ecx', 'rcx', 'cx', 'cl'), 1: ('edx', 'rdx', 'dx', 'dl'), 2: ('r8d', 'r8', 'r8w', 'r8b'), 3: ('r9d', 'r9', 'r9w', 'r9b')}
WIDTH = {'byte': 8, 'word': 16, 'dword': 32, 'qword': 64}
ok = bad = 0
bad_list = []
for f in fx:
    cva = int(f['caller'].split('_')[1], 16); tva = int(f['callee'].split('_')[1], 16)
    ins = m.disasm_fn(cva)
    idx = [i for i, x in enumerate(ins) if x.mnemonic == 'call' and x.op_str == hex(tva)]
    good = False
    if f['k'] < len(idx):
        j = idx[f['k']] - 1
        names = ALIAS.get(f['pos'])
        slot = 0x20 + 8 * (f['pos'] - 4)
        while j >= 0:
            x = ins[j]
            if x.mnemonic in ('call', 'ret', 'jmp') or x.mnemonic.startswith('j'):
                break
            dst = x.op_str.split(',')[0].strip()
            if names is None:
                if f'[rsp + 0x{slot:x}]' in dst:
                    parts = x.op_str.split(', ')
                    if x.mnemonic == 'mov' and len(parts) == 2 and dst.split()[0] in WIDTH:
                        try:
                            v = int(parts[1], 0)
                        except ValueError:
                            v = None
                        if v is not None:
                            bits = WIDTH[dst.split()[0]]
                            got = ('int', v & ((1 << bits) - 1))
                            good = got == (f['const']['kind'], f['const']['val']) and bits == f.get('bits', bits)
                    break
                j -= 1
                continue
            if dst in names:
                if x.mnemonic == 'xor' and dst in names[:2] and x.op_str.split(', ')[1] == dst:
                    got = ('int', 0)
                elif dst == names[0] and x.mnemonic == 'mov' and x.op_str.split(', ')[1].startswith(('0x', '-')) or (dst == names[0] and x.mnemonic == 'mov' and x.op_str.split(', ')[1].isdigit()):
                    got = ('int', int(x.op_str.split(', ')[1], 0) & 0xffffffff)
                elif x.mnemonic == 'lea' and 'rip' in x.op_str:
                    disp = x.op_str.split('rip ')[1].rstrip(']').replace(' ', '')
                    got = ('ptr', x.address + x.size + int(disp, 0) - 0x400000 + lb)
                else:
                    got = None
                good = got == (f['const']['kind'], f['const']['val'])
                break
            j -= 1
    if good:
        ok += 1
    else:
        bad += 1; bad_list.append(f)
print('[verify] fixes %d: match %d / mismatch %d' % (len(fx), ok, bad))
for f in bad_list[:5]:
    print('  MISMATCH', f)
sys.exit(1 if bad else 0)
