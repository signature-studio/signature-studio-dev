#!/usr/bin/env python3
"""pedis.py 部分: FLEngine_x64.dll の指定 VA 範囲を capstone で逆アセンブル (RIP 相対の文字列/データ注釈付き)"""
import sys, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

DLL = '/home/ubuntu/work/webstudio/tools/startup/work/FLEngine_x64.dll'
pe = pefile.PE(DLL, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True

def read_va(va, n):
    return pe.get_data(va - BASE, n)

def annot(op_str, insn):
    # RIP 相対 → 実効アドレス
    out = op_str
    for op in insn.operands:
        if op.type == pefile.__dict__.get('x', 0):  # noop
            pass
    return out

def main():
    va = int(sys.argv[1], 16)
    n = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x80
    code = read_va(va, n)
    for insn in md.disasm(code, va):
        line = f"{insn.address:08x}  {insn.bytes.hex():<24} {insn.mnemonic} {insn.op_str}"
        # RIP 相対注釈
        if 'rip' in insn.op_str:
            import re
            m = re.search(r'\[rip ([+-]) (0x[0-9a-f]+)\]', insn.op_str)
            if m:
                d = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
                tgt = insn.address + insn.size + d
                line += f"   ; -> {tgt:08x}"
                try:
                    d8 = pe.get_data(tgt - BASE, 32)
                    # UTF-16LE 文字列として読めるか
                    s = ''
                    ok = True
                    for i in range(0, 20, 2):
                        w = d8[i] | d8[i+1] << 8
                        if w == 0: break
                        if 32 <= w < 0x3000: s += chr(w)
                        else: ok = False; break
                    if ok and s: line += f' L"{s}"'
                    else: line += f' b={d8[:8].hex()}'
                except Exception:
                    pass
        print(line)

if __name__ == '__main__':
    main()
