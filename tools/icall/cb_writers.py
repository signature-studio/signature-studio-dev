#!/usr/bin/env python3
# #5843 (ICALL-119): objdump 全量 dsm から、[reg+0xa80] への格納を含む関数を集計する。
# 使い方: python3 tools/icall/cb_writers.py <core64.dsm> [<呼出し先アドレス>]
#   呼出し先を渡すと、その関数の呼出し元 (call / jmp の直接参照) を、呼出し元の関数開始つきで列挙する。
# 関数境界は r13_callee_check.sh と同じ近似 (ret の直後の int3 パディングの次の命令を開始とする)。
# パディング無しで隣の関数が続く場合は一つにまとまるため、関数数は近似の結果である。
import re
import sys

LINE = re.compile(r'^\s*([0-9a-f]+):\t(?:[0-9a-f]{2} ?)+\s+(.*)$')
STORE = re.compile(r'^mov\s+QWORD PTR \[(r[a-z0-9]+)\+0xa80\],')
CALLJMP = re.compile(r'^(?:call|jmp)\s+(?:0x)?([0-9a-f]+)\b')

funcs = []
cur = None
after_ret = False
in_pad = False
with open(sys.argv[1]) as f:
    for raw in f:
        m = LINE.match(raw.rstrip('\n'))
        if not m:
            continue
        addr, text = int(m.group(1), 16), m.group(2).strip()
        is_pad = text.startswith('int3')
        if is_pad and after_ret:
            in_pad = True
            continue
        if cur is None or (in_pad and not is_pad):
            cur = (addr, [])
            funcs.append(cur)
            in_pad = False
        if cur is not None:
            cur[1].append((addr, text))
        after_ret = text.startswith('ret')

writers = {}
for start, body in funcs:
    for addr, text in body:
        if STORE.match(text):
            writers.setdefault(start, []).append(addr)

print('funcs_total', len(funcs))
print('writer_funcs', len(writers))
print('store_sites', sum(len(v) for v in writers.values()))
for s in sorted(writers):
    print('%x stores=%s' % (s, ','.join('%x' % a for a in writers[s])))

if len(sys.argv) > 2:
    target = int(sys.argv[2], 16)
    callers = []
    for start, body in funcs:
        for addr, text in body:
            m = CALLJMP.match(text)
            if m and int(m.group(1), 16) == target:
                callers.append((start, addr, text.split(' ')[0]))
    print('callers_of %x: %d' % (target, len(callers)))
    for start, addr, op in callers:
        print('  %x (func %x) %s' % (addr, start, op))
