#!/usr/bin/env python3
"""hs_call_41d110_glob.py — 0x41d110 が読むグローバル 2 つ (フラグ 0x15ec2d8・戻り値の源 0x15ec2d0) と添字 0x13a9388 の所属セクションと、.text 内の直接書込み (rip 相対 mov) を出す (#5421 / PLG-P0b-58)。

出す事実 (機械語・VA):
  1. 各 VA が入る PE セクション名と範囲
  2. .text 0x1000000..0x1400000 で rip 相対 `mov [rip+X], reg/imm` の宛先がその VA に一致する箇所
  3. 0x41d110 が使う添字 0x13a9388 について同じ書込み箇所

限界: 間接書込み・実行時の初期化 (ローダ・TLS 割当) は含まない。
使い方: FL_WIN64_DIR=<展開先の親> PYTHONPATH=<unicorn,pefile,capstone,tools/shared の site-packages> python3 hs_call_41d110_glob.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hs_resp_src as S
import hs_disp_emu as E
import hs_store_111c as W

TARGETS = {
    'flag byte': 0x15ec2d8,
    'ret source qword': 0x15ec2d0,
    'index dword': 0x13a9388,
}
TEXT_LO, TEXT_HI = 0x401000, 0x13a44b0


def main():
    pe, base, _ = E.load_image(open(E.PE_PATH, 'rb').read())
    rd = S.make_reader(pe, base)

    for name, va in TARGETS.items():
        rva = va - base
        sec = None
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                sec = s.Name.rstrip(b'\0').decode(errors='replace')
        print('== %s @ 0x%x: セクション %s' % (name, va, sec))

    allins = W.scan(rd, TEXT_LO, TEXT_HI)
    refs = {name: [] for name in TARGETS}
    for i in allins:
        if 'rip +' not in i.op_str:
            continue
        try:
            disp = int(i.op_str.split('rip + ')[1].split(']')[0], 16)
        except (IndexError, ValueError):
            continue
        va = i.address + i.size + disp
        for name, t in TARGETS.items():
            if va == t:
                w = i.mnemonic == 'mov' and i.op_str.split(',')[0].strip().endswith(']')
                refs[name].append(('W' if w else 'R', i))
    for name, va in TARGETS.items():
        print('== %s 0x%x: rip 相対の参照 %d 件' % (name, va, len(refs[name])))
        for kind, i in refs[name]:
            print('  %s 0x%x %s %s' % (kind, i.address, i.mnemonic, i.op_str))


if __name__ == '__main__':
    main()
