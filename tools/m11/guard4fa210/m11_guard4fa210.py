#!/usr/bin/env python3
"""#2773: 4fa210 (件数の線形探索) の件数 0 ガードを IR に復元する修復 pass (冪等・双方向). D19 と同型 (DEFECTS.md D19).

機械語 4fa210: 4fa232 で件数 [rcx+0x10] を読み、4fa23c cmp / 4fa23f jg 0x4fa28e で件数 0 のとき本体を飛ばして戻り値 0 を返す。
RetDec の IR (dec_label_pc_4fa210) ではこの分岐が脱落し、無条件に dec_label_pc_4fa248 (本体) へ進む。件数 0 で本体が 1 回走ると、
範囲外の 47a250 (例外 raise。lift では戻ってくる) を呼び、件数 0 → 0xFFFFFFFF の減算で約 2^32 回の周回に入る (REPORT_679 §10)。
--mode on : 入口ブロックの末尾の無条件 br を次の形に置換する (件数 == 0 なら戻り値 0)。
              %g4fa = icmp eq i32 %9, 0
              br i1 %g4fa, label %dec_label_pc_4fa210_g4fa, label %dec_label_pc_4fa248
            dec_label_pc_4fa210_g4fa:
              ret i64 0
--mode off: 逆変換 (脱落状態に戻す。ネガコン用)。
想定形でない場合は exit 1 (黙って通さない)。
"""
import argparse
import json
import sys

BLK = 'dec_label_pc_4fa210'
GD = BLK + '_g4fa'
NEXT = 'dec_label_pc_4fa248'
COUNT = '  %9 = load i32, ptr %8, align 4\n'
STORE = '  store i64 %10, ptr %r14.0.reg2mem\n'
PLAIN = '  br label %' + NEXT + '\n'
GUARD = ('  %g4fa = icmp eq i32 %9, 0\n'
         '  br i1 %g4fa, label %' + GD + ', label %' + NEXT + '\n'
         + GD + ':\n'
         '  ret i64 0\n')


def fail(msg):
    print('[guard4fa210] FAIL: ' + msg, file=sys.stderr)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--mode', choices=['on', 'off'], default='on')
    ap.add_argument('--report')
    a = ap.parse_args()

    s = open(a.src).read()
    head = '\n' + BLK + ':\n'
    if s.count(head) != 1:
        fail('%s の定義が %d 件 (1 件であること)' % (BLK, s.count(head)))
    if s.count('\ndefine i64 @function_4fa210(') != 1:
        fail('define i64 @function_4fa210 が 1 件でない')
    i = s.index(head) + 1
    j = s.index('\n\n', i) + 1
    blk = s[i:j]
    if blk.count(COUNT) != 1:
        fail('件数 load が 1 件でない')

    if GUARD in blk:
        before = 'guarded'
    elif blk.endswith(STORE + PLAIN):
        before = 'none'
    else:
        fail('入口ブロックの末尾が想定形でない: %r' % blk[-160:])

    if a.mode == 'on':
        new_blk = blk if before == 'guarded' else blk[:-len(PLAIN)] + GUARD
    else:
        new_blk = blk if before == 'none' else blk.replace(GUARD, PLAIN)
    after = 'guarded' if a.mode == 'on' else 'none'

    open(a.dst, 'w').write(s[:i] + new_blk + s[j:])
    report = {'fn': 'function_4fa210', 'block': BLK, 'guard_block': GD, 'mode': a.mode,
              'cond_before': before, 'cond_after': after, 'changed': before != after}
    if a.report:
        json.dump(report, open(a.report, 'w'), indent=1)
    print('[guard4fa210] mode=%s before=%s after=%s changed=%s' % (a.mode, before, after, report['changed']))


if __name__ == '__main__':
    main()
