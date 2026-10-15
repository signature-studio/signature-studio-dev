#!/usr/bin/env python3
"""test_f3c_indirect_4421.py: f3c_indirect_call_before の単体テスト (#4421)。

最初の deref の前に間接 call (呼出先が即値でない) があれば置換しない、の規則を確かめる。
機械語の断片を capstone で実デコードする。IR と PE は使わない。
失敗が 1 件でもあれば終了 1。 使い方: python3 test_f3c_indirect_4421.py
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capstone  # noqa: E402
import ldfix as L  # noqa: E402

VA = 0x1000
CS = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
CS.detail = True

# (名前, 機械語 (hex の列), 最初の deref の命令 index, 期待 (True = 置換しない))
# 'mov rax,[rdi]' = 488b07 / 'call rax' = ffd0 / 'call rel32 0' = e800000000 (即値の直接 call)
# 'call qword ptr [rip+0]' = ff1500000000 (間接 call、c40420 の形)
CASES = [
    ('間接 call (レジスタ) の後に deref', ['ffd0', '488b07'], 1, True),
    ('間接 call (メモリ経由) の後に deref', ['ff1500000000', '488b07'], 1, True),
    ('即値の直接 call の後に deref', ['e800000000', '488b07'], 1, False),
    ('call なしの deref', ['488b07'], 0, False),
    ('間接 call が deref の後なら対象外', ['488b07', 'ffd0'], 0, False),
]


def has_indirect(hex_parts, deref_idx):
    ins = list(CS.disasm(bytes.fromhex(''.join(hex_parts)), VA))
    fv = types.SimpleNamespace(ins=ins)
    return L.f3c_indirect_call_before(fv, ins[deref_idx].address)


def main():
    bad = 0
    for name, parts, idx, want in CASES:
        got = has_indirect(parts, idx)
        ok = got == want
        bad += 0 if ok else 1
        print('%-36s got=%s want=%s %s' % (name, got, want, 'PASS' if ok else 'FAIL'))
    print('FAIL=%d' % bad)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
