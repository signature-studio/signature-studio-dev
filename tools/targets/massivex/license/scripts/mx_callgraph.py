#!/usr/bin/env python3
"""CAB-46/MX-1: Massive X VST3 callgraph + rip-relative/IAT xref sweep.

.pdata で関数境界を取り (x64 なので正確)、capstone disasm_lite を並列走査して
  - call/jmp rel32 の target -> 呼出元関数マップ (callgraph)
  - rip 相対 operand の target -> (insn_va, func_va) 逆引き (xrefs)
  - call [rip+..] / jmp [rip+..] の IAT スロット逆引き (iat)
を 1 パスで作る。

usage: mx_callgraph.py <pe> <out.pkl> [nproc]
"""
import pickle
import re
import struct
import sys
from multiprocessing import Pool


_PE = None
_DATA = None
_FUNCS = None


def load_pdata(pe, data):
    t = None
    for s in pe.sections:
        if s.Name.rstrip(b'\0').decode() == '.pdata':
            t = s
            break
    raw = data[t.PointerToRawData:t.PointerToRawData + t.Misc_VirtualSize]
    funcs = []
    for i in range(0, len(raw) - 11, 12):
        start, end, _uw = struct.unpack_from("<III", raw, i)
        if end > start and start:
            funcs.append((start, end - start))
    return funcs


def _init(path):
    global _PE, _DATA, _FUNCS
    import pefile
    _PE = pefile.PE(path, fast_load=True)
    _DATA = open(path, 'rb').read()
    _FUNCS = dict(load_pdata(_PE, _DATA))


def _sweep(rvas):
    import capstone
    from capstone import CS_ARCH_X86, CS_MODE_64
    base = _PE.OPTIONAL_HEADER.ImageBase
    t = _PE.sections[0]
    t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize

    def off(rva):
        return t.PointerToRawData + (rva - t.VirtualAddress)

    md = capstone.Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = False
    rip = {}
    iat = {}
    calls = {}
    for rva in rvas:
        size = _FUNCS.get(rva)
        if not size:
            continue
        buf = _DATA[off(rva):off(rva) + size]
        cs = set()
        js = set()
        for addr, isz, mn, ops in md.disasm_lite(buf, base + rva):
            if '[rip' in ops:
                m = re.search(r'\[rip \+ (0x[0-9a-f]+)\]|\[rip - (0x[0-9a-f]+)\]', ops)
                if m:
                    disp = int(m.group(1), 16) if m.group(1) else -int(m.group(2), 16)
                    tgt = addr + isz + disp - base
                    outside = tgt < t_lo or tgt >= t_hi
                    if mn in ('call', 'jmp') and outside:
                        iat.setdefault(tgt, []).append((addr, rva + base))
                    else:
                        rip.setdefault(tgt, []).append((addr, rva + base))
            if mn in ('call', 'jmp'):
                m = re.match(r'^0x([0-9a-f]+)$', ops.split(', ')[0])
                if m:
                    tgt = int(m.group(1), 16) - base
                    if t_lo <= tgt < t_hi:
                        (cs if mn == 'call' else js).add(tgt)
        if cs or js:
            calls[rva + base] = {'calls': cs, 'jmps': js, 'size': size}
    return rip, iat, calls


def main():
    path, outp = sys.argv[1], sys.argv[2]
    nproc = int(sys.argv[3]) if len(sys.argv) > 3 else 14
    import pefile
    pe = pefile.PE(path, fast_load=True)
    data = open(path, 'rb').read()
    funcs = load_pdata(pe, data)
    print("pdata functions:", len(funcs))
    rvas = [r for r, sz in funcs]
    chunks = [rvas[i::nproc * 8] for i in range(nproc * 8)]
    rip_all, iat_all, calls_all = {}, {}, {}
    with Pool(nproc, initializer=_init, initargs=(path,)) as p:
        done = 0
        for rip, iat, calls in p.imap_unordered(_sweep, chunks):
            for k, v in rip.items():
                rip_all.setdefault(k, []).extend(v)
            for k, v in iat.items():
                iat_all.setdefault(k, []).extend(v)
            calls_all.update(calls)
            done += 1
            if done % 1000 == 0:
                print("  chunks %d/%d" % (done, len(chunks)), flush=True)
    pickle.dump({'rip': rip_all, 'iat': iat_all, 'calls': calls_all,
                 'funcs': dict(funcs)}, open(outp, 'wb'), protocol=4)
    print("callgraph: funcs %d, rip targets %d, iat %d -> %s"
          % (len(calls_all), len(rip_all), len(iat_all), outp))


if __name__ == '__main__':
    main()
