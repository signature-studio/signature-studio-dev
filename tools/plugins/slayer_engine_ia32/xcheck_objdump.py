#!/usr/bin/env python3
"""measure.py の capstone 数値を GNU objdump (別デコーダ) で検算する (#674 / PR #688)。

  $PY xcheck_objdump.py   (素材・SHA-256 の扱いは measure.py と同じ。 objdump が必要)
"""
import collections, hashlib, os, re, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure

OBJ_PRIV = frozenset(['in', 'ins', 'out', 'outs', 'iret', 'hlt', 'cli', 'sti', 'lgdt', 'lidt', 'lldt', 'ltr',
                      'lmsw', 'sgdt', 'sidt', 'sldt', 'clts', 'invd', 'wbinvd', 'invlpg', 'rdmsr', 'wrmsr', 'rsm',
                      'sysexit', 'swapgs', 'xsetbv'])


def main():
    path = os.path.join(measure.fl_dir(), 'extracted', 'block22434_PE.bin')
    data = open(path, 'rb').read()
    if hashlib.sha256(data).hexdigest() != measure.EXPECT_SHA256:
        sys.exit('[xcheck] FAIL 入力の SHA-256 が一致しない: %s' % path)
    t = measure.parse_pe(data)['text']
    code = data[t['rawptr']:t['rawptr'] + t['vsize']]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'text.bin')
        open(p, 'wb').write(code)
        out = subprocess.run(['objdump', '-D', '-b', 'binary', '-m', 'i386', '-M', 'intel', p],
                             capture_output=True, text=True, check=True).stdout
    ver = subprocess.run(['objdump', '--version'], capture_output=True, text=True).stdout.splitlines()[0]
    n, bad, x87 = 0, [], 0
    ctrl = collections.Counter()
    call_d = call_i = jmp = 0
    priv = []
    for line in out.splitlines():
        parts = line.split('\t')
        if len(parts) < 3 or not parts[2].strip():
            continue
        addr = int(parts[0].strip().rstrip(':'), 16)
        text = parts[2].strip()
        if text == '(bad)':
            bad.append(addr)
            continue
        n += 1
        mn = text.split()[0]
        ops = text[len(mn):].strip()
        if mn.startswith('f') and mn != 'fwait':
            x87 += 1
        if mn in ('fldcw', 'fnstcw', 'fstcw', 'fnstenv', 'fldenv'):
            ctrl[mn] += 1
        if mn == 'call':
            if ops.startswith('0x'):
                call_d += 1
            else:
                call_i += 1
        if mn == 'jmp':
            jmp += 1
        if mn in OBJ_PRIV:
            priv.append('0x%x:%s' % (addr, mn))
    print('[xcheck] %s text=%d B' % (ver, len(code)))
    print('[xcheck] insn=%d bad=%d (.text offsets %s)' % (n, len(bad), ' '.join('0x%x' % b for b in bad)))
    print('[xcheck] x87(f*, fwait 除外)=%d fldcw=%d fnstcw=%d fstcw=%d fnstenv=%d fldenv=%d' % (
        x87, ctrl['fldcw'], ctrl['fnstcw'], ctrl['fstcw'], ctrl['fnstenv'], ctrl['fldenv']))
    print('[xcheck] call=%d (direct %d / indirect %d) jmp=%d' % (call_d + call_i, call_d, call_i, jmp))
    print('[xcheck] priv=%d: %s' % (len(priv), ' '.join(priv)))


if __name__ == '__main__':
    main()
