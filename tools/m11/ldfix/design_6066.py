#!/usr/bin/env python3
"""design_6066.py — #6066 (LD-296): rep-not-dominated の 6 組 (#3195 §2) について、修復方式の設計材料を測る。
各置換対象の使用 (IR 行) について: その行を支配する deref ブロックがあるか / 使用の直後の経路 (直接の後続) か /
使用ブロックから最初の deref の IR ブロックまでの間にある記憶書込み (store・call) の数 を出す。
判定は本体 ldfix.py と同じ Machine (PE 直読)。
使い方 (tools/m11 で実行): python3 ldfix/design_6066.py <block00031_PE.bin>"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ldfix  # noqa: E402
from ldfix import Machine, ir_dominators, ir_succ  # noqa: E402
from ldmach import FnMach  # noqa: E402

PAIRS = [0x101d180, 0x10626e0, 0x12f9730, 0x41a670, 0x786d50, 0x787380]
WRITE = re.compile(r'\bstore\b|\bcall\b')


def main():
    pe = sys.argv[1]
    text = open('work/boot_final3.ll', errors='replace').read()
    for x in ldfix.DEF_RE.finditer(text):
        ldfix.F3C_ARITY[int(x.group('name')[9:], 16)] = len([p for p in x.group('args').split(',') if p.strip()])
    mach = Machine(pe)
    for m in ldfix.DEF_RE.finditer(text):
        va = int(m.group('name')[9:], 16)
        if va not in PAIRS:
            continue
        end = text.index('\n}', m.end()) + 2
        body = text[m.start():end]
        fn = ldfix.Fn('function_%x' % va, va, body)
        lines = body.split('\n')
        blocks = fn.blocks()
        names = [b for b, _ in blocks]
        starts, off = [], 0
        for _b, ls in blocks:
            starts.append(off)
            off += len(ls)
        succ = ir_succ([ls for _b, ls in blocks])
        dom = ir_dominators(succ)
        blk_vas = [bva for (bva, _l) in fn.blocks() if bva is not None]
        if hasattr(mach, 'cover'):
            mach.cover(va, max(blk_vas))
        fv = FnMach(mach, va, blk_vas)
        _lsf, _ptr, uses, blk0 = ldfix.f3c_track(fv)
        lead = ldfix._f3c_leaders(fv.ins)

        def blk_of_line(k):
            return max(j for j in range(len(blocks)) if starts[j] <= k)

        for n in sorted({u[2] for u in uses if u[0] == 'deref' and u[4] == 'arg'}):
            ds = [u for u in uses if u[0] == 'deref' and u[2] == n and u[4] == 'arg']
            first = min(u[1] for u in ds)
            if first in blk0:
                continue
            raws = [u for u in uses if u[0] == 'raw' and u[2] == n]
            if any(u[3] != 64 for u in ds) or sum(1 for u in raws if u[1] > first):
                continue
            pat = re.compile(r'(?<![\w.$-])%arg' + str(n) + r'(?![\w.$-])')
            idx = [k for k in range(1, len(lines)) if pat.search(lines[k])]
            rep_idx = idx[len(raws):]
            if not rep_idx:
                continue
            bstart = max([x for x in lead if x <= first], default=None)
            bj = [j for j in range(len(blocks)) if names[j] == bstart]
            if not bj:
                continue
            bj = bj[0]
            dblk = {}
            for u in ds:
                bs = max([x for x in lead if x <= u[1]], default=None)
                for j in range(len(blocks)):
                    if names[j] == bs:
                        dblk.setdefault(j, []).append(u[1])
            print('%x arg%d deref_blk=%s (B=blk%d)' % (va, n, sorted('%x' % names[j] for j in dblk), bj))
            for k in rep_idx:
                bk = blk_of_line(k)
                covered = any(j in dom[bk] for j in dblk)
                direct = bk in succ and bj in succ[bk]
                writes = sum(1 for l in lines[k + 1:starts[bk] + len(blocks[bk][1])] if WRITE.search(l))
                mids = [x for x in range(len(blocks)) if x in dom[bj] and bk in dom[x] and x != bj]
                wmid = sum(1 for x in set(mids) for l in blocks[x][1] if WRITE.search(l))
                print('  line %d blk %x covered_by_deref=%s direct_pred_of_B=%s writes_after_use_in_blk=%d writes_between_use_and_B=%d' % (
                    k, names[bk], covered, direct, writes, wmid))


if __name__ == '__main__':
    main()
