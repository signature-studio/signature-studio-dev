#!/usr/bin/env python3
"""verify_dest_2202.py — REPORT_2202 の review 指摘 1〜3 の検証 (#2202)。

使い方: python3 verify_dest_2202.py PE.bin
  - 指摘 1: PE 上の 69c381 (not eax) が trace_dest で 69c378 (mov eax,[rip+...]) の DEST_RIPREAD に辿れること
  - 指摘 2: RMW の第 2 オペランド (add eax,ecx / shl eax,cl) の元を追跡すること。
            元が reg 即値・reg 定義 (memory 無し) なら、RIP 読みへ帰属させず REGLIVE に落ちること
  - 指摘 3: bt / xadd / cmpxchg / rcl / rcr を consumer としたとき、dest の元 mov に到達すること
合成機械語は下記 code*。期待値は trace_dest の実際の規則 (最初に見つかった writer を返す) に合わせている。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capstone  # noqa: E402
from ldmach import Machine  # noqa: E402
from audit_undefload_dest import trace_dest  # noqa: E402


class FakeMach:
    """disasm_fn だけを持つ合成用の Machine 代替。"""

    def __init__(self, code, base=0x1000):
        self.cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.cs.detail = True
        self.base = base
        self.code = code

    def disasm_fn(self, va):
        return list(self.cs.disasm(self.code, va))


def check_pe(pe):
    m = Machine(pe)
    va = 0x69c360  # JSON の fn と同じ絶対 VA (ImageBase 込み)
    seq = m.disasm_fn(va)
    cons = next(i for i in seq if i.address == 0x69c381 and i.mnemonic == 'not')
    mo, w = trace_dest(m, va, cons.address, cons)
    ok = mo is not None and mo.get('rip_rva') is not None and w is not None and w.address == 0x69c378
    print('[1] PE 69c381 %s <- %x %s %s : rip_rva=%s  %s' % (
        cons.op_str, w.address if w else 0, w.mnemonic if w else '-', w.op_str if w else '-',
        hex(mo['rip_rva']) if mo and mo.get('rip_rva') is not None else None, 'OK' if ok else 'NG'))
    return ok


def check_synthetic(name, code, cons_index, exp_writer_index, exp_mem):
    """exp_mem: True なら memory read (rip 読み) に到達、False なら mo=None (REGLIVE)。"""
    fm = FakeMach(code)
    seq = fm.disasm_fn(fm.base)
    cons = seq[cons_index]
    mo, w = trace_dest(fm, fm.base, cons.address, cons)
    got_addr = w.address if w else None
    exp_addr = seq[exp_writer_index].address if exp_writer_index is not None else None
    ok = got_addr == exp_addr and ((mo is not None) == exp_mem)
    print('[%s] consumer %s %s -> writer %s %s  mem=%s  %s' % (
        name, cons.mnemonic, cons.op_str, w.mnemonic if w else '-', w.op_str if w else '-',
        mo is not None, 'OK' if ok else 'NG'))
    return ok


def main():
    pe = sys.argv[1]
    results = [check_pe(pe)]
    # 指摘 2a: mov eax,[rip+0xfa] ; mov ecx,edx ; add eax,ecx ; cmp eax,0
    #   add の第 2 オペランド ecx の元は reg 定義 (mov ecx,edx) で memory 無し → REGLIVE (RIP に帰属しない)
    code2a = bytes.fromhex('8b05fa000000' '89d1' '01c8' '83f800')
    results.append(check_synthetic('2a add eax,ecx (ecx=reg def)', code2a, 3, 1, False))
    # 指摘 2b: mov eax,[rip+0xfa] ; mov ecx,[rip+0x1fa] ; shl eax,cl ; cmp eax,0
    #   cl → rcx に正規化され、その元 mov ecx,[rip] に到達する
    code2b = bytes.fromhex('8b05fa000000' '8b0dfa010000' 'd3e0' '83f800')
    results.append(check_synthetic('2b shl eax,cl (cl=rip read)', code2b, 3, 1, True))
    # 指摘 3a: mov eax,[rip+0xfa] ; bt eax,ecx  (consumer は bt)
    code3a = bytes.fromhex('8b05fa000000' '0fa3c8')
    results.append(check_synthetic('3a bt eax,ecx', code3a, 1, 0, True))
    # 指摘 3b: mov eax,[rip+0xfa] ; xadd eax,ecx
    code3b = bytes.fromhex('8b05fa000000' '0fc1c8')
    results.append(check_synthetic('3b xadd eax,ecx', code3b, 1, 0, True))
    # 指摘 3c: mov ecx,[rip+0xfa] ; cmpxchg ecx,edx  (dest=ecx)
    code3c = bytes.fromhex('8b0dfa000000' '0fb1d1')
    results.append(check_synthetic('3c cmpxchg ecx,edx', code3c, 1, 0, True))
    # 指摘 3 (回帰): mov eax,[rip+0xfa] ; rcl eax,cl / rcr eax,1  (consumer は rcl/rcr)
    code3d = bytes.fromhex('8b05fa000000' 'd3d0')
    results.append(check_synthetic('3d rcl eax,cl', code3d, 1, 0, True))
    code3e = bytes.fromhex('8b05fa000000' 'd1d8')
    results.append(check_synthetic('3e rcr eax,1', code3e, 1, 0, True))
    print('ALL OK' if all(results) else 'FAIL')
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
