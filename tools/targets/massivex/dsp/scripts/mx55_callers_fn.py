#!/usr/bin/env python3
"""MX-55 (#5030) 残件: `call [reg+0x100]` の全サイトを関数単位で分類する。

mx55_callers.py は直前 40 命令の窓で xmm2 の書込みを探すだけで、窓が call で打ち切られる。
本スクリプトは .pdata の関数始点から呼出し直前までを読み、
  - xmm2 を書く命令が、最後の call/ret/jmp より後にあるか (= 呼出し時点で xmm2 が有効か)
を出す。0x17b680 を呼ぶサイトなら呼出し時点で xmm2 が有効なはず (float 引数)。

usage: mx55_callers_fn.py <pe> [target_rva_hex]
"""
import re
import struct
import sys
from bisect import bisect_right

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

CALL_RE = re.compile(rb'\xff([\x90\x91\x92\x93\x95\x96\x97])([\x00-\xff]{4})')


def main(pe_path, target_rva='0x17b680'):
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    sec = {s.Name.rstrip(b'\0'): s for s in pe.sections}
    rd = sec[b'.rdata']
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    t_lo = base + text.VirtualAddress
    t_hi = t_lo + text.Misc_VirtualSize
    rd_lo = base + rd.VirtualAddress
    rd_hi = rd_lo + rd.Misc_VirtualSize
    T = base + int(target_rva, 16)

    def rq(va):
        return struct.unpack_from('<Q', data, rd.PointerToRawData + (va - rd_lo))[0]

    disps = set()
    for va in range(rd_lo, rd_hi - 7, 8):
        if rq(va) != T:
            continue
        v = va
        while v - 8 >= rd_lo and t_lo <= rq(v - 8) < t_hi:
            v -= 8
        disps.add((va - v) // 8 * 8)

    ex = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    ex_sec = [s for s in pe.sections if s.VirtualAddress <= ex.VirtualAddress < s.VirtualAddress + s.Misc_VirtualSize][0]
    ex_off = ex.VirtualAddress - ex_sec.VirtualAddress + ex_sec.PointerToRawData
    starts = sorted(
        base + struct.unpack_from('<I', data, ex_off + k * 12)[0]
        for k in range(ex.Size // 12)
    )

    def fn_start(va):
        i = bisect_right(starts, va) - 1
        return starts[i] if i >= 0 else None

    blob = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    sites = []
    for m in CALL_RE.finditer(blob):
        if int.from_bytes(m.group(2), 'little', signed=True) not in disps:
            continue
        h = m.start()
        lo = max(0, h - 96)
        insns = list(md.disasm(blob[lo:h + 16], t_lo + lo))
        if any(i.address == t_lo + h for i in insns):
            sites.append(t_lo + h)

    counts = {'xmm2_live': 0, 'xmm2_not_live': 0, 'no_fn': 0}
    for va in sites:
        fs = fn_start(va)
        if fs is None:
            counts['no_fn'] += 1
            print('%#x no pdata function' % va)
            continue
        code = blob[fs - t_lo:va - t_lo]
        insns = list(md.disasm(code, fs))
        # 保守側: jmp では状態を戻さず、call/ret でのみ戻す (分岐をまたぐ書込みを落とさない)。
        live = False
        called = False
        for i in insns:
            if i.mnemonic in ('call', 'ret'):
                live = False
                called = True
                continue
            _, wr = i.regs_access()
            if any(md.reg_name(r) == 'xmm2' for r in wr):
                live = True
        if live:
            key = 'xmm2_written'
        elif called:
            key = 'clobbered_by_call'
        else:
            key = 'livein_passthrough'
        counts[key] = counts.get(key, 0) + 1
        print('%#x fn %#x %s' % (va, fs, key))
    print('disps: %s' % sorted(hex(d) for d in disps))
    print('sites: %d %s' % (len(sites), counts))
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:3]))
