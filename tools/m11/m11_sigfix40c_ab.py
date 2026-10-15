#!/usr/bin/env python3
"""M11-N210 (#4747): function_40c650 の署名変更で unit 149・158 が退行する要因を切り分ける A/B 生成器.

入力: work/boot_final.ll (m11_gen_ir2.sh の出力) と fix_xmm_args.py の report (変換候補の一覧)。
出力: work/sigfix40c/<variant>.ll。各 variant を m11_build.sh (M11_XMM_ARGS=1, boot_final.xa.ll として置く) と
      m11_survey.mjs で測る。variant:
  only40c : function_40c650 だけを (i32, f64) に変換 (実際の退行条件)
  ctlB    : only40c と同じ変換。callee の本体は入力を読まず 0 固定 (呼出し側の値は実値のまま)
  ctlC    : 呼出し側 16 site を 0.0 にする。callee 本体は入力を読む (署名は同じ)
  sigzero : 呼出し側 0.0 かつ callee 本体も 0 固定 (ctlB と ctlC の両方を外した形)

使い方: python3 m11_sigfix40c_ab.py work/boot_final.ll work/sigfix40c <fix_xmm_args の出力 ll (only40c)>
"""
import os
import re
import sys

CALLEE = '@function_40c650'
BODY_OLD = '  %in.xmm0.bits = bitcast double %in.xmm0 to i64\n  %0 = alloca i128\n  %1 = zext i64 %in.xmm0.bits to i128\n'
BODY_ZERO = '  %0 = alloca i128\n  %1 = xor i128 0, 0\n'
CALL_RE = re.compile(r'call (i64|i128) ' + re.escape(CALLEE) + r'\(double %[^)]*\)')


def rewrite_calls(s):
    out = []
    for line in s.split('\n'):
        if not (line.startswith('define') or line.startswith('declare')):
            line = CALL_RE.sub(lambda m: 'call %s %s(double 0.0)' % (m.group(1), CALLEE), line)
        out.append(line)
    return '\n'.join(out)


def main():
    src, outdir, only = sys.argv[1], sys.argv[2], sys.argv[3]
    s = open(only).read()
    if s.count(BODY_OLD) != 1:
        sys.exit('callee body not found in %s' % only)
    os.makedirs(outdir, exist_ok=True)
    variants = {
        'only40c': s,
        'ctlB': s.replace(BODY_OLD, BODY_ZERO),
        'ctlC': rewrite_calls(s),
        'sigzero': rewrite_calls(s.replace(BODY_OLD, BODY_ZERO)),
    }
    for name, text in variants.items():
        p = os.path.join(outdir, name + '.ll')
        open(p, 'w').write(text)
        print(p, len(text))
    print('src', src)


if __name__ == '__main__':
    main()
