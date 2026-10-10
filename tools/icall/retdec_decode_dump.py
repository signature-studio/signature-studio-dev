#!/usr/bin/env python3
"""retdec_decode_dump.py PE RANGES OUT.ll : RetDec を --print-after-all で走らせ、
"Input binary to LLVM IR decoding" 直後の module dump (= 最適化前の faithful な 1命令=1塊 IR) だけを取り出して打ち切る.
RetDec の後段 analysis pass (Constants / RDA / Stack / param-return) が mov rax,[rcx] を rax=rcx にする等の意味破壊を
起こすため、decode 段の IR を直接使う route の入力を作る。stderr を pipe で読み、2 個目以降の dump 見出しで kill."""
import subprocess, sys, os, re, tempfile
pe, ranges, out = sys.argv[1:4]
tmpd = os.path.join(os.path.dirname(os.path.abspath(out)), 'tmp'); os.makedirs(tmpd, exist_ok=True)
env = dict(os.environ, TMPDIR=tmpd)
rg = open(ranges).read().strip() if os.path.isfile(ranges) else ranges
p = subprocess.Popen(['/opt/retdec/bin/retdec-decompiler', pe, '-o', out + '.c', '--select-ranges', rg, '--select-decode-only', '--print-after-all'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
buf = []
state = 0
hdr = re.compile(rb'^\*\*\* IR Dump After (.*) \*\*\*$')
for line in p.stderr:
    m = hdr.match(line.rstrip(b'\n'))
    if m:
        name = m.group(1).decode()
        if state == 1:
            break
        if name == 'Input binary to LLVM IR decoding':
            state = 1
            continue
    elif state == 1:
        buf.append(line)
p.kill(); p.wait()
open(out, 'wb').write(b''.join(buf))
print('wrote', out, sum(len(b) for b in buf), 'bytes')
