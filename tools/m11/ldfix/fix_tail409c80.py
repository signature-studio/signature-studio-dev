#!/usr/bin/env python3
"""fix_tail409c80.py — #5358 (FLE-44): function_409c80 の 0x409d2d `jae 0x409c40` を tail call に直す。

機械語 409d2d: `cmp rax,[rip+...]; jae 0x409c40`。0x409c40 は jmp 先で、戻り値はそのまま 409c80 の戻り値になる (tail jump)。
lift 段 (boot0.lift.ll) は call + fall-through (`%101 = call i64 @function_409c40()` → `store` → 後続命令) にし、
引数を渡さなかった。m11_post の sigfix はこの引数不足を 0 詰め (`(0,0,0)`) で埋め、戻った後に機械語に無い後続処理を実行していた
(trap 位置 `function_409c80` wasm 0xbf736 の OOB の直接原因の経路。tools/m11/REPORT.md)。

この経路では rcx・rdx・r8 は 409c80 の入口値のまま (409c80 → 409d03 → 409d2d の間に書込み無し) なので、
引数は (%arg1, %arg2, %arg3) に等しい。分岐の条件 (%99) は機械語の jae と一致しており変えない。

想定と違う入力は assert で止める (fail-closed)。使い方: python3 fix_tail409c80.py IN.ll OUT.ll
"""
import re
import sys

FN = re.compile(r'^define [^\n]*@function_409c80\(.*?\n}\n', re.M | re.S)
DEF = re.compile(r'^define [^\n]*@function_409c80\(([^)]*)\)', re.M)
OLD = ('  %101 = call i64 @function_409c40()\n'
       '  store i64 %101, ptr %rax.1.reg2mem\n'
       '  br label %dec_label_pc_409d3a\n')
NEW = ('  %101 = call i64 @function_409c40(i64 %arg1, i64 %arg2, i64 %arg3)\n'
       '  ret i64 %101\n')


def patch(fn):
    d = DEF.match(fn)
    assert d, 'function_409c80 の define 行が読めない'
    assert d.group(1).replace(' ', '') == 'i64%arg1,i64%arg2,i64%arg3', '仮引数の署名が想定と違う: %r' % d.group(1)
    assert fn.count(OLD) == 1, 'tail jump の行が 1 件でない: %d' % fn.count(OLD)
    assert 'tail409c80' not in fn, '適用済み (二重適用)'
    return fn.replace(OLD, NEW)


def main():
    src = open(sys.argv[1], errors='replace').read()
    fns = list(FN.finditer(src))
    assert len(fns) == 1, 'function_409c80 の定義が 1 件でない: %d' % len(fns)
    f = fns[0].group(0)
    out = src[:fns[0].start()] + patch(f) + src[fns[0].end():]
    assert out != src
    open(sys.argv[2], 'w').write(out)
    print('[fix_tail409c80] function_409c80: 0x409d2d jae の tail jump を引数付き tail call に置換')


if __name__ == '__main__':
    main()
