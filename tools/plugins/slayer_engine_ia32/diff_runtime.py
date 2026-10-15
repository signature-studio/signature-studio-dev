#!/usr/bin/env python3
"""diff_runtime.py: 実行時の間接 call (ott_dispatch 経由) の native vs wasm 突合 (#3128 (a))。 bit 単位・不一致は exit 1。

  python3 diff_runtime.py               突合
  python3 diff_runtime.py --nega        ネガコン: wasm 出力の 1 bit を壊した出力を判定器に通す (FAIL 検出で exit 0)

入口: 間接 call を含む関数 2 本 (diff_entry.py の build・判定を共用する)。 どちらも p = a0 = OBJ (0x10F80000)、
 obj = [p+0x40] = OBJ、 vtable = [obj] = OBJ+0x60 として、 行ごとに候補の関数を vtable の slot に入れる。
  0x10001060: `mov ecx,[eax+0x40]` … `push a1` … `mov edx,[ecx]; call [edx+8]`  → 呼先は ret 4 (引数 1) の関数
  0x10001080: `mov ecx,[eax+0x40]` … `push a2; push a1` … `mov edx,[ecx]; call [edx+4]` → 呼先は ret 8 (引数 2) の関数
呼先の候補は、 呼出し側の push 数と ret N が一致し、 OBJ 以外のメモリを参照しない (ret 4 / ret 8) 関数に限る。
入力: diff_entry.py と同じ work/entry/ (lift_text.py の出力 work/lift_text/ott_lifted.c が要る)。
"""
import os, random, struct, sys

import diff_entry as D

HERE = D.HERE
SEED = 3128
N_PER_ENTRY = 64
OBJ = D.OBJ
OBJ_LEN = D.OBJ_LEN
VT = OBJ + 0x60

# 入口 VA: (vtable 内の slot の init 上の位置, 候補の呼先)
ENTRIES = {
    0x10001060: (0x60 + 8, [0x10001240, 0x10001230, 0x100011d0, 0x10009310, 0x10001ba0]),
    0x10001080: (0x60 + 4, [0x10001b40, 0x10001210, 0x10001b90, 0x10001ab0]),
}


def gen_scen(seed, n):
    rng = random.Random(seed)
    rows = []
    for va, (slot, targets) in ENTRIES.items():
        for _ in range(n):
            init = bytearray(rng.randrange(256) for _ in range(OBJ_LEN))
            struct.pack_into('<I', init, 0x00, VT)
            struct.pack_into('<I', init, 0x40, OBJ)
            struct.pack_into('<I', init, slot, rng.choice(targets))
            ecx = rng.getrandbits(32)
            a1, a2, a3 = (rng.getrandbits(32) for _ in range(3))
            rows.append('%08x %08x %08x %08x %08x %08x %s' % (va, ecx, OBJ, a1, a2, a3, bytes(init).hex()))
    return rows


def target_hist(rows):
    hist = {}
    for r in rows:
        f = r.split()
        va = int(f[0], 16)
        slot = ENTRIES[va][0]
        t = struct.unpack_from('<I', bytes.fromhex(f[6]), slot)[0]
        hist.setdefault(va, {}).setdefault(t, 0)
        hist[va][t] += 1
    return hist


def main():
    nega = '--nega' in sys.argv
    os.makedirs(D.WORK, exist_ok=True)
    img = D.pe_image()
    img_path = os.path.join(D.WORK, 'image.bin')
    open(img_path, 'wb').write(img)
    rows = gen_scen(SEED, N_PER_ENTRY)
    scen = os.path.join(D.WORK, 'runtime_scen.txt')
    open(scen, 'w').write('\n'.join(rows) + '\n')
    print('[scen] entries %d x %d = %d 行 (seed %d)' % (len(ENTRIES), N_PER_ENTRY, len(rows), SEED))
    for va, targets in sorted(target_hist(rows).items()):
        print('[scen] %08x の呼先 (vtable slot 経由) の出現: %s' % (va, ' '.join('%08x:%d' % (t, n) for t, n in sorted(targets.items()))))
    if not os.path.isfile(D.LIFT):
        sys.exit('[diff_runtime] FAIL: %s が無い (lift_text.py を先に実行)' % D.LIFT)
    nat, t_nat_build, mjs, t_wasm_build = D.build()
    nat_out = os.path.join(D.WORK, 'runtime_native_out.txt')
    wasm_out = os.path.join(D.WORK, 'runtime_wasm_out.txt')
    load = os.getloadavg()[0]
    t_nat = D.run([nat, img_path, scen, nat_out], 'native run')
    t_wasm = D.run(['node', os.path.join(HERE, 'entry_wasm.mjs'), mjs, img_path, scen, wasm_out], 'wasm run (node)', timeout=900)
    print('[build] native %.2f s, wasm emcc %.2f s; [run] native %.3f s, wasm(node) %.3f s; load1 before run %.2f' % (
        t_nat_build, t_wasm_build, t_nat, t_wasm, load))
    changed = D.effect_count(nat_out, rows)
    print('[effect] native 実行で OBJ 領域が変わった行 %d / %d (入力の非自明性)' % (changed, len(rows)))
    if not nega:
        rc = D.compare(nat_out, wasm_out, len(rows))
        if rc == 0:
            print('[diff_runtime] PASS')
        sys.exit(rc)
    lines = open(wasm_out).read().splitlines()
    head, rest = lines[0].split(' mem=')
    eax_part = head.split(' eax=')
    v = int(eax_part[1], 16) ^ 0x1
    lines[0] = eax_part[0] + ' eax=%08x mem=' % v + rest
    nega_out = os.path.join(D.WORK, 'runtime_nega_out.txt')
    open(nega_out, 'w').write('\n'.join(lines) + '\n')
    rc = D.compare(nat_out, nega_out, len(rows))
    if rc == 0:
        print('[nega] FAIL: 1 bit 壊した出力が PASS した (判定器が効いていない)')
        sys.exit(1)
    print('[nega] 1 bit 壊した出力を検出 (FAIL, exit %d)。 ネガコン OK' % rc)
    sys.exit(0)


if __name__ == '__main__':
    main()
