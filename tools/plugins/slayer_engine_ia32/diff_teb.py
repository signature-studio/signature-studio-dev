#!/usr/bin/env python3
"""diff_teb.py: fs: (TEB) を読み書きする関数の native vs wasm 突合 (#3905 PLG-G2-37)。 bit 単位・不一致は exit 1。

  python3 diff_teb.py               突合
  python3 diff_teb.py --nega        ネガコン: wasm 出力の 1 bit を壊した出力を判定器に通す (FAIL 検出で exit 0)

入口: fs:[0] (SEH chain head) を読み書きする関数のうち、 KERNEL32 import を native の既存モデル (native_entry.c の n_*) だけで
  通る 3 本 (0x1000a307・0x1000a42e・0x100106a5)。 残り 5 本は MultiByteToWideChar・LCMapString 系を通り、 native 側が未実装
  (#3127 の方針表で fail-fast) のため本件では扱わない (子 issue に分ける)。
入力: 行ごとに TEB (fs base の 64 B) の内容を変える。 0 埋め模型 (teb 欄なし) と非 0 の値 (ExceptionList 等) の両方。
  行の 8 番目の欄が TEB の内容 (hex 64 B)。 欄が無い行は TEB を 0 埋めにする。
出力: idx va eax mem(OBJ 128 B) heap(64 B) [teb(64 B)]。 native と wasm で同じ書式。
"""
import os, random, sys

import diff_entry as D

HERE = D.HERE
SEED = 3905
N_PER_ENTRY = 64
TEB_LEN = 64
LIM_SIZE = 0x80000

# 入口 VA: 引数の形 (stdcall は使わない。 cdecl の a0〜a3 を 4 本入れる)
ENTRIES = [0x1000a307, 0x1000a42e, 0x100106a5]


def gen_scen(seed, n):
    rng = random.Random(seed)
    rows = []
    for va in ENTRIES:
        for k in range(n):
            init = bytes(rng.randrange(256) for _ in range(D.OBJ_LEN))
            a = [rng.getrandbits(32) for _ in range(4)]
            if va == 0x1000a42e:
                a[0] = rng.randrange(LIM_SIZE)   # 大きい a0 は HeapAlloc の巨大サイズ経路 (モデルの heap 領域を超える) のため、 範囲を絞る
            if va == 0x100106a5:
                a[0] = rng.randrange(0x8000)     # a0*a1 を HeapAlloc に渡す。 積が heap 領域を超えないよう両方を絞る (積 < 0x80000)
                a[1] = rng.randrange(0x10)
            if k % 2 == 0:
                teb = bytes(TEB_LEN)   # 0 埋め模型 (ott_teb_blk と同じ)
            else:
                teb = bytes(rng.randrange(256) for _ in range(TEB_LEN))   # 非 0 (ExceptionList 等)
            rows.append('%08x %08x %08x %08x %08x %08x %s %s' % (va, D.OBJ, a[0], a[1], a[2], a[3], init.hex(), teb.hex()))
    return rows


def main():
    nega = '--nega' in sys.argv
    os.makedirs(D.WORK, exist_ok=True)
    img = D.pe_image()
    img_path = os.path.join(D.WORK, 'image.bin')
    open(img_path, 'wb').write(img)
    rows = gen_scen(SEED, N_PER_ENTRY)
    scen = os.path.join(D.WORK, 'teb_scen.txt')
    open(scen, 'w').write('\n'.join(rows) + '\n')
    print('[scen] entries %d x %d = %d 行 (seed %d、 偶数行は TEB 0 埋め・奇数行は非 0)' % (len(ENTRIES), N_PER_ENTRY, len(rows), SEED))
    if not os.path.isfile(D.LIFT):
        sys.exit('[diff_teb] FAIL: %s が無い (lift_text.py を先に実行)' % D.LIFT)
    nat, t_nat_build, mjs, t_wasm_build = D.build()
    nat_out = os.path.join(D.WORK, 'teb_native_out.txt')
    wasm_out = os.path.join(D.WORK, 'teb_wasm_out.txt')
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
            print('[diff_teb] PASS')
        sys.exit(rc)
    lines = open(wasm_out).read().splitlines()
    head, rest = lines[0].split(' mem=')
    eax_part = head.split(' eax=')
    v = int(eax_part[1], 16) ^ 0x1
    lines[0] = eax_part[0] + ' eax=%08x mem=' % v + rest
    nega_out = os.path.join(D.WORK, 'teb_nega_out.txt')
    open(nega_out, 'w').write('\n'.join(lines) + '\n')
    rc = D.compare(nat_out, nega_out, len(rows))
    if rc == 0:
        print('[nega] FAIL: 1 bit 壊した出力が PASS した (判定器が効いていない)')
        sys.exit(1)
    print('[nega] 1 bit 壊した出力を検出 (FAIL, exit %d)。 ネガコン OK' % rc)
    sys.exit(0)


if __name__ == '__main__':
    main()
