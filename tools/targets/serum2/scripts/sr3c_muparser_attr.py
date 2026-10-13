#!/usr/bin/env python3
"""SR-3c: muParser 窓外 6 関数 (§11.3) の呼び出し元・参照文字列・名前表の突合。前提: sr3_run.sh 実行済み (work/index.npz, work/Serum2_win64.vst3)。"""
import sys, bisect, numpy as np, pefile, struct
IMG=0x180000000
z=np.load('work/index.npz'); funcs=z['funcs']; refs=z['refs']
fs=funcs[:,0].tolist()
def fi(r):
    i=bisect.bisect_right(fs,r)-1
    return i if i>=0 and funcs[i][0]<=r<funcs[i][1] else -1
pe=pefile.PE('work/Serum2_win64.vst3',fast_load=True)
S={s.Name.rstrip(b'\0').decode():s for s in pe.sections}
dm=pe.get_memory_mapped_image()
six=[0x1809e3240,0x1809eb7b0,0x1809ef030,0x1809ef7b0,0x180a0a3e0,0x180a0f3f0]
names=[b'acos\0',b'log2\0',b'sinh\0',b'sqrt\0',b'log10\0',b'asin\0',b'cosh\0',b'tanh\0',b'exp\0',b'log\0',b'sin\0',b'cos\0',b'tan\0',b'abs\0',b'min\0',b'max\0',b'sign\0',b'floor\0',b'ceil\0']
for v in six:
    f=fi(v-IMG); b,e=funcs[f][0]+IMG,funcs[f][1]+IMG
    callers=[int(r[0])+IMG for r in refs if r[1]==funcs[f][0] and r[2] in (1,2)]
    tgts=sorted({int(r[1])+IMG for r in refs if fi(int(r[0]))==f and r[2]==0})
    print(hex(b),'size',e-b,'callers(call/jmp)',[hex(c) for c in callers][:8],'data/lea targets',[hex(t) for t in tgts][:8])
