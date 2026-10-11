#!/usr/bin/env python3
"""MX-2: 関数 zone 逆アセンブラ (MX-1 mx_cg.pkl + mx_strings.json を注釈に利用)。

usage:
  mx_zone.py zone   <pe> <cg.pkl> <strings.json> <VA> [maxlen]   # 関数逆アセンブル
  mx_zone.py range  <pe> <cg.pkl> <strings.json> <VA> <VA>       # 範囲逆アセンブル
  mx_zone.py callers <cg.pkl> <VA>                                # 直接 caller 一覧
  mx_zone.py callees <cg.pkl> <VA>                                # 直接 callee 一覧
"""
import json
import pickle
import re
import struct
import sys

import pefile
import capstone
from capstone import CS_ARCH_X86, CS_MODE_64


def load_pdata(pe, data):
    t = next(s for s in pe.sections if s.Name.rstrip(b'\0').decode() == '.pdata')
    raw = data[t.PointerToRawData:t.PointerToRawData + t.Misc_VirtualSize]
    funcs = {}
    for i in range(0, len(raw) - 11, 12):
        start, end, _ = struct.unpack_from('<III', raw, i)
        if end > start and start:
            funcs[start] = end - start
    return funcs


def main():
    cmd = sys.argv[1]
    if cmd in ('callers', 'callees'):
        cg = pickle.load(open(sys.argv[2], 'rb'))
        va = int(sys.argv[3], 16)
        rva = va - 0x180000000
        if cmd == 'callers':
            out = [f + 0x180000000 for f, r in cg['calls'].items()
                   if rva in r['calls'] or rva in r['jmps']]
        else:
            r = cg['calls'].get(rva)
            out = sorted((c + 0x180000000 for c in (r['calls'] | r['jmps'])), key=hex) if r else []
        print('\n'.join(hex(x) for x in out))
        return

    pe, cg, strs = sys.argv[2], sys.argv[3], sys.argv[4]
    peo = pefile.PE(pe, fast_load=True)
    data = open(pe, 'rb').read()
    base = peo.OPTIONAL_HEADER.ImageBase
    funcs = load_pdata(peo, data)
    cg = pickle.load(open(cg, 'rb')) if cg != '-' else None
    strings = {int(k, 16): v for k, v in json.load(open(strs)).items()} if strs != '-' else {}

    def rva2off(rva):
        for s in peo.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                d = rva - s.VirtualAddress
                if d < s.SizeOfRawData:
                    return s.PointerToRawData + d
        return None

    if cmd == 'zone':
        va = int(sys.argv[5], 16)
        start = va - base
        size = funcs.get(start, int(sys.argv[6], 0) if len(sys.argv) > 6 else 0x200)
    else:
        a, b = int(sys.argv[5], 16), int(sys.argv[6], 16)
        start, size = a - base, b - a
    off = rva2off(start)
    assert off is not None, hex(start)
    buf = data[off:off + size]

    md = capstone.Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    # 分岐先集合 (ラベル用)
    tgts = set()
    insns = list(md.disasm(buf, base + start))
    for ins in insns:
        if ins.group(capstone.CS_GRP_JUMP) or ins.group(capstone.CS_GRP_CALL) or ins.mnemonic.startswith('loop'):
            try:
                tgts.add(ins.operands[0].imm)
            except Exception:
                pass
    for ins in insns:
        lbl = 'L_%x:' % ins.address if ins.address in tgts else '       '
        # rip 相対の注釈
        note = ''
        m = re.search(r'\[rip \+ (0x[0-9a-f]+)\]|\[rip - (0x[0-9a-f]+)\]', ins.op_str)
        if m:
            disp = int(m.group(1), 16) if m.group(1) else -int(m.group(2), 16)
            tgt = ins.address + ins.size + disp
            s = strings.get(tgt)
            if s:
                note = '  ; %s %r' % (s['sec'], s['s'][:70])
            elif cg:
                for slot, refs in (('iat', cg['iat']), ('rip', cg['rip'])):
                    if (tgt - base) in {t for t, _ in []}:
                        pass
                if (tgt - base) in cg['iat']:
                    note = '  ; IAT'
        print('%s %08x  %-8s %-40s%s' % (lbl, ins.address, ins.mnemonic, ins.op_str, note))


if __name__ == '__main__':
    main()
