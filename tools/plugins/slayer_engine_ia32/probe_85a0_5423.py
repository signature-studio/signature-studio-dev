#!/usr/bin/env python3
"""probe_85a0_5423.py: #5423 (PLG-G2-78)。 0x100085a0 は [ecx+0x520cc8] のポインタ P を読み、
[P + 4*(a0 + 34*[ecx+0x18]) + 0x18] の float を ST(0) に積む。 P は窓 (ecx の 0x540 B) の外 (ecx+0x520cc8) にある。
既存の x87_fn_native.c / x87_fn_entry_wasm.mjs は窓の外に語を書く経路が無いため、rc -11 で落ちる (#4147 / #4922)。

本プローブは、既存の harness を変えずに、その 1 語だけを書く複製を work/85a0_5423/ に作る:
  - 行の a1 (この関数は読まない) を P とし、ecx = WIDE_BASE の行で ecx+0x520cc8 に P を書く (native・wasm とも同じ位置)。
  - 窓の +0x18 の語 w と a0 でインデックスを決める。 P は image 内の .data 相当の番地 (IMG_BASE + [0x1000, 0x60000))。
  - 既定 harness でも同じ入力を流し、segfault (rc -11) を確かめる (ベースライン)。

  python3 lift_text.py && python3 probe_85a0_5423.py
出力: work/85a0_5423/ (gitignore)。 seed 5423。
"""
import os, random, re, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import x87_fn_diff as D

VA = 0x100085A0
ECX = D.ECX_HI
PTR_OFF = 0x520CC8
OBJ_WIN = D.OBJ_WIN
N = 2000
SEED = 5423
WORK = os.path.join(HERE, 'work', '85a0_5423')


def rows():
    rng = random.Random(SEED)
    out = []
    for i in range(N):
        a0 = rng.randrange(16)
        p = D.IMG_BASE + rng.randrange(0x1000, 0x60000, 4)
        words = [struct.unpack('<I', struct.pack('<f', rng.uniform(-1000, 1000)))[0] for _ in range(OBJ_WIN // 4)]
        words[0x18 // 4] = rng.randrange(16)
        init = b''.join(struct.pack('<I', w) for w in words)
        line = '%08x %08x %08x %08x %08x %08x %08x %08x %s' % (VA, ECX, a0, p, 0, 0, 0, 0, init.hex())
        out.append(line)
    return out


def make_variants():
    nat_src = open(os.path.join(HERE, 'x87_fn_native.c')).read()
    old = '        if (wide) wcopy((volatile u32 *)(WIDE_SAVE + WIDE_LEN), (volatile u32 *)WIDE_BASE);\n'
    assert nat_src.count(old) == 1, 'native の wide 保存行が見つからない'
    new = '        if (wide) *(volatile u32 *)(win + 0x520cc8u) = a[1];\n' + old
    open(os.path.join(WORK, 'native_ptr.c'), 'w').write(nat_src.replace(old, new))
    mjs_src = open(os.path.join(HERE, 'x87_fn_entry_wasm.mjs')).read()
    old_w = '    if (wide) M.HEAPU8.set(wideInit, WIDE_BASE);\n'
    assert mjs_src.count(old_w) == 1, 'wasm の wide 復元行が見つからない'
    new_w = old_w + '    if (wide) new DataView(M.HEAPU8.buffer).setUint32(ecx + 0x520cc8, a1, true);\n'
    open(os.path.join(WORK, 'entry_ptr.mjs'), 'w').write(mjs_src.replace(old_w, new_w))


def run(cmd, timeout):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr)[-600:]


def parse(path):
    out = []
    for ln in open(path).read().splitlines():
        d = {}
        for tok in ln.split()[1:]:
            if '=' in tok:
                k, v = tok.split('=', 1)
                d[k] = v
        out.append(d)
    return out


def main():
    os.makedirs(WORK, exist_ok=True)
    if not os.path.isfile(D.LIFT):
        sys.exit('[85a0] FAIL: %s が無い (lift_text.py を先に実行)' % D.LIFT)
    img_p = os.path.join(WORK, 'image.bin')
    open(img_p, 'wb').write(D.pe_image())
    rs = rows()
    sp = os.path.join(WORK, 'scen.txt')
    open(sp, 'w').write('\n'.join(rs) + '\n')
    make_variants()
    gcc = ['gcc', '-m32', '-O1', '-fno-pic', '-fno-pie', '-fno-stack-protector', '-fcf-protection=none',
           '-fno-asynchronous-unwind-tables', '-ffreestanding', '-nostdlib', '-static', '-no-pie']
    nat_base = os.path.join(WORK, 'native_base')
    nat_ptr = os.path.join(WORK, 'native_ptr')
    rc, msg = run(gcc + ['-o', nat_base, os.path.join(HERE, 'x87_fn_native.c')], 300)
    if rc:
        sys.exit('[85a0] native base build rc %d %s' % (rc, msg))
    rc, msg = run(gcc + ['-o', nat_ptr, os.path.join(WORK, 'native_ptr.c')], 300)
    if rc:
        sys.exit('[85a0] native ptr build rc %d %s' % (rc, msg))
    rc, msg = run(['emcc', '-O1', '-ffp-contract=off', '-fno-fast-math', '-w', '-I', D.RT,
                   '-DLIFT_C="%s"' % D.LIFT, os.path.join(HERE, 'x87_fn_glue.c'), os.path.join(D.RT, 'ott_cpu.c'),
                   '-sENVIRONMENT=node', '-sMODULARIZE=1', '-sEXPORT_NAME=createModule', '-sEXIT_RUNTIME=0',
                   '-sEXPORTED_FUNCTIONS=_ott_call32x,_ott_x87_st0,_ott_x87_st0d_hi,_ott_x87_st0d_lo,_ott_x87_depth',
                   '-sEXPORTED_RUNTIME_METHODS=HEAPU8',
                   '-sGLOBAL_BASE=%d' % 0x11000000, '-sSTACK_SIZE=2097152', '-sINITIAL_MEMORY=%d' % 0x14000000,
                   '-sALLOW_MEMORY_GROWTH=0', '-o', os.path.join(WORK, 'wasm_ptr.cjs')], 900)
    if rc:
        sys.exit('[85a0] wasm build rc %d %s' % (rc, msg))
    rc0, msg0 = run([nat_base, img_p, sp, os.path.join(WORK, 'base.out')], 300)
    print('[85a0] ベースライン (既定 harness・窓の外の語なし): native rc %d' % rc0)
    nrc, nmsg = run([nat_ptr, img_p, sp, os.path.join(WORK, 'native.out')], 300)
    wrc, wmsg = run(['node', '--liftoff-only', os.path.join(WORK, 'entry_ptr.mjs'), os.path.join(WORK, 'wasm_ptr.cjs'),
                     img_p, sp, os.path.join(WORK, 'wasm.out')], 600)
    print('[85a0] 複製: native rc %d | wasm rc %d' % (nrc, wrc))
    if nrc or wrc:
        print(nmsg[-300:], wmsg[-300:])
        sys.exit(1)
    na, wa = parse(os.path.join(WORK, 'native.out')), parse(os.path.join(WORK, 'wasm.out'))
    same = sum(1 for a, b in zip(na, wa) if all(a.get(k) == b.get(k) for k in ('eax', 'st0', 'st0d', 'd', 'mem', 'stk', 'wide')))
    print('[85a0] 行数 native %d wasm %d 入力 %d' % (len(na), len(wa), N))
    print('[85a0] 全項目一致 %d / %d' % (same, len(na)))
    print('[85a0] eax の種類 %d (期待 >=2: P が行ごとに変わる)' % len(set(r['eax'] for r in na)))
    print('[85a0] 広い範囲が変わった行 native %d / %d (FNV 初期値 0000:811c9dc5 以外)' % (
        sum(1 for r in na if r.get('wide', '-') not in ('-', '0000:811c9dc5')), len(na)))


if __name__ == '__main__':
    main()
