#!/usr/bin/env python3
"""diff_entry.py: Slayer_Engine.dll (block22434) の関数 1 本以上を native (実 ia32 機械語) と wasm (ia32 x64c lift) で実行し、
戻り値 (eax) と書込み先メモリ (OBJ 領域 128 B) を bit 単位で突合する (#1223 PLG-G2-11)。

  python3 diff_entry.py                 突合 (不一致・件数不足は exit 1)
  python3 diff_entry.py --nega          ネガコン: wasm 側の 1 bit を壊した出力を判定器に通し、FAIL することを確かめる (FAIL 検出で exit 0)

入力: $FL_WIN64_DIR/extracted/block22434_PE.bin (既定 $RUNNER_TEMP/fl-win64)。 出力: work/entry/ (gitignore)。
入口: ENTRIES 4 本 (下の表)。 各入口は leaf 関数 (import も未 lift の call も無い) で、OBJ 領域への store だけを行う。
native: native_entry.c (freestanding i386 ELF。 image を VA 0x10000000 に敷設して call)。
wasm  : lift_text.py の出力 ott_lifted.c + rt/ott_cpu.c + rt32_glue.c を emcc で wasm 化し entry_wasm.mjs で実行。
"""
import os, random, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
RT = os.path.join(ROOT, 'tools', 'ott', 'rt')
WORK = os.path.join(HERE, 'work', 'entry')
LIFT = os.path.join(HERE, 'work', 'lift_text', 'ott_lifted.c')
IMG_BASE = 0x10000000
OBJ = 0x10F80000
OBJ_LEN = 0x80
N_PER_ENTRY = 64
SEED = 1223

# 入口 VA, 引数の形 (thiscall: ecx=OBJ), 引数生成の種類
ENTRIES = {
    0x10001b40: 'thiscall_two_stores',   # mov [ecx+0x1c],a0 / mov [ecx+4],a1
    0x10009300: 'thiscall_byte_store',   # mov [ecx+0x15],al (al = a0)
    0x1000d77e: 'ptr_obj_stores',        # mov [a0+0x50],imm32 / mov [a0+0x14],1
    0x10008630: 'ptr_byte_zero',         # mov byte [a1],0
}


def pe_image():
    import pefile
    d = os.environ.get('FL_WIN64_DIR') or os.path.join(os.environ.get('RUNNER_TEMP', ''), 'fl-win64')
    p = os.path.join(d, 'extracted', 'block22434_PE.bin')
    if not os.path.isfile(p):
        sys.exit('[diff_entry] FAIL: %s が無い (素材 fl-win64 を展開すること)' % p)
    pe = pefile.PE(p)
    if pe.OPTIONAL_HEADER.ImageBase != IMG_BASE:
        sys.exit('[diff_entry] FAIL: ImageBase 0x%x != 0x%x' % (pe.OPTIONAL_HEADER.ImageBase, IMG_BASE))
    img = bytearray(pe.OPTIONAL_HEADER.SizeOfImage)
    for s in pe.sections:
        raw = s.get_data()[:s.Misc_VirtualSize or len(s.get_data())]
        img[s.VirtualAddress:s.VirtualAddress + len(raw)] = raw
    return bytes(img)


def gen_scen(seed, n):
    rng = random.Random(seed)
    rows = []
    for va, kind in ENTRIES.items():
        for _ in range(n):
            init = bytes(rng.randrange(256) for _ in range(OBJ_LEN))
            a = [rng.getrandbits(32) for _ in range(4)]
            if kind == 'ptr_obj_stores':
                a[0] = OBJ
            if kind == 'ptr_byte_zero':
                a[1] = OBJ + rng.randrange(OBJ_LEN)
            rows.append('%08x %08x %08x %08x %08x %08x %s' % (va, OBJ, a[0], a[1], a[2], a[3], init.hex()))
    return rows


def run(cmd, what, timeout=600):
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-1500:] + r.stderr[-1500:])
        sys.exit('[diff_entry] FAIL: %s rc %d' % (what, r.returncode))
    return time.time() - t0


def compare(exp_path, act_path, n_expected):
    exp = open(exp_path).read().splitlines()
    act = open(act_path).read().splitlines()
    if len(exp) != n_expected or len(act) != n_expected:
        print('[compare] FAIL: 件数 native %d / wasm %d / 期待 %d' % (len(exp), len(act), n_expected))
        return 1
    bad = [i for i, (x, y) in enumerate(zip(exp, act)) if x != y]
    for i in bad[:3]:
        print('[compare] mismatch #%d\n  native %s\n  wasm   %s' % (i, exp[i], act[i]))
    print('[compare] %s: %d / %d 件が bit 一致、不一致 %d 件' % ('PASS' if not bad else 'FAIL', n_expected - len(bad), n_expected, len(bad)))
    return 1 if bad else 0


def effect_count(exp_path, scen_rows):
    changed = 0
    for row, line in zip(scen_rows, open(exp_path).read().splitlines()):
        init = row.split()[6]
        mem = line.split(' mem=')[1]
        changed += (init != mem)
    return changed


def main():
    nega = '--nega' in sys.argv
    os.makedirs(WORK, exist_ok=True)
    img = pe_image()
    open(os.path.join(WORK, 'image.bin'), 'wb').write(img)
    rows = gen_scen(SEED, N_PER_ENTRY)
    scen = os.path.join(WORK, 'scen.txt')
    open(scen, 'w').write('\n'.join(rows) + '\n')
    print('[scen] entries %d x %d = %d 行 (seed %d)' % (len(ENTRIES), N_PER_ENTRY, len(rows), SEED))
    if not os.path.isfile(LIFT):
        sys.exit('[diff_entry] FAIL: %s が無い (lift_text.py を先に実行)' % LIFT)
    nat = os.path.join(WORK, 'native_entry')
    t_nat_build = run(['gcc', '-m32', '-O1', '-fno-pic', '-fno-pie', '-fno-stack-protector', '-fcf-protection=none',
                       '-fno-asynchronous-unwind-tables', '-ffreestanding', '-nostdlib', '-static', '-no-pie',
                       '-o', nat, os.path.join(HERE, 'native_entry.c')], 'native build')
    mjs = os.path.join(WORK, 'wasm_entry.cjs')
    t_wasm_build = run(['emcc', '-O1', '-ffp-contract=off', '-fno-fast-math', '-w', '-I', RT, '-I', HERE,
                        LIFT, os.path.join(RT, 'ott_cpu.c'), os.path.join(HERE, 'rt32_glue.c'),
                        '-sENVIRONMENT=node', '-sMODULARIZE=1', '-sEXPORT_NAME=createModule', '-sEXIT_RUNTIME=0',
                        '-sEXPORTED_FUNCTIONS=_ott_call32', '-sEXPORTED_RUNTIME_METHODS=HEAPU8',
                        '-sGLOBAL_BASE=%d' % 0x11000000, '-sSTACK_SIZE=2097152', '-sINITIAL_MEMORY=%d' % 0x14000000,
                        '-sALLOW_MEMORY_GROWTH=0', '-o', mjs], 'wasm build (emcc)', timeout=900)
    nat_out = os.path.join(WORK, 'native_out.txt')
    wasm_out = os.path.join(WORK, 'wasm_out.txt')
    load = os.getloadavg()[0]
    t_nat = run([nat, os.path.join(WORK, 'image.bin'), scen, nat_out], 'native run')
    t_wasm = run(['node', os.path.join(HERE, 'entry_wasm.mjs'), mjs, os.path.join(WORK, 'image.bin'), scen, wasm_out], 'wasm run (node)', timeout=900)
    print('[build] native %.2f s, wasm emcc %.2f s; [run] native %.3f s, wasm(node) %.3f s; load1 before run %.2f' % (
        t_nat_build, t_wasm_build, t_nat, t_wasm, load))
    changed = effect_count(nat_out, rows)
    print('[effect] native 実行で OBJ 領域が変わった行 %d / %d (入力の非自明性)' % (changed, len(rows)))
    if not nega:
        rc = compare(nat_out, wasm_out, len(rows))
        if rc == 0:
            print('[diff_entry] PASS')
        sys.exit(rc)
    # ネガコン: wasm 出力の 1 行目の eax の 1 bit を壊し、判定器が FAIL することを確かめる
    lines = open(wasm_out).read().splitlines()
    head, rest = lines[0].split(' mem=')
    eax_part = head.split(' eax=')
    v = int(eax_part[1], 16) ^ 0x1
    lines[0] = eax_part[0] + ' eax=%08x mem=' % v + rest
    nega_out = os.path.join(WORK, 'nega_out.txt')
    open(nega_out, 'w').write('\n'.join(lines) + '\n')
    rc = compare(nat_out, nega_out, len(rows))
    if rc == 0:
        print('[nega] FAIL: 1 bit 壊した出力が PASS した (判定器が効いていない)')
        sys.exit(1)
    print('[nega] 1 bit 壊した出力を検出 (FAIL, exit %d)。 ネガコン OK' % rc)
    sys.exit(0)


if __name__ == '__main__':
    main()
