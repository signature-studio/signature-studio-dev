#!/usr/bin/env python3
"""LD-263 (#5277): 6ed480 の戻り型 (double / float) を、callee の ret 直前命令と呼出し元の利用命令で判定する。

  python3 tools/liftdiff/tests/ld263_ret_type.py <PE>

判定 (全部満たすとき double):
  (a) callee: 戻り値は表から 8 バイト (movsd xmm0, qword ptr [.. + idx*8]) で読まれ、ret 直前の xmm0 書込みがこれ。
  (b) 呼出し元 (call 直後): 最初に xmm0 を読む命令が ucomisd (倍精度比較) で、その間に xmm0 は書かれない。
  (c) 比較相手は 64 ビット絶対値マスク 0x7fffffffffffffff を掛けた値 (float なら 32 ビットのマスク)。
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'liftdiff'))
import capstone  # noqa: E402
from ldlib import pe as P  # noqa: E402

CALLEE = 0x6ed480
CALLERS = (0x6ece54, 0x6ed54d, 0x6eedda)  # E8 走査で得た 3 呼出し元 (call 命令の VA)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    p = P.PE(sys.argv[1])
    txt = [s for s in p.sections if s['name'] == '.text'][0]
    base = p.base + txt['rva']
    data = txt['data']
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    def dis(va, n=200):
        off = va - base
        return list(md.disasm(data[off:off + n], va))

    def read(va, n):
        for s in p.sections:
            b = p.base + s['rva']
            if b <= va < b + len(s['data']):
                o = va - b
                return s['data'][o:o + n]
        return None

    ok = True
    body = []
    for i in dis(CALLEE):
        body.append(i)
        if i.mnemonic == 'ret':
            break
    last = body[-2]
    print(f'callee ret 直前: {last.mnemonic} {last.op_str}')
    a_ok = last.mnemonic == 'movsd' and last.op_str.startswith('xmm0, qword ptr') and '*8]' in last.op_str
    print(f'(a) 8 バイト読み: {"OK" if a_ok else "NG"}')
    ok &= a_ok

    tab = body[0].address + body[0].size + int(body[0].op_str.split('+')[1].split(']')[0], 16)
    for idx in (0, 1):
        v = struct.unpack('<d', read(tab + 8 * idx, 8))[0]
        print(f'  表[{idx}] = {v!r}')

    for call_va in CALLERS:
        ins = dis(call_va, 16)[0]
        if ins.mnemonic != 'call':
            print(f'{hex(call_va)}: call ではない')
            ok = False
            continue
        seq = dis(call_va + ins.size, 80)
        first = None
        clobber = False
        for j in seq:
            rd, wr = j.regs_access()
            names_w = {j.reg_name(r) for r in wr}
            names_r = {j.reg_name(r) for r in rd}
            if 'xmm0' in names_r and first is None:
                first = j
                break
            if 'xmm0' in names_w:
                clobber = True
                break
        if first is None or first.mnemonic != 'ucomisd' or clobber:
            print(f'{hex(call_va)}: 最初の xmm0 読みが ucomisd でない ({first and first.mnemonic})')
            ok = False
            continue
        mask_op = [j for j in seq if j.mnemonic == 'pand' and '[rip' in j.op_str]
        mask = None
        if mask_op:
            m = mask_op[0]
            tgt = m.address + m.size + int(m.op_str.split('+')[1].split(']')[0], 16)
            mask = read(tgt, 8)
        mask_ok = mask is not None and struct.unpack('<Q', mask)[0] == 0x7FFFFFFFFFFFFFFF
        print(f'{hex(call_va)}: ucomisd 直前に 64 bit 絶対値マスク: {"OK" if mask_ok else "NG"}')
        ok &= mask_ok

    print('判定: double' if ok else '判定: 不確定')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
