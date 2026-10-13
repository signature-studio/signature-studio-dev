#!/usr/bin/env python3
# MX-3b U1: 指定 VA から最大 N 命令を逆アセンブルし、第 2 引数 (rdx = ProcessData*) の
# 参照 offset を集計する。pdata 非依存。停止規則: max_insn 命令に達するか、
# ret を 30 命令超の後に最初に見た地点で止める (ret/int3 の境界は見ない)。
# usage: mx_slot_body.py <pe> <func_va_hex> [max_insn]
# self-test (PE 不要): mx_slot_body.py --selftest
import sys, collections
from capstone import Cs, CS_ARCH_X86, CS_MODE_64


def scan(code, fva, maxn=400):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    offs = collections.Counter()
    calls = []
    n = 0
    for ins in md.disasm(code, fva):
        n += 1
        if n > maxn:
            break
        if ins.mnemonic == 'call':
            calls.append((ins.address, ins.op_str))
        for op in ins.operands:
            if op.type == 3 and op.mem.base != 0:  # X86_OP_MEM
                if md.reg_name(op.mem.base) == 'rdx':
                    offs[op.mem.disp] += 1
        if ins.mnemonic == 'ret' and n > 30:
            break
    return n, offs, calls


def selftest():
    # 既知エンコード: mov rax,[rdx+0x18] / mov ecx,[rdx+4] / ret (rdx 参照 2 件)
    pos = bytes.fromhex('488b4218' + '8b4a04' + 'c3')
    n, offs, calls = scan(pos, 0x1000)
    assert sorted(offs.items()) == [(4, 1), (0x18, 1)], (n, offs)
    # 負例: mov rax,[rcx+0x18] / ret (rdx 参照 0 件)
    neg = bytes.fromhex('488b4118' + 'c3')
    n2, offs2, _ = scan(neg, 0x1000)
    assert sum(offs2.values()) == 0, (n2, offs2)
    print('selftest PASS: positive rdx refs=%d (offsets %s), negative rdx refs=%d'
          % (sum(offs.values()), sorted(offs.items()), sum(offs2.values())))


def main():
    import pefile
    pe_path, fva = sys.argv[1], int(sys.argv[2], 16)
    maxn = int(sys.argv[3]) if len(sys.argv) > 3 else 400
    pe = pefile.PE(pe_path, fast_load=True)
    IB = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_memory_mapped_image()
    code = None
    for s in pe.sections:
        base = IB + s.VirtualAddress
        if base <= fva < base + s.Misc_VirtualSize:
            off = fva - IB
            code = data[off:off + 0x2000]
            break
    assert code is not None, 'VA not in a section'
    n, offs, calls = scan(code, fva, maxn)
    print('insns=%d' % n)
    print('rdx-based mem offsets:', sorted(offs.items()))
    print('calls: %d' % len(calls))
    for a, o in calls[:40]:
        print('  %x call %s' % (a, o))


if __name__ == '__main__':
    if sys.argv[1:2] == ['--selftest']:
        selftest()
    else:
        main()
