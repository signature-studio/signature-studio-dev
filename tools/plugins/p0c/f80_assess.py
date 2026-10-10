#!/usr/bin/env python3
"""80 kernel 実装の x87 (f80) 使用を実機械語から分類し、f80→f64 lowering の影響を
micro-benchmark (f80_micro.c) の実測に対応付ける (CAB-196 P0c)。

分類 (複数ラベル可):
  f32chain  : fld/fst/fstp/fadd/fmul/fsub dword (f32) のみ — f64 lowering は bit-exact (実測 0/2M)
  f64mem    : qword mem op を含む — 出力 f64 の場合は ±1 ulp が 0.018% (実測)
  int32x87  : fild/fistp/fist/fimul/fisub dword — i32 は f64 に正確 (bit-exact)
  int64x87  : fild/fistp qword (i64) — f64 経由だと |v|>2^53 で不一致 (実測 64%) → i64 保持 lowering 要
  rc_chop   : fldcw (0x0F3F: RC=chop) — C trunc cast と一致 (実測 0/1M)
  transc    : f2xm1/fscale/frndint/fldl2e (Intel HW アルゴリズム) — 実測 0/200k (T∈[-20,20], f32 出力)
  cmpsel    : fucompi/fcmovb/fcompp/fabs/fldz — 比較は f64 でも一致 (unordered 含む, 実測 0)
出力: work/f80_classes.json + stdout 表
usage: f80_assess.py
"""
import json, os, struct, sys, collections
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM

HERE = os.path.dirname(os.path.abspath(__file__))
PE = '/home/ubuntu/work/analysis/win64/extracted/block18983_PE.bin'
MD = Cs(CS_ARCH_X86, CS_MODE_64)
MD.detail = True

pe = pefile.PE(data=open(PE, 'rb').read(), fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
F = {}
for k in range(len(pd) // 12):
    b, e, u = struct.unpack_from('<III', pd, 12 * k)
    if b and not u & 1:
        F[base + b] = base + e
tva = [base + s.VirtualAddress for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
td = [s.get_data()[:s.Misc_VirtualSize] for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
secs = [(s.Name.rstrip(b'\0').decode(), base + s.VirtualAddress, s.get_data()[:s.Misc_VirtualSize]) for s in pe.sections]


def fb(va):
    return td[va - tva:F[va] - tva]


def rdmem(va, n):
    for nm, a, d in secs:
        if a <= va < a + len(d):
            return d[va - a:va - a + n]
    return b''


kt = json.load(open(os.path.join(HERE, '..', 'work', 'kernel_table.json')))

# IR 側の x86_fp80 情報 (k80.lift.ll = 80 kernel の RetDec lift; 無ければ skip)
f80ir = {}
llpath = os.path.join(HERE, 'work', 'k80.lift.ll')
if os.path.exists(llpath):
    import re
    ll = open(llpath).read()
    for f in re.split(r'\ndefine ', ll)[1:]:
        m = re.match(r'[^@]*@function_([0-9a-f]+)', f)
        if not m:
            continue
        n = f.count('x86_fp80')
        if n:
            f80ir[hex(int(m.group(1), 16))] = n
    json.dump(f80ir, open(os.path.join(HERE, 'work', 'f80_kernels.json'), 'w'), indent=1)

rows = []
for k in kt['kernels']:
    va = int(k['va'], 16)
    mn = collections.Counter()
    memsz = collections.Counter()
    cws = []
    rip_const = []
    for i in MD.disasm(fb(va), va):
        m = i.mnemonic
        if m.startswith('f') or m in ('fucompi', 'fucomipp'):
            mn[m] += 1
        if i.operands and i.operands[0].type == X86_OP_MEM and m.startswith('f'):
            memsz[(m, i.operands[0].size)] += 1
        if m == 'fldcw':
            op = i.operands[0]
            tgt = i.address + i.size + op.mem.disp
            cw = struct.unpack('<H', rdmem(tgt, 2))[0]
            cws.append('%04x' % cw)
    labels = set()
    q = dict(memsz)
    data4 = any((m, 4) in q for m in ('fld', 'fadd', 'fmul', 'fsub', 'fstp'))
    data8 = any((m, 8) in q for m in ('fld', 'fstp', 'fadd', 'fmul', 'fsub'))
    if data4 and not data8 and 'int64x87' not in labels:
        labels.add('f32chain')
    if data8:
        labels.add('f64mem')
    if any(m in mn for m in ('fild', 'fistp', 'fist', 'fimul', 'fisub')) and not any((m, 8) in q for m in ('fild', 'fistp')):
        labels.add('int32x87')
    if any((m, 8) in q for m in ('fild', 'fistp')):
        labels.add('int64x87')
    if cws:
        labels.add('rc_chop')
    if any(m in mn for m in ('f2xm1', 'fscale', 'frndint', 'fldl2e')):
        labels.add('transc')
    if any(m in mn for m in ('fucompi', 'fcmovb', 'fcompp', 'fabs', 'fldz', 'fucomip')):
        labels.add('cmpsel')
    rows.append({'va': hex(va), 'size': k['size'], 'x87': k['x87'], 'labels': sorted(labels),
                 'memops': {'%s:%d' % m: n for m, n in sorted(memsz.items())}, 'fldcw': cws})

# 集計
lab = collections.Counter()
for r in rows:
    for L in r['labels']:
        lab[L] += 1
print('kernel 80 本の x87 分類 (複数ラベル):', dict(lab))
f80ir = json.load(open(os.path.join(HERE, 'work', 'f80_kernels.json'))) if os.path.exists(os.path.join(HERE, 'work', 'f80_kernels.json')) else {}
print('IR に x86_fp80 を持つ kernel: %d (machine x87: %d)' % (len(f80ir), sum(1 for r in rows if r['x87'])))
print()
print('%-10s %4s %-28s %s' % ('kernel', 'size', 'labels', 'memops / fldcw'))
for r in sorted(rows, key=lambda r: int(r['va'], 16)):
    if not r['x87']:
        continue
    ir = ' IR:f80' if r['va'] in f80ir else ''
    print('%-10s %4d %-28s %s%s' % (r['va'], r['size'], ','.join(r['labels']),
                                    json.dumps(r['memops'], ensure_ascii=False) + (' cw=' + ','.join(r['fldcw']) if r['fldcw'] else ''), ir))
json.dump({'labels': dict(lab), 'kernels': rows}, open(os.path.join(HERE, 'work', 'f80_classes.json'), 'w'), indent=1)
