#!/usr/bin/env python3
"""Massive X.vst3 全域 callgraph sweep (.pdata 関数境界 + capstone)。

KN の callgraph.py と同じ目的・別実装。出力は dsp/work/cg.pkl:
  { 'base': int, 'fsz': {rva: size}, 'callees': {rva: [rva,...]},
    't_lo','t_hi': .text 範囲 }
- 関数境界 = .pdata RUNTIME_FUNCTION の BeginAddress (有効のみ・重複は最大サイズ)
- size > 256KB の異常 entry は次の begin までの距離に丸める (repack 由来の破損 entry)
- callees = 直接 call / tail jmp の rel32 先のうち .text 内のもの
  (import thunk 領域 0x396e000-0x3970200 は除外 — あそこは jmp [rip+IAT] のスタブ群)
usage: mx_cg.py <pe> <out.pkl>
"""
import sys, struct, pickle, bisect, time
import pefile, capstone


def main(path, outp):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, 'rb').read()
    t = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize
    t_raw = t.PointerToRawData
    pds = sorted([s for s in pe.sections if s.Name.rstrip(b'\0').decode() == '.pdata'],
                 key=lambda s: -s.Misc_VirtualSize)
    raw = data[pds[0].PointerToRawData: pds[0].PointerToRawData + pds[0].Misc_VirtualSize]
    items = []
    for i in range(0, len(raw) - 11, 12):
        st, e, u = struct.unpack_from('<III', raw, i)
        if e > st and st and 0x1000 <= st < t_hi:
            items.append((st, e))
    items.sort()
    begins = sorted(set(st for st, _ in items))
    fsz = {}
    for st, e in items:
        fsz[st] = e - st

    def clamp(st):
        i = bisect.bisect_right(begins, st)
        return begins[i] if i < len(begins) else t_hi

    for st in list(fsz):
        if fsz[st] > 0x40000:
            fsz[st] = max(1, clamp(st) - st)

    def rd(rva, n):
        o = t_raw + (rva - t_lo)
        return data[o:o + n]

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    thunk_lo, thunk_hi = 0x396e000, 0x3970200
    callees = {}
    t0 = time.time()
    for rva in begins:
        sz = fsz[rva]
        cs = set()
        try:
            for a, s, mn, ops in md.disasm_lite(rd(rva, sz), base + rva):
                if mn in ('call', 'jmp') and ops.startswith('0x'):
                    tg = int(ops, 16) - base
                    if thunk_lo <= tg < thunk_hi:
                        continue
                    if t_lo <= tg < t_hi:
                        cs.add(tg)
        except capstone.CsError:
            pass
        if cs:
            callees[rva] = sorted(cs)
    pickle.dump({'base': base, 'fsz': fsz, 'callees': callees, 't_lo': t_lo, 't_hi': t_hi,
                 'begins': begins}, open(outp, 'wb'), protocol=4)
    print('functions %d (pdata begins) sum %d B; with direct callees %d; %.1fs'
          % (len(begins), sum(fsz.values()), len(callees), time.time() - t0))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
