#!/usr/bin/env python3
"""probe_ba05_4923.py: #4923 (PLG-G2-68)。 0x1000ba05 は edx の指す 8 バイトの double を読む (ポインタ引数)。
既存の x87_fn_native.c / x87_fn_glue.c は call_guest で edx=0 に固定するため、native が rc -11 で落ちる (#4087)。
本プローブは、その 1 行だけを変えた複製 (edx = OBJ 窓の番地) で native と wasm を同じ入力に通して突合する。
既存の harness・ゲートは変えない (複製は work/ba05_4923/ に作る)。

  python3 lift_text.py && python3 probe_ba05_4923.py   (前提: work/lift_text/ott_lifted.c・gcc -m32・emcc・pefile)
出力: work/ba05_4923/ (gitignore)。
入力: edx = OBJ (0x10F80000)。 OBJ 窓の先頭 8 バイトに double を置く (符号・指数の種類を変える)。 seed 4923。
"""
import os, random, re, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import x87_fn_diff as D

VA = 0x1000BA05
OBJ = D.OBJ
OBJ_WIN = D.OBJ_WIN
N = 2000
SEED = 4923
WORK = os.path.join(HERE, 'work', 'ba05_4923')
KINDS = ['normal', 'inf', 'nan', 'zero', 'denorm', 'big']


def dbl_bits(kind, rng):
    sign = rng.getrandbits(1) << 63
    if kind == 'normal':
        exp, mant = rng.randint(1, 2046), rng.getrandbits(52)
    elif kind == 'inf':
        exp, mant = 0x7FF, 0
    elif kind == 'nan':
        exp, mant = 0x7FF, rng.getrandbits(52) | 1
    elif kind == 'zero':
        exp, mant = 0, 0
    elif kind == 'denorm':
        exp, mant = 0, rng.getrandbits(52) | 1
    else:
        exp, mant = rng.randint(0x7F0, 0x7FE), rng.getrandbits(52)
    return sign | (exp << 52) | mant


def rows():
    rng = random.Random(SEED)
    out = []
    for i in range(N):
        kind = KINDS[i % len(KINDS)]
        head = struct.pack('<Q', dbl_bits(kind, rng))
        rest = bytes(rng.getrandbits(8) for _ in range(OBJ_WIN - 8))
        init = head + rest
        line = '%08x %08x %s %s' % (VA, OBJ, ' '.join('%08x' % 0 for _ in range(6)), init.hex())
        out.append((kind, line))
    return out


def make_variants():
    nat_src = open(os.path.join(HERE, 'x87_fn_native.c')).read()
    old = '" mov %edx,%ecx\\n xor %eax,%eax\\n xor %edx,%edx\\n mov $0x10F00000-0x1000,%ebp\\n"'
    new = '" mov %edx,%ecx\\n xor %eax,%eax\\n mov $0x10F00000-0x1000,%ebp\\n"'
    assert nat_src.count(old) == 1, 'native call_guest の行が見つからない'
    open(os.path.join(WORK, 'native_edx.c'), 'w').write(nat_src.replace(old, new))
    glue = open(os.path.join(HERE, 'x87_fn_glue.c')).read()
    assert glue.count('R[RCX] = ecx; R[RAX] = 0; R[RDX] = 0;') == 1, 'glue の行が見つからない'
    open(os.path.join(WORK, 'glue_edx.c'), 'w').write(glue.replace('R[RCX] = ecx; R[RAX] = 0; R[RDX] = 0;', 'R[RCX] = ecx; R[RAX] = 0; R[RDX] = ecx;'))


def run(cmd, timeout):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr)[-800:]


def parse(path):
    out = []
    for ln in open(path).read().splitlines():
        t = ln.split()
        d = {}
        for tok in t[1:]:
            if '=' in tok:
                k, v = tok.split('=', 1)
                d[k] = v
        out.append(d)
    return out


def main():
    os.makedirs(WORK, exist_ok=True)
    if not os.path.isfile(D.LIFT):
        sys.exit('[ba05] FAIL: %s が無い (lift_text.py を先に実行)' % D.LIFT)
    img_p = os.path.join(WORK, 'image.bin')
    open(img_p, 'wb').write(D.pe_image())
    rs = rows()
    sp = os.path.join(WORK, 'scen.txt')
    open(sp, 'w').write('\n'.join(r[1] for r in rs) + '\n')
    make_variants()
    nat = os.path.join(WORK, 'native_edx')
    rc, msg = run(['gcc', '-m32', '-O1', '-fno-pic', '-fno-pie', '-fno-stack-protector', '-fcf-protection=none',
                   '-fno-asynchronous-unwind-tables', '-ffreestanding', '-nostdlib', '-static', '-no-pie',
                   '-o', nat, os.path.join(WORK, 'native_edx.c')], 300)
    if rc:
        sys.exit('[ba05] native build rc %d %s' % (rc, msg))
    mjs = os.path.join(WORK, 'wasm_edx.cjs')
    rc, msg = run(['emcc', '-O1', '-ffp-contract=off', '-fno-fast-math', '-w', '-I', D.RT,
                   '-DLIFT_C="%s"' % D.LIFT, os.path.join(WORK, 'glue_edx.c'), os.path.join(D.RT, 'ott_cpu.c'),
                   '-sENVIRONMENT=node', '-sMODULARIZE=1', '-sEXPORT_NAME=createModule', '-sEXIT_RUNTIME=0',
                   '-sEXPORTED_FUNCTIONS=_ott_call32x,_ott_x87_st0,_ott_x87_st0d_hi,_ott_x87_st0d_lo,_ott_x87_depth',
                   '-sEXPORTED_RUNTIME_METHODS=HEAPU8',
                   '-sGLOBAL_BASE=%d' % 0x11000000, '-sSTACK_SIZE=2097152', '-sINITIAL_MEMORY=%d' % 0x14000000,
                   '-sALLOW_MEMORY_GROWTH=0', '-o', mjs], 900)
    if rc:
        sys.exit('[ba05] wasm build rc %d %s' % (rc, msg))
    no, wo = os.path.join(WORK, 'native.out'), os.path.join(WORK, 'wasm.out')
    nrc, nmsg = run([nat, img_p, sp, no], 300)
    wrc, wmsg = run(['node', '--liftoff-only', os.path.join(HERE, 'x87_fn_entry_wasm.mjs'), mjs, img_p, sp, wo], 600)
    print('[ba05] native rc %d | wasm rc %d %s' % (nrc, wrc, (wmsg.strip().splitlines() or [''])[-1][:160] if wrc else ''))
    if nrc or wrc or not os.path.exists(no) or not os.path.exists(wo):
        sys.exit(1)
    nat_rows, wa_rows = parse(no), parse(wo)
    print('[ba05] 行数 native %d wasm %d 入力 %d' % (len(nat_rows), len(wa_rows), N))
    tot = {}
    bad = []
    for i, ((kind, _), a, b) in enumerate(zip(rs, nat_rows, wa_rows)):
        t = tot.setdefault(kind, [0, 0])
        t[1] += 1
        same = all(a.get(k) == b.get(k) for k in ('eax', 'st0d', 'd', 'mem'))
        if same:
            t[0] += 1
        elif len(bad) < 5:
            bad.append((i, kind, {k: (a.get(k), b.get(k)) for k in ('eax', 'st0d', 'd') if a.get(k) != b.get(k)},
                        a.get('mem') == b.get('mem')))
    for kind in KINDS:
        s, n = tot.get(kind, [0, 0])
        print('[ba05] %-7s 一致 %d / %d' % (kind, s, n))
    print('[ba05] 全体 一致 %d / %d (eax・st0d・d・OBJ 窓)' % (sum(v[0] for v in tot.values()), sum(v[1] for v in tot.values())))
    for x in bad:
        print('[ba05] 不一致例 行%d %s %s mem一致=%s' % x)


if __name__ == '__main__':
    main()
