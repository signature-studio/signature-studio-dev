#!/usr/bin/env python3
"""hs_resp_src.py — Dispatcher (0x13173a0) の応答スロット [rbp+0x11a0] への格納元を ID ごとに特定する (#2886 / PLG-P0b-25)。

方式: hs_disp_emu.py の unicorn 実行 (HS_DISP_PATH=1 で実行経路を取得) で、ID ごとに
  * 格納元 19 ID: 経路上で最後に実行した [rbp+0x11a0] への格納命令を求め、その格納値 (rax) の
    直前の書込み命令を経路上で逆に辿る (call 戻り値 / [obj]+off / global / フィールド / 即値)。
  * 仮想呼出し出口 27 ID: 経路末端の間接 call の受け手レジスタの書込み元を同様に辿る。
  * 呼出先は実行せず戻り値 0 で代替する (hs_disp_emu.py と同じ制限)。経路上の分岐は callee 戻り値 0 に依存する。
出力は ID ごとの要約 (格納番地・格納命令・辿った供給元)。機械語の解釈は出力を根拠に REPORT で行う。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_resp_src.py [IDs...]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('HS_DISP_PATH', '1')

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

import hs_disp_emu as E

STORE19 = [0x01, 0x07, 0x0e, 0x13, 0x18, 0x1c, 0x1d, 0x26, 0x2e, 0x3d, 0x41, 0x45, 0x46, 0x47, 0x4e, 0x54, 0x56, 0x64, 0x65]
EXIT27 = [0x00, 0x04, 0x09, 0x0a, 0x12, 0x1a, 0x1e, 0x23, 0x2c, 0x2f, 0x3a, 0x3c, 0x44, 0x49, 0x4b, 0x57, 0x59, 0x5b, 0x5c, 0x5d, 0x5e, 0x5f, 0x60, 0x62, 0x67, 0x69, 0x6a]
SLOT_STR = '[rbp + 0x11a0]'
WRITE_MNEM = {'mov', 'movzx', 'movsx', 'movsxd', 'lea', 'xor', 'add', 'sub', 'and', 'or', 'shl', 'shr', 'sar',
              'imul', 'neg', 'not', 'inc', 'dec', 'pop', 'setne', 'sete', 'seta', 'setb', 'setg', 'setl', 'cmove', 'cmovne'}
RAX_NAMES = ('rax', 'eax', 'al', 'ax')

md = Cs(CS_ARCH_X86, CS_MODE_64)
_code = {}


def make_reader(pe, base):
    def read_va(va, n):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                off = rva - s.VirtualAddress
                return s.get_data()[off:off + n]
        return b''
    return read_va


def ins_at(read_va, addr):
    if addr not in _code:
        ins = next(md.disasm(read_va(addr, 16), addr, 1), None)
        _code[addr] = ins
    return _code[addr]


def fmt(ins):
    return '0x%x: %s %s' % (ins.address, ins.mnemonic, ins.op_str)


def source_of(read_va, path, k, names, limit=80):
    """path[k] の直前から逆向きに、レジスタ names のうち最後に書いた命令を探す。call は戻り値 (rax) の供給元。"""
    for j in range(k - 1, max(-1, k - 1 - limit), -1):
        ins = ins_at(read_va, path[j])
        if ins is None:
            continue
        if ins.mnemonic == 'call' and names == RAX_NAMES:
            return fmt(ins), j
        dest = ins.op_str.split(',')[0].strip()
        if ins.mnemonic in WRITE_MNEM and dest in names:
            return fmt(ins), j
    return None, None


def is_slot_store(read_va, addr):
    ins = ins_at(read_va, addr)
    return ins is not None and ins.mnemonic in ('mov', 'or') and ins.op_str.startswith('qword ptr ' + SLOT_STR + ',')


def run_id(ident, pe, base, size, sections, read_va):
    r = E.run_one(ident, pe, base, size, sections)
    path = r['path'] or []
    out = {'id': ident, 'rax': r['rax'], 'stop': r['stop'], 'path_len': len(path), 'leaf': fmt(ins_at(read_va, path[-1])) if path else None}
    stores = [k for k, a in enumerate(path) if is_slot_store(read_va, a)]
    out['store_count'] = len(stores)
    if stores:
        k = stores[-1]
        sins = ins_at(read_va, path[k])
        out['store'] = fmt(sins)
        out['store_va'] = path[k]
        if sins.op_str.endswith(', rax'):
            src, _ = source_of(read_va, path, k, RAX_NAMES)
            out['src'] = src
        else:
            out['src'] = 'imm %s' % sins.op_str.split(',')[-1].strip()
    return out


def main():
    ids = [int(a, 0) for a in sys.argv[1:]] or STORE19 + EXIT27
    pe_data = open(E.PE_PATH, 'rb').read()
    pe, base, size = E.load_image(pe_data)
    sections = [(base + s.VirtualAddress, s.get_data()) for s in pe.sections]
    sections.insert(0, (base, pe_data[:pe.OPTIONAL_HEADER.SizeOfHeaders]))
    read_va = make_reader(pe, base)
    for ident in ids:
        o = run_id(ident, pe, base, size, sections, read_va)
        print('ID=0x%02x rax=0x%x path=%d stop=%s stores=%d' % (ident, o['rax'], o['path_len'], o['stop'], o['store_count']))
        print('   leaf : %s' % o['leaf'])
        if 'store' in o:
            print('   store: %s (va 0x%x)' % (o['store'], o['store_va']))
            print('   src  : %s' % o['src'])


if __name__ == '__main__':
    main()
