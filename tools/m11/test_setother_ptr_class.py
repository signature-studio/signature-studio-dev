#!/usr/bin/env python3
"""m11_setother_ptr_class.load_def の負例・正例 (#5392 / M11-N242)。実行: python3 test_setother_ptr_class.py"""
import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capstone
import m11_setother_ptr_class as M

CS = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
CS.detail = True

MOV_IMM_RAX8 = '48c7400801000000'   # mov qword ptr [rax + 8], 1
MOV_LD_RAX8 = '488b4808'            # mov rcx, qword ptr [rax + 8]
MOV_LD_RBX8 = '488b4b08'            # mov rcx, qword ptr [rbx + 8]
MOV_REG_RAX8 = '48894808'           # mov qword ptr [rax + 8], rcx
MOV_IMM_RBX8 = '48c7430801000000'   # mov qword ptr [rbx + 8], 1
MOV_IMM32_RAX8 = 'c7400801000000'   # mov dword ptr [rax + 8], 1
MOV_RAX_RAX8 = '488b4008'           # mov rax, qword ptr [rax + 8]
MOV_IMM_RAX0 = '48c7400001000000'   # mov qword ptr [rax], 1
CALL_REL = 'e800000000'             # call +0
MOV_RCX_RSI = '4889f1'              # mov rcx, rsi
MOV_CL_5 = 'b105'                   # mov cl, 5
MOV_R8D_9 = '41b809000000'          # mov r8d, 9
MOV_LD_RCX8 = '488b5108'            # mov rdx, qword ptr [rcx + 8]
MOV_LD_R8_8 = '498b5008'            # mov rdx, qword ptr [r8 + 8]


def seq(*hexes):
    out, addr = [], 0x1000
    for h in hexes:
        ins = list(CS.disasm(bytes.fromhex(h), addr))
        assert len(ins) == 1, h
        out.append(ins[0])
        addr += ins[0].size
    return out


def load_at_end(*hexes, base='rax'):
    ins = seq(*hexes)
    return M.load_def(CS, ins, len(ins) - 1, base, 8, 64, set())


class LoadDefTest(unittest.TestCase):
    def test_imm_store_same_base_is_value(self):
        self.assertEqual(load_at_end(MOV_IMM_RAX8, MOV_LD_RAX8), ('実値化', 'ptr_imm', 1))

    def test_other_base_write_is_alias(self):
        self.assertEqual(load_at_end(MOV_IMM_RBX8, MOV_LD_RAX8)[1], 'ptr_alias_write')

    def test_reg_store_is_not_value(self):
        self.assertEqual(load_at_end(MOV_REG_RAX8, MOV_LD_RAX8), ('未決', 'ptr_reg_store', None))

    def test_width_mismatch_is_not_value(self):
        self.assertEqual(load_at_end(MOV_IMM32_RAX8, MOV_LD_RAX8), ('未決', 'ptr_width_mismatch', None))

    def test_call_blocks(self):
        self.assertEqual(load_at_end(MOV_IMM_RAX8, CALL_REL, MOV_LD_RAX8), ('未決', 'ptr_call', None))

    def test_base_redefined_blocks(self):
        self.assertEqual(load_at_end(MOV_IMM_RAX8, MOV_RAX_RAX8, MOV_LD_RAX8)[1], 'ptr_base_def')

    def test_no_store_is_entry(self):
        self.assertEqual(load_at_end(MOV_RCX_RSI, MOV_LD_RAX8), ('未決', 'ptr_entry', None))

    def test_partial_byte_base_redefined_blocks(self):
        self.assertEqual(load_at_end(MOV_CL_5, MOV_LD_RCX8, base='rcx'), ('未決', 'ptr_base_def', None))

    def test_partial_dword_r8_base_redefined_blocks(self):
        self.assertEqual(load_at_end(MOV_R8D_9, MOV_LD_R8_8, base='r8'), ('未決', 'ptr_base_def', None))


if __name__ == '__main__':
    unittest.main()
