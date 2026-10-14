#!/usr/bin/env python3
"""LD-62 (#1767) 受入条件 2: 0x417b70 の除算を sdiv (符号付き) に直した wasm で、同じ 8 入力を再実行する。

native (実機相当) の結果と、udiv 版 wasm (work/m11) / sdiv 版 wasm (work/m11_sdiv) を並べ、
native との食い違い (status / rax / mem / calls) を入力ごとに出す。

  FL_WIN64_DIR=<fl-win64 展開先> python3 tools/liftdiff/tests/trace_417b70_sdiv_rerun.py > tools/liftdiff/results/m11_417b70_sdiv_rerun.md

前提: 素材 work-m11 (tools/m11/work/boot_final3.ll) と work-liftdiff (work/m11 の udiv 版) を展開済み。
sdiv 版の IR と target JSON は tools/m11/m11_sdiv_variant.py が作る (work/ 以外に手順を持たせるため、
この harness が最初に呼ぶ)。sdiv 版 wasm は harness 内で build する。
"""
import contextlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(ROOT, '..', '..'))
sys.path.insert(0, ROOT)
from ldlib import build_wasm  # noqa: E402
from ldlib.session import Session  # noqa: E402
from ldlib.runners import Runner  # noqa: E402
from ldlib import compare  # noqa: E402

FN = 0x417b70
TRAP = 0x409730
M64 = (1 << 64) - 1
GRID = [(16, 1), (-16, 1), (16, 2), (-16, 2), (-16, 3), (16, 1 << 60), (-16, 1 << 60), (2147483647, 3)]


def le(v, n):
    return (v & ((1 << (8 * n)) - 1)).to_bytes(n, 'little').hex()


def case_lines(s, st, cnt):
    patch = ';'.join(['a:0x102:%s' % le(st, 4), 'a:0x106:q=a:0x400', 'a:0x200:%s' % le(cnt, 8)])
    return 'id=%x:st%d_c%d fn=%x blob=- args=i:a:0x300,i:a:0x100,i:0x0,i:a:0x200 trace=1 xfill=0 ' \
           'sig=i64,i64,i64,i64 rt=i64 p=%s' % (FN, st & M64, cnt & M64, FN, patch)


def run(s, runner_name, cmd, init_lines, timeout):
    r = Runner(runner_name, cmd, init_lines, timeout=timeout)
    lines = [case_lines(s, st, cnt) for st, cnt in GRID]
    out = r.run_cases(lines, ['%d_%d' % g for g in GRID])
    r.close()
    return out


def run_native(s):
    return run(s, 'native', ['setarch', '-R', os.path.join(ROOT, 'work/ld_native'), s.t['pe']],
               s.init_lines('native') + [s.tracelines()], 10.0)


def run_wasm(s):
    return run(s, 'wasm', ['node', '--stack-size=4000', os.path.join(ROOT, s.runner_js), s.wasm_js,
                           s.t.get('image') or '-', '%x' % s.origin, '%x' % s.delta,
                           '--init=' + ','.join(s.t.get('init_exports', [])),
                           '--timeout-ms=%d' % s.wasm_timeout_ms], s.init_lines('wasm'),
               max(s.timeout, s.wasm_timeout_ms / 1000.0 + 5.0))


def summarize(r):
    if r.get('status') != 'ok':
        return r.get('status')
    return 'ok rax=%s' % r.get('rax')


def main():
    # sdiv 版の IR と target.json を work/ 外の手順 (tools/m11) から作り、その target を build する。
    # 進捗ログは stdout (結果表の正本) に出さず stderr へ送る。
    subprocess.run([sys.executable, os.path.join(REPO, 'tools/m11/m11_sdiv_variant.py')], check=True, stdout=sys.stderr)
    s = Session(os.path.join(ROOT, 'targets/m11.json'), build=False, trace=True)
    nat = run_native(s)
    udiv = run_wasm(s)
    sdiv_t = os.path.join(ROOT, 'work/m11_sdiv/target.json')
    with contextlib.redirect_stdout(sys.stderr):
        build_wasm.build(build_wasm.load_target(sdiv_t))
    s_sdiv = Session(sdiv_t, build=False, trace=True)
    sdiv = run_wasm(s_sdiv)
    print('<!-- 自動生成: python3 tools/liftdiff/tests/trace_417b70_sdiv_rerun.py (LD-62, #1767) -->')
    print('| stride | count | native | udiv wasm | sdiv wasm | udiv 食い違い | sdiv 食い違い |')
    print('|---:|---:|---|---|---|:---:|:---:|')
    for (st, cnt), n, u, d in zip(GRID, nat, udiv, sdiv):
        def diff(w):
            c = compare.compare_case(n, w, s.ctx, s.sigs, s.stub_info, s.thunks())
            return c.get('outcome', '?')
        print('| %d | %d | %s | %s | %s | %s | %s |' % (st, cnt, summarize(n), summarize(u), summarize(d),
                                                    diff(u), diff(d)))
    print()
    print('wasm 側 trace 先頭 (sdiv 版):')
    for (st, cnt), d in zip(GRID, sdiv):
        print('- stride %d count %d: %s' % (st, cnt, [t[0] for t in d.get('trace', [])[:8]]))


if __name__ == '__main__':
    main()
