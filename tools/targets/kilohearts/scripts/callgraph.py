#!/usr/bin/env python3
"""HeartCore .text 全域 sweep: 関数ごとの (size, 直接 call/jmp 先, SIMD 命令統計, 間接 call 数, IAT call 数)。

関数境界 = .pdata ∪ 追加発見 (leaf: 直接 call 先で pdata に無いもの、vtable slot)。
leaf の終端は「最後の前方分岐先を過ぎた後の ret / 無条件 jmp」ヒューリスティック。
usage: callgraph.py HeartCore.core_64 rtti_vtables.json out.pkl [nproc]
"""
import sys, json, pickle, collections
import numpy as np
import pefile
from multiprocessing import Pool
import capstone
from capstone import CS_ARCH_X86, CS_MODE_64

PE = DATA = None
SCAL = ('add', 'sub', 'mul', 'div', 'min', 'max', 'sqr', 'cmp', 'cvt', 'mov', 'ucomis', 'comis', 'rcp', 'rsq', 'rou')


def classify(mn, ops):
    if mn.startswith('v'):
        if mn.startswith(('vfmadd', 'vfmsub', 'vfnmadd', 'vfnmsub')):
            return 'fma'
        if 'zmm' in ops:
            return 'avx512'
        if 'ymm' in ops:
            return 'avx256'
        if mn in ('vzeroupper', 'vzeroall'):
            return 'vzero'
        return 'avx128'
    if 'xmm' not in ops:
        return None
    if mn.startswith(('mov', 'unpck', 'shuf', 'andn', 'xorp', 'orp', 'andp', 'blend')):
        if mn in ('movss', 'movsd'):
            return 'sse_scalar'
        return 'sse_move_logic'
    if mn.endswith(('ss', 'sd')) and mn.startswith(SCAL):
        return 'sse_scalar'
    if mn.endswith(('ps', 'pd')) and not mn.startswith('p'):
        return 'sse_packed_fp'
    if mn.startswith('p') and mn not in ('push', 'pop', 'pause'):
        return 'sse_packed_int'
    return None


def init(path):
    global PE, DATA
    PE = pefile.PE(path, fast_load=True)
    DATA = open(path, 'rb').read()


def sweep(args):
    base = PE.OPTIONAL_HEADER.ImageBase
    t = PE.sections[0]
    t_hi = t.VirtualAddress + t.Misc_VirtualSize

    def off(rva):
        return t.PointerToRawData + (rva - t.VirtualAddress)

    md = capstone.Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = False
    out = {}
    for start, end in args:
        leaf = end is None
        lim = min(start + 0x2000, t_hi) if leaf else end
        buf = DATA[off(start):off(lim)]
        calls, jmps, cnt = [], [], collections.Counter()
        indir = iat = n = cpuid = 0
        maxfwd = 0
        real_end = lim
        for addr, size, mn, ops in md.disasm_lite(buf, base + start):
            n += 1
            nxt = addr + size - base
            c = classify(mn, ops)
            if c:
                cnt[c] += 1
            if mn == 'call':
                if ops.startswith('0x'):
                    calls.append(int(ops, 16) - base)
                elif '[rip' in ops:
                    iat += 1
                else:
                    indir += 1
            elif mn == 'cpuid':
                cpuid += 1
            elif mn == 'jmp' or mn.startswith('j'):
                if ops.startswith('0x'):
                    tgt = int(ops, 16) - base
                    inside = start <= tgt < lim
                    if leaf:
                        inside = start <= tgt < nxt + 0x80 or tgt > nxt and tgt < nxt + 0x400 and tgt >= maxfwd and False
                        inside = start <= tgt < max(nxt, maxfwd) + 0x40
                    if mn == 'jmp' and not inside:
                        jmps.append(tgt)
                    if tgt > nxt:
                        maxfwd = max(maxfwd, tgt if inside else 0)
                elif mn == 'jmp':
                    if '[rip' in ops:
                        iat += 1
                    else:
                        indir += 1
            if leaf and mn in ('ret', 'jmp') and nxt >= maxfwd:
                real_end = nxt
                break
            if leaf and mn == 'int3':
                real_end = nxt - 1
                break
        out[start] = dict(size=real_end - start, n=n, calls=sorted(set(calls)), jmps=sorted(set(jmps)), simd=dict(cnt),
                          indir=indir, iat=iat, cpuid=cpuid, leaf=leaf)
    return out


def main(path, vtj, outp, nproc=16):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, 'rb').read()
    secs = {s.Name.rstrip(b'\0').decode(): s for s in pe.sections}
    pd = secs['.pdata']
    pdb = data[pd.PointerToRawData:pd.PointerToRawData + pd.Misc_VirtualSize]
    arr = np.frombuffer(pdb[:len(pdb) // 12 * 12], dtype='<u4').reshape(-1, 3)
    funcs = {int(b): int(e) for b, e, _ in arr if b}
    print('pdata funcs', len(funcs), file=sys.stderr)
    vt = json.load(open(vtj))
    extra = set()
    for cls, lst in vt.items():
        for v in lst:
            for s in v['slots']:
                r = int(s, 16) - base
                if r not in funcs:
                    extra.add(r)
    print('vtable slots w/o pdata', len(extra), file=sys.stderr)
    t = secs['.text']
    t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize

    allres = {}
    todo = [(b, e) for b, e in funcs.items()] + [(r, None) for r in extra]
    seen = set(funcs) | extra
    rounds = 0
    while todo and rounds < 8:
        rounds += 1
        nchunk = nproc * 16
        chunks = [todo[i::nchunk] for i in range(nchunk)]
        with Pool(nproc, initializer=init, initargs=(path,)) as p:
            for res in p.imap_unordered(sweep, chunks):
                allres.update(res)
        new = set()
        for s, r in allres.items():
            for tgt in r['calls'] + r['jmps']:
                if t_lo <= tgt < t_hi and tgt not in seen:
                    new.add(tgt)
        print('round', rounds, 'swept', len(allres), 'new leaf targets', len(new), file=sys.stderr)
        todo = [(r, None) for r in new]
        seen |= new
    pickle.dump({'base': base, 'funcs': funcs, 'res': allres}, open(outp, 'wb'))
    print('done', len(allres), file=sys.stderr)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 16)
