#!/usr/bin/env python3
"""probe12_4087.py: #4087 (PLG-G2-44) の 12 本を native と wasm で同じ入力に通し、異常終了の有無と結果を記録する。

  python3 probe12_4087.py   (前提: lift_text.py 実行済み・gcc -m32・emcc・pefile)
出力: work/probe12_4087/ (gitignore)。 x87_fn_diff.py の build と同じ手順を使う。
入力は x87_fn_diff.py の gen_rows と同じ乱数方式 (seed 4087・行数は関数あたり N)。
"""
import os, random, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import x87_fn_diff as D

VAS = [
    (0x10003FE0, 'fn_10003fe0'), (0x100051F0, 'fn_100051f0'), (0x100085A0, 'fn_100085a0'),
    (0x100096D0, 'fn_100096d0'), (0x1000A95A, 'fn_1000a95a'), (0x1000BA05, 'fn_1000ba05'),
    (0x1000B6C1, 'fn_1000b6c1'), (0x1000B8A2, 'fn_1000b8a2'), (0x1000B8CD, 'fn_1000b8cd'),
    (0x1000B8CF, 'fn_1000b8cf'), (0x1000B8F7, 'fn_1000b8f7'), (0x1000B936, 'fn_1000b936'),
]
N = 16
SEED = 4087
OBJ = 0x10F80000
WORK = os.path.join(HERE, 'work', 'probe12_4087')


def rows():
    rng = random.Random(SEED)
    out = []
    for va, name in VAS:
        for _ in range(N):
            init = b''.join(struct.pack('<f', rng.uniform(-1000, 1000)) for _ in range(D.OBJ_WIN // 4))
            a = [D.f32(rng.uniform(-100, 100)) for _ in range(5)] + [0]
            line = '%08x %08x %s %s' % (va, OBJ, ' '.join('%08x' % v for v in a), init.hex())
            out.append((name, line))
    return out


def run(cmd, what, timeout):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr)[-600:]


def main():
    os.makedirs(WORK, exist_ok=True)
    img = D.pe_image()
    img_p = os.path.join(WORK, 'image.bin')
    open(img_p, 'wb').write(img)
    rs = rows()
    scen = os.path.join(WORK, 'scen.txt')
    open(scen, 'w').write('\n'.join(r[1] for r in rs) + '\n')
    # 関数ごとに 1 行ずつ実行して rc を取る (異常終了を関数単位で切り分ける)
    nat = os.path.join(WORK, 'native_x87')
    rc, msg = run(['gcc', '-m32', '-O1', '-fno-pic', '-fno-pie', '-fno-stack-protector', '-fcf-protection=none',
                   '-fno-asynchronous-unwind-tables', '-ffreestanding', '-nostdlib', '-static', '-no-pie',
                   '-o', nat, os.path.join(HERE, 'x87_fn_native.c')], 'native build', 300)
    if rc:
        sys.exit('native build rc %d %s' % (rc, msg))
    mjs = os.path.join(WORK, 'wasm_x87.cjs')
    rc, msg = run(['emcc', '-O1', '-ffp-contract=off', '-fno-fast-math', '-w', '-I', D.RT,
                   '-DLIFT_C="%s"' % D.LIFT, os.path.join(HERE, 'x87_fn_glue.c'), os.path.join(D.RT, 'ott_cpu.c'),
                   '-sENVIRONMENT=node', '-sMODULARIZE=1', '-sEXPORT_NAME=createModule', '-sEXIT_RUNTIME=0',
                   '-sEXPORTED_FUNCTIONS=_ott_call32x,_ott_x87_st0,_ott_x87_st0d_hi,_ott_x87_st0d_lo,_ott_x87_depth',
                   '-sEXPORTED_RUNTIME_METHODS=HEAPU8',
                   '-sGLOBAL_BASE=%d' % 0x11000000, '-sSTACK_SIZE=2097152', '-sINITIAL_MEMORY=%d' % 0x14000000,
                   '-sALLOW_MEMORY_GROWTH=0', '-o', mjs], 'wasm build', 900)
    if rc:
        sys.exit('wasm build rc %d %s' % (rc, msg))
    for _, name in VAS:
        sub = [r[1] for r in rs if r[0] == name]
        sp = os.path.join(WORK, name + '.scen')
        open(sp, 'w').write('\n'.join(sub) + '\n')
        no = os.path.join(WORK, name + '.native')
        wo = os.path.join(WORK, name + '.wasm')
        nrc, nmsg = run([nat, img_p, sp, no], 'native', 120)
        wrc, wmsg = run(['node', '--liftoff-only', os.path.join(HERE, 'x87_fn_entry_wasm.mjs'), mjs, img_p, sp, wo], 'wasm', 300)
        nlines = len(open(no).read().splitlines()) if os.path.exists(no) else 0
        wlines = len(open(wo).read().splitlines()) if os.path.exists(wo) else 0
        print('%s native rc %d out_lines %d | wasm rc %d out_lines %d %s' % (
            name, nrc, nlines, wrc, wlines, (wmsg.strip().splitlines() or [''])[-1][:160] if wrc else ''))
        sys.stdout.flush()


if __name__ == '__main__':
    main()
