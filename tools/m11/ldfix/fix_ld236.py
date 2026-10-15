#!/usr/bin/env python3
"""fix_ld236.py — #4675 (LD-236): function_1046a30 の上流 X の 1 段不足を機械語に合わせて直す。

機械語 (m11_image.bin・capstone 実測。cell = LVA 18752024 = VA 0x15e2218):
  10474a6 mov rax,[rip+0x59ad6b]   ; C = [cell]
  10474ad mov rax,[rax]            ; S = [C]
  10474b6 cmp ecx,[rax+0x10]       ; 比較は [S+16]
  10474bf mov rax,[rip+...]        ; (同じ cell) C = [cell]
  10474c6 mov rax,[rax]            ; S = [C]
  10474c9 mov rax,[rax+8]          ; [S+8]
  10474d4 mov rax,[rax+rcx*8]      ; [[S+8]+idx*8]
→ 基底は S = [C] (cell を 2 段 deref した値)。

現行 IR (m2r 後) は `%351 = load i32 [cell]` (= C の下位 32 bit) を基底にする。
C を基底にするため [C] の 1 段 deref が無く、%353 ([C+16]) と %357 ([C+8]) が機械語の [S+16]・[S+8] とずれている。
本 pass は `%351` の 1 行を次の 2 段に置き換える (%352 以降は変えない):
  %fx236c = load i64 [cell]              ; C
  %fx236p = inttoptr i64 %fx236c to ptr
  %fx236s = load i64 [%fx236p]           ; S = [C] (機械語 10474ad)
  %351 = trunc i64 %fx236s to i32        ; 後続の sext/add は既存のまま

想定と違う入力は assert で止める (fail-closed)。使い方: python3 fix_ld236.py IN.ll OUT.ll
"""
import re
import sys

FN = re.compile(r'^define [^\n]*@function_1046a30\(.*?\n}\n', re.M | re.S)
CELL_LOAD = '  %351 = load i32, ptr inttoptr (i64 18752024 to ptr), align 4\n'
CELL_NEW = ('  %fx236c = load i64, ptr inttoptr (i64 18752024 to ptr), align 8\n'
            '  %fx236p = inttoptr i64 %fx236c to ptr\n'
            '  %fx236s = load i64, ptr %fx236p, align 8\n'
            '  %351 = trunc i64 %fx236s to i32\n')
USE_352 = '  %352 = sext i32 %351 to i64\n'
MARK = 'fx236'


def patch(fn):
    head = fn.split('\n', 1)[0]
    assert '@function_1046a30(' in head, 'function_1046a30 の define 行が読めない: %r' % head
    assert MARK not in fn, '適用済み (二重適用)'
    assert fn.count(CELL_LOAD) == 1, 'cell 読みの行が 1 件でない: %d' % fn.count(CELL_LOAD)
    assert fn.count(USE_352) == 1, '%352 の定義が 1 件でない: %d' % fn.count(USE_352)
    return fn.replace(CELL_LOAD, CELL_NEW)


def main():
    src = open(sys.argv[1], errors='replace').read()
    fns = list(FN.finditer(src))
    assert len(fns) == 1, 'function_1046a30 の定義が 1 件でない: %d' % len(fns)
    f = fns[0].group(0)
    out = src[:fns[0].start()] + patch(f) + src[fns[0].end():]
    assert out != src
    open(sys.argv[2], 'w').write(out)
    print('[fix_ld236] function_1046a30: 上流 X の cell 読みを cell→C→[C] の 2 段に置換 (機械語 10474a6〜10474ad)')


if __name__ == '__main__':
    main()
