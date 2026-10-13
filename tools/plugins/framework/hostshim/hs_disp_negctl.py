#!/usr/bin/env python3
"""hs_disp_negctl.py — hs_disp_emu.py のネガティブコントロール (#986 / PLG-P0b-2)。

1 件を壊して経路が変わる (または WATCH が消える) ことを、基準 JSON との差分で数値化する。
  * ret_tag / ret_one : Dispatcher 外 call の戻り値 0 を 0x54534154 / 1 に変える
  * watch_broken      : WATCH 0x131bb5c を 0x131bb5d (命令途中) に壊す
  * nomap             : 未マップ領域への自動 0 埋めを止める (アクセスで実行停止)

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn 入り lib> HS_DISP_NEGCTL_BASE=<基準 JSON> \
        python3 hs_disp_negctl.py <mode>
出力: HS_DISP_OUT_DIR (既定 $RUNNER_TEMP または /tmp) に <mode>.json を書き、基準との差分を表示する。
"""
import os
import sys
import json
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'hs_disp_emu.py')


def build(mode):
    src = open(SRC).read()
    if mode == 'ret_tag':
        src = src.replace("uc_.reg_write(UC_X86_REG_RAX, 0)", "uc_.reg_write(UC_X86_REG_RAX, 0x54534154)", 1)
    elif mode == 'ret_one':
        src = src.replace("uc_.reg_write(UC_X86_REG_RAX, 0)", "uc_.reg_write(UC_X86_REG_RAX, 1)", 1)
    elif mode == 'watch_broken':
        src = src.replace("WATCH = {0x131bb5c,", "WATCH = {0x131bb5d,", 1)
    elif mode == 'nomap':
        src = src.replace("        page = addr & ~(PAGE - 1)\n", "        return False\n        page = addr & ~(PAGE - 1)\n", 1)
    elif mode != 'base':
        raise SystemExit('unknown mode: %s' % mode)
    return src


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'base'
    src = build(mode)
    out_dir = os.environ.get('HS_DISP_OUT_DIR') or os.environ.get('RUNNER_TEMP') or tempfile.gettempdir()
    out = os.path.join(out_dir, 'negctl_%s.json' % mode)
    g = {'__file__': SRC, '__name__': 'negctl'}
    exec(compile(src, SRC, 'exec'), g)
    os.environ['HS_DISP_OUT'] = out
    sys.argv = ['hs_disp_emu.py']
    g['main']()

    base_path = os.environ.get('HS_DISP_NEGCTL_BASE')
    if base_path and mode != 'base':
        b = json.load(open(base_path))
        c = json.load(open(out))
        print('mode=%s vs base: path_hash diff IDs=%d / path_len diff=%d / leaf diff=%d / rax diff=%d / hit diff=%d' % (
            mode,
            sum(b[k]['path_hash'] != c[k]['path_hash'] for k in b),
            sum(b[k]['path_len'] != c[k]['path_len'] for k in b),
            sum(b[k]['trail'][-1] != c[k]['trail'][-1] for k in b),
            sum(b[k]['rax'] != c[k]['rax'] for k in b),
            sum(b[k]['hit'] != c[k]['hit'] for k in b)))


if __name__ == '__main__':
    main()
