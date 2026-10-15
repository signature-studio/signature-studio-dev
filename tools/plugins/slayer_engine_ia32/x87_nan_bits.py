#!/usr/bin/env python3
"""x87_nan_bits.py: x87_fn_diff.py --special の NaN どうしのビット差 (#4756 PLG-G2-60) を分類する。

  python3 x87_nan_bits.py   (先に python3 x87_fn_diff.py --special を実行して work/x87fn_special/ を作る)

 1. 二項演算 (+ * - /) の NaN 入力 10 種 x 10 種を、native x87 (flds/fadds 等) と wasm 側の double 演算
    (f2d → C の演算 → d2f、ott_x87.h と同じ経路) で実行し、結果の差を数える。
 2. 突合の行 (work/x87fn_special/native_out.txt と wasm_out.txt) で NaN どうしの差を、入力の NaN・inf・0 の有無
    で分類する。 eax と ST(0) の両方を数える。 NaN と数値の混在は別に数える (0 でなければ判定は FAIL)。
"""
import collections, os, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work', 'x87fn_special')
NAN_IN = [0x7FC00000, 0xFFC00000, 0x7FC00001, 0x7F800001, 0xFF800001,
          0x7F800000, 0xFF800000, 0x3F800000, 0x00000000, 0x80000000]

C_NATIVE = r'''
#include <stdio.h>
#include <stdint.h>
#include <string.h>
static uint32_t run(uint32_t a, uint32_t b, int op) {
    volatile float x, y, z;
    memcpy((void*)&x, &a, 4); memcpy((void*)&y, &b, 4);
    switch (op) {
    case 0: __asm__ volatile("flds %1\n\tfadds %2\n\tfstps %0" : "=m"(z) : "m"(x), "m"(y) : "memory"); break;
    case 1: __asm__ volatile("flds %1\n\tfmuls %2\n\tfstps %0" : "=m"(z) : "m"(x), "m"(y) : "memory"); break;
    case 2: __asm__ volatile("flds %1\n\tfsubs %2\n\tfstps %0" : "=m"(z) : "m"(x), "m"(y) : "memory"); break;
    default: __asm__ volatile("flds %1\n\tfdivs %2\n\tfstps %0" : "=m"(z) : "m"(x), "m"(y) : "memory"); break;
    }
    uint32_t o; memcpy(&o, (void*)&z, 4); return o;
}
int main(void) {
    uint32_t v[] = {%s};
    for (int op = 0; op < 4; op++) for (int i = 0; i < 10; i++) for (int j = 0; j < 10; j++)
        printf("%%d %%d %%d %%08x\n", op, i, j, run(v[i], v[j], op));
    return 0;
}
'''

C_MODEL = r'''
#include <stdio.h>
#include <stdint.h>
#include <string.h>
static double f2d(uint32_t u) { float f; memcpy(&f, &u, 4); return (double)f; }
static uint32_t d2f(double d) { float f = (float)d; uint32_t u; memcpy(&u, &f, 4); return u; }
int main(void) {
    uint32_t v[] = {%s};
    for (int op = 0; op < 4; op++) for (int i = 0; i < 10; i++) for (int j = 0; j < 10; j++) {
        volatile double x = f2d(v[i]), y = f2d(v[j]), r;
        switch (op) { case 0: r = x + y; break; case 1: r = x * y; break; case 2: r = x - y; break; default: r = x / y; }
        printf("%%d %%d %%d %%08x\n", op, i, j, d2f(r));
    }
    return 0;
}
'''


def is_nan(u):
    return (u & 0x7F800000) == 0x7F800000 and (u & 0x7FFFFF) != 0


def is_inf(u):
    return (u & 0x7FFFFFFF) == 0x7F800000


def is_zero(u):
    return (u & 0x7FFFFFFF) == 0


def run_c(src_fmt, name, tmp):
    src = src_fmt.replace('%s', ', '.join('0x%08xu' % v for v in NAN_IN)).replace('%%', '%')
    c = os.path.join(tmp, name + '.c')
    exe = os.path.join(tmp, name)
    open(c, 'w').write(src)
    subprocess.run(['gcc', '-O0', '-o', exe, c], check=True)
    return subprocess.run([exe], capture_output=True, text=True, check=True).stdout


def table(text):
    t = {}
    for ln in text.split('\n'):
        p = ln.split()
        if len(p) == 4:
            t[(int(p[0]), int(p[1]), int(p[2]))] = int(p[3], 16)
    return t


def probe():
    with tempfile.TemporaryDirectory() as tmp:
        nat = table(run_c(C_NATIVE, 'nat', tmp))
        mod = table(run_c(C_MODEL, 'mod', tmp))
    both = mixed = 0
    for k, a in nat.items():
        b = mod[k]
        if a == b:
            continue
        if is_nan(a) and is_nan(b):
            both += 1
        else:
            mixed += 1
    print('[probe] 二項演算 %d 組: native と model の差 %d 組 (両方 NaN %d・NaN と数値の混在 %d)' % (
        len(nat), both + mixed, both, mixed))


def classify_run():
    def parse(p):
        return [dict(t.split('=', 1) for t in ln.split()[1:] if '=' in t) for ln in open(p) if ln.strip()]
    nat_p = parse(os.path.join(WORK, 'native_out.txt'))
    wasm_p = parse(os.path.join(WORK, 'wasm_out.txt'))
    scen = [ln.split() for ln in open(os.path.join(WORK, 'scen.txt')) if ln.strip()]
    cnt = collections.Counter()
    mixed = 0
    for i, (n, w) in enumerate(zip(nat_p, wasm_p)):
        for field in ('eax', 'st0'):
            a, b = int(n[field], 16), int(w[field], 16)
            if a == b:
                continue
            if not (is_nan(a) and is_nan(b)):
                mixed += 1
                continue
            args = [int(x, 16) for x in scen[i][2:8]]
            kinds = sorted({'NaN' if is_nan(x) else 'inf' if is_inf(x) else '0'
                            for x in args if is_nan(x) or is_inf(x) or is_zero(x)})
            cnt[(field, scen[i][0], ','.join(kinds))] += 1
    print('[classify] NaN どうしの差 (eax・ST(0)) を VA と入力 a0..a5 に含む特殊値の種類で分類:')
    for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
        print('[classify]   %5d  %-4s 0x%s 入力に含む: %s' % (v, k[0], k[1], k[2]))
    print('[classify] NaN どうし %d 件 / NaN と数値の混在 %d 件' % (sum(cnt.values()), mixed))


if __name__ == '__main__':
    probe()
    if os.path.isfile(os.path.join(WORK, 'native_out.txt')):
        classify_run()
    else:
        print('[classify] skip: 先に python3 x87_fn_diff.py --special を実行する')
