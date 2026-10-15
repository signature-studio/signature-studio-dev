#!/usr/bin/env python3
"""#3564: strict 候補の件ごと判定に使う材料を出す (判定はしない).

使い方:
  python3 judge_src.py <IR.ll> <fn> <VA>... [--mx N]
      fn の IR ブロックのうち VA (16 進, 接尾辞付きを含む) に一致するものを全部出す。
      各ブロックの本文 (先頭 N 行) と、参照する絶対アドレス (inttoptr の定数) を出す。
  python3 judge_src.py <IR.ll> <fn> --pe <PE.bin> --jcc <hex> [--n N]
      jcc の前 N 命令 (機械語) を出す。RIP 相対の参照は IR 上の絶対アドレスに直す
      (次命令アドレス + disp − 0x400000。REPORT_718 §4i で 19649808 の一致を確認)。
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'guard699'))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'ldfix'))
from strict_evidence import fn_text, block_lines  # noqa: E402
import scan_guard as sg  # noqa: E402

IMAGE_BASE = 0x400000


def show_blocks(text, fn, vas, mx):
    body = fn_text(text, fn)
    if body is None:
        sys.exit('function not found: %s' % fn)
    lines = block_lines(body)
    for va in vas:
        keys = [k for k in lines if k == va or k.startswith(va + '.')]
        if not keys:
            print('## %s: not found' % va)
        for key in keys:
            print('## %s' % key)
            glob = []
            for ln in lines[key]:
                glob += re.findall(r'inttoptr \(i64 (\d+) to ptr\)', ln)
            print('   globals: %s' % sorted(set(int(g) for g in glob)))
            for ln in lines[key][:mx]:
                print('   ' + ln.rstrip()[:200])


def show_mach(text, fn, pe, jcc, n):
    from ldmach import Machine, FnMach  # noqa: E402
    body = fn_text(text, fn)
    blocks = sg.parse_blocks(body)
    own, _ = sg.owners(blocks)
    va = int(fn[len('function_'):], 16)
    fv = FnMach(Machine(pe), va, list(own.keys()))
    A = int(jcc, 16)
    idx = next(i for i, x in enumerate(fv.ins) if x.address == A)
    for x in fv.ins[max(0, idx - n):idx + 1]:
        mark = '>>' if x.address == A else '  '
        tgt = ''
        m = re.search(r'\[rip \+ 0x([0-9a-f]+)\]', x.op_str)
        if m:
            ir = x.address + x.size + int(m.group(1), 16) - IMAGE_BASE
            tgt = '   [rip -> IR %d (0x%x)]' % (ir, ir)
        print('%s %x: %s %s%s' % (mark, x.address, x.mnemonic, x.op_str, tgt))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('fn')
    ap.add_argument('vas', nargs='*')
    ap.add_argument('--mx', type=int, default=40)
    ap.add_argument('--pe')
    ap.add_argument('--jcc')
    ap.add_argument('--n', type=int, default=12)
    a = ap.parse_args()
    text = open(a.ir, errors='replace').read()
    if a.pe and a.jcc:
        show_mach(text, a.fn, a.pe, a.jcc, a.n)
    else:
        show_blocks(text, a.fn, a.vas, a.mx)


if __name__ == '__main__':
    main()
