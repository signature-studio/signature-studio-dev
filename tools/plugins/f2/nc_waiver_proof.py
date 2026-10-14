#!/usr/bin/env python3
"""PLG-F2 (#514) waiver_proof.py のネガティブコントロール: 述語を壊した PE の複製で V5 が FAIL (exit 1) することを確かめる。

  NC-A  0x740f22 の jae 0x7411dd (0f 83) を jb (0f 82) に書換え → v∈[7,13] の経路が 0x740f28 に落ちて到達する
  NC-B  0x740e6d の cmp eax,0xe (83 f8 0e) を cmp eax,0x14 に書換え → v∈[14,19] が v<20 として 0x740f28 に到達する
どちらも waiver_proof.py は exit 1 でなければならない (通れば検査が空振り)。
使い方: python3 tools/plugins/f2/nc_waiver_proof.py [--pe PE] (既定は waiver_proof.py と同じ)
"""
import argparse, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR

BLOCK = 18979
TEXT_RAW_DELTA = 0x400 - 0x1000  # .text: file offset = RVA - 0x1000 + 0x400 (block18979_PE.bin の .text 配置)
IMAGE_BASE = 0x400000


def off(va):
    return va - IMAGE_BASE + TEXT_RAW_DELTA


def patch(src, dst, va, old, new):
    b = bytearray(open(src, 'rb').read())
    o = off(va)
    assert bytes(b[o:o + len(old)]) == old, 'NC 書換え位置のバイトが想定と違う (0x%x: %s)' % (va, b[o:o + len(old)].hex())
    b[o:o + len(new)] = new
    open(dst, 'wb').write(bytes(b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', default=os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % BLOCK))
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix='nc_waiver_proof_')
    cases = [
        ('NC-A jae->jb (0x740f22)', 0x740f22, bytes.fromhex('0f83'), bytes.fromhex('0f82')),
        ('NC-B cmp eax,0xe->0x14 (0x740e6d)', 0x740e6d, bytes.fromhex('83f80e'), bytes.fromhex('83f814')),
    ]
    fail = 0
    for name, va, old, new in cases:
        dst = os.path.join(tmp, 'nc.bin')
        patch(a.pe, dst, va, old, new)
        p = subprocess.run([sys.executable, os.path.join(HERE, 'waiver_proof.py'), '--pe', dst], capture_output=True, text=True)
        rc = p.returncode
        verdict = 'DETECTED' if rc != 0 else 'MISSED'
        print('[%s] %s: waiver_proof rc=%d' % (verdict, name, rc))
        for line in p.stdout.splitlines():
            if line.startswith('FAIL'):
                print('      ' + line)
        fail += rc == 0
    shutil.rmtree(tmp, ignore_errors=True)
    print('NC RESULT %s (%d/%d DETECTED)' % ('PASS' if fail == 0 else 'FAIL', len(cases) - fail, len(cases)))
    sys.exit(0 if fail == 0 else 1)


if __name__ == '__main__':
    main()
