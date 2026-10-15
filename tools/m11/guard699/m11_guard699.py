#!/usr/bin/env python3
"""#699: 8c5eb0 の件数 0 ループ先頭ガードを IR に復元する修復 pass (冪等・双方向).

機械語 8c5eb0: 8c5f0c で件数 [rcx+0x14] を読み、8c5f15 cmp / 8c5f18 jg 0x8c6066 で件数 <= 0 のとき本体を飛ばす。
RetDec の IR (dec_label_pc_8c5ef5) ではこの分岐が脱落し、無条件に dec_label_pc_8c5f23 へ進む (#662 REPORT_662 §3)。
--mode on : 末尾の無条件 br を次の形に置換する (REPORT_699 §1 が正本)。
              %g699 = <cond>                        ; 既定 icmp sle i32 %9, 0 (件数 <= 0)
              br i1 %g699, label %dec_label_pc_8c5ef5_g699, label %dec_label_pc_8c5f23
            dec_label_pc_8c5ef5_g699:               ; ガード辺専用ブロック。8c6066 へ合流させない
              arg2 下位 byte != 0 → _t:
                arg3 != 0 → call 8ca670(arg3, [rbp+0x80]) (機械語 8c6071〜8c607f。戻り値は捨てる)
                → call 410360([rbp+0x80]) し、その戻り値を ret (機械語 8c608d〜8c60a0 の mov [rbp+0x80],rax; jmp 8c60df)
                  (#3077: 旧版は llvm.trap で fail-fast。boot が件数 0 の init 54 でこの経路に入り、停止していた)
              arg2 下位 byte == 0 → _e:
                arg3 == 0 → ret [rbp+0x80]          (機械語 8c6067 je 8c6084 → 8c608b je 8c60df → mov rax,[rbp+0x80])
                arg3 != 0 → call 8ca670(arg3, [rbp+0x80]) してから ret [rbp+0x80] (機械語 8c6071〜8c607f)
            件数 > 0 の経路 (dec_label_pc_8c5f23 への枝) は元 IR と一致する (store は通らない)。
--mode off: 逆変換 (脱落状態に戻す。ネガコン用)。
対象ブロックが 1 件でない・想定形でない場合は exit 1 (黙って通さない)。
"""
import argparse
import json
import re
import sys

BLK = 'dec_label_pc_8c5ef5'
GD = BLK + '_g699'
NEXT = 'dec_label_pc_8c5f23'
COUNT = '%9 = load i32, ptr %8, align 4'
TAG = '%g699'
DEFAULT_COND = 'icmp sle i32 %9, 0'
PLAIN = '  br label %' + NEXT + '\n'
GD_BLOCK = (GD + ':\n'
            '  %g699a = and i64 %arg2, 255\n'
            '  %g699b = icmp ne i64 %g699a, 0\n'
            '  br i1 %g699b, label %' + GD + '_t, label %' + GD + '_e\n'
            + GD + '_t:\n'
            '  %g699t = icmp eq i64 %arg3, 0\n'
            '  br i1 %g699t, label %' + GD + '_t2, label %' + GD + '_t1\n'
            + GD + '_t1:\n'
            '  %g699u = call i64 @function_8ca670(i64 %arg3, i64 %stack_var_8.0.reload)\n'
            '  br label %' + GD + '_t2\n'
            + GD + '_t2:\n'
            '  %g699v = call i64 @function_410360(i64 %stack_var_8.0.reload)\n'
            '  ret i64 %g699v\n'
            + GD + '_e:\n'
            '  %g699c = icmp eq i64 %arg3, 0\n'
            '  br i1 %g699c, label %' + GD + '_r, label %' + GD + '_c\n'
            + GD + '_c:\n'
            '  %g699d = call i64 @function_8ca670(i64 %arg3, i64 %stack_var_8.0.reload)\n'
            '  br label %' + GD + '_r\n'
            + GD + '_r:\n'
            '  ret i64 %stack_var_8.0.reload\n')
GUARDED = re.compile(r'  ' + re.escape(TAG) + r' = (icmp [^\n]*)\n  br i1 ' + re.escape(TAG)
                     + r', label %' + GD + r', label %' + NEXT + r'\n' + re.escape(GD_BLOCK))


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
    if 'define i64 @function_8ca670(' not in s and 'declare i64 @function_8ca670(' not in s:
        fail('function_8ca670 の宣言が無い')
    if 'define weak i64 @function_410360(' not in s and 'define i64 @function_410360(' not in s and 'declare i64 @function_410360(' not in s:
        fail('function_410360 の宣言が無い')

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
        new_blk = body + '  %s = %s\n  br i1 %s, label %%%s, label %%%s\n' % (TAG, a.cond, TAG, GD, NEXT) + GD_BLOCK
    else:
        new_blk = body + PLAIN
    out = s[:i] + new_blk + s[j:]

    open(a.dst, 'w').write(out)
    report = {
        'fn': 'function_8c5eb0', 'block': BLK, 'guard_block': GD, 'mode': a.mode,
        'cond_before': before, 'cond_after': a.cond if a.mode == 'on' else 'none',
        'changed': before != (a.cond if a.mode == 'on' else 'none'),
    }
    if a.report:
        json.dump(report, open(a.report, 'w'), indent=1)
    print('[guard699] mode=%s before=%r after=%r changed=%s' % (
        a.mode, before, report['cond_after'], report['changed']))


if __name__ == '__main__':
    main()
