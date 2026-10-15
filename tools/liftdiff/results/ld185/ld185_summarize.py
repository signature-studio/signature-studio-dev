#!/usr/bin/env python3
"""LD-185: ld185_trace.mjs の出力 (trace.json) から、命令 VA 位置の要約を作る。
使い方: python3 ld185_summarize.py <trace.json>
分岐の判定: je 1801c0b6f は直後の VA が 1801c0ba8 なら成立 (taken)、1801c0b71 なら不成立 (not taken)。
call 1801c0b82 は直後の VA が呼出し先 (HeapFree の stub) ではなく戻り先 1801c0b87 になる前提で数えるだけ。"""
import json
import sys

IMG_BASE = 0x180000000
SHIFT = 0x150000000


def to_img(s):
    return int(s, 16) + SHIFT


def main():
    t = json.load(open(sys.argv[1]))
    JE, JE_TAKEN, JE_NOT = 0x1801c0b6f, 0x1801c0ba8, 0x1801c0b71
    CALL = 0x1801c0b82
    for c in t['cases']:
        vas = [to_img(v) for v in c['vas']]
        print('pattern=%s count=%d ret=%s' % (c['pattern'], c['count'], c['ret']))
        for i, va in enumerate(vas):
            if va == JE:
                nxt = vas[i + 1] if i + 1 < len(vas) else None
                res = 'taken' if nxt == JE_TAKEN else ('not-taken' if nxt == JE_NOT else 'unknown')
                print('  je@%08x idx=%d next=%08x -> %s' % (va, i, nxt or 0, res))
            if va == CALL:
                print('  call@%08x idx=%d' % (va, i))


if __name__ == '__main__':
    main()
