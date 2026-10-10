#!/usr/bin/env python3
"""hs_dbg_trace.py — CAB-195 デバッグ用: 全 lifted define の入口に fw_dbg_enter(va) を挿入.

plugin 連鎖 (CreatePlugInstance → ctor) で trap / OOB した際に「どこまで到達したか」を
決めるための call trace。fw_dbg_enter は 0x6bdde0 (CreatePlugInstance) を観測したら
記録を開始する (Phase A の framework smoke とは無関係に, Phase B の連鎖だけを追う)。

注意 (clang の .ll パーサ):
  * 整数リテラルは **10 進** で書く必要がある (clang は `i32 0x40fff3` を
    "floating point constant invalid for type" で拒否する)。
  * RetDec IR は関数先頭に `dec_label_pc_XXXX:` (basic block label) を置くため、
    trace call は先頭 label 群の **後** に挿入する (途中に label を置くと壊れる)。

使い方: python3 hs_dbg_trace.py hs_flat3.ll hs_dbgflat.ll
"""
import re
import sys

SRC, DST = sys.argv[1], sys.argv[2]
LABEL = re.compile(r'^[A-Za-z0-9_.$-]+:$')
DEF = re.compile(r'^define .*@function_([0-9a-f]+)\(')
DECL = 'declare void @fw_dbg_enter(i32) local_unnamed_addr\n'

out = []
pending = None
n = 0
with open(SRC, errors='replace') as f:
    for l in f:
        if pending is not None:
            out.append(l)
            if LABEL.match(l.rstrip('\n')) or not l.strip():
                continue          # 先頭 label / 空行はまだ pending 維持
            out.append('  call void @fw_dbg_enter(i32 %d)\n' % pending)
            n += 1
            pending = None
            continue
        m = DEF.match(l)
        if m and l.rstrip().endswith('{'):
            pending = int(m.group(1), 16)
        out.append(l)

text = ''.join(out)
if DECL not in text:
    idx = text.index('\ndefine ')
    text = text[:idx + 1] + DECL + '\n' + text[idx + 1:]
open(DST, 'w').write(text)
print('[hs_dbg] %d define に入力 trace を挿入 -> %s' % (n, DST))
