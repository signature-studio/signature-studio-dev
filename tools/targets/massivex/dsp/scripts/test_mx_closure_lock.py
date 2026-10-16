#!/usr/bin/env python3
"""mx_closure.py の先頭ブロック判定の SDM 規則テスト (MX-50 / #4068 受入 1・2)。

insn_sdm_ok を capstone の出力 (mn, ops) に対して直接呼ぶ。capstone の受理に依存させないため、
規則の入力は disasm_lite が返した命令だけにする (空を返す形は規則の検査にならないので使わない)。
規則を壊すと落ちる (LOCK 規則・REX 後 F0・REX 後 F3・HLE 形)。
実行: python3 scripts/test_mx_closure_lock.py
"""
import os, sys, unittest
import capstone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mx_closure as mc

MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)


def first(hexs):
    raw = bytes.fromhex(hexs.replace(' ', ''))
    ea, iz, mn, ops = next(MD.disasm_lite(raw, 0))
    return raw[:iz], mn, ops


def rule(hexs):
    raw, mn, ops = first(hexs)
    return mc.insn_sdm_ok(raw, mn, ops)


class LockRule(unittest.TestCase):
    def test_lock_on_memory_ok(self):
        self.assertTrue(rule('f0 01 07'))         # lock add [rdi], eax
        self.assertTrue(rule('f0 0f b1 0f'))      # lock cmpxchg [rdi], ecx
        self.assertTrue(rule('f0 ff 00'))         # lock inc [rax]

    def test_lock_on_register_dest_rejected(self):
        self.assertFalse(mc.insn_sdm_ok(bytes.fromhex('f0 01 c8'), 'lock add', 'eax, ecx'))

    def test_lock_on_non_lockable_rejected(self):
        self.assertFalse(mc.insn_sdm_ok(bytes.fromhex('f0 0f 1f 00'), 'lock nop', 'dword ptr [rax]'))
        self.assertFalse(mc.insn_sdm_ok(bytes.fromhex('f0 90'), 'lock nop', ''))

    def test_lock_with_rep_rejected(self):
        self.assertFalse(mc.insn_sdm_ok(bytes.fromhex('f0 f3 01 07'), 'add', 'dword ptr [rdi], eax'))
        self.assertFalse(mc.insn_sdm_ok(bytes.fromhex('f0 f2 01 07'), 'add', 'dword ptr [rdi], eax'))
        self.assertFalse(mc.insn_sdm_ok(bytes.fromhex('f0 f2 f3 01 07'), 'xacquire lock add', 'dword ptr [rdi], eax'))


class RexRule(unittest.TestCase):
    def test_rex_then_f0_not_rejected(self):
        self.assertTrue(mc.insn_sdm_ok(bytes.fromhex('45 f0 01 07'), 'lock add', 'dword ptr [rdi], eax'))   # SDM 2.2.1: REX が無視されるだけ
        self.assertFalse(mc.insn_sdm_ok(bytes.fromhex('45 f0 03 00'), 'lock add', 'eax, dword ptr [rax]'))   # 宛先がレジスタ: LOCK 規則で不可

    def test_rex_then_f3_not_rejected(self):
        self.assertTrue(rule('40 f3 0f 7f 00'))   # REX の後の F3: REX が無視されるだけで #UD ではない


class HleRule(unittest.TestCase):
    def test_xrelease_lock_ok(self):
        self.assertTrue(rule('f3 f0 0f b1 0f'))   # xrelease lock cmpxchg [rdi], ecx

    def test_xacquire_lock_ok(self):
        self.assertTrue(rule('f2 f0 01 07'))      # xacquire lock add [rdi], eax


if __name__ == '__main__':
    unittest.main()
