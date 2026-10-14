#!/usr/bin/env python3
"""x64c (flelift) の VEX/legacy 追加 handler の差分テスト (KH-38 #3065)。
実行: python3 tools/flelift/tests/x64c_vex_diff.py (GNU as / objcopy / gcc / python3.13+ の math.fma が必要)。
各命令を GNU as で機械語にし、x64c の FnLift で C に落として fle_cpu runtime と共に実行し、
Intel SDM の意味から計算した参照値 (Python, math.fma 使用) と全 state を比較する。"""
import sys, os, subprocess, math, struct, random

import tempfile
WS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
sys.path.insert(0, os.path.join(WS, 'tools/flelift'))
import capstone
import x64c as L

L.IMG = 0x1000; L.SHIFT = 0; L.IMG_SIZE = 0x100000
D = tempfile.mkdtemp(prefix='x64c_vex_diff_', dir=os.environ.get('RUNNER_TEMP') or None)
BASE = 0x1000
MASK = (1 << 64) - 1
random.seed(3065)

NICE = [1.25, -2.5, 3.75, 0.5, 7.0, -0.125, 10.0, 2.0, 3.0, -1.0]


def dbits(x):
    return struct.unpack('<Q', struct.pack('<d', x))[0]


def fval(bits):
    return struct.unpack('<d', struct.pack('<Q', bits))[0]


def fbits32(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def f32val(b):
    return struct.unpack('<f', struct.pack('<I', b & 0xffffffff))[0]


def fresh_state():
    st = {'X': [[random.getrandbits(64), random.getrandbits(64)] for _ in range(16)],
          'YL': [[random.getrandbits(64), random.getrandbits(64)] for _ in range(16)],
          'R': [random.getrandbits(64) for _ in range(16)],
          'F': {'ZF': 0, 'SF': 0, 'CF': 0, 'OF': 0, 'PF': 0}}
    for i in range(16):
        st['X'][i][0] = dbits(random.choice(NICE))
    return st


def clone(st):
    return {'X': [list(x) for x in st['X']], 'YL': [list(x) for x in st['YL']],
            'R': list(st['R']), 'F': dict(st['F'])}


def set_nice_lo(st, i, v):
    st['X'][i][0] = dbits(v)


# (asm, prep(st) -> st, expect(st0) -> expected state)
def cases():
    C = []

    def add(asm, expect, prep=None):
        C.append((asm, prep, expect))

    def e_vaddsd(st):
        s = clone(st)
        s['X'][2] = [dbits(fval(st['X'][1][0]) + fval(st['X'][3][0])), st['X'][1][1]]
        s['YL'][2] = [0, 0]
        return s
    add('vaddsd xmm2, xmm1, xmm3', e_vaddsd)

    def e_vaddsd_alias(st):
        s = clone(st)
        s['X'][2] = [dbits(fval(st['X'][2][0]) + fval(st['X'][1][0])), st['X'][1][1]]
        s['YL'][2] = [0, 0]
        return s
    add('vaddsd xmm2, xmm1, xmm2', e_vaddsd_alias)

    def e_vmulpd(st):
        s = clone(st)
        s['X'][4] = [dbits(fval(st['X'][5][0]) * fval(st['X'][6][0])), dbits(fval(st['X'][5][1]) * fval(st['X'][6][1]))]
        s['YL'][4] = [0, 0]
        return s
    def p_vmulpd(st):
        for i in (5, 6):
            st['X'][i] = [dbits(random.choice(NICE)), dbits(random.choice(NICE))]
        return st
    add('vmulpd xmm4, xmm5, xmm6', e_vmulpd, p_vmulpd)

    def e_fma213(st):
        s = clone(st)
        s['X'][0] = [dbits(math.fma(fval(st['X'][2][0]), fval(st['X'][0][0]), fval(st['X'][3][0]))), st['X'][0][1]]
        s['YL'][0] = [0, 0]
        return s
    add('vfmadd213sd xmm0, xmm2, xmm3', e_fma213)

    def e_fnmadd231(st):
        s = clone(st)
        s['X'][0] = [dbits(math.fma(-fval(st['X'][2][0]), fval(st['X'][3][0]), fval(st['X'][0][0]))), st['X'][0][1]]
        s['YL'][0] = [0, 0]
        return s
    add('vfnmadd231sd xmm0, xmm2, xmm3', e_fnmadd231)

    def e_fmsub213(st):
        s = clone(st)
        s['X'][5] = [dbits(math.fma(fval(st['X'][6][0]), fval(st['X'][5][0]), -fval(st['X'][1][0]))), st['X'][5][1]]
        s['YL'][5] = [0, 0]
        return s
    add('vfmsub213sd xmm5, xmm6, xmm1', e_fmsub213)

    def e_psrlq(st):
        s = clone(st)
        s['X'][3] = [st['X'][0][0] >> 52, st['X'][0][1] >> 52]
        s['YL'][3] = [0, 0]
        return s
    add('vpsrlq xmm3, xmm0, 0x34', e_psrlq)

    def e_pshufd(st):
        s = clone(st)
        a0 = st['X'][1][0] & 0xffffffff; a1 = st['X'][1][0] >> 32
        s['X'][4] = [a0 | (a1 << 32), a0 | (a1 << 32)]
        s['YL'][4] = [0, 0]
        return s
    add('vpshufd xmm4, xmm1, 0x44', e_pshufd)

    def e_movq(st):
        s = clone(st)
        s['X'][0] = [st['R'][0], 0]
        s['YL'][0] = [0, 0]
        return s
    add('vmovq xmm0, rax', e_movq)

    def e_movd(st):
        s = clone(st)
        s['X'][2] = [st['R'][2] & 0xffffffff, 0]
        s['YL'][2] = [0, 0]
        return s
    add('vmovd xmm2, edx', e_movd)

    def e_insert(st):
        s = clone(st)
        s['X'][1] = list(st['X'][2])
        s['YL'][1] = list(st['X'][3])
        return s
    add('vinsertf128 ymm1, ymm2, xmm3, 1', e_insert)

    def e_rcr(st):
        s = clone(st)
        edx = st['R'][2] & 0xffffffff
        cf = st['F']['CF']
        v = (cf << 32) | edx
        b = v & 1
        v = (v >> 1) | (b << 32)
        ncf = (v >> 32) & 1
        r = v & 0xffffffff
        s['R'][2] = r
        s['F']['CF'] = ncf
        s['F']['OF'] = ((r >> 31) & 1) ^ ncf
        s['F']['ZF'] = int(r == 0); s['F']['SF'] = (r >> 31) & 1
        s['F']['PF'] = 1 if bin(r & 0xff).count('1') % 2 == 0 else 0
        return s
    add('rcr edx, 1', e_rcr)

    def e_movsld(st):
        s = clone(st)
        d0 = st['X'][1][0] & 0xffffffff; d2 = st['X'][1][1] & 0xffffffff
        s['X'][0] = [d0 | (d0 << 32), d2 | (d2 << 32)]
        return s
    add('movsldup xmm0, xmm1', e_movsld)

    def e_cmple(st):
        s = clone(st)
        out = [0, 0]
        for k in range(4):
            a = f32val(st['X'][1][k // 2] >> (32 * (k % 2)))
            b = f32val(st['X'][2][k // 2] >> (32 * (k % 2)))
            m = 0xffffffff if a <= b else 0
            out[k // 2] |= m << (32 * (k % 2))
        s['X'][1] = out
        return s
    def p_cmple(st):
        vals1 = [1.0, 3.0, -2.0, 5.0]; vals2 = [2.0, 2.0, -2.0, 4.0]
        for i, vs in ((1, vals1), (2, vals2)):
            lo = fbits32(vs[0]) | (fbits32(vs[1]) << 32); hi = fbits32(vs[2]) | (fbits32(vs[3]) << 32)
            st['X'][i] = [lo, hi]
        return st
    add('cmpleps xmm1, xmm2', e_cmple, p_cmple)

    def e_ucomi(st):
        s = clone(st)
        a = fval(st['X'][0][0]); b = fval(st['X'][1][0])
        s['F'] = {'ZF': 0, 'PF': 0, 'CF': 0, 'SF': 0, 'OF': 0}
        if a > b:
            pass
        elif a < b:
            s['F']['CF'] = 1
        else:
            s['F']['ZF'] = 1
        return s
    def p_ucomi(st):
        st['X'][0][0] = dbits(3.0); st['X'][1][0] = dbits(1.0)
        return st
    add('vucomisd xmm0, xmm1', e_ucomi, p_ucomi)

    def e_movsd_rr(st):
        s = clone(st)
        s['X'][5] = [st['X'][3][0], st['X'][5][1]]
        s['YL'][5] = [0, 0]
        return s
    add('vmovsd xmm5, xmm5, xmm3', e_movsd_rr)

    def e_subsd(st):
        s = clone(st)
        s['X'][3] = [dbits(fval(st['X'][5][0]) - fval(st['X'][2][0])), st['X'][5][1]]
        s['YL'][3] = [0, 0]
        return s
    add('vsubsd xmm3, xmm5, xmm2', e_subsd)
    return C


def main():
    cs = cases()
    code = bytearray(0x10000)
    texts = []
    vas = []
    for k, (asm, _, _) in enumerate(cs):
        va = BASE + 0x100 * k
        src = os.path.join(D, 'case%d.s' % k)
        with open(src, 'w') as fh:
            fh.write('.intel_syntax noprefix\n.text\n%s\nret\n' % asm)
        subprocess.run(['as', '-o', src[:-2] + '.o', src], check=True)
        subprocess.run(['objcopy', '-O', 'binary', '-j', '.text', src[:-2] + '.o', src[:-2] + '.bin'], check=True)
        b = open(src[:-2] + '.bin', 'rb').read()
        code[va - BASE:va - BASE + len(b)] = b
        vas.append(va)

    class FakePE:
        iat = {}
        img = b''

        def bytes_at(self, va, n):
            o = va - BASE
            return bytes(code[o:o + n])

    pe = FakePE()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); md.detail = True
    for va in vas:
        f = L.FnLift(pe, va, {va}, md, {})
        texts.append(f.lift())
        if f.unsup:
            print('UNSUP', va, dict(f.unsup))

    rng_states = [fresh_state() for _ in cs]
    lines = ['#include "fle_cpu.h"', '#include <stdio.h>']
    lines += texts
    lines.append('int main(void) {')
    for k, (asm, prep, expect) in enumerate(cs):
        st = rng_states[k]
        if prep:
            st = prep(st)
            rng_states[k] = st
        for i in range(16):
            lines.append('  X[%d].q[0]=0x%xULL; X[%d].q[1]=0x%xULL; YL[%d].q[0]=0x%xULL; YL[%d].q[1]=0x%xULL; R[%d]=0x%xULL;' % (
                i, st['X'][i][0], i, st['X'][i][1], i, st['YL'][i][0], i, st['YL'][i][1], i, st['R'][i]))
        lines.append('  fZF=%d; fSF=%d; fCF=%d; fOF=%d; fPF=%d;' % (st['F']['ZF'], st['F']['SF'], st['F']['CF'], st['F']['OF'], st['F']['PF']))
        lines.append('  f_%x();' % vas[k])
        lines.append('  printf("C %d");' % k)
        for i in range(16):
            lines.append('  printf(" %%llx %%llx %%llx %%llx %%llx", (unsigned long long)X[%d].q[0], (unsigned long long)X[%d].q[1], (unsigned long long)YL[%d].q[0], (unsigned long long)YL[%d].q[1], (unsigned long long)R[%d]);' % (i, i, i, i, i))
        lines.append('  printf(" %d %d %d %d %d\\n", fZF, fSF, fCF, fOF, fPF);')
    lines.append('  return 0;\n}')
    cfile = os.path.join(D, 'harness.c')
    open(cfile, 'w').write('\n'.join(lines) + '\n')
    rt = os.path.join(WS, 'tools/flelift/rt')
    exe = os.path.join(D, 'harness')
    cc = subprocess.run(['gcc', '-std=gnu11', '-O0', '-w', '-I', rt, cfile, os.path.join(rt, 'fle_cpu.c'),
                         '-o', exe, '-lm'], capture_output=True, text=True)
    if cc.returncode != 0:
        print(cc.stderr[:3000]); sys.exit(1)
    out = subprocess.run([exe], capture_output=True, text=True).stdout.splitlines()
    ok = 0; bad = 0
    for k, (asm, prep, expect) in enumerate(cs):
        line = [l for l in out if l.startswith('C %d ' % k)]
        if not line:
            print('NO OUTPUT', asm); bad += 1; continue
        vals = line[0].split()[2:]
        got_X = []; got_YL = []; got_R = []
        p = 0
        for i in range(16):
            x0, x1, y0, y1, r = (int(vals[p + j], 16) for j in range(5)); p += 5
            got_X.append([x0, x1]); got_YL.append([y0, y1]); got_R.append(r)
        fl = [int(v) for v in vals[p:p + 5]]
        got = {'X': got_X, 'YL': got_YL, 'R': got_R, 'F': dict(zip(['ZF', 'SF', 'CF', 'OF', 'PF'], fl))}
        exp = expect(clone(rng_states[k]))
        exp['R'][4] = (exp['R'][4] + 8) & MASK   # ret が RSP を 8 進める
        diffs = []
        for i in range(16):
            if exp['X'][i] != got['X'][i]: diffs.append('X%d exp %x %x got %x %x' % (i, *exp['X'][i], *got['X'][i]))
            if exp['YL'][i] != got['YL'][i]: diffs.append('YL%d exp %x %x got %x %x' % (i, *exp['YL'][i], *got['YL'][i]))
            if exp['R'][i] != got['R'][i]: diffs.append('R%d exp %x got %x' % (i, exp['R'][i], got['R'][i]))
        for fk in ('ZF', 'SF', 'CF', 'OF', 'PF'):
            if exp['F'][fk] != got['F'][fk]: diffs.append('%s exp %d got %d' % (fk, exp['F'][fk], got['F'][fk]))
        if diffs:
            bad += 1
            print('FAIL', asm); [print('   ', d) for d in diffs[:6]]
        else:
            ok += 1
            print('PASS', asm)
    print('SUMMARY pass %d fail %d' % (ok, bad))


if __name__ == '__main__':
    main()
