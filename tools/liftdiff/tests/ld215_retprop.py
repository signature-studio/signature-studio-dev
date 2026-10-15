#!/usr/bin/env python3
"""LD-215 (#4429): 併存 ret=i128 関数の戻りレジスタを、窓を越えた機械語の経路で判定する。

  python3 tools/liftdiff/tests/ld215_retprop.py <PE> [--fn VA ...] [--budget N] [--tsv OUT]

2 つの側から判定する。
  (a) 呼出し先: ret に至る全経路で、rax / rdx / xmm0 のどれが必ず書かれるか (must-def) と、
      どれかの経路で書かれるか (may-def)。
  (b) 呼出し元: call 直後から分岐の両方を辿り (間接 jmp・call で打ち切り)、各レジスタが
      『読まれる』『上書きされる (全経路)』『ret まで素通し (戻り値として伝播)』『未確定』のどれかに分類する。

判定: 関数 F の戻りレジスタ候補 = must-def(F) ∩ 『読まれる』を 1 件以上の呼出し元が持つもの。
限界: 間接分岐・未知の call で打ち切るため未確定が残る。経路数は budget で打ち切る。
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
REGS = tuple(GROUPS)
NORET = ('ud2', 'int3', 'hlt')
TARGETS = ('6ed480 7ce2e0 ba05f0 13114b0 1311f70 40c420 40c650 6a3a90 1311ea0 442670 '
           '442890 6a3ac0 40f210 677820 12657b0 4421d0 45e3c0 45ee00 5b0970 8e6660')


def canon(name):
    for k, names in GROUPS.items():
        if name in names:
            return k
    return None


class Text:
    def __init__(self, pe):
        p = P.PE(pe)
        txt = [s for s in p.sections if s['name'] == '.text'][0]
        self.base = p.base + txt['rva']
        self.data = txt['data']
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        self.cache = {}

    def at(self, va):
        if va in self.cache:
            return self.cache[va]
        off = va - self.base
        ins = None
        if 0 <= off < len(self.data):
            ins = next(self.md.disasm(self.data[off:off + 15], va, 1), None)
        self.cache[va] = ins
        return ins

    def acc(self, ins):
        rd_ids, wr_ids = ins.regs_access()
        rd = {canon(ins.reg_name(r)) for r in rd_ids} - {None}
        wr = {canon(ins.reg_name(r)) for r in wr_ids} - {None}
        if ins.mnemonic in ('xor', 'sub', 'pxor', 'xorps', 'xorpd') and ins.op_str.count(',') == 1:
            a_, b_ = [x.strip() for x in ins.op_str.split(',')]
            if a_ == b_:
                rd = set()
        return rd, wr


def callee_defs(t, entry, budget):
    """entry から全経路を辿り、ret 到達時点で書かれていたレジスタの積 (must) と和 (may) を返す。"""
    must = None
    may = set()
    seen = set()
    stack = [(entry, frozenset())]
    steps = 0
    while stack:
        va, written = stack.pop()
        if (va, written) in seen:
            continue
        seen.add((va, written))
        steps += 1
        if steps > budget:
            return None, None, False
        ins = t.at(va)
        if ins is None:
            return None, None, False
        rd, wr = t.acc(ins)
        if ins.mnemonic in ('ret', 'retq'):
            may |= written
            must = set(written) if must is None else (must & written)
            continue
        m = ins.mnemonic
        if m.startswith('j') and not ins.op_str.startswith('0x'):
            return None, None, False
        if m in NORET:
            continue
        w2 = written | frozenset(wr)
        if m == 'call':
            if not ins.op_str.startswith('0x'):
                return None, None, False
            w2 = written   # call は揮発性レジスタを clobber するだけで、戻り値の定義とは数えない
        nxt = va + ins.size
        if m == 'jmp':
            stack.append((int(ins.op_str, 16), w2))
        elif m.startswith('j'):
            stack.append((nxt, w2))
            stack.append((int(ins.op_str, 16), w2))
        else:
            stack.append((nxt, w2))
    return (set(must or set()), may, True)


def caller_use(t, ret_va, budget):
    """call 直後 ret_va から経路を辿り、レジスタごとに分類する。
    返り値: {reg: 'read' | 'dead' | 'pass' | 'unknown'} (read は経路のどれかで読まれたら優先)。"""
    res = {k: None for k in REGS}
    mn = {k: '' for k in REGS}
    seen = set()
    stack = [(ret_va, frozenset(REGS))]   # pending = まだ読みも上書きもされていない
    steps = 0
    unknown_hit = set()
    while stack:
        va, pending = stack.pop()
        if not pending:
            continue
        if (va, pending) in seen:
            continue
        seen.add((va, pending))
        steps += 1
        if steps > budget:
            for k in pending:
                unknown_hit.add(k)
            break
        ins = t.at(va)
        if ins is None:
            for k in pending:
                unknown_hit.add(k)
            continue
        rd, wr = t.acc(ins)
        pend = set(pending)
        for k in list(pend):
            if k in rd:
                pend.discard(k)
                if res[k] is None:
                    res[k] = 'read'
                    mn[k] = ins.mnemonic
        for k in list(pend):
            if k in wr:
                pend.discard(k)
                if res[k] is None:
                    res[k] = 'dead'
        if not pend:
            continue
        m = ins.mnemonic
        if m in ('ret', 'retq'):
            for k in pend:
                if res[k] is None:
                    res[k] = 'pass'
            continue
        if m == 'call':
            for k in pend:
                unknown_hit.add(k)
            continue
        if m == 'jmp':
            if ins.op_str.startswith('0x'):
                stack.append((int(ins.op_str, 16), frozenset(pend)))
            else:
                for k in pend:
                    unknown_hit.add(k)
            continue
        if m.startswith('j'):
            stack.append((va + ins.size, frozenset(pend)))
            if ins.op_str.startswith('0x'):
                stack.append((int(ins.op_str, 16), frozenset(pend)))
            else:
                for k in pend:
                    unknown_hit.add(k)
            continue
        stack.append((va + ins.size, frozenset(pend)))
    out = {}
    for k in REGS:
        if res[k] in ('read', 'dead', 'pass'):
            out[k] = res[k]
        else:
            out[k] = 'unknown'
    return out, mn


def call_sites(t, targets):
    hits = {tv: [] for tv in targets}
    data = t.data
    i = data.find(b'\xe8')
    while i != -1 and i + 5 <= len(data):
        rel = struct.unpack_from('<i', data, i + 1)[0]
        call_va = t.base + i
        tgt = (call_va + 5 + rel) & 0xffffffffffffffff
        if tgt in hits:
            ins = t.at(call_va)
            if ins is not None and ins.mnemonic == 'call' and ins.size == 5:
                hits[tgt].append(call_va)
        i = data.find(b'\xe8', i + 1)
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pe')
    ap.add_argument('--fn', nargs='*', default=TARGETS.split())
    ap.add_argument('--budget', type=int, default=400)
    ap.add_argument('--tsv', default=None)
    a = ap.parse_args()

    t = Text(a.pe)
    want = {int(x, 16): x for x in a.fn}
    hits = call_sites(t, want)
    rows = []
    for va, name in want.items():
        must, may, ok = callee_defs(t, va, a.budget * 4)
        use = {k: {'read': 0, 'dead': 0, 'pass': 0, 'unknown': 0, 'mn': {}} for k in REGS}
        for c in hits[va]:
            r, mn = caller_use(t, c + 5, a.budget)
            for k in REGS:
                use[k][r[k]] += 1
                if mn[k]:
                    use[k]['mn'][mn[k]] = use[k]['mn'].get(mn[k], 0) + 1
        rd_n = {k: use[k]['read'] for k in REGS}
        cand = sorted(k for k in REGS if ok and k in must and rd_n[k] > 0)
        rows.append((name, ok, must, may, len(hits[va]), use, cand))
        print('== %s  callee_ok=%s must=%s may=%s  calls=%d' % (
            name, ok, sorted(must) if ok else '-', sorted(may) if ok else '-', len(hits[va])))
        for k in REGS:
            print('   %-5s read=%d dead=%d pass=%d unknown=%d  最初の読み: %s' % (
                k, use[k]['read'], use[k]['dead'], use[k]['pass'], use[k]['unknown'],
                ' '.join('%s:%d' % kv for kv in sorted(use[k]['mn'].items(), key=lambda x: -x[1])) or '-'))
        print('   候補 (必ず書かれ かつ 読まれる) = %s' % (','.join(cand) or '-'))
    if a.tsv:
        os.makedirs(os.path.dirname(os.path.abspath(a.tsv)), exist_ok=True)
        with open(a.tsv, 'w') as f:
            f.write('fn\tcallee_ok\tmust\tcalls\tcand\n')
            for name, ok, must, may, n, use, cand in rows:
                f.write('%s\t%s\t%s\t%d\t%s\n' % (name, ok, ','.join(sorted(must or [])), n, ','.join(cand)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
