#!/usr/bin/env python3
"""LD-212 (#4379): 併存 20 関数の戻りレジスタを、呼出し元の機械語で判定する。

  python3 tools/liftdiff/tests/ld212_retuse.py <PE> [--fn VA ...] [--window N] [--tsv OUT]

各 E8 call (rel32) について、戻り先 (call 直後の命令) から線形に N 命令先まで読み、
rax / rdx / xmm0 (下位 64bit で見る) が『読まれる』『書かれる (上書きされる)』『未確定』のどれが
先に起きるかを見る。判定は呼出し元ごとの 1 件で、関数ごとに件数を集計する。

限界 (REPORT_LD212 に書く):
  - 線形走査。分岐の先は追わず、jcc の fall-through のみ追う。ret / 無条件 jmp / call で打ち切る。
  - call 直後の rax / rdx / xmm0 を読むのは『戻り値の利用』の候補。別の値の再利用も含みうる。
  - E8 走査なので偽陽性を含む。call 命令として再デコードして target が一致したものだけ数える。
"""
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'liftdiff'))
import capstone  # noqa: E402
from ldlib import pe as P  # noqa: E402

GROUPS = {
    'rax': ('rax', 'eax', 'ax', 'al', 'ah'),
    'rdx': ('rdx', 'edx', 'dx', 'dl', 'dh'),
    'xmm0': ('xmm0', 'ymm0', 'zmm0'),
}
TARGETS = ('6ed480 7ce2e0 ba05f0 13114b0 1311f70 40c420 40c650 6a3a90 1311ea0 442670 '
           '442890 6a3ac0 40f210 677820 12657b0 4421d0 45e3c0 45ee00 5b0970 8e6660')


def canon(name):
    for k, names in GROUPS.items():
        if name in names:
            return k
    return None


def classify(md, data, base, start_va, window):
    """戻り先から線形に読み、最初に起きたアクセスで各レジスタ群を分類する。
    返り値: (状態 dict, 最初に読んだ命令のニーモニック dict)。"""
    off = start_va - base
    state = {k: 'unknown' for k in GROUPS}
    first_read = {k: '' for k in GROUPS}
    pending = set(GROUPS)
    n = 0
    for ins in md.disasm(data[off:off + window * 15], start_va):
        n += 1
        if n > window:
            break
        rd_ids, wr_ids = ins.regs_access()
        rd = {canon(ins.reg_name(r)) for r in rd_ids} - {None}
        wr = {canon(ins.reg_name(r)) for r in wr_ids} - {None}
        if ins.mnemonic in ('xor', 'sub', 'pxor', 'xorps', 'xorpd') and ins.op_str.count(',') == 1:
            a_, b_ = [x.strip() for x in ins.op_str.split(',')]
            if a_ == b_:
                rd = set()
        for k in list(pending):
            if k in rd:
                state[k] = 'read'
                first_read[k] = ins.mnemonic
                pending.discard(k)
            elif k in wr:
                state[k] = 'dead'
                pending.discard(k)
        if ins.mnemonic in ('ret', 'retq', 'call', 'jmp'):
            break
        if not pending:
            break
    return state, first_read


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pe')
    ap.add_argument('--fn', nargs='*', default=TARGETS.split())
    ap.add_argument('--window', type=int, default=24)
    ap.add_argument('--tsv', default=None)
    a = ap.parse_args()

    p = P.PE(a.pe)
    txt = [s for s in p.sections if s['name'] == '.text'][0]
    base = p.base + txt['rva']
    data = txt['data']
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    want = {int(t, 16): t for t in a.fn}
    hits = {t: [] for t in want}

    i = data.find(b'\xe8')
    while i != -1 and i + 5 <= len(data):
        rel = struct.unpack_from('<i', data, i + 1)[0]
        call_va = base + i
        tgt = (call_va + 5 + rel) & 0xffffffffffffffff
        if tgt in want:
            ins = next(md.disasm(data[i:i + 5], call_va), None)
            if ins is not None and ins.mnemonic == 'call' and ins.size == 5:
                hits[tgt].append(call_va)
        i = data.find(b'\xe8', i + 1)

    rows = []
    for t_va, t in want.items():
        counts = {'rax': {'read': 0, 'dead': 0, 'unknown': 0},
                  'rdx': {'read': 0, 'dead': 0, 'unknown': 0},
                  'xmm0': {'read': 0, 'dead': 0, 'unknown': 0}}
        mnem = {k: {} for k in GROUPS}
        for c in hits[t_va]:
            st, fr = classify(md, data, base, c + 5, a.window)
            for k in counts:
                counts[k][st[k]] += 1
                if st[k] == 'read':
                    mnem[k][fr[k]] = mnem[k].get(fr[k], 0) + 1
        for k in GROUPS:
            if mnem[k]:
                print('   %s 最初の読み命令: %s' % (k, ' '.join('%s:%d' % kv for kv in sorted(mnem[k].items(), key=lambda x: -x[1]))))
        rows.append((t, len(hits[t_va]), counts))
        print('== %s  calls=%d  rax r/d/u=%d/%d/%d  rdx r/d/u=%d/%d/%d  xmm0 r/d/u=%d/%d/%d' % (
            t, len(hits[t_va]),
            counts['rax']['read'], counts['rax']['dead'], counts['rax']['unknown'],
            counts['rdx']['read'], counts['rdx']['dead'], counts['rdx']['unknown'],
            counts['xmm0']['read'], counts['xmm0']['dead'], counts['xmm0']['unknown']))
    if a.tsv:
        with open(a.tsv, 'w') as f:
            f.write('fn\tcalls\trax_read\trax_dead\trax_unknown\trdx_read\trdx_dead\trdx_unknown\txmm0_read\txmm0_dead\txmm0_unknown\n')
            for t, n, c in rows:
                f.write('%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n' % (
                    t, n, c['rax']['read'], c['rax']['dead'], c['rax']['unknown'],
                    c['rdx']['read'], c['rdx']['dead'], c['rdx']['unknown'],
                    c['xmm0']['read'], c['xmm0']['dead'], c['xmm0']['unknown']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
