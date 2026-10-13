#!/usr/bin/env python3
"""ir414_fix.py IN.ll OUT.ll [--none] : function_414ad0 の IR 本体を機械語どおりに置換する (#683, liftdiff 用の IR 版)。

m11_ov.c の C 版 function_414ad0 と同じ分岐・同じ 1 段 deref 復元 (`mov rax,[rbx]`) を LLVM IR で書いたもの。
liftdiff は C 上書きを取り込まないため、68 関数の batch (#307 §9) ではこの IR 版を使う。
--none: 置換せず複写のみ (ネガコン = 基準 IR と同じ)。置換対象の define が 1 個以外なら exit 1。
"""
import sys

NAME = 'function_414ad0'
BODY = r'''define weak i64 @function_414ad0(i64 %arg1, i64 %arg2) local_unnamed_addr {
dec_label_pc_414ad0:
  %arg2z = and i64 %arg2, 4294967295
  %esi = trunc i64 %arg2 to i32
  %le0 = icmp sle i32 %esi, 0
  %slot = alloca i64, align 8
  br i1 %le0, label %dec_clr, label %dec_pos

dec_clr:
  %r_clr = call i64 @function_412d60(i64 %arg1, i64 %arg2)
  ret i64 %r_clr

dec_pos:
  %argp = inttoptr i64 %arg1 to ptr
  %pv = load i64, ptr %argp, align 8
  %pnull = icmp eq i64 %pv, 0
  br i1 %pnull, label %dec_alloc, label %dec_chkrc

dec_chkrc:
  %a8 = add i64 %pv, -8
  %p8 = inttoptr i64 %a8 to ptr
  %rc = load i32, ptr %p8, align 4
  %isuniq = icmp eq i32 %rc, 1
  br i1 %isuniq, label %dec_uniq, label %dec_alloc

dec_uniq:
  %a4 = add i64 %pv, -4
  %p4 = inttoptr i64 %a4 to ptr
  %len = load i32, ptr %p4, align 4
  %same = icmp eq i32 %len, %esi
  br i1 %same, label %dec_retp, label %dec_realloc

dec_retp:
  ret i64 %pv

dec_realloc:
  %blk = add i64 %pv, -16
  store i64 %blk, ptr %slot, align 8
  %r13 = sext i32 %esi to i64
  %r13x2 = mul i64 %r13, 2
  %sz = add i64 %r13x2, 18
  %r_re = call i64 @function_409470(ptr nonnull %slot, i64 %sz)
  %np = load i64, ptr %slot, align 8
  %lenp = add i64 %np, 12
  %lenptr = inttoptr i64 %lenp to ptr
  store i32 %esi, ptr %lenptr, align 4
  %nd = add i64 %np, 16
  store i64 %nd, ptr %argp, align 8
  %s1 = call i64 @function_414850(i64 %nd)
  %tp = add i64 %s1, %r13x2
  %tptr = inttoptr i64 %tp to ptr
  store i16 0, ptr %tptr, align 2
  ret i64 %s1

dec_alloc:
  %rdi = call i64 @function_412c20(i64 %arg2z)
  br i1 %pnull, label %dec_fresh, label %dec_copy

dec_fresh:
  store i64 %rdi, ptr %argp, align 8
  ret i64 0

dec_copy:
  %cA4 = add i64 %pv, -4
  %cP4 = inttoptr i64 %cA4 to ptr
  %oldlen = load i32, ptr %cP4, align 4
  %gt = icmp sgt i32 %oldlen, %esi
  %m = select i1 %gt, i32 %esi, i32 %oldlen
  %src = call i64 @function_414850(i64 %pv)
  %m2 = mul i32 %m, 2
  %m2x = sext i32 %m2 to i64
  %r_mv = call i64 @function_409c80(i64 %src, i64 %rdi, i64 %m2x)
  %ret = call i64 @function_412d60(i64 %arg1, i64 %rdi)
  store i64 %rdi, ptr %argp, align 8
  ret i64 %ret
}
'''


def main():
    args = [a for a in sys.argv[1:] if a != '--none']
    none = '--none' in sys.argv[1:]
    if len(args) != 2:
        sys.exit(__doc__)
    lines = open(args[0]).read().split('\n')
    hit = [i for i, l in enumerate(lines) if l.startswith('define ') and ('@%s(' % NAME) in l]
    if len(hit) != 1:
        sys.exit('define @%s が %d 個 (1 個であること)' % (NAME, len(hit)))
    end = next(j for j in range(hit[0], len(lines)) if lines[j].startswith('}'))
    if none:
        out = lines
    else:
        out = lines[:hit[0]] + BODY.rstrip('\n').split('\n') + lines[end + 1:]
    open(args[1], 'w').write('\n'.join(out))
    print('replaced=%s lines_before=%d lines_after=%d' % ('no' if none else 'yes', end - hit[0] + 1, len(BODY.rstrip('\n').split('\n'))))


if __name__ == '__main__':
    main()
