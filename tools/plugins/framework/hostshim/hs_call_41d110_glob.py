#!/usr/bin/env python3
"""hs_call_41d110_glob.py — 0x41d110 が読むグローバル 2 つ (フラグ 0x15ec2d8・戻り値の源 0x15ec2d0) と添字 0x13a9388 の所属セクションと、.text 内の参照 (読み/書き) を出す (#5421 / PLG-P0b-58)。

出す事実 (機械語・VA):
  1. 各 VA が入る PE セクション名と範囲
  2. .text 0x401000..0x13a44b0 でメモリオペランドが対象 VA を含む箇所 (rip 相対と絶対 disp32 の両方)。
     読み/書きは capstone の operand access (WRITE/READ) で判定する (mov 以外の add・or・setcc・xchg 等も含む)
  3. 0x41d110 が使う添字 0x13a9388 について同じ箇所

限界: レジスタ経由の間接アクセス・実行時の初期化 (ローダ・TLS 割当) は含まない。
使い方: FL_WIN64_DIR=<展開先の親> PYTHONPATH=<unicorn,pefile,capstone,tools/shared の site-packages> python3 hs_call_41d110_glob.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hs_resp_src as S
import hs_disp_emu as E
import hs_store_111c as W
from capstone import CS_AC_READ, CS_AC_WRITE, CS_OP_MEM
from capstone.x86 import X86_REG_RIP, X86_REG_INVALID

TARGETS = {
    'flag byte': 0x15ec2d8,
    'ret source qword': 0x15ec2d0,
    'index dword': 0x13a9388,
}
TEXT_LO, TEXT_HI = 0x401000, 0x13a44b0


def main():
    pe, base, _ = E.load_image(open(E.PE_PATH, 'rb').read())
    rd = S.make_reader(pe, base)
    S.md.detail = True

    for name, va in TARGETS.items():
        rva = va - base
        sec = None
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                sec = s.Name.rstrip(b'\0').decode(errors='replace')
        print('== %s @ 0x%x: セクション %s' % (name, va, sec))

    refs = {name: [] for name in TARGETS}
    cur = TEXT_LO
    while cur < TEXT_HI:
        try:
            chunk = rd(cur, min(W.CHUNK, TEXT_HI - cur))
        except Exception:
            cur += W.CHUNK
            continue
        limit = cur + W.CHUNK - 16
        nxt = None
        for i in S.md.disasm(chunk, cur):
            if i.address >= limit:
                break
            nxt = i.address + i.size
            for o in i.operands:
                if o.type != CS_OP_MEM:
                    continue
                m = o.mem
                if m.base == X86_REG_RIP:
                    ea = i.address + i.size + m.disp
                elif m.base == X86_REG_INVALID and m.index == X86_REG_INVALID:
                    ea = m.disp
                else:
                    continue
                for name, t in TARGETS.items():
                    if ea <= t < ea + o.size:
                        acc = ('W' if o.access & CS_AC_WRITE else '') + ('R' if o.access & CS_AC_READ else '')
                        refs[name].append((acc, i.address, i.mnemonic, i.op_str))
        cur = nxt if nxt is not None and nxt > cur else cur + 1
    for name, va in TARGETS.items():
        print('== %s 0x%x: 参照 %d 件' % (name, va, len(refs[name])))
        for acc, addr, mn, ops in refs[name]:
            print('  %s 0x%x %s %s' % (acc, addr, mn, ops))


if __name__ == '__main__':
    main()
