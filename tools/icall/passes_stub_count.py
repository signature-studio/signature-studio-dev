#!/usr/bin/env python3
"""passes_stub_count.py RW_PE RANGES OUT.txt : RetDec --print-after-all の各段で、
関数ごとの書換え stub 呼出し (function_1cd3f30 / function_1cd3fe0) 数を数え、
関数数・stub 数が変わった段だけを OUT.txt に書く (#229 の段特定用)。"""
import subprocess, sys, os, re, tempfile

pe, ranges, out = sys.argv[1:4]
tmp = tempfile.mkdtemp(prefix='passes_')
env = dict(os.environ, TMPDIR=tmp)
rg = open(ranges).read().strip()
p = subprocess.Popen(['/opt/retdec/bin/retdec-decompiler', pe, '-o', os.path.join(tmp, 'x.c'),
                      '--select-ranges', rg, '--select-decode-only', '--print-after-all'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
hdr = re.compile(rb'^\*\*\* IR Dump After (.*) \*\*\*$')
cur, buf, rows = None, [], []


def flush(name, lines):
    txt = b''.join(lines).decode(errors='replace')
    fns = re.findall(r'define[^\n]*@(function_\w+)\(', txt)
    tot = 0
    for f in fns:
        m = re.search(r'define[^\n]*@%s\(.*?\n\}' % f, txt, re.S)
        body = m.group(0) if m else ''
        tot += body.count('function_1cd3f30()') + body.count('function_1cd3fe0()')
    rows.append((name, len(fns), tot))


for line in p.stderr:
    m = hdr.match(line.rstrip(b'\n'))
    if m:
        if cur is not None:
            flush(cur, buf)
        cur, buf = m.group(1).decode(), []
        continue
    if cur is not None:
        buf.append(line)
if cur is not None:
    flush(cur, buf)
p.wait()
prev = None
with open(out, 'w') as f:
    for name, nf, tot in rows:
        if (nf, tot) != prev:
            f.write('funcs=%d stub_calls=%d  %s\n' % (nf, tot, name))
        prev = (nf, tot)
print('wrote', out, len(rows), 'passes')
