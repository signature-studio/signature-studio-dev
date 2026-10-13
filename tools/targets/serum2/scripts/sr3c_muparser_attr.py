#!/usr/bin/env python3
"""SR-3c: muParser 窓外 6 関数 (§11.3) の所在・呼び出し元・参照先と、数学名表の走査・lea 参照元の突合。前提: sr3_run.sh 実行済み (work/index.npz, work/Serum2_win64.vst3, out/sr3_gap_blocks.tsv)。"""
import bisect, struct, numpy as np, pefile
IMG=0x180000000
z=np.load('work/index.npz'); funcs=z['funcs']; refs=z['refs']
fs=funcs[:,0].tolist()
def fi(r):
    i=bisect.bisect_right(fs,r)-1
    return i if i>=0 and funcs[i][0]<=r<funcs[i][1] else -1
pe=pefile.PE('work/Serum2_win64.vst3',fast_load=True)
dm=pe.get_memory_mapped_image()
RD=[s for s in pe.sections if s.Name.rstrip(b'\0')==b'.rdata'][0]
RLO=RD.VirtualAddress; RHI=RLO+RD.Misc_VirtualSize
def u64(rva): return struct.unpack_from('<Q',dm,rva)[0]
def cstr(rva):
    if not RLO<=rva<RHI: return None
    e=dm.find(b'\0',rva,min(rva+32,len(dm)))
    if e<0: return None
    s=bytes(dm[rva:e])
    return s.decode() if 2<=len(s)<=24 and all(0x21<=c<0x7f for c in s) else None
def entry(off):
    ID=u64(off); p=u64(off+8)
    if not 5<=ID<=0x21: return None
    n=cstr(p-IMG) if IMG<=p<IMG+len(dm) else None
    return (ID,n) if n is not None else None
# 名前表: .rdata 内で (ID, 名前ポインタ) の 16 B 組が 4 件以上連続する最長の run
best=(0,0)
for off in range(RLO,RHI-32,8):
    k=0
    while off+16*k+16<=RHI and entry(off+16*k) is not None: k+=1
    if k>=4 and k>best[1]: best=(off,k)
tlo,k=best
print('name table: rva',hex(tlo+IMG) if k else '-','entries',k)
table=[entry(tlo+16*i) for i in range(k)]
for ID,n in table: print('  ID',hex(ID),n)
thi=tlo+16*k
srcs=sorted({int(r[0]) for r in refs if r[2]==0 and tlo<=r[1]<thi})
print('lea/mov refs into name table:',len(srcs))
for s in srcs:
    f=fi(s); print('  src',hex(s+IMG),'owner',hex(funcs[f][0]+IMG) if f>=0 else '.pdata 外')
gap={}
for ln in open('out/sr3_gap_blocks.tsv').readlines()[1:]:
    c=ln.split('\t'); gap[int(c[0],16)-IMG]=int(c[1])
six=[0x1809e3240,0x1809eb7b0,0x1809ef030,0x1809ef7b0,0x180a0a3e0,0x180a0f3f0]
for v in six:
    r=v-IMG; f=fi(r)
    if f>=0:
        b,e=int(funcs[f][0]),int(funcs[f][1]); where='.pdata'
    else:
        b=r; e=r+gap[r] if r in gap else None; where='.pdata 外 (gap 候補)' if r in gap else '.pdata 外 (gap 行なし)'
    callers=sorted({int(x[0])+IMG for x in refs if x[1]==b and x[2] in (1,2)})
    tgts=sorted({int(x[1])+IMG for x in refs if e is not None and b<=x[0]<e and x[2]==0})
    print(hex(b+IMG),where,'size',e-b if e is not None else '-','callers(call/jmp)',[hex(c) for c in callers][:8],'data/lea targets',[hex(t) for t in tgts][:8])
