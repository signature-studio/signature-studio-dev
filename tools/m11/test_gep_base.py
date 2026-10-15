#!/usr/bin/env python3
"""m11_setother_gep_global.gep_base / mov_imm_class の負例・正例 (#4905 / M11-N228). 実行: python3 test_gep_base.py"""
import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capstone
import m11_argrecover as AR
import m11_setother_gep_global as G

CS = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
CS.detail = True

MOV_RCX_IMM = '48c7c101000000'   # mov rcx, 1
MOV_ECX_IMM = 'b901000000'       # mov ecx, 1
MOV_R8D_IMM = '41b801000000'     # mov r8d, 1
MOV_CL_IMM = 'b101'              # mov cl, 1
MOV_CX_IMM = '66b90100'          # mov cx, 1
MOV_AL_IMM = 'b001'              # mov al, 1
MOV_RCX_5 = '48c7c105000000'     # mov rcx, 5
MOV_RCX_LD = '488b4d48'          # mov rcx, qword ptr [rbp + 0x48]
MOV_RCX_PTR = '488b08'           # mov rcx, qword ptr [rax]
CALL_REL0 = 'e800000000'         # call +0
JE_NEXT = '7400'                 # je +0 (次の命令へ分岐する)
LEA_RCX = '488d5108'             # lea rdx, [rcx + 8]
LEA_R8 = '498d5008'              # lea rdx, [r8 + 8]
LEA_RAX = '488d5008'             # lea rdx, [rax + 8]


class FakeMach:
    def __init__(self, ins):
        self.cs = CS
        self._ins = ins

    def disasm_fn(self, va):
        return self._ins


def classify(*hexes):
    """hexes の末尾を lea [base+d] として、base の到達定義を gep_base で分類する。"""
    ins, addr = [], 0x1000
    for h in hexes:
        got = list(CS.disasm(bytes.fromhex(h), addr))
        assert len(got) == 1, h
        ins.append(got[0])
        addr += got[0].size
    cf = AR.Fn(FakeMach(ins), 0x1000)
    return G.gep_base(cf, {'def': hex(ins[-1].address), 'caller': 'fn_1000'})


class MovImmClassTest(unittest.TestCase):
    def test_64bit_is_value(self):
        self.assertEqual(G.mov_imm_class('rcx'), ('実値化', 'base_const'))

    def test_32bit_is_value(self):
        self.assertEqual(G.mov_imm_class('ecx'), ('実値化', 'base_const'))
        self.assertEqual(G.mov_imm_class('r8d'), ('実値化', 'base_const'))

    def test_8bit_and_16bit_are_partial(self):
        for dst in ('al', 'cl', 'ax', 'cx'):
            self.assertEqual(G.mov_imm_class(dst), ('未決', 'base_partial'), dst)


class GepBaseTest(unittest.TestCase):
    def test_mov_rcx_imm_is_value(self):
        self.assertEqual(classify(MOV_RCX_IMM, LEA_RCX), ('実値化', 'base_const'))

    def test_mov_ecx_imm_is_value(self):
        self.assertEqual(classify(MOV_ECX_IMM, LEA_RCX), ('実値化', 'base_const'))

    def test_mov_r8d_imm_is_value(self):
        self.assertEqual(classify(MOV_R8D_IMM, LEA_R8), ('実値化', 'base_const'))

    def test_mov_cl_imm_is_partial(self):
        self.assertEqual(classify(MOV_CL_IMM, LEA_RCX), ('未決', 'base_partial'))

    def test_mov_cx_imm_is_partial(self):
        self.assertEqual(classify(MOV_CX_IMM, LEA_RCX), ('未決', 'base_partial'))

    def test_mov_al_imm_base_rax_is_partial(self):
        # 基底 rax を al へ書く: 8bit 書込は上位を保持するので実値化しない
        self.assertEqual(classify(MOV_AL_IMM, LEA_RAX), ('未決', 'base_partial'))

    def test_partial_write_after_full_def_does_not_reach_old_value(self):
        # mov rcx, 5 → mov cl, 1 → lea [rcx+8]: cl の書込で rcx は上位保持の部分書込。旧値 5 を実値化しない
        self.assertEqual(classify(MOV_RCX_5, MOV_CL_IMM, LEA_RCX), ('未決', 'base_partial'))

    def test_call_return_is_unrecoverable(self):
        self.assertEqual(classify(CALL_REL0, LEA_RCX), ('復元不能', 'base_call_ret'))

    def test_merge_is_unknown(self):
        self.assertEqual(classify(MOV_ECX_IMM, JE_NEXT, LEA_RCX), ('未決', 'base_merge'))

    def test_stack_slot_is_unknown(self):
        self.assertEqual(classify(MOV_RCX_LD, LEA_RCX), ('未決', 'base_stack_slot'))

    def test_ptr_load_is_unknown(self):
        self.assertEqual(classify(MOV_RCX_PTR, LEA_RCX), ('未決', 'base_ptr_load'))

    def test_no_def_is_entry(self):
        self.assertEqual(classify(LEA_RCX), ('未決', 'base_entry'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
