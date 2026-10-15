#!/usr/bin/env python3
"""M11-N210 (#4747) / M11-N223 (#4809): function_40c650 の署名変更で unit 149・158 が退行する要因を切り分ける A/B 生成器.

入力: work/boot_final.ll (m11_gen_ir2.sh の出力・素材 work-m11 の IR) と PE。
出力: <outdir>/<variant>.ll。各 variant を m11_build.sh (M11_XMM_ARGS=1, boot_final.xa.ll として置く) と
      m11_survey.mjs で測る。variant:
  only40c : function_40c650 だけを (i32, f64) に変換 (実際の退行条件)。fix_xmm_args.py --only-funcs で作る
  ctlB    : only40c と同じ変換。callee の本体は入力を読まず 0 固定 (呼出し側の値は実値のまま)
  ctlC    : 呼出し側 16 site を 0.0 にする。callee 本体は入力を読む (署名は同じ)
  sigzero : 呼出し側 0.0 かつ callee 本体も 0 固定 (ctlB と ctlC の両方を外した形)

使い方: python3 m11_sigfix40c_ab.py work/boot_final.ll work/sigfix40c --pe <PE>
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONV = os.path.join(HERE, '..', 'plugins', 'lift', 'passes', 'fix_xmm_args.py')
CALLEE = '@function_40c650'
BODY_OLD = '  %in.xmm0.bits = bitcast double %in.xmm0 to i64\n  %0 = alloca i128\n  %1 = zext i64 %in.xmm0.bits to i128\n'
BODY_ZERO = '  %0 = alloca i128\n  %1 = xor i128 0, 0\n'
CALL_RE = re.compile(r'call (i64|i128) ' + re.escape(CALLEE) + r'\(double %[^)]*\)')
DEF_RE = re.compile(r'^define [^\n]*' + re.escape(CALLEE) + r'\(double %in\.xmm0\)[^\n]*\n.*?^}\n', re.M | re.S)


def callee_def(s):
    ms = list(DEF_RE.finditer(s))
    if len(ms) != 1:
        sys.exit('callee definition count != 1 in %s (got %d)' % (CALLEE, len(ms)))
    return ms[0]


def replace_callee_body(s, new):
    m = callee_def(s)
    d = m.group(0)
    if d.count(BODY_OLD) != 1:
        sys.exit('callee body count != 1 in %s (got %d)' % (CALLEE, d.count(BODY_OLD)))
    return s[:m.start()] + d.replace(BODY_OLD, new) + s[m.end():]


def rewrite_calls(s):
    out = []
    for line in s.split('\n'):
        if not (line.startswith('define') or line.startswith('declare')):
            line = CALL_RE.sub(lambda m: 'call %s %s(double 0.0)' % (m.group(1), CALLEE), line)
        out.append(line)
    return '\n'.join(out)


def make_only40c(src, pe, tmp):
    cmd = [sys.executable, CONV, src, tmp, '--pe', pe, '--only-funcs', CALLEE[1:]]
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.exit('fix_xmm_args failed rc=%d: %s' % (r.returncode, r.stderr[-400:]))
    s = open(tmp).read()
    if CALLEE + '(double %xmmcv' not in s:
        sys.exit('only40c: %s was not converted to (double) params' % CALLEE)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('outdir')
    ap.add_argument('--pe', required=True)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    s = make_only40c(a.src, a.pe, os.path.join(a.outdir, 'only40c.tmp.ll'))
    os.remove(os.path.join(a.outdir, 'only40c.tmp.ll'))
    variants = {
        'only40c': s,
        'ctlB': replace_callee_body(s, BODY_ZERO),
        'ctlC': rewrite_calls(s),
        'sigzero': rewrite_calls(replace_callee_body(s, BODY_ZERO)),
    }
    for name, text in variants.items():
        p = os.path.join(a.outdir, name + '.ll')
        open(p, 'w').write(text)
        print(p, len(text))
    print('src', a.src)


if __name__ == '__main__':
    main()
