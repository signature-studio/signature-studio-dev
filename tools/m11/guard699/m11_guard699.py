#!/usr/bin/env python3
"""#699: 8c5eb0 の件数 0 ループ先頭ガードを IR に復元する修復 pass (冪等・双方向).

機械語 8c5eb0: 8c5f0c で件数 [rcx+0x14] を読み、8c5f15 cmp / 8c5f18 jg 0x8c6066 で件数 <= 0 のとき本体を飛ばす。
RetDec の IR (dec_label_pc_8c5ef5) ではこの分岐が脱落し、無条件に dec_label_pc_8c5f23 へ進む (#662 REPORT_662 §3)。
--mode on : 末尾の無条件 br を `%g699 = <cond>` + `br i1 %g699, dec_label_pc_8c6066, dec_label_pc_8c5f23` に置換する。
--mode off: 逆変換 (脱落状態に戻す。ネガコン用)。
対象ブロックが 1 件でない・想定形でない場合は exit 1 (黙って通さない)。
"""
import argparse
import json
import re
import sys

BLK = 'dec_label_pc_8c5ef5'
EXIT = 'dec_label_pc_8c6066'
NEXT = 'dec_label_pc_8c5f23'
COUNT = '%9 = load i32, ptr %8, align 4'
TAG = '%g699'
DEFAULT_COND = 'icmp sle i32 %9, 0'
PLAIN = '  br label %' + NEXT + '\n'
GUARDED = re.compile(r'  ' + re.escape(TAG) + r' = (icmp [^\n]*)\n  br i1 ' + re.escape(TAG)
                     + r', label %' + EXIT + r', label %' + NEXT + r'\n')


def fail(msg):
    print('[guard699] FAIL: ' + msg, file=sys.stderr)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--mode', choices=['on', 'off'], default='on')
    ap.add_argument('--cond', default=DEFAULT_COND)
    ap.add_argument('--report')
    a = ap.parse_args()

    s = open(a.src).read()
    head = '\n' + BLK + ':'
    if s.count(head) != 1:
        fail('%s の定義が %d 件 (1 件であること)' % (BLK, s.count(head)))
    if 'define i64 @function_8c5eb0(' not in s:
        fail('define i64 @function_8c5eb0 が無い')
    i = s.index(head) + 1
    j = s.index('\n\n', i) + 1
    blk = s[i:j]
    if blk.count(COUNT) != 1:
        fail('件数 load (%s) が 1 件でない' % COUNT)
    if ('label %' + EXIT) not in s:
        fail('飛び先 %s が無い' % EXIT)

    m = GUARDED.search(blk)
    if m and m.end() == len(blk):
        before, body = m.group(1), blk[:m.start()]
    elif blk.endswith(PLAIN):
        before, body = 'none', blk[:-len(PLAIN)]
    else:
        fail('末尾の terminator が想定形でない: %r' % blk[-160:])
    if 'store i64 %10, ptr %rbx.0.reg2mem\n' not in body[-200:]:
        fail('ガード挿入位置 (件数 zext 後の store) が想定形でない')

    if a.mode == 'on':
        new_blk = body + '  %s = %s\n  br i1 %s, label %%%s, label %%%s\n' % (TAG, a.cond, TAG, EXIT, NEXT)
    else:
        new_blk = body + PLAIN
    out = s[:i] + new_blk + s[j:]

    open(a.dst, 'w').write(out)
    report = {
        'fn': 'function_8c5eb0', 'block': BLK, 'mode': a.mode,
        'cond_before': before, 'cond_after': a.cond if a.mode == 'on' else 'none',
        'changed': before != (a.cond if a.mode == 'on' else 'none'),
    }
    if a.report:
        json.dump(report, open(a.report, 'w'), indent=1)
    print('[guard699] mode=%s before=%r after=%r changed=%s' % (
        a.mode, before, report['cond_after'], report['changed']))


if __name__ == '__main__':
    main()
