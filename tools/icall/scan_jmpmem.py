#!/usr/bin/env python3
"""scan_jmpmem.py — PE の .pdata 関数 (8 KiB 以下) から `jmp [base+idx*s+d]` (rip 相対でない index 付き MEM) を集める (ICALL-32 / #1589).

  python3 scan_jmpmem.py DIR_OR_PE... [--json out.json]

DIR を渡すと直下の *_PE.bin を全部見る。出力: 関数数・site 数・PE 数と、関数ごとの site VA 一覧。
"""
import argparse, glob, json, os, sys
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_icall as A
import capstone
from capstone import x86

MAX_FN = 0x2000


def scan_pe(path):
    img = A.Image(path)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    out = []
    for s, e in sorted(img.pdata.items()):
        code = img.read(s, e - s)
        if not code:
            continue
        sites = []
        for ins in md.disasm(code, s):
            if ins.mnemonic not in ('jmp', 'call'):
                continue
            for op in ins.operands:
                if op.type != x86.X86_OP_MEM:
                    continue
                m = op.mem
                if m.index == 0 or m.base == x86.X86_REG_RIP:
                    continue
                sites.append({'va': '0x%x' % ins.address, 'mn': ins.mnemonic})
        if sites:
            out.append({'pe': os.path.basename(path), 'fn': '0x%x-0x%x' % (s, e), 'size': e - s, 'sites': sites})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--json')
    ap.add_argument('--jobs', type=int, default=4)
    a = ap.parse_args()
    pes = []
    for p in a.paths:
        if os.path.isdir(p):
            pes += sorted(glob.glob(os.path.join(p, '*_PE.bin')))
        else:
            pes.append(p)
    with Pool(a.jobs) as pool:
        rows = [r for rs in pool.map(scan_pe, pes) for r in rs]
    nsite = sum(len(r['sites']) for r in rows)
    npe = len({r['pe'] for r in rows})
    print('PE %d / 関数 %d / site %d / site を持つ PE %d' % (len(pes), len(rows), nsite, npe))
    if a.json:
        with open(a.json, 'w') as f:
            json.dump(rows, f, indent=1)


if __name__ == '__main__':
    main()
