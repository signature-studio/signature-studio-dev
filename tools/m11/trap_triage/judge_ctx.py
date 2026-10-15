#!/usr/bin/env python3
"""#3502: strict_evidence.tsv のデータ行 lo..hi (1 始まり, ヘッダ除く) の件ごとの判定文脈をダンプする (判定はしない).

各行について: 機械語 (jcc 前後 8 命令) / IR の帰属ブロック B の本文 / ループ先頭 L の本文 /
脱出先 T の有無と先頭 / T・B への参照元 (B の直前ブロックの終端と末尾 6 行) を出す。
使い方: python3 judge_ctx.py <IR.ll> <evidence.tsv> <PE.bin> <lo> <hi>
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(os.path.dirname(HERE), 'guard699')
LDFIX = os.path.join(os.path.dirname(HERE), 'ldfix')
sys.path.insert(0, GUARD)
sys.path.insert(0, LDFIX)
sys.path.insert(0, HERE)
from ldmach import Machine, FnMach  # noqa: E402
import scan_guard as sg  # noqa: E402
from strict_evidence import fn_text, block_lines  # noqa: E402


def main():
    ir, tsv, pe, lo, hi = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
    text = open(ir, errors='replace').read()
    rows = list(csv.DictReader(open(tsv), delimiter='\t'))
    mach = Machine(pe)
    for i in range(lo, hi + 1):
        r = rows[i - 1]
        name = r['fn']
        body = fn_text(text, name)
        blocks = sg.parse_blocks(body)
        own, _ = sg.owners(blocks)
        lines = block_lines(body)
        va = int(name[len('function_'):], 16)
        fv = FnMach(mach, va, list(own.keys()))
        A = int(r['jcc'], 16)
        idx = next(k for k, x in enumerate(fv.ins) if x.address == A)
        print('=' * 80)
        print('#%d %s jcc=%s %s -> %s  L=%s B=%s' % (i, name, r['jcc'], r['mnemonic'], r['target'], r['loop_head'], r['block']))
        print('-- MACH (jcc 前後)')
        for x in fv.ins[max(0, idx - 8):idx + 4]:
            mark = '>>' if x.address == A else '  '
            print('  %s %x: %s %s' % (mark, x.address, x.mnemonic, x.op_str))
        bname = r['block']
        lname = own.get(int(r['loop_head'], 16), '')
        tname = own.get(int(r['target'], 16), '')
        print('-- IR B=%s term: %s' % (bname, blocks[bname]['term'].strip()))
        for ln in lines.get(bname, [])[:60]:
            print('   B| ' + ln.rstrip()[:220])
        print('-- IR L=%s (ループ先頭)' % lname)
        for ln in lines.get(lname, [])[:60]:
            print('   L| ' + ln.rstrip()[:220])
        print('-- IR T=%s (脱出先) 有無: %s' % (tname, 'あり' if tname in blocks else 'なし'))
        if tname in blocks:
            for ln in lines.get(tname, [])[:12]:
                print('   T| ' + ln.rstrip()[:220])
        refs_T = [n for n in blocks if int(r['target'], 16) in blocks[n]['succ']]
        print('-- IR 脱出先 %s への参照元: %s' % (r['target'], refs_T))
        preds_B = [n for n in blocks if int(bname.split('.')[0], 16) in blocks[n]['succ']]
        print('-- IR B への参照元 (succ に含む): %s' % preds_B[:10])
        for p in preds_B[:4]:
            print('   P=%s term: %s' % (p, blocks[p]['term'].strip()[:200]))
            for ln in lines.get(p, [])[-6:]:
                print('     P| ' + ln.rstrip()[:200])


if __name__ == '__main__':
    main()
