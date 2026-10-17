#!/usr/bin/env python3
"""#3677 (LD-173): function_1046a30 の命令形 10 進 VA `inttoptr i64 N to ptr` (N が VA 範囲) を
機械語の rip 先と突き合わせ、件ごとの表 (TSV) を出す。IR は書き換えない (remap は行わない)。

入力: work/boot_allfx.ll (pass 前の IR) と work/m11_image.bin (VA-0x400000 がオフセット)。
出力: results/rip_1046a30_3677.tsv
列: ir_line, name, va_dec, va_hex, lva, ir_width, mc_insn(rip 参照の先頭), mc_width, width_ok, ir_depth, mc_depth
  - width_ok: IR の load 幅と機械語の rip 参照オペランド幅が一致
  - depth: 値を読んだ後に何段逆参照するか (推定。IR 側は inttoptr の連鎖、機械語側は mov 後の [reg] 参照)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
M11 = os.path.normpath(os.path.join(HERE, '..'))
FN = 'function_1046a30'
BASE = 0x400000
IR_LO, IR_HI = 0x400000, 0x1abf400
WIDTH = {'byte': 1, 'word': 2, 'dword': 4, 'qword': 8, 'xmmword': 16}
IRW = {'i8': 1, 'i16': 2, 'i32': 4, 'i64': 8, 'double': 8, 'float': 4}


def disasm_fn():
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
    return ins


def rip_target(i):
    m = re.search(r'\[rip ([+-]) 0x([0-9a-f]+)\]', i.op_str)
    if not m:
        return None, None
    d = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
    w = re.search(r'(byte|word|dword|qword|xmmword) ptr', i.op_str)
    return i.address + i.size + d, (WIDTH[w.group(1)] if w else None)


def mc_depth(ins, k):
    """ins[k] は mov R, [rip+X]。R を読んだ後の逆参照の段数 (1 = 直接オペランド、2 = [R] を 1 回)。"""
    i = ins[k]
    if i.mnemonic != 'mov':
        return 1
    R = i.op_str.split(',')[0].strip()
    d = 1
    for n in ins[k + 1:k + 4]:
        ops = n.op_str
        if re.search(r'\[%s[\s+\]*]' % re.escape(R), ops):
            return d + 1
        if ops.split(',')[0].strip() == R:
            return d
    return d


def main():
    ins = disasm_fn()
    rip = {}
    for k, i in enumerate(ins):
        t, w = rip_target(i)
        if t is not None:
            rip.setdefault(t, []).append((k, w))
    L = open(os.path.join(M11, 'work', 'boot_allfx.ll')).read().split('\n')
    s = [i for i, l in enumerate(L) if l.startswith('define') and ('@' + FN + '(') in l][0]
    e = next(j for j in range(s + 1, len(L)) if L[j] == '}')
    rows = []
    for i in range(s, e + 1):
        m = re.search(r'%(ce\d+n11_' + FN + r') = inttoptr i64 (\d+) to ptr', L[i])
        if not m:
            continue
        v = int(m.group(2))
        if not (IR_LO <= v <= IR_HI):
            continue
        nm = m.group(1)
        ld = None
        for j in range(i, min(e, i + 6)):
            mm = re.search(r'%([\w.]+) = load (\S+), ptr %' + re.escape(nm) + r'\b', L[j])
            if mm:
                ld = (mm.group(1), mm.group(2))
                break
        ir_w = IRW.get(ld[1]) if ld else None
        refs = rip.get(v, [])
        ref = refs[0] if refs else None
        mc_w = ref[1] if ref else None
        ir_d = 2 if ld and re.search(r'= inttoptr i64 %' + re.escape(ld[0]) + r' ', L[j + 1] if j + 1 < len(L) else '') else 1
        mc_d = mc_depth(ins, ref[0]) if ref else None
        rows.append([
            str(i + 1), nm, str(v), hex(v), str(v - BASE),
            ld[1] if ld else '?', (hex(ins[ref[0]].address) + ' ' + ins[ref[0]].mnemonic) if ref else '-',
            str(mc_w), 'yes' if ref and ir_w == mc_w else ('no' if ref else 'NOREF'),
            str(ir_d), str(mc_d) if mc_d is not None else '-',
        ])
    out = os.path.join(HERE, 'results', 'rip_1046a30_3677.tsv')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as f:
        f.write('\t'.join(['ir_line', 'name', 'va_dec', 'va_hex', 'lva', 'ir_width', 'mc_insn', 'mc_width', 'width_ok', 'ir_depth', 'mc_depth']) + '\n')
        for r in rows:
            f.write('\t'.join(r) + '\n')
    print('rows', len(rows), 'width_ok yes', sum(1 for r in rows if r[8] == 'yes'), '->', out)


if __name__ == '__main__':
    sys.exit(main())
