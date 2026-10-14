#!/usr/bin/env python3
"""x64c_vex_diff.py の rcr 参照値 (rcr_ref) を x86-64 実機の rcr と照合する (KH-38 #3065)。
実行: python3 tools/flelift/tests/rcr_native_check.py (x86-64 ホストと gcc が必要。他ホストは SKIP)。
インライン asm で 8/16/32/64bit の rcr を実行し、結果・CF・OF・ZF/SF/PF を rcr_ref と比べる。"""
import os, platform, random, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from x64c_vex_diff import rcr_ref, MASKS_W

DRIVER = r'''
#include <stdint.h>
#include <stdio.h>
/* stdin: "<w> <val hex> <cnt dec> <flags hex>" (flags: CF=bit0 PF=bit2 ZF=bit6 SF=bit7 OF=bit11)
   stdout: "<result hex> <flags-out hex>" (pushfq の下位 12bit) */
int main(void) {
    int w; unsigned long long val, cnt, fin;
    while (scanf("%d %llx %llu %llx", &w, &val, &cnt, &fin) == 4) {
        unsigned long long fout = 0, res = 0, f = fin;
        switch (w) {
        case 8: { unsigned char v = (unsigned char)val;
            asm volatile("pushq %[f]\n\tpopfq\n\trcrb %%cl, %b[v]\n\tpushfq\n\tpopq %[fo]\n"
                         : [v] "+q"(v), [fo] "=r"(fout) : [f] "r"(f), "c"(cnt) : "cc", "memory");
            res = v; break; }
        case 16: { unsigned short v = (unsigned short)val;
            asm volatile("pushq %[f]\n\tpopfq\n\trcrw %%cl, %w[v]\n\tpushfq\n\tpopq %[fo]\n"
                         : [v] "+r"(v), [fo] "=r"(fout) : [f] "r"(f), "c"(cnt) : "cc", "memory");
            res = v; break; }
        case 32: { unsigned int v = (unsigned int)val;
            asm volatile("pushq %[f]\n\tpopfq\n\trcrl %%cl, %k[v]\n\tpushfq\n\tpopq %[fo]\n"
                         : [v] "+r"(v), [fo] "=r"(fout) : [f] "r"(f), "c"(cnt) : "cc", "memory");
            res = v; break; }
        default: { uint64_t v = (uint64_t)val;
            asm volatile("pushq %[f]\n\tpopfq\n\trcrq %%cl, %q[v]\n\tpushfq\n\tpopq %[fo]\n"
                         : [v] "+r"(v), [fo] "=r"(fout) : [f] "r"(f), "c"(cnt) : "cc", "memory");
            res = v; break; }
        }
        printf("%llx %llx\n", res, fout & 0xfffULL);
    }
    return 0;
}
'''


def main():
    if platform.machine() not in ('x86_64', 'AMD64'):
        print('SKIP rcr native check (host is %s)' % platform.machine())
        return 0
    D = tempfile.mkdtemp(prefix='rcr_native_', dir=os.environ.get('RUNNER_TEMP') or None)
    src = os.path.join(D, 'rcr_hw.c')
    open(src, 'w').write(DRIVER)
    exe = os.path.join(D, 'rcr_hw')
    cc = subprocess.run(['gcc', '-std=gnu11', '-O1', '-mno-red-zone', '-Wall', '-o', exe, src], capture_output=True, text=True)
    if cc.returncode != 0:
        print(cc.stderr[:2000]); return 1
    random.seed(3065)
    N = 4000
    flag_bits = (1 << 0) | (1 << 2) | (1 << 6) | (1 << 7) | (1 << 11)
    cases = []
    for _ in range(N):
        w = random.choice([8, 16, 32, 64])
        a = random.getrandbits(w)
        cnt = random.randrange(0, 256)
        fl = random.getrandbits(12) & flag_bits
        cases.append((w, a, cnt, fl))
    inp = ''.join('%d %x %d %x\n' % c for c in cases)
    out = subprocess.run([exe], input=inp, capture_output=True, text=True, check=True).stdout.split('\n')
    hw = [tuple(int(x, 16) for x in l.split()) for l in out if l.strip()]
    ok = 0
    bad = []
    for (w, a, cnt, fl), (hr, hf) in zip(cases, hw):
        F = {'CF': fl & 1, 'PF': (fl >> 2) & 1, 'ZF': (fl >> 6) & 1, 'SF': (fl >> 7) & 1, 'OF': (fl >> 11) & 1}
        r, nf = rcr_ref(w, a, cnt, F)
        nfl = nf['CF'] | (nf['PF'] << 2) | (nf['ZF'] << 6) | (nf['SF'] << 7) | (nf['OF'] << 11)
        if hr == r and (hf & flag_bits) == nfl:
            ok += 1
        elif len(bad) < 5:
            bad.append((w, hex(a), cnt, hex(fl), hex(hr), hex(hf & flag_bits), hex(r), hex(nfl)))
    print('rcr_ref vs native: pass %d / %d (w=8,16,32,64; count 0..255; random flags)' % (ok, N))
    for b in bad:
        print('  MISMATCH w=%d a=%s cnt=%d fl=%s hw=%s/%s ref=%s/%s' % b)
    return 0 if ok == N else 1


if __name__ == '__main__':
    sys.exit(main())
