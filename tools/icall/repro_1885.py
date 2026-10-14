#!/usr/bin/env python3
"""REPORT_APPENDIX_1885 の再現: OTT F 0x1801a31fb の jump table 入口 jcc の誤結線を確認する。

usage: python3 tools/icall/repro_1885.py <rt_ott-F ディレクトリ>
  dsm (機械語の正) と before.0.drc.ll (RetDec の before IR) を突合する。
  対象 (0x1801a30e8) と対照 (0x1801ac5ba, 正しく結線された switch 畳み込み側) を同じ規則で判定する。
"""
import re
import sys
from pathlib import Path

d = Path(sys.argv[1])
ll = (d / 'before.0.drc.ll').read_text(errors='replace')
dsm = (d / 'before.0.drc.dsm').read_text(errors='replace').split('\n')

FN = 'function_1801a30d0'
TARGET_JCC = 0x1801a30e8
CONTROL_JCC = 0x1801ac5ba
DISPATCH = 0x1801a31e0
JMP_R9_VA = 0x1801a31fb

meta = {m.group(1): int(m.group(2)) for m in re.finditer(r'^!(\d+) = !\{i64 (\d+)\}', ll, re.M)}


def dsm_target(va):
    for l in dsm:
        m = re.match(r'^(0x[0-9a-f]+):\s+[0-9a-f ]+\tj[a-z]+ (0x[0-9a-f]+)', l)
        if m and int(m.group(1), 16) == va:
            return int(m.group(2), 16)
    return None


def ir_true_target(va):
    for l in ll.split('\n'):
        m = re.search(r'br i1 %\S+, label %dec_label_pc_([0-9a-f]+), label %dec_label_pc_([0-9a-f]+), !insn\.addr !(\d+)', l)
        if m and meta.get(m.group(3)) == va:
            return int(m.group(1), 16)
    return None


for name, va in (('対象', TARGET_JCC), ('ネガティブコントロール', CONTROL_JCC)):
    dj = dsm_target(va)
    it = ir_true_target(va)
    print('[%s] jcc 0x%x: dsm 飛び先 %s / IR true 側 %s / IR true == dsm 飛び先: %s' % (
        name, va,
        ('0x%x' % dj) if dj is not None else 'なし',
        ('dec_label_pc_%x' % it) if it is not None else 'なし',
        (it is not None and it == dj)))

s = ll.index('define i64 @%s' % FN)
e = ll.index('\n}\n', s)
body = ll[s:e]
print('dispatch label dec_label_pc_%x in IR: %s' % (DISPATCH, ('dec_label_pc_%x:' % DISPATCH) in ll))
print('switch in %s: %d' % (FN, body.count('switch ')))
addr_in = sum(1 for l in body.split('\n') if 'insn.addr' in l)
print('insn.addr-bearing lines in %s: %d' % (FN, addr_in))
print('dsm jmp r9 at 0x%x present: %s' % (JMP_R9_VA, any(('0x%x:' % JMP_R9_VA) in l for l in dsm)))
