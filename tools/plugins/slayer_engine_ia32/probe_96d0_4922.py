#!/usr/bin/env python3
"""probe_96d0_4922.py: #4922 (PLG-G2-67)。 0x100096d0 は引数のポインタを辿る (窓の外の入力)。
  a0 = S0: [S0] = X (eax・読む float 列)、 [S0+4] = Y (esi・読む float 列)。
  a1 = S1: [S1] = Z (edx・書込み先)、 [S1+4] = W (edi・書込み先)。 a2 = 件数 (ebx)。 a3..a5 は読まない。
  窓 (ecx = ECX_HI) の [+0x18] の byte は分岐の旗 (0 なら何もせず戻る)。
  S0・S1・X・Y・Z・W は、ecx = WIDE_BASE の広い範囲 (slot 0x100 B 単位) に置く。 Z・W への書込みは
  native の wide 突合 (変化語数と FNV ハッシュ) で観測される。 既存の harness は変えない (tokens のみ)。

  python3 lift_text.py && python3 probe_96d0_4922.py
出力: work/96d0_4922/ (gitignore)。 seed 4922。
"""
import os, random, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import x87_fn_diff as D

VA = 0x100096D0
ECX = D.ECX_HI
WIDE = D.ECX_HI
SLOT = 0x100
SLOT_BASE = WIDE + 0x1000
NSLOT = 0x7000
N = 2000
SEED = 4922
WORK = os.path.join(HERE, 'work', '96d0_4922')


def slot(k):
    return SLOT_BASE + k * SLOT


def rows():
    rng = random.Random(SEED)
    out = []
    for _ in range(N):
        sa, sb, sc, sd, se, sf = rng.sample(range(NSLOT), 6)
        s0, x, y = slot(sa), slot(sb) + 0x20, slot(sc) + 0x20
        s1, z, w = slot(sd), slot(se) + 0x20, slot(sf) + 0x20
        cnt = rng.randrange(1, 9)
        flag = 0 if rng.random() < 0.25 else 1
        init = b''.join(struct.pack('<f', rng.uniform(-1000, 1000)) for _ in range(D.OBJ_WIN // 4))
        toks = ['@%08x=%02x' % (ECX + 0x18, flag)]
        toks.append('@%08x=%s' % (s0, struct.pack('<I', x).hex()))
        toks.append('@%08x=%s' % (s0 + 4, struct.pack('<I', y).hex()))
        toks.append('@%08x=%s' % (s1, struct.pack('<I', z).hex()))
        toks.append('@%08x=%s' % (s1 + 4, struct.pack('<I', w).hex()))
        for base in (x, y, z, w):
            data = b''.join(struct.pack('<f', rng.uniform(-100, 100)) for _ in range(cnt + 1))
            toks.append('@%08x=%s' % (base, data.hex()))
        line = '%08x %08x %08x %08x %08x %08x %08x %08x %s %s' % (
            VA, ECX, s0, s1, cnt, 0, 0, 0, init.hex(), ' '.join(toks))
        out.append(line)
    return out


def run(cmd, timeout):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr)[-600:]


def main():
    os.makedirs(WORK, exist_ok=True)
    if not os.path.isfile(D.LIFT):
        sys.exit('[96d0] FAIL: %s が無い (lift_text.py を先に実行)' % D.LIFT)
    img_p = os.path.join(WORK, 'image.bin')
    open(img_p, 'wb').write(D.pe_image())
    rs = rows()
    sp = os.path.join(WORK, 'scen.txt')
    open(sp, 'w').write('\n'.join(rs) + '\n')
    nat = os.path.join(WORK, 'native_x87')
    rc, msg = run(['gcc', '-m32', '-O1', '-fno-pic', '-fno-pie', '-fno-stack-protector', '-fcf-protection=none',
                   '-fno-asynchronous-unwind-tables', '-ffreestanding', '-nostdlib', '-static', '-no-pie',
                   '-o', nat, os.path.join(HERE, 'x87_fn_native.c')], 300)
    if rc:
        sys.exit('[96d0] native build rc %d %s' % (rc, msg))
    mjs = os.path.join(WORK, 'wasm_x87.cjs')
    rc, msg = run(['emcc', '-O1', '-ffp-contract=off', '-fno-fast-math', '-w', '-I', D.RT,
                   '-DLIFT_C="%s"' % D.LIFT, os.path.join(HERE, 'x87_fn_glue.c'), os.path.join(D.RT, 'ott_cpu.c'),
                   '-sENVIRONMENT=node', '-sMODULARIZE=1', '-sEXPORT_NAME=createModule', '-sEXIT_RUNTIME=0',
                   '-sEXPORTED_FUNCTIONS=_ott_call32x,_ott_x87_st0,_ott_x87_st0d_hi,_ott_x87_st0d_lo,_ott_x87_depth',
                   '-sEXPORTED_RUNTIME_METHODS=HEAPU8',
                   '-sGLOBAL_BASE=%d' % 0x11000000, '-sSTACK_SIZE=2097152', '-sINITIAL_MEMORY=%d' % 0x14000000,
                   '-sALLOW_MEMORY_GROWTH=0', '-o', mjs], 900)
    if rc:
        sys.exit('[96d0] wasm build rc %d %s' % (rc, msg))
    no, wo = os.path.join(WORK, 'native.out'), os.path.join(WORK, 'wasm.out')
    nrc, nmsg = run([nat, img_p, sp, no], 300)
    wrc, wmsg = run(['node', '--liftoff-only', os.path.join(HERE, 'x87_fn_entry_wasm.mjs'), mjs, img_p, sp, wo], 600)
    print('[96d0] native rc %d | wasm rc %d' % (nrc, wrc))
    if nrc or wrc:
        print(nmsg[-300:], wmsg[-300:])
        sys.exit(1)
    na, wa = D.parse(no), D.parse(wo)
    print('[96d0] 行数 native %d wasm %d 入力 %d' % (len(na), len(wa), N))
    fields = ('eax', 'st0', 'st0d', 'd', 'mem', 'stk', 'wide')
    full = sum(1 for a, b in zip(na, wa) if all(a.get(k) == b.get(k) for k in fields))
    print('[96d0] 全項目一致 %d / %d' % (full, len(na)))
    for k in fields:
        bad = sum(1 for a, b in zip(na, wa) if a.get(k) != b.get(k))
        print('[96d0]   %s 不一致 %d' % (k, bad))
    print('[96d0] eax の種類 %d' % len(set(r['eax'] for r in na)))
    changed = sum(1 for r in na if r.get('wide', '-') not in ('-', '0000:811c9dc5'))
    print('[96d0] 広い範囲が変わった行 native %d / %d' % (changed, len(na)))
    def expect(s):
        f = s.split()
        e = bytearray(bytes.fromhex(f[8]))
        for t in f[9:]:
            if t.startswith('@%08x=' % (ECX + 0x18)):
                e[0x18] = int(t.split('=')[1], 16)
        return e.hex()
    win_changed = sum(1 for r, s in zip(na, rs) if r['mem'] != expect(s))
    print('[96d0] OBJ 窓が変わった行 native %d / %d (旗の語 +0x18 を除いて比較)' % (win_changed, len(na)))
    print('[96d0] 広い範囲のハッシュの種類 %d' % len(set(r.get('wide', '-') for r in na)))


if __name__ == '__main__':
    main()
