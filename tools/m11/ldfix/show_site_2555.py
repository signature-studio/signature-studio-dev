#!/usr/bin/env python3
"""show_site_2555.py — #2555: 1 候補 (関数 VA・deref VA・call VA) の機械語窓と IR の対応行を表示する (判定の補助)。

使い方: python3 show_site_2555.py IR.ll --pe PE.bin FN_VA CALL_VA [--before 14]
  機械語: FN 内で CALL_VA の 1 つ前までの --before 命令 (既定 14) と CALL_VA の命令
  IR    : FN の IR 本体で、CALL_VA と同じ呼出し先の k 番目 (機械語での出現順) の call 行と、その引数の定義を深さ 4 まで
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402

DEF_RE = re.compile(r'^\s*(%[\w.]+) = (.*)$')


def body_of(ir, fva):
    text = open(ir, errors='replace').read()
    m = re.search(r'^define [^\n]*@function_%x\(.*?\n}\n' % fva, text, re.M | re.S)
    return m.group(0) if m else None


def def_line(body, name):
    for ln in body.splitlines():
        m = DEF_RE.match(ln)
        if m and m.group(1) == name:
            return ln.strip()
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--pe', required=True)
    ap.add_argument('fn')
    ap.add_argument('call')
    ap.add_argument('--before', type=int, default=14)
    a = ap.parse_args()
    fva, cva = int(a.fn, 16), int(a.call, 16)
    m = Machine(a.pe)
    ins = m.disasm_fn(fva)
    idx = [i for i, x in enumerate(ins) if x.address == cva][0]
    print('## 機械語 (fn 0x%x, call 0x%x)' % (fva, cva))
    for x in ins[max(0, idx - a.before):idx + 1]:
        print('  0x%x  %s %s' % (x.address, x.mnemonic, x.op_str))
    tgt = ins[idx].op_str
    k = len([x for x in ins[:idx + 1] if x.mnemonic == 'call' and x.op_str == tgt])
    body = body_of(a.ir, fva)
    calls = [ln for ln in body.splitlines() if re.search(r'@function_%s\(' % tgt[2:], ln) and ' call ' in ln]
    print('## IR: 呼出し先 %s の機械語での %d 番目 (IR の呼出しは %d 件)' % (tgt, k, len(calls)))
    if k - 1 < len(calls):
        line = calls[k - 1].strip()
        print('  ' + line)
        names = re.findall(r'%[\w.]+', line.split('(', 1)[1])
        seen = set()
        todo = [(n, 0) for n in names]
        while todo:
            n, d = todo.pop(0)
            if n in seen or n.startswith('%arg') or d > 4:
                continue
            seen.add(n)
            dl = def_line(body, n)
            if dl:
                print('    ' * (d + 1) + dl[:200])
                todo += [(x, d + 1) for x in re.findall(r'%[\w.]+', dl.split('=', 1)[1])]
    else:
        print('  (IR に対応する呼出し無し)')


if __name__ == '__main__':
    main()
