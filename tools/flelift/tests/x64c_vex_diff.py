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


MASKS_W = {8: 0xff, 16: 0xffff, 32: 0xffffffff, 64: MASK}


def rcr_ref(w, a, cnt, F):
    """RCR の参照値 (Intel SDM の疑似コード + 実機 rcr の測定)。
    count は &0x1F (64bit は &0x3F)。マスク後が 0 なら flags 不変。8bit は MOD 9、16bit は MOD 17 で回転量を決める
    (マスク後が 9・17 の倍数なら回転 0 でも CF は不変、OF は更新される)。CF は (W+1)bit 環の最後に落ちたビット、
    OF = MSB(結果) ^ MSB-1(結果) (SDM は 1bit のみ定義。実機は count>1 でも同式)。ZF/SF/PF は変えない。"""
    c = cnt & (0x3F if w == 64 else 0x1F)
    if c == 0:
        return a, dict(F)
    if w == 8:
        c %= 9
    elif w == 16:
        c %= 17
    v = (F['CF'] << w) | a
    for _ in range(c):
        v = (v >> 1) | ((v & 1) << w)
    r = v & MASKS_W[w]
    nf = dict(F)
    nf['CF'] = (v >> w) & 1
    nf['OF'] = ((r >> (w - 1)) ^ (r >> (w - 2))) & 1
    return r, nf


def fresh_state():
    st = {'X': [[random.getrandbits(64), random.getrandbits(64)] for _ in range(16)],
          'YL': [[random.getrandbits(64), random.getrandbits(64)] for _ in range(16)],
          'R': [random.getrandbits(64) for _ in range(16)],
          'F': {k: random.getrandbits(1) for k in ('ZF', 'SF', 'CF', 'OF', 'PF')}}
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

    def rcr_case(asm, reg, w, count_of, val=None, cf=None, flags=None, rcx=None):
        def prep(st):
            if val is not None:
                st['R'][reg] = val
            if cf is not None:
                st['F']['CF'] = cf
            if flags is not None:
                st['F'].update(flags)
            if rcx is not None:
                st['R'][1] = rcx
            return st

        def e(st):
            s = clone(st)
            r, f = rcr_ref(w, st['R'][reg] & MASKS_W[w], count_of(st), st['F'])
            keep = 0 if w >= 32 else st['R'][reg] & ~MASKS_W[w] & MASK
            s['R'][reg] = keep | r
            s['F'] = f
            return s
        add(asm, e, prep)

    rcr_case('rcr edx, 1', 2, 32, lambda st: 1, val=0xdead00000001, cf=0,
             flags={'ZF': 1, 'SF': 1, 'PF': 0, 'OF': 0})
    rcr_case('rcr edx, 1', 2, 32, lambda st: 1, val=0xdead00000001, cf=1,
             flags={'ZF': 0, 'SF': 0, 'PF': 1, 'OF': 1})
    rcr_case('rcr edx, 32', 2, 32, lambda st: 32, val=1, cf=0)
    rcr_case('rcr edx, 33', 2, 32, lambda st: 33, val=1, cf=0)
    rcr_case('rcr edx, 0', 2, 32, lambda st: 0)
    rcr_case('rcr edx, cl', 2, 32, lambda st: st['R'][1] & 0xff, val=1, cf=0, rcx=33)
    rcr_case('rcr edx, cl', 2, 32, lambda st: st['R'][1] & 0xff, val=1, cf=0, rcx=32)
    rcr_case('rcr dl, 9', 2, 8, lambda st: 9)
    rcr_case('rcr dl, 18', 2, 8, lambda st: 18)
    rcr_case('rcr dl, 10', 2, 8, lambda st: 10, cf=1)
    rcr_case('rcr ax, 17', 0, 16, lambda st: 17)
    rcr_case('rcr ax, 31', 0, 16, lambda st: 31, cf=1)
    rcr_case('rcr rax, 1', 0, 64, lambda st: 1, val=0x8000000000000001, cf=0)
    rcr_case('rcr rax, 1', 0, 64, lambda st: 1, val=0x8000000000000001, cf=1)
    rcr_case('rcr rax, 64', 0, 64, lambda st: 64)
    rcr_case('rcr rax, 65', 0, 64, lambda st: 65, cf=1)
    rcr_case('rcr rax, 63', 0, 64, lambda st: 63)
    rcr_case('rcr rax, 2', 0, 64, lambda st: 2)
    rcr_case('rcr edx, 5', 2, 32, lambda st: 5)

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

    def e_subsd_dd(st):
        s = clone(st)
        s['X'][3] = [dbits(fval(st['X'][5][0]) - fval(st['X'][3][0])), st['X'][5][1]]
        s['YL'][3] = [0, 0]
        return s
    add('vsubsd xmm3, xmm5, xmm3', e_subsd_dd)

    def e_divsd_dd(st):
        s = clone(st)
        s['X'][4] = [dbits(fval(st['X'][6][0]) / fval(st['X'][4][0])), st['X'][6][1]]
        s['YL'][4] = [0, 0]
        return s
    def p_divsd_dd(st):
        st['X'][6][0] = dbits(7.0); st['X'][4][0] = dbits(2.0)
        return st
    add('vdivsd xmm4, xmm6, xmm4', e_divsd_dd, p_divsd_dd)

    def p_ss_dd(st):
        st['X'][5][0] = fbits32(7.0) | (0x1234 << 32); st['X'][3][0] = fbits32(2.0) | (0x0badc0de << 32)
        return st
    def e_subss_dd(st):
        s = clone(st)
        lo5 = st['X'][5][0]; lo3 = st['X'][3][0]
        s['X'][3] = [(lo5 & 0xffffffff00000000) | fbits32(f32val(lo5) - f32val(lo3)), st['X'][5][1]]
        s['YL'][3] = [0, 0]
        return s
    add('vsubss xmm3, xmm5, xmm3', e_subss_dd, p_ss_dd)

    def p_ssdiv_dd(st):
        st['X'][6][0] = fbits32(7.0) | (0x5678 << 32); st['X'][4][0] = fbits32(2.0) | (0x9abc << 32)
        return st
    def e_divss_dd(st):
        s = clone(st)
        lo6 = st['X'][6][0]; lo4 = st['X'][4][0]
        s['X'][4] = [(lo6 & 0xffffffff00000000) | fbits32(f32val(lo6) / f32val(lo4)), st['X'][6][1]]
        s['YL'][4] = [0, 0]
        return s
    add('vdivss xmm4, xmm6, xmm4', e_divss_dd, p_ssdiv_dd)

    def e_xorps(st):
        s = clone(st)
        s['X'][1] = [st['X'][2][0] ^ st['X'][3][0], st['X'][2][1] ^ st['X'][3][1]]
        s['YL'][1] = [0, 0]
        return s
    add('vxorps xmm1, xmm2, xmm3', e_xorps)

    def e_cvtt(st):
        s = clone(st)
        lo = (math.trunc(fval(st['X'][6][0])) & 0xffffffff) | ((math.trunc(fval(st['X'][6][1])) & 0xffffffff) << 32)
        s['X'][5] = [lo, 0]
        s['YL'][5] = [0, 0]
        return s
    def p_cvtt(st):
        st['X'][6] = [dbits(2.5), dbits(-3.75)]
        return st
    add('vcvttpd2dq xmm5, xmm6', e_cvtt, p_cvtt)

    QNAN = 0x7ff8000000000000
    def e_cmpneq_nan(st):
        s = clone(st)
        s['X'][0] = [MASK, 0]
        return s
    def p_cmpneq_nan(st):
        st['X'][0] = [QNAN, dbits(1.0)]; st['X'][1] = [QNAN, dbits(1.0)]
        return st
    add('cmpneqpd xmm0, xmm1', e_cmpneq_nan, p_cmpneq_nan)

    def e_cmpneq_ne(st):
        s = clone(st)
        s['X'][0] = [0, MASK]
        return s
    def p_cmpneq_ne(st):
        st['X'][0] = [dbits(1.0), dbits(2.0)]; st['X'][1] = [dbits(1.0), dbits(3.0)]
        return st
    add('cmpneqpd xmm0, xmm1', e_cmpneq_ne, p_cmpneq_ne)

    def e_vpsrldq(st):
        s = clone(st)
        v = (st['X'][3][1] << 64) | st['X'][3][0]
        r = v >> 40
        s['X'][2] = [r & MASK, r >> 64]
        s['YL'][2] = [0, 0]
        return s
    add('vpsrldq xmm2, xmm3, 5', e_vpsrldq)
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
