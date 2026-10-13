#!/usr/bin/env python3
"""disasm_735.py — REPORT_735.md §1.1 の機械語 (41a670 / 41a69c〜41a6a3) を PE から逆アセンブルする。

使い方: python3 disasm_735.py [PE パス]
  既定 PE = $FL_WIN64_DIR/extracted/block00031_PE.bin (fl-win64 素材。未指定時は $RUNNER_TEMP/fl-win64 を見る)
依存: capstone, pefile (ldmach.py が import する)。
VA = RVA + ImageBase (0x400000)。.pdata の関数区間 (ldmach.Machine.fns) を使う。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402

FN = 0x41a670
LO, HI = 0x41a69c, 0x41a6a4

pe = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.environ.get('FL_WIN64_DIR') or os.path.join(os.environ.get('RUNNER_TEMP', '/tmp'), 'fl-win64'),
    'extracted', 'block00031_PE.bin')
m = Machine(pe)
ins = m.disasm_fn(FN)
if not ins:
    sys.exit('function %#x not found in .pdata of %s' % (FN, pe))
print('function %#x size=%#x (pdata)' % (FN, m.fns[FN][1]))
for i in ins:
    if LO <= i.address <= HI:
        print('%x  %-6s %s' % (i.address, i.mnemonic, i.op_str))
