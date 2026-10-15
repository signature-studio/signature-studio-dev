#!/usr/bin/env python3
"""m11_setother_mem_class.load_def の負例・正例 (#3906 / M11-N196)。実行: python3 test_setother_mem_class.py"""
import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capstone
import m11_setother_mem_class as M

CS = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
CS.detail = True

MOV_IMM = '48c7454801000000'    # mov qword ptr [rbp + 0x48], 1
MOVQ_ST = '660fd64548'          # movq qword ptr [rbp + 0x48], xmm0
POP_MEM = '8f4548'              # pop qword ptr [rbp + 0x48]
REP_STOSQ = 'f348ab'            # rep stosq qword ptr [rdi], rax
MOV_IDX = '48c744c54801000000'  # mov qword ptr [rbp + rax*8 + 0x48], 1
MOV_LD = '488b4d48'             # mov rcx, qword ptr [rbp + 0x48]


def seq(*hexes):
    out, addr = [], 0x1000
    for h in hexes:
        ins = list(CS.disasm(bytes.fromhex(h), addr))
        assert len(ins) == 1, h
        out.append(ins[0])
        addr += ins[0].size
    return out


def load_at_end(*hexes):
    ins = seq(*hexes)
    return M.load_def(CS, ins, len(ins) - 1, 'rbp', 0x48, set())


class LoadDefTest(unittest.TestCase):
    def test_imm_store_is_value(self):
        self.assertEqual(load_at_end(MOV_IMM, MOV_LD), ('実値化', 'slot_imm', 1, '0x1000'))

    def test_xmm_store_between_is_unknown(self):
        self.assertEqual(load_at_end(MOV_IMM, MOVQ_ST, MOV_LD)[:2], ('未決', 'slot_unknown_write'))

    def test_pop_store_between_is_unknown(self):
        self.assertEqual(load_at_end(MOV_IMM, POP_MEM, MOV_LD)[:2], ('未決', 'slot_unknown_write'))

    def test_rep_stosq_between_is_unknown(self):
        self.assertEqual(load_at_end(MOV_IMM, REP_STOSQ, MOV_LD)[:2], ('未決', 'slot_unknown_write'))

    def test_indexed_imm_store_is_not_direct(self):
        self.assertEqual(load_at_end(MOV_IDX, MOV_LD)[:2], ('未決', 'slot_index_write'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
