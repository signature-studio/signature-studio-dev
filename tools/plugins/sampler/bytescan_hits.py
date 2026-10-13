#!/usr/bin/env python3
"""byte 走査で nonfw 本体に現れた「VA 下位 32 bit / RVA と一致する 4 バイト列」を、含む命令の種類で 1 件ずつ判定する (#667 REPORT_UNREACHED §2d-3)。 capstone の IMM 集合に入らなかったものだけが対象。

  bytescan_hits.py [--out-dir DIR]    前提: closure_unreached.py 実行済み (work/sampler/unr/block*.sets.json) + source sampler/env.sh

判定 (一致位置 o を含む命令を、関数先頭からの線形走査 (capstone) で求める。 線形走査なので誤同期の可能性あり):
  即値   = 含む命令の IMM オペランドの下位 32 bit が一致
  変位   = 含む命令のメモリオペランドの disp の下位 32 bit が一致
  偶発   = 含む命令の中に一致するが、IMM にも disp にも一致しない (opcode / ModRM / SIB / 他の定数の一部)
  データ = どの命令にも含まれない (復号範囲外・命令境界外)
出力: stdout の表 / work/sampler/bytescan_hits.json
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from capstone import CS_OP_IMM, CS_OP_MEM  # noqa: E402
import closure_indirect as CI  # noqa: E402
import closure_unreached as CU  # noqa: E402
import targets  # noqa: E402

WORK = CI.WORK
MASK32 = 0xffffffff


def classify(x, f, s, v, ins_list):
    va = x.base + f + s
    cover = [i for i in ins_list if i.address <= va < i.address + i.size]
    if not cover:
        return 'データ (復号範囲外・命令境界外)', '-'
    i = cover[0]
    ops = i.operands
    text = '%s %s' % (i.mnemonic, i.op_str)
    if any(op.type == CS_OP_IMM and (op.imm & MASK32) == v for op in ops):
        return '即値', text
    if any(op.type == CS_OP_MEM and (op.mem.disp & MASK32) == v for op in ops):
        return '変位', text
    return '偶発 (命令内の他のバイト)', text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default=os.path.join(WORK, 'sampler'))
    a = ap.parse_args()
    cnt = json.load(open(os.path.join(WORK, 'fw_hash_counts.json')))
    rows, res = [], {}
    for name, blk, _ in targets.SHELLS:
        x = CI.Pe(blk, cnt)
        sets = json.load(open(os.path.join(a.out_dir, 'unr', 'block%05d.sets.json' % blk)))
        nonfw, outside, dset = set(sets['nonfw']), set(sets['outside']), set(sets['d'])
        cap_va, cap_rv = set(), set()
        for f in nonfw:
            va, rv = CU.imm_capstone(x, f, nonfw)
            cap_va |= va
            cap_rv |= rv
        maps = (('VA', {(x.base + r) & MASK32: r for r in nonfw}, cap_va),
                ('RVA', {r: r for r in nonfw}, cap_rv))
        res[name] = []
        for f in sorted(nonfw):
            b = x.body(f)
            ins_list = None
            for kind, vmap, cap in maps:
                for s in range(len(b) - 3):
                    v = int.from_bytes(b[s:s + 4], 'little')
                    t = vmap.get(v)
                    if t is None or t in cap:
                        continue
                    if ins_list is None:
                        ins_list = list(x.md.disasm(b, x.base + f))
                    cls, text = classify(x, f, s, v, ins_list)
                    rec = {'plugin': name, 'kind': kind, 'target': t, 'func': f, 'off': s, 'va': x.base + f + s,
                           'insn': text, 'class': cls, 'func_region': 'outside' if f in outside else 'total2',
                           'target_region': 'd' if t in dset else ('outside' if t in outside else 'total2')}
                    res[name].append(rec)
                    rows.append(rec)
    print('| プラグイン | 種別 | 対象 (RVA) | 含む関数 (RVA) | 関数内オフセット | VA | 含む命令 | 判定 | 関数の区分 | 対象の区分 |')
    print('|---|---|---|---|--:|---|---|---|---|---|')
    for r in rows:
        print('| %s | %s | 0x%x | 0x%x | 0x%x | 0x%x | `%s` | %s | %s | %s |' % (
            r['plugin'], r['kind'], r['target'], r['func'], r['off'], r['va'], r['insn'], r['class'],
            r['func_region'], r['target_region']))
    tally = {}
    for r in rows:
        tally[r['class']] = tally.get(r['class'], 0) + 1
    print('\n件数 %d: %s' % (len(rows), ', '.join('%s %d' % kv for kv in sorted(tally.items()))))
    json.dump(res, open(os.path.join(a.out_dir, 'bytescan_hits.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
