#!/usr/bin/env python3
"""sccp_stub_drop.py RW_PE RANGES OUTDIR : #847 (ICALL-9) の段特定。

RetDec の --print-after-all 全段 dump を 1 段ずつ分け、段ごとに関数単位で
  lines      : その関数の IR 行数 (define から閉じ括弧まで)
  bbs        : 基本ブロック数 (ラベル行の数)
  stub       : 書換え stub 呼出し (function_1cd3f30() / function_1cd3fe0()) 数
  br_undef   : `br i1 undef` の本数
  ld_1dc0080 : `load ... inttoptr (i64 31195264 ...)` (= 0x1dc0080) の本数
  st_1dc0080 : 同 store の本数
を数え、dump 1 本ごとの生データを OUTDIR/dumps.tsv に書く (段の合計は dumps.tsv から集計する)。
stub 数が変わった関数の直前・直後を OUTDIR/sccp_pairs.tsv に書く。

用途: RetDec の段ごとの IR 変化を再現する。RetDec は RETDEC_BIN (既定 /opt/retdec/bin/retdec-decompiler)。
入力 RW_PE は measure_flengine_split.sh の base/rw.dll (after.ranges と組で使う)。
"""
import os, re, subprocess, sys, tempfile
from collections import defaultdict

RETDEC = os.environ.get('RETDEC_BIN', '/opt/retdec/bin/retdec-decompiler')
STUB = re.compile(r'function_1cd3f30\(\)|function_1cd3fe0\(\)')
DEF = re.compile(r'^define[^\n]*@(function_\w+)\(', re.M)
LABEL = re.compile(r'^[A-Za-z_.$][\w.$-]*:', re.M)
HDR = re.compile(rb'^\*\*\* IR Dump After (.*) \*\*\*$')


def func_stats(txt):
    out = {}
    for m in DEF.finditer(txt):
        name = m.group(1)
        end = txt.find('\n}', m.start())
        body = txt[m.start(): end + 2] if end >= 0 else txt[m.start():]
        out[name] = dict(
            lines=body.count('\n') + 1,
            bbs=len(LABEL.findall(body)),
            stub=len(STUB.findall(body)),
            br_undef=body.count('br i1 undef'),
            ld_1dc0080=len(re.findall(r'load i64, i64\* inttoptr \(i64 31195264 ', body)),
            st_1dc0080=len(re.findall(r'store i64 [^\n]*inttoptr \(i64 31195264 ', body)),
        )
    return out


def main():
    pe, ranges, outdir = sys.argv[1:4]
    os.makedirs(outdir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='sccp_')
    env = dict(os.environ, TMPDIR=tmp)
    rg = open(ranges).read().strip()
    p = subprocess.Popen([RETDEC, pe, '-o', os.path.join(tmp, 'x.c'), '--select-ranges', rg,
                          '--select-decode-only', '--print-after-all'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
    dumps = []  # (pass, {func: stats})
    cur, buf = None, []

    def flush():
        if cur is not None:
            dumps.append((cur, func_stats(b''.join(buf).decode(errors='replace'))))

    for line in p.stderr:
        m = HDR.match(line.rstrip(b'\n'))
        if m:
            flush()
            cur, buf = m.group(1).decode(), []
            continue
        if cur is not None:
            buf.append(line)
    flush()
    p.wait()

    # RetDec は段ごとに関数単位のモジュールを交互に dump する。段の合計はこの生データから集計する
    # (dump 順の全行: 段名・関数名・stub・行数・基本ブロック・br i1 undef・0x1dc0080 の load/store)
    with open(os.path.join(outdir, 'dumps.tsv'), 'w') as f:
        f.write('idx\tpass\tfunc\tstub\tlines\tbbs\tbr_undef\tld_1dc0080\tst_1dc0080\n')
        k = 0
        for name, fs in dumps:
            for fn, v in fs.items():
                f.write('%d\t%s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\n' % (k, name, fn, v['stub'], v['lines'],
                                                              v['bbs'], v['br_undef'], v['ld_1dc0080'],
                                                              v['st_1dc0080']))
            k += 1
    # 関数ごとに stub 数が変わった段の直前 (before) と直後 (after)
    with open(os.path.join(outdir, 'sccp_pairs.tsv'), 'w') as f:
        f.write('func\tpass_before\tstub\tlines\tbbs\tbr_undef\tld_1dc0080\tpass_after\tstub\tlines\tbbs\tbr_undef\tld_1dc0080\tst_1dc0080\n')
        last = {}
        for name, fs in dumps:
            for fn, v in fs.items():
                if fn in last and last[fn][1]['stub'] != v['stub']:
                    pb, b = last[fn]
                    f.write('%s\t%s\t%d\t%d\t%d\t%d\t%d\t%s\t%d\t%d\t%d\t%d\t%d\t%d\n' % (
                        fn, pb, b['stub'], b['lines'], b['bbs'], b['br_undef'], b['ld_1dc0080'],
                        name, v['stub'], v['lines'], v['bbs'], v['br_undef'], v['ld_1dc0080'], v['st_1dc0080']))
                last[fn] = (name, v)
    print('dumps', len(dumps), 'wrote', outdir)


if __name__ == '__main__':
    main()
