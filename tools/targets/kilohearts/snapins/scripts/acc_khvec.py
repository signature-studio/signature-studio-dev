#!/usr/bin/env python3
"""acc_khvec.py — KHV2 vectors.bin パーサ (harness/compare.mjs とは独立実装・規則 37)。

compare.mjs は node で同じ仕事をするが、本モジュールは Python 側で同じ bin を読む
(独立再計算のための別実装)。数え方の定義 (規則 36):
  - 1 行 = 1 バイト。region = (off, len) の「照合対象バイト列」。
  - 1 trial = qebig/formant 等の scenario 1 試行。1 call = 1 関数呼出。
  - post = call 後に比較する領域 (region 名と off/len はヘッダに同梱)。
"""
import struct
import sys


class Vec:
    def __init__(self, path):
        self.buf = open(path, 'rb').read()
        b = self.buf
        if b[0:4] != b'KHV2':
            raise SystemExit('bad magic %r' % b[0:4])
        self.ntrials, self.nslots = struct.unpack_from('<II', b, 4)
        self.p = 12
        self.trials = []
        self.rtabs = []
        for _ in range(self.ntrials):
            ncalls, _pad = struct.unpack_from('<II', b, self.p)
            self.p += 8
            calls = []
            for _ in range(ncalls):
                np_ = struct.unpack_from('<I', b, self.p)[0]
                self.p += 4
                regs = []
                for _ in range(np_):
                    off, ln = struct.unpack_from('<II', b, self.p)
                    self.p += 8
                    data = b[self.p:self.p + ln]
                    self.p += ln
                    regs.append((off, ln, data))
                va = struct.unpack_from('<Q', b, self.p)[0]
                self.p += 8
                a = struct.unpack_from('<4Q', b, self.p)
                self.p += 32
                x = struct.unpack_from('<4Q', b, self.p)
                self.p += 32
                rk, rax, xmm0 = struct.unpack_from('<IQQ', b, self.p)
                self.p += 20
                plen = struct.unpack_from('<I', b, self.p)[0]
                self.p += 4
                post = b[self.p:self.p + plen]
                self.p += plen
                calls.append(dict(regs=regs, va=va, a=a, x=x, rk=rk, rax=rax, xmm0=xmm0,
                                  post=post))
            # trial 末尾に region テーブル: u32 nreg { u32 off, u32 len, u32 namelen, name[] }
            nreg = struct.unpack_from('<I', b, self.p)[0]
            self.p += 4
            rtab = []
            for _ in range(nreg):
                off, ln, nl = struct.unpack_from('<III', b, self.p)
                self.p += 12
                nm = b[self.p:self.p + nl].decode('latin1')
                self.p += nl
                rtab.append((off, ln, nm))
            self.trials.append(calls)
            self.rtabs.append(rtab)
        if self.p != len(b):
            raise SystemExit('trailing bytes: parsed %d of %d' % (self.p, len(b)))

    def __len__(self):
        return self.ntrials


def calls_of(v, va):
    """指定 VA の call を全 trial から抽出 (定義: rk == 2 = float 戻り, xmm0 に格納)。"""
    out = []
    for t in v.trials:
        for c in t:
            if c['va'] == va:
                out.append(c)
    return out


if __name__ == '__main__':
    p = sys.argv[1] if len(sys.argv) > 1 else 'work/quickeq/qebig.bin'
    v = Vec(p)
    print('trials=%d calls=%d' % (v.ntrials, sum(len(t) for t in v.trials)))
    from collections import Counter
    cnt = Counter(hex(c['va']) for t in v.trials for c in t)
    print('by va:', dict(cnt))
    print('rtab trial0:', v.rtabs[0])
    c0 = v.trials[0][0]
    print('first call: rk=%d rax=%#x xmm0=%#x a0=%#x x0=%#x' % (c0['rk'], c0['rax'], c0['xmm0'], c0['a'][0], c0['x'][0]))
