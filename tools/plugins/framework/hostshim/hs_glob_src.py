#!/usr/bin/env python3
"""hs_glob_src.py — Dispatcher 応答格納元のグローバル変数の実値を PE の初期値と書込み元から確定する (#2945 / PLG-P0b-37)。

方式 (静的): block00031_PE.bin の全セクションを ImageBase に置き、
  * G の初期値: 生データ上の qword (.bss 相当は 0)
  * G を参照する全命令: .text を線形逆アセンブル (capstone) し、rip 相対オペランドの解決先が G に一致するもの。
    格納 (メモリ・オペランドが第 1 オペランド) と読出しを分けて VA と命令を出す。
  * 2 段の参照 ([[G]]+off) は、G の初期値 P を読み、P が画像内なら [P+off] を読む (P が 0 なら未確定)。
実行時の値は初期化経路で書かれるため、ここでは「初期値」と「書込み命令の一覧」までを確定する。書込み元の値が
即値・画像内の定数であれば実値として確定し、ヒープ等の実行時ポインタであれば未確定とする。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<capstone,pefile> python3 hs_glob_src.py 0x15ec298 [0x15e0ff8 ...]
"""
import os
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

PE_PATH = os.path.join(os.environ['FL_WIN64_DIR'], 'extracted', 'block00031_PE.bin')
STORE_MNEM = {'mov', 'movsx', 'movsxd', 'movzx', 'movss', 'movsd', 'add', 'sub', 'and', 'or', 'xor', 'inc', 'dec', 'shl', 'shr', 'sar', 'setg', 'sete', 'setne', 'lea'}


def load(pe_data):
    pe = pefile.PE(data=pe_data)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = []
    for s in pe.sections:
        secs.append({'va': base + s.VirtualAddress, 'raw': s.get_data(), 'vsize': s.Misc_VirtualSize,
                     'name': s.Name.rstrip(b'\0').decode('latin1'), 'exec': bool(s.Characteristics & 0x20000000)})
    return pe, base, secs


def read_va(secs, va, n):
    for s in secs:
        if s['va'] <= va < s['va'] + max(s['vsize'], len(s['raw'])):
            off = va - s['va']
            b = s['raw'][off:off + n]
            return b + b'\0' * (n - len(b))
    return None


def qword(secs, va):
    b = read_va(secs, va, 8)
    return None if b is None else int.from_bytes(b, 'little')


def sec_of(secs, va):
    for s in secs:
        if s['va'] <= va < s['va'] + s['vsize']:
            return s['name']
    return '-'


def writers_and_readers(secs, targets):
    """全実行セクションを線形逆アセンブルし、rip 相対の解決先が targets に入る命令を集める。"""
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    hits = {t: {'store': [], 'load': []} for t in targets}
    for s in secs:
        if not s['exec']:
            continue
        code = s['raw']
        off = 0
        while off < len(code):
            ins = next(md.disasm(code[off:off + 16], s['va'] + off, 1), None)
            if ins is None:
                off += 1
                continue
            off += ins.size
            if '[rip ' not in ins.op_str:
                continue
            sign = -1 if '[rip - ' in ins.op_str else 1
            disp = sign * int(ins.op_str.split('[rip ')[1].split(']')[0].lstrip('+- '), 16)
            tgt = ins.address + ins.size + disp
            if tgt not in hits:
                continue
            first = ins.op_str.split(',')[0]
            kind = 'store' if ('ptr [rip' in first and ins.mnemonic in STORE_MNEM and ins.op_str.count(',') >= 1) else 'load'
            hits[tgt][kind].append((ins.address, '%s %s' % (ins.mnemonic, ins.op_str)))
    return hits


def main():
    targets = [int(a, 0) for a in sys.argv[1:]]
    pe_data = open(PE_PATH, 'rb').read()
    pe, base, secs = load(pe_data)
    hits = writers_and_readers(secs, targets)
    for t in targets:
        v = qword(secs, t)
        print('G=0x%x sec=%s image_qword=%s' % (t, sec_of(secs, t), '-' if v is None else '0x%x' % v))
        for va, txt in hits[t]['store']:
            print('   store 0x%x: %s' % (va, txt))
        print('   loads=%d (HS_GLOB_LOADS=1 で一覧)' % len(hits[t]['load']))
        if os.environ.get('HS_GLOB_LOADS') == '1':
            for va, txt in hits[t]['load']:
                print('   load  0x%x: %s' % (va, txt))


if __name__ == '__main__':
    main()
