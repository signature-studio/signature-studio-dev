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


class FakeMach:
    """fns (VA -> (rva, size)) と disasm_fn (VA -> ins) だけを持つ最小の Machine 代用。"""
    def __init__(self, fns=None):
        self.cs = CS
        self.fns = fns or {}
        self.bodies = {}

    def disasm_fn(self, va):
        return self.bodies.get(va)


def load_at_end(*hexes, base='rax', mach=None):
    ins = seq(*hexes)
    return M.load_def(mach or FakeMach(), ins, len(ins) - 1, base, 8, 64, set(), {})


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
        # 揮発基底 (rax) は call で値が変わるので ptr_base_def。非揮発基底の未知の先は ptr_call
        self.assertEqual(load_at_end(MOV_IMM_RAX8, CALL_REL, MOV_LD_RAX8)[1], 'ptr_base_def')
        self.assertEqual(load_at_end(MOV_IMM_RBX8, CALL_REL, MOV_LD_RBX8, base='rbx')[1], 'ptr_call')

    def test_base_redefined_blocks(self):
        self.assertEqual(load_at_end(MOV_IMM_RAX8, MOV_RAX_RAX8, MOV_LD_RAX8)[1], 'ptr_base_def')

    def test_call_to_pure_callee_passes_nonvolatile_base(self):
        # 呼出し先は rsp 基底の格納と ret だけ (非スタック書込みなし) → rbx 基底の区間を跨いで実値化
        mach = FakeMach()
        callee_va = 0x2000
        mach.fns[callee_va] = (0, 0x10)
        mach.bodies[callee_va] = list(CS.disasm(bytes.fromhex('48c7442408' + '01000000' + 'c3'), callee_va))
        ins = list(CS.disasm(bytes.fromhex(MOV_IMM_RBX8) + bytes.fromhex('e8' + (callee_va - 0x1008 - 5).to_bytes(4, 'little', signed=True).hex()) + bytes.fromhex(MOV_LD_RBX8), 0x1000))
        self.assertEqual([i.mnemonic for i in ins], ['mov', 'call', 'mov'])
        self.assertEqual(M.load_def(mach, ins, 2, 'rbx', 8, 64, set(), {}), ('実値化', 'ptr_imm', 1))

    def test_call_to_writing_callee_blocks(self):
        # 呼出し先が非スタック (rbp 基底) へ書く → 未決 (ptr_call)
        mach = FakeMach()
        mach.fns[0x2000] = (0, 0x10)
        mach.bodies[0x2000] = list(CS.disasm(bytes.fromhex('48c7450801000000' + 'c3'), 0x2000))
        ins = list(CS.disasm(bytes.fromhex(MOV_IMM_RBX8) + bytes.fromhex('e8' + (0x2000 - 0x1008 - 5).to_bytes(4, 'little', signed=True).hex()) + bytes.fromhex(MOV_LD_RBX8), 0x1000))
        self.assertEqual(M.load_def(mach, ins, 2, 'rbx', 8, 64, set(), {})[:2], ('未決', 'ptr_call'))

    def test_no_store_is_entry(self):
        self.assertEqual(load_at_end(MOV_RCX_RSI, MOV_LD_RAX8), ('未決', 'ptr_entry', None))

    def test_partial_byte_base_redefined_blocks(self):
        self.assertEqual(load_at_end(MOV_CL_5, MOV_LD_RCX8, base='rcx'), ('未決', 'ptr_base_def', None))

    def test_partial_dword_r8_base_redefined_blocks(self):
        self.assertEqual(load_at_end(MOV_R8D_9, MOV_LD_R8_8, base='r8'), ('未決', 'ptr_base_def', None))


if __name__ == '__main__':
    unittest.main()
