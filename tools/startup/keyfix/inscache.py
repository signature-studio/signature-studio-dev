#!/usr/bin/env python3
"""inscache.py — 全 .text 命令のキャッシュ (pickle) を使う高速ユーティリティ"""
import pickle, os, re
import feparse as F
import fnindex

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work')
RE_RIP = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')


class Ins:
    __slots__ = ('address', 'mnemonic', 'op_str', 'size')

    def __init__(self, t):
        self.address, self.mnemonic, self.op_str, self.size = t


_cache = None


def all_ins():
    global _cache
    if _cache is None:
        p = os.path.join(WORK, 'allins.pkl')
        if os.path.exists(p):
            with open(p, 'rb') as f:
                _cache = [Ins(t) for t in pickle.load(f)]
        else:
            F.load()
            tva, tsize = F.text_range()
            off = F.va2off(tva)
            _cache = list(F.md().disasm(F._RAW[off:off + tsize], tva))
            with open(p, 'wb') as f:
                pickle.dump([(x.address, x.mnemonic, x.op_str, x.size) for x in _cache], f)
    return _cache


_fidx = None


def by_func():
    global _fidx
    if _fidx is None:
        _fidx = {}
        for x in all_ins():
            f = fnindex.func_of(x.address)
            k = f[0] if f else 0
            _fidx.setdefault(k, []).append(x)
    return _fidx


def rip_target(x):
    m = RE_RIP.search(x.op_str)
    if not m:
        return None
    disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
    return x.address + x.size + disp


def funcs_referring(G):
    out = set()
    for x in all_ins():
        t = rip_target(x)
        if t == G:
            f = fnindex.func_of(x.address)
            out.add(f[0] if f else 0)
    return out
