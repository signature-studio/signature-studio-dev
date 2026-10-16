#!/usr/bin/env python3
"""LD-240 (#4801): SNAPSHOT 直後のスタック区間 (SP・stack_base・stack_end) と、RESET の差分を実測する probe。

  python3 ld240_hi_probe.py > work/ld240/probe.json

wasm ランナだけを起動し (native は使わない)、SNAPSHOT 関数の内側で記録した SP (snap_sp) を STK 行で読む。
hi 区間 [snap_sp, stack_base) の長さ・全区間の RESET 差分 (mask 1 / 256 / 512 / 128 / 7) を出す。
RESET は 1 回ごとに SNAPSHOT 時点へ戻すため、各 mask は別プロセスで測る。
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldlib.session import Session
from ldlib.runners import Runner, ROOT

TARGET = os.path.join(HERE, 'targets', 'm11.json')
MASKS = [1, 256, 512, 128, 7]


def run_mask(sess, mask):
    lines = sess.init_lines('wasm')
    was = Runner('wasm', ['node', '--stack-size=4000', os.path.join(ROOT, sess.runner_js), sess.wasm_js,
                          sess.t.get('image') or '-', '%x' % sess.origin, '%x' % sess.delta,
                          '--init=' + ','.join(sess.t.get('init_exports', [])),
                          '--timeout-ms=%d' % sess.wasm_timeout_ms], lines, timeout=60.0)
    try:
        was._send('STK')
        stk = json.loads(was._recv(30.0))
        was._send('RESET %d' % mask)
        ack = json.loads(was._recv(30.0))
        return stk, ack['diff']
    finally:
        was.close()


def idem(sess):
    """同じ区間を続けて戻したとき、2 回目の差分が 0 になること (戻しの冪等性)。"""
    was = Runner('wasm', ['node', '--stack-size=4000', os.path.join(ROOT, sess.runner_js), sess.wasm_js,
                          sess.t.get('image') or '-', '%x' % sess.origin, '%x' % sess.delta,
                          '--init=' + ','.join(sess.t.get('init_exports', [])),
                          '--timeout-ms=%d' % sess.wasm_timeout_ms], sess.init_lines('wasm'), timeout=60.0)
    try:
        out = []
        for m in [6, 6, 2, 2, 4, 4]:
            was._send('RESET %d' % m)
            out.append(json.loads(was._recv(30.0))['diff'])
        return out
    finally:
        was.close()


def main():
    sess = Session(TARGET, shards=1, build=False, trace=True, timeout=10.0)
    res = {}
    stk0 = None
    for m in MASKS:
        stk, diff = run_mask(sess, m)
        stk0 = stk0 or stk
        res[str(m)] = diff
    sp, top, base, end = stk0['snap_sp'], stk0['top'], stk0['base'], stk0['end']
    out = {'snap_sp': hex(sp), 'top_after_snapshot': hex(top), 'stack_base': hex(base), 'stack_end': hex(end),
           'stack_bytes': base - end, 'hi_bytes': base - sp, 'deep_bytes': sp - end,
           'reset_diff': res, 'idem_diff_6_6_2_2_4_4': idem(sess)}
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
