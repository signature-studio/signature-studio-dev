#!/usr/bin/env python3
"""Per-function census of a PE32+ via .pdata (RUNTIME_FUNCTION) + capstone SIMD classification.
usage: text_census.py <pe> <out.json> [--workers N]"""
import sys, json, struct, collections, multiprocessing as mp
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_GRP_SSE1, X86_GRP_SSE2, X86_GRP_SSE3, X86_GRP_SSSE3, X86_GRP_SSE41, X86_GRP_SSE42, X86_GRP_AVX, X86_GRP_AVX2, X86_GRP_FMA, X86_GRP_AVX512, X86_GRP_MMX

MOVES={'movss','movsd','movaps','movups','movapd','movupd','movd','movq','movdqa','movdqu','movlps','movhps','movlpd','movhpd','movmskps','movmskpd','movlhps','movhlps','movntps','movntdq','movddup','movshdup','movsldup','shufps','shufpd','unpcklps','unpckhps','unpcklpd','unpckhpd','xorps','xorpd','andps','andpd','andnps','andnpd','orps','orpd','cvtsi2ss','cvtsi2sd','cvtss2sd','cvtsd2ss','cvttss2si','cvttsd2si','cvtss2si','cvtsd2si','pxor','por','pand','pandn','punpcklqdq','pshufd','punpcklbw','punpcklwd','punpckldq','punpckhqdq','pcmpeqb','pcmpeqd','pmovmskb'}
PATH = sys.argv[1]
pe = pefile.PE(PATH, fast_load=True)
IMG = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
TB, TVA = text.get_data(), text.VirtualAddress
pdata = [s for s in pe.sections if s.Name.startswith(b'.pdata')][0].get_data()
funcs = []
for i in range(0, len(pdata) - 11, 12):
    b, e, u = struct.unpack_from('<III', pdata, i)
    if b == 0: continue
    if TVA <= b < TVA + len(TB): funcs.append((b, e))
funcs.sort()

def classify(rng):
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    c = collections.Counter(); insn = 0
    per = []
    for (b, e) in rng:
        code = TB[b - TVA:e - TVA]
        fc = collections.Counter(); n = 0
        for i in md.disasm(code, b):
            n += 1
            m = i.mnemonic
            fc['insn'] += 1
            ops = i.op_str
            if 'zmm' in ops: fc['zmm'] += 1
            elif 'ymm' in ops: fc['ymm'] += 1
            elif 'xmm' in ops:
                fc['xmm'] += 1
                mm = m[1:] if m.startswith('v') else m
                if mm in MOVES: fc['sse_move'] += 1
                elif mm.endswith(('ss', 'sd')): fc['sse_scalar_fp'] += 1
                elif mm.endswith(('ps', 'pd')): fc['sse_packed_fp'] += 1
                else: fc['sse_int'] += 1
            gs = set(i.groups)
            if X86_GRP_SSE3 in gs: fc['isa_sse3'] += 1
            if X86_GRP_SSSE3 in gs: fc['isa_ssse3'] += 1
            if X86_GRP_SSE41 in gs: fc['isa_sse41'] += 1
            if X86_GRP_SSE42 in gs: fc['isa_sse42'] += 1
            if X86_GRP_AVX in gs: fc['isa_avx'] += 1
            if X86_GRP_AVX2 in gs: fc['isa_avx2'] += 1
            if m.startswith('v'): fc['vex'] += 1
            if m.startswith('vfmadd') or m.startswith('vfnmadd') or m.startswith('vfmsub'): fc['fma'] += 1
            if m in ('cpuid', 'xgetbv'): fc[m] += 1
            if m.startswith('f') and m not in ('fs',) and i.group(0) is None: pass
            if m in ('fld','fstp','fmul','fadd','fld1','fldz','fsub','fdiv','fild','fistp','fxch','fcomi','fucomi'): fc['x87'] += 1
            if m in ('call',): fc['call'] += 1
            if m == 'syscall' or m == 'int3': pass
            if m in ('rdtsc','rdtscp'): fc['rdtsc'] += 1
        per.append((b, e - b, dict(fc)))
    return per

if __name__ == '__main__':
    nw = 12
    if '--workers' in sys.argv: nw = int(sys.argv[sys.argv.index('--workers') + 1])
    chunks = [funcs[i::nw * 4] for i in range(nw * 4)]
    with mp.Pool(nw) as p:
        res = p.map(classify, chunks)
    per = sorted([x for r in res for x in r])
    tot = collections.Counter()
    for _, _, fc in per:
        tot.update(fc)
    sizes = sorted(s for _, s, _ in per)
    n = len(per)
    summ = {
        'image': PATH, 'text_size': len(TB), 'pdata_funcs': n, 'func_bytes_sum': sum(sizes),
        'size_median': sizes[n // 2], 'size_p90': sizes[int(n * .9)], 'size_p99': sizes[int(n * .99)], 'size_max': sizes[-1],
        'gt4k': sum(1 for s in sizes if s > 4096), 'gt16k': sum(1 for s in sizes if s > 16384),
        'totals': dict(tot),
        'funcs_with_xmm': sum(1 for _, _, f in per if f.get('xmm')), 'funcs_with_ymm': sum(1 for _, _, f in per if f.get('ymm')),
        'funcs_with_zmm': sum(1 for _, _, f in per if f.get('zmm')), 'funcs_with_fma': sum(1 for _, _, f in per if f.get('fma')),
        'bytes_in_ymm_funcs': sum(s for _, s, f in per if f.get('ymm')), 'bytes_in_xmm_funcs': sum(s for _, s, f in per if f.get('xmm')),
        'bytes_in_fma_funcs': sum(s for _, s, f in per if f.get('fma')),
        'funcs_with_packed_arith': sum(1 for _, _, f in per if f.get('sse_packed_fp')),
        'funcs_with_isa_sse41': sum(1 for _, _, f in per if f.get('isa_sse41')),
    }
    json.dump({'summary': summ, 'funcs': [(hex(b + IMG), s, f) for b, s, f in per]}, open(sys.argv[2], 'w'))
    print(json.dumps(summ, indent=1))
