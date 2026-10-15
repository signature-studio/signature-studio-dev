#!/usr/bin/env python3
"""test_f3d_slots_3528.py: f3d_crosscheck_3528.mach_entry_loads の spill slot 追跡の単体テスト (#3528)。

機械語の断片を capstone で実デコードし、入口の movzx word の基底 reg の由来 argN を確かめる。IR と PE は使わない。
失敗が 1 件でもあれば終了 1。 使い方: python3 test_f3d_slots_3528.py
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capstone  # noqa: E402
import f3d_crosscheck_3528 as X  # noqa: E402

VA = 0x1000
CS = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
CS.detail = True
MACH = types.SimpleNamespace(cs=CS)

# (名前, 機械語 (hex の列), 期待する由来 argN)。
# 'mov [rbp-0x10],rcx' = 48894df0 / 'mov rax,[rbp-0x10]' = 488b45f0 / 'movzx eax,word[rax]' = 0fb700
# B・C・E は修正前の版では由来 1 が残り、誤った OK の原因になっていた。
CASES = [
    ('64bit spill の再読込 (arg1)', ['48894df0', '488b45f0', '0fb700'], 1),
    ('32bit 上書きの後の再読込 (None)', ['48894df0', '8955f0', '488b45f0', '0fb700'], None),
    ('add で書き換えた後 (None)', ['48894df0', '480155f0', '488b45f0', '0fb700'], None),
    ('cmp は書かない (arg1)', ['48894df0', '48837df000', '488b45f0', '0fb700'], 1),
    ('+4 の 32bit 上書きと重なる (None)', ['48894df0', '8955f4', '488b45f0', '0fb700'], None),
    ('レジスタ間の複写 (arg1)', ['4889ca', '0fb702'], 1),
]


def entry_origin(hex_parts):
    ins = list(CS.disasm(bytes.fromhex(''.join(hex_parts)), VA))

    class FnMach:
        def __init__(self, mach, va, block_vas):
            self.blocks = {VA: ins}

    class Fn:
        def __init__(self, name, va, body):
            pass

        def blocks(self):
            return [(VA, [])]

    X.FnMach = FnMach
    X.L.Fn = Fn
    res, _n = X.mach_entry_loads(MACH, VA, '')
    return res[0][3] if len(res) == 1 else 'n=%d' % len(res)


def main():
    bad = 0
    for name, parts, want in CASES:
        got = entry_origin(parts)
        ok = got == want
        bad += 0 if ok else 1
        print('%-36s got=%s want=%s %s' % (name, got, want, 'PASS' if ok else 'FAIL'))
    print('FAIL=%d' % bad)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
