#!/usr/bin/env python3
"""rax_source (vtable_closure.py) の分類を capstone の機械語で固定する回帰テスト (#849)。
実行: python3 test_rax_source.py (pefile / capstone が必要)。"""
import unittest

import capstone

import vtable_closure as vc

BASE = 0x140000000
ADDR = 0x140001000
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)


def classify(code, res=None):
    ins = list(MD.disasm(code, ADDR))
    k = next(i for i, x in enumerate(ins) if x.mnemonic == 'call')
    return vc.rax_source(ins, k, BASE, res or {})


CALL_RIP = bytes.fromhex('ff1500000000')  # call [rip+0]


class RaxSourceTest(unittest.TestCase):
    def test_rip_qword_load_is_rip_load_not_vtable(self):
        # mov rax, qword ptr [rip+0x40]; call [rip+0]
        kind, arg = classify(bytes.fromhex('488b05' + '40000000') + CALL_RIP)
        self.assertEqual(kind, 'rip_load')
        self.assertEqual(arg, ADDR + 7 + 0x40)

    def test_vtable_form_is_vtable_cfg(self):
        # mov rax, qword ptr [rax+0x18]; call [rip+0]
        self.assertEqual(classify(bytes.fromhex('488b4018') + CALL_RIP), ('vtable_cfg', 0x18))

    def test_cdqe_overwrites_rax(self):
        # mov rax, qword ptr [rax+0x18]; cdqe; call [rip+0]
        self.assertEqual(classify(bytes.fromhex('488b4018' + '4898') + CALL_RIP), ('other_write:cdqe', None))

    def test_one_operand_mul_overwrites_rax(self):
        # mov rax, qword ptr [rax+0x18]; mul rcx; call [rip+0]
        self.assertEqual(classify(bytes.fromhex('488b4018' + '48f7e1') + CALL_RIP), ('other_write:mul', None))

    def test_xchg_with_rax_overwrites_rax(self):
        # mov rax, qword ptr [rax+0x18]; xchg rax, rcx; call [rip+0]
        self.assertEqual(classify(bytes.fromhex('488b4018' + '4891') + CALL_RIP), ('other_write:xchg', None))

    def test_indexed_mov_is_other_write_mov(self):
        # mov rax, qword ptr [rcx+rdx*8]; call [rip+0]
        self.assertEqual(classify(bytes.fromhex('488b04d1') + CALL_RIP), ('other_write:mov', None))

    def test_reg_copy(self):
        # mov rax, rcx; call [rip+0]
        self.assertEqual(classify(bytes.fromhex('4889c8') + CALL_RIP), ('reg_copy', None))

    def test_push_rax_does_not_write_rax(self):
        # mov rax, qword ptr [rax+0x18]; push rax; call [rip+0]
        self.assertEqual(classify(bytes.fromhex('488b4018' + '50') + CALL_RIP), ('vtable_cfg', 0x18))

    def test_bt_rax_does_not_write_rax(self):
        # mov rax, qword ptr [rax+0x18]; bt rax, 3; call [rip+0]
        self.assertEqual(classify(bytes.fromhex('488b4018' + '480fbae003') + CALL_RIP), ('vtable_cfg', 0x18))

    def test_lea_rip_to_function_head(self):
        # lea rax, [rip+0x10]; call [rip+0]  (target = ADDR+7+0x10 が res の関数先頭)
        res = {ADDR + 7 + 0x10 - BASE: {'size': 1, 'calls': [], 'jmps': []}}
        self.assertEqual(classify(bytes.fromhex('488d05' + '10000000') + CALL_RIP, res),
                         ('lea_fn', ADDR + 7 + 0x10))


if __name__ == '__main__':
    unittest.main()
