#!/usr/bin/env python3
"""f3c_gate_probe.py — ldfix.fix_f3c の門 (gate) を 1 関数について 1 つずつ評価し、どこで落ちたかを表示する (#484)。

fix_f3c と同じ条件式を同じ補助関数 (ldfix.prologue_homes / base_resolves_to_arg) で評価するだけで、IR は書き換えない。
使い方: python3 f3c_gate_probe.py IR.ll VA_HEX IMAGE.bin 'CONFIG_GLOB'     (VA は 16 進。複数可: カンマ区切り)
出力: 機械語ブロックごとに G1(zero-disp load が恰好 1 本) / G2(base→argN 解決) / G3(IR に既存 load 無し) /
      G4(機械語に rB の生 store 無し) / G5(同一 IR ブロック内に argN 値 store あり) の成否。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ldfix  # noqa: E402
from ldfix import ARGREG_ARG, Fn, DEF_RE, base_resolves_to_arg, prologue_homes  # noqa: E402
from ldmach import FnMach  # noqa: E402
from ldmach_img import ImageMachine  # noqa: E402


def load_fn(text, va):
    for m in DEF_RE.finditer(text):
        if int(m.group('name')[9:], 16) == va:
            end = text.index('\n}', m.end()) + 2
            return Fn(m.group('name'), va, text[m.start():end])
    return None


def main():
    ir, vas, image, cfg = sys.argv[1:5]
    text = open(ir, errors='replace').read()
    mach = ImageMachine(image, cfg)
    for va in [int(x, 16) for x in vas.split(',')]:
        fn = load_fn(text, va)
        blocks = fn.blocks()
        cum, blk_meta = 0, []
        for (bva, ls) in blocks:
            blk_meta.append((bva, cum, cum + len(ls), ls))
            cum += len(ls)
        print('== function_%x  IR ブロック(BLK_RE が認識した VA 付き): %s' % (va, ' '.join('%x' % b[0] for b in blk_meta if b[0] is not None)))
        print('   IR の dec_label_pc_* 全ラベル行: %s' % ' '.join(re.findall(r'^(dec_label_pc_[0-9a-f.\w]+):', fn.body, re.M)))
        fv = FnMach(mach, va, [b[0] for b in blk_meta if b[0] is not None])
        mblk, _ = ldfix.fn_mach_blocks(fv, va, [b[0] for b in blk_meta if b[0] is not None])
        homes = prologue_homes(fv)
        print('   prologue homes: %s' % {('%s%+#x' % k): v for k, v in homes.items()})
        for (bva, ia, ib, ls) in blk_meta:
            if bva is None:
                continue
            mins = mblk.get(bva, [])
            zl = []
            for ins in mins:
                if ins.mnemonic != 'mov' or len(ins.operands) != 2:
                    continue
                o0, o1 = ins.operands
                if o0.type != 1 or o1.type != 3 or o1.mem.index or o1.mem.disp or not o1.mem.base:
                    continue
                bn = fv.cs.reg_name(o1.mem.base)
                if bn in ARGREG_ARG:
                    zl.append((fv.cs.reg_name(o0.reg), bn, o1.size * 8, ins))
            if not zl:
                continue
            row = ['block %x: G1(zero-disp load 本数=%d, 要 1) %s' % (bva, len(zl), 'PASS' if len(zl) == 1 else 'FAIL')]
            if len(zl) == 1:
                rD, rB, bits, insL = zl[0]
                idx = mins.index(insL) + 1
                a_as_is = base_resolves_to_arg(fv, mins, rB, homes, idx)
                a_before = base_resolves_to_arg(fv, mins, rB, homes, idx - 1)
                row.append('   load = %x: mov %s,[%s] (%d bit)' % (insL.address, rD, rB, bits))
                row.append('   G2 base→argN: ldfix 現行 (upto=load 自身を含む)=%s / load 直前まで=%s  %s'
                           % (a_as_is, a_before, 'PASS' if a_as_is is not None else 'FAIL'))
                argn = a_as_is if a_as_is is not None else a_before
                if argn is not None:
                    blk_text = '\n'.join(ls)
                    has_ld = bool(re.search(r'load [i0-9]+, ptr [^,\n]*%%arg%d(?![\w.$-])' % argn, blk_text))
                    row.append('   G3 IR ブロック内に argN からの既存 load 無し: %s' % ('PASS' if not has_ld else 'FAIL'))
                    rs = [i for i in mins if i.mnemonic == 'mov' and len(i.operands) == 2 and i.operands[0].type == 3
                          and i.operands[1].type == 1 and fv.cs.reg_name(i.operands[1].reg) == rB]
                    row.append('   G4 機械語に rB(=%s) の store 無し: %s %s' % (rB, 'PASS' if not rs else 'FAIL',
                               ('(store: ' + ', '.join('%x: mov %s' % (i.address, i.op_str) for i in rs) + ')') if rs else ''))
                    st = [k for k in range(ia, ib) if re.match(r'^\s*store i\d+ %arg' + str(argn) + r'(?![\w.$-])', ls[k - ia])]
                    row.append('   G5 同一 IR ブロック内の argN 値 store 行数: %d  %s' % (len(st), 'PASS' if st else 'FAIL'))
            print('\n'.join(row))
        # IR 全体での argN 値 store の所在
        print('   IR 全体の `store iN %argK` 行:')
        cur = None
        for l in fn.body.split('\n'):
            m = re.match(r'^([\w.$-]+):', l)
            if m:
                cur = m.group(1)
            if re.match(r'^\s*store i\d+ %arg\d+, ptr ', l):
                print('     [%s] %s' % (cur, l.strip()))


if __name__ == '__main__':
    main()
