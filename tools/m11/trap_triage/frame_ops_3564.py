#!/usr/bin/env python3
"""#3564: 関数内の機械語のうち、オペランドが正規表現に一致する命令を出す (判定はしない).

使い方:
  python3 frame_ops_3564.py <IR.ll> <fn> <PE.bin> <regex>
      例: "rbp \\+ 0xac\\]" (書込み・読出しの列挙)、"rbp \\+ 0x" (lea を含む rbp 相対の全命令)。
      REPORT_APPENDIX_3564 §8.1 の [rbp+0xac] の書込み箇所と、別名 (lea) の確認に使う。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'guard699'))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'ldfix'))
from strict_evidence import fn_text  # noqa: E402
import scan_guard as sg  # noqa: E402
from ldmach import Machine, FnMach  # noqa: E402


def main():
    ir, fn, pe, pat = sys.argv[1:5]
    text = open(ir, errors='replace').read()
    body = fn_text(text, fn)
    if body is None:
        sys.exit('function not found: %s' % fn)
    own, _ = sg.owners(sg.parse_blocks(body))
    va = int(fn[len('function_'):], 16)
    fv = FnMach(Machine(pe), va, list(own.keys()))
    for x in fv.ins:
        if re.search(pat, x.op_str):
            print('%x: %s %s' % (x.address, x.mnemonic, x.op_str))


if __name__ == '__main__':
    main()
