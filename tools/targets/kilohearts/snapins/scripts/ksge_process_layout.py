#!/usr/bin/env python3
"""ksge_process_layout.py — GraphicEqDsp process (vtable slot 14) の ctx / self / buf 参照オフセットを集計する (KH-155 / #5377)。

入力: HeartCore.core_64 (PE) と rtti_vtables.json (rtti_walk.py の出力)。
出力: 関数の objdump (intel) と、基底レジスタ別の [base+disp] 参照回数・初出 site。
objdump の結果だけを使う (機械語からの読み取り)。意味づけは REPORT_APPENDIX_5377.md を見る。
使い方 (tools/targets/kilohearts/ で実行):
  python3 snapins/scripts/ksge_process_layout.py work/winpkg/HeartCore.core_64 work/rtti_vtables.json work/ksge_layout.txt
"""
import json, re, subprocess, sys
from collections import defaultdict

CLS = '.?AVGraphicEqDsp@graphiceq@@'
SLOT = 14


def main():
    pe, vt_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    vt = json.load(open(vt_path))
    base = 0x180000000
    start = int(vt[CLS][0]['slots'][SLOT], 16)
    size = vt[CLS][0]['sizes'][SLOT]
    if size is None:
        sys.exit('slot %d の extent が無い' % SLOT)
    txt = subprocess.run(['objdump', '-d', '-M', 'intel', '--start-address=%#x' % start,
                          '--stop-address=%#x' % (start + size), pe],
                         capture_output=True, text=True, check=True).stdout
    open(out + '.asm', 'w').write(txt)
    ref = re.compile(r'\[(rbx|rdi|rsi)\+(0x[0-9a-f]+)\]')
    cnt = defaultdict(int)
    first = {}
    for line in txt.splitlines():
        m = re.match(r'\s*([0-9a-f]+):', line)
        if not m:
            continue
        for b, d in ref.findall(line):
            k = (b, int(d, 16))
            cnt[k] += 1
            first.setdefault(k, int(m.group(1), 16))
    with open(out, 'w') as f:
        f.write('# slot %d = %#x (size %d) base=%#x\n' % (SLOT, start, size, base))
        for b in ('rdi', 'rbx', 'rsi'):
            f.write('## base %s\n' % b)
            for (bb, d) in sorted(k for k in cnt if k[0] == b):
                f.write('  +%#x  refs=%d  first=%#x\n' % (d, cnt[(bb, d)], first[(bb, d)]))
    print('wrote', out, 'entries', len(cnt))


if __name__ == '__main__':
    main()
