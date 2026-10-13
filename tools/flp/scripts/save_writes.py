#!/usr/bin/env python3
"""SaveRestoreState の Save 分岐から Stream->Write(buf,len) 列を抽出する (逆アセンブル出力のテキストを読む簡易版)。
usage: save_writes.py <dis.txt>  (plugin_slot3.py の出力)。 lea rdx,[...]/mov r8d,imm/call [rax+0x20] の並びを拾う。"""
import re, sys
rows = []
for ln in open(sys.argv[1]):
    m = re.match(r'([0-9a-f]+):\s+(\S+)\s*(.*)', ln)
    if m: rows.append((int(m.group(1), 16), m.group(2), m.group(3).strip()))
rdx = r8 = None
for a, mn, op in rows:
    if mn == 'lea' and op.startswith('rdx,'): rdx = op[4:].strip()
    if mn == 'mov' and op.startswith('r8d,'): r8 = op[4:].strip()
    if mn == 'call' and op == 'qword ptr [rax + 0x20]':
        print('%x  Write(%s, %s)' % (a, rdx, r8))
    if mn == 'call' and op == 'qword ptr [rax + 0x18]':
        print('%x  Read (%s, %s)' % (a, rdx, r8))
