"""#5032 (LD-253): 8 byte の 2 要素 struct (%tagPOINT) を 1 レジスタで受ける import (WindowFromPoint) の
引数比較。wasm 側の arg1 (y) は native では rcx (= a[0]) の上位 32bit に当たる。比較器は a[1] (rdx) を見ないこと。
規則を壊すと失敗で非 0 終了する。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from ldlib import irtool, compare  # noqa: E402

IR = """%tagPOINT = type { i32, i32 }
declare ptr @WindowFromPoint(%tagPOINT) local_unnamed_addr
declare i32 @ScrollThing(ptr, %tagRECT) local_unnamed_addr
"""


class _Ctx:
    """ctx.eq の比較規則を素直に写す (rebase なし・幅で切り詰める)。"""

    def eq(self, vn, vw, width=64):
        m = (1 << width) - 1
        return (vn & m) == (vw & m)

    def n2w(self, v):
        return v


def _call(native_args, wasm_args):
    n = {'calls': [{'n': 'WindowFromPoint', 'a': native_args}], 'status': 'ok'}
    w = {'calls': [{'n': 'WindowFromPoint', 'a': wasm_args}], 'status': 'ok'}
    return n, w


def main():
    with tempfile.NamedTemporaryFile('w', suffix='.ll', delete=False) as f:
        f.write(IR)
        path = f.name
    try:
        irtool.gen_stubs(path, set())
        slots = irtool.gen_stubs.slots['WindowFromPoint']
        assert slots == [(0, 0), (0, 32)], slots

        # pattern s と同じ: rcx=0x3 (x=3, y=0)・rdx=0x5 (native の旧比較が誤って見ていた値)。wasm は (3, 0)。
        stub = {'WindowFromPoint': {'widths': [32, 32], 'slots': slots}}
        n, w = _call(['0x3', '0x5', '0x0', '0x0'], ['0x3', '0x0', '0x0', '0x0'])
        assert compare.cmp_calls(n, w, _Ctx(), stub) is None, compare.cmp_calls(n, w, _Ctx(), stub)

        # y が本当に違えば検出する (rcx の上位 32bit = 0x7 のとき wasm 0x0 とは不一致)。
        n, w = _call(['0x700000003', '0x0', '0x0', '0x0'], ['0x3', '0x0', '0x0', '0x0'])
        d = compare.cmp_calls(n, w, _Ctx(), stub)
        assert d and d['kind'] == 'call_arg' and d['arg'] == 1, d

        # 旧 stubs.json (slots 無し) は従来どおり a[k] を見る: a[1]=0x5 と wasm 0x0 は不一致になる。
        n, w = _call(['0x3', '0x5', '0x0', '0x0'], ['0x3', '0x0', '0x0', '0x0'])
        old = {'WindowFromPoint': {'widths': [32, 32]}}
        d = compare.cmp_calls(n, w, _Ctx(), old)
        assert d and d['arg'] == 1, d
    finally:
        os.unlink(path)
    print('test_ld253_point_arg_slot: OK')


if __name__ == '__main__':
    main()
