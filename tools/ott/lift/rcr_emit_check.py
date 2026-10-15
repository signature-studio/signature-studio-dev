#!/usr/bin/env python3
"""OTT 版 x64c.py の i_rcr が生成する C 断片を x86-64 実機の rcr と照合する (KH-38 #3125)。
実行: python3 tools/ott/lift/rcr_emit_check.py [--module PATH]  (x86-64 ホストと gcc / clang が必要。他ホストは SKIP)
--module 既定 = tools/ott/lift/x64c.py。別の版 (例: 旧 main の x64c.py) を渡すと、その版の断片を同じ入力で比べる (ネガティブコントロール)。
FnLift.i_rcr を本物のメソッドのまま呼び、rd/wr/L だけを差し替えて C 断片を得る。断片だけを実行する driver を gcc で作り、
rcr_native_check.py と同じ乱数 (8/16/32/64bit・count 0..255・乱数の上位 bit・乱数 flags) で実機の 64bit レジスタ全体と CF/OF/ZF/SF/PF を比べる。
あわせて断片に SETZSP が無いこと、gcc と clang の -Wshift-count-overflow 警告が無いことを確かめる。"""
import argparse, importlib.util, os, platform, random, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MASK64 = (1 << 64) - 1
MASK = {8: 0xff, 16: 0xffff, 32: 0xffffffff, 64: MASK64}
FLAG_BITS = (1 << 0) | (1 << 2) | (1 << 6) | (1 << 7) | (1 << 11)  # CF PF ZF SF OF

NATIVE = r'''
#include <stdint.h>
#include <stdio.h>
int main(void) {
    int w; unsigned long long val, cnt, fin;
    while (scanf("%d %llx %llu %llx", &w, &val, &cnt, &fin) == 4) {
        unsigned long long fout = 0, res = 0, f = fin;
        uint64_t v = (uint64_t)val;
        switch (w) {
        case 8:
            asm volatile("pushq %[f]\n\tpopfq\n\trcrb %%cl, %b[v]\n\tpushfq\n\tpopq %[fo]\n"
                         : [v] "+r"(v), [fo] "=r"(fout) : [f] "r"(f), "c"(cnt) : "cc", "memory"); break;
        case 16:
            asm volatile("pushq %[f]\n\tpopfq\n\trcrw %%cl, %w[v]\n\tpushfq\n\tpopq %[fo]\n"
                         : [v] "+r"(v), [fo] "=r"(fout) : [f] "r"(f), "c"(cnt) : "cc", "memory"); break;
        case 32:
            asm volatile("pushq %[f]\n\tpopfq\n\trcrl %%cl, %k[v]\n\tpushfq\n\tpopq %[fo]\n"
                         : [v] "+r"(v), [fo] "=r"(fout) : [f] "r"(f), "c"(cnt) : "cc", "memory"); break;
        default:
            asm volatile("pushq %[f]\n\tpopfq\n\trcrq %%cl, %q[v]\n\tpushfq\n\tpopq %[fo]\n"
                         : [v] "+r"(v), [fo] "=r"(fout) : [f] "r"(f), "c"(cnt) : "cc", "memory"); break;
        }
        res = v;
        printf("%llx %llx\n", res, fout & 0xfffULL);
    }
    return 0;
}
'''


class Op:
    def __init__(self, size, kind):
        self.size, self.kind = size, kind


class Emit:
    """FnLift の rd/wr/L の代わり。断片を文字列で集める。"""
    def __init__(self):
        self.body = []

    def rd(self, ins, op, size=None):
        return 'IN_CNT' if op.kind == 'cnt' else 'IN_A'

    def wr(self, ins, op, val, size=None):
        if op.size == 4:
            return 'OUT_A = (uint64_t)(uint32_t)(%s);' % val
        if op.size == 8:
            return 'OUT_A = (uint64_t)(%s);' % val
        return 'OUT_A = (IN_A & 0x%xULL) | (uint64_t)(%s);' % (MASK64 ^ MASK[op.size * 8], val)

    def L(self, s):
        self.body.append(s)


def load_module(path):
    spec = importlib.util.spec_from_file_location('ott_x64c_under_test', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def emit_body(mod, w):
    e = Emit()
    ops = [Op(w // 8, 'dst'), Op(1, 'cnt')]
    mod.FnLift.i_rcr(e, None, ops)
    return ' '.join(e.body)


def driver(mod):
    fns = []
    for w, name in ((8, 'rcr8'), (16, 'rcr16'), (32, 'rcr32'), (64, 'rcr64')):
        fns.append('static void %s(void) { %s }' % (name, emit_body(mod, w)))
    return r'''
#include <stdint.h>
#include <stdio.h>
#define PAR8(x) (!__builtin_parity((uint8_t)(x)))
#define SETZSP(W, r) do { fZF = ((uint##W##_t)(r) == 0); fSF = (((uint##W##_t)(r)) >> (W - 1)) & 1; fPF = PAR8(r); } while (0)
static uint8_t fCF, fOF, fZF, fSF, fPF;
static uint64_t IN_A, IN_CNT, OUT_A;
''' + '\n'.join(fns) + r'''
int main(void) {
    int w; unsigned long long val, cnt, fin;
    while (scanf("%d %llx %llu %llx", &w, &val, &cnt, &fin) == 4) {
        IN_A = val; IN_CNT = cnt; OUT_A = val;
        fCF = fin & 1; fPF = (fin >> 2) & 1; fZF = (fin >> 6) & 1; fSF = (fin >> 7) & 1; fOF = (fin >> 11) & 1;
        switch (w) {
        case 8: rcr8(); break;
        case 16: rcr16(); break;
        case 32: rcr32(); break;
        default: rcr64(); break;
        }
        printf("%llx %llx\n", (unsigned long long)OUT_A,
               (unsigned long long)(fCF | (fPF << 2) | (fZF << 6) | (fSF << 7) | (fOF << 11)));
    }
    return 0;
}
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--module', default=os.path.join(HERE, 'x64c.py'))
    ap.add_argument('--n', type=int, default=4000)
    a = ap.parse_args()
    if platform.machine() not in ('x86_64', 'AMD64'):
        print('SKIP rcr emit check (host is %s)' % platform.machine())
        return 0
    mod = load_module(a.module)
    D = tempfile.mkdtemp(prefix='ott_rcr_emit_', dir=os.environ.get('RUNNER_TEMP') or None)
    src = os.path.join(D, 'rcr_ott.c')
    open(src, 'w').write(driver(mod))
    nsrc = os.path.join(D, 'rcr_native.c')
    open(nsrc, 'w').write(NATIVE)
    exe, nexe = os.path.join(D, 'rcr_ott'), os.path.join(D, 'rcr_native')
    cc = subprocess.run(['gcc', '-std=gnu11', '-O1', '-mno-red-zone', '-Wall', '-o', exe, src], capture_output=True, text=True)
    if cc.returncode != 0:
        print(cc.stderr[:2000]); return 1
    warn = []
    for cmd in (['gcc'], ['clang']):
        r = subprocess.run(cmd + ['-std=gnu11', '-O1', '-Wall', '-Wshift-count-overflow', '-c', src, '-o', os.path.join(D, 'w.o')],
                           capture_output=True, text=True)
        if r.returncode != 0 and 'shift-count-overflow' not in r.stderr:
            print(r.stderr[:2000]); return 1
        warn.append((cmd[0], r.stderr.count('shift-count-overflow')))
    subprocess.run(['gcc', '-std=gnu11', '-O1', '-mno-red-zone', '-o', nexe, nsrc], capture_output=True, text=True, check=True)
    random.seed(3125)
    cases = []
    for _ in range(a.n):
        w = random.choice([8, 16, 32, 64])
        cases.append((w, random.getrandbits(64), random.randrange(0, 256), random.getrandbits(12) & FLAG_BITS))
    for cnt in (0, 32, 64, 96):
        cases.append((32, random.getrandbits(64), cnt, random.getrandbits(12) & FLAG_BITS))
    inp = ''.join('%d %x %d %x\n' % c for c in cases)
    hw = [tuple(int(x, 16) for x in l.split()) for l in subprocess.run([nexe], input=inp, capture_output=True, text=True, check=True).stdout.split('\n') if l.strip()]
    ott = [tuple(int(x, 16) for x in l.split()) for l in subprocess.run([exe], input=inp, capture_output=True, text=True, check=True).stdout.split('\n') if l.strip()]
    ok, bad = 0, []
    for (w, av, cnt, fl), (hr, hf), (orr, of) in zip(cases, hw, ott):
        if hr == orr and (hf & FLAG_BITS) == (of & FLAG_BITS):
            ok += 1
        elif len(bad) < 5:
            bad.append((w, hex(av), cnt, hex(fl), hex(hr), hex(hf & FLAG_BITS), hex(orr), hex(of & FLAG_BITS)))
    print('module %s: OTT emitted rcr vs native: pass %d / %d (w=8,16,32,64; count 0..255; 32bit の count 0/32/64/96 を含む; random flags)' % (a.module, ok, len(cases)))
    print('shift-count-overflow warnings: ' + ', '.join('%s %d' % w for w in warn))
    print('SETZSP in emitted rcr: %s' % any('SETZSP' in emit_body(mod, w) for w in (8, 16, 32, 64)))
    for b in bad:
        print('  MISMATCH w=%d a=%s cnt=%d fl=%s hw=%s/%s ott=%s/%s' % b)
    clean = ok == len(cases) and all(n == 0 for _, n in warn) and not any('SETZSP' in emit_body(mod, w) for w in (8, 16, 32, 64))
    return 0 if clean else 1


if __name__ == '__main__':
    sys.exit(main())
