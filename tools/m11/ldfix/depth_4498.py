#!/usr/bin/env python3
"""#4498 (LD-221): 1046a30 の命令形 VA inttoptr 73 件の段数 (値を読んだ後の逆参照の回数) を確定する。

入力: results/rip_1046a30_3677.tsv (rip_match_3677.py の出力)、work/boot_allfx.ll、work/m11_image.bin
出力: results/depth_1046a30_4498.tsv
列: ir_line, va_hex, ir_use (IR 側: PTR = 読んだ値を inttoptr して再参照 / VAL = 値として使う),
    mc_insn (機械語の rip 参照), mc_use (機械語側: PTR = mov R,[rip] の後に [R] で参照 / VAL = 値として使う),
    depth (確定段数), match (IR と機械語の段数が一致)
判定: 定数アドレスの load の結果を追い、inttoptr (直接または add を挟む) で再参照されるなら 2 段。
      機械語は mov R,[rip] の後に [R] または [R+...] で参照されるなら 2 段。
      添字や加算を挟んだ連鎖は VAL ではなく PTR として扱う (34334・34723 の判定誤りの修正)。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
M11 = os.path.normpath(os.path.join(HERE, '..'))
BASE = 0x400000


def load_ins():
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    img = open(os.path.join(M11, 'work', 'm11_image.bin'), 'rb').read()
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    ins, va = [], 0x1046a30
    while va < 0x104d000:
        got = list(md.disasm(img[va - BASE:va - BASE + 4096], va))
        if not got:
            break
        ins += got
        va = got[-1].address + got[-1].size
    return {i.address: i for i in ins}, ins


def ir_use(L, ln, nm):
    """ln 行目の定数 (名前 nm) から、その load の結果の使われ方を返す。"""
    for j in range(ln, min(len(L), ln + 8)):
        m = re.match(r'\s*%([\w.]+) = load \S+, ptr %' + re.escape(nm) + r'\b', L[j])
        if not m:
            continue
        v = m.group(1)
        for k in range(j + 1, min(len(L), j + 40)):
            s = L[k]
            if re.search(r'inttoptr i64 %' + re.escape(v) + r'\b', s):
                return 'PTR'
            if re.search(r'= add i64 %' + re.escape(v) + r'\b|= add i64 %\S+, %' + re.escape(v) + r'\b', s):
                return 'PTR'
            if re.search(r'%' + re.escape(v) + r'\b', s):
                return 'VAL'
        return 'VAL'
    return '?'


def mc_use(ins_by, mc_va):
    """mc_va の rip 参照命令の使われ方。mov R,[rip] の後に [R...] が来れば PTR。"""
    i = ins_by.get(mc_va)
    if i is None or i.mnemonic != 'mov' or 'rip' not in i.op_str:
        return 'VAL'
    R = i.op_str.split(',')[0].strip()
    a = i.address + i.size
    for _ in range(4):
        n = ins_by.get(a)
        if n is None:
            break
        if re.search(r'\[%s[\s+\]*]' % re.escape(R), n.op_str):
            return 'PTR'
        if n.op_str.split(',')[0].strip() == R:
            break
        a = n.address + n.size
    return 'VAL'


def main():
    L = open(os.path.join(M11, 'work', 'boot_allfx.ll')).read().split('\n')
    ins_by, _ = load_ins()
    src = os.path.join(HERE, 'results', 'rip_1046a30_3677.tsv')
    rows = [l.split('\t') for l in open(src).read().strip().split('\n')[1:]]
    out = [['ir_line', 'va_hex', 'ir_use', 'mc_insn', 'mc_use', 'depth', 'match']]
    for r in rows:
        ln, nm, va_hex, mc = int(r[0]), r[1], r[3], r[6].split()[0]
        iu = ir_use(L, ln - 1, nm)
        mu = mc_use(ins_by, int(mc, 16)) if mc != '-' else '?'
        d_ir = 2 if iu == 'PTR' else 1
        d_mc = 2 if mu == 'PTR' else 1
        out.append([r[0], va_hex, iu, mc, mu, str(d_ir), 'yes' if d_ir == d_mc else 'no'])
    dst = os.path.join(HERE, 'results', 'depth_1046a30_4498.tsv')
    with open(dst, 'w') as f:
        for o in out:
            f.write('\t'.join(o) + '\n')
    no = [o[0] for o in out[1:] if o[6] != 'yes']
    print('rows', len(out) - 1, 'match yes', len(out) - 1 - len(no), 'no', no, '->', dst)
    return 0


if __name__ == '__main__':
    sys.exit(main())
