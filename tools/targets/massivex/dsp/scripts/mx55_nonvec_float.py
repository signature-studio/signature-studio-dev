#!/usr/bin/env python3
"""MX-55 (#5030 = MX-54 U3g): 内部の既知形 (定数テーブルを読む scalar float 関数) を探し、読み幅を確認する。

判定規則は mx33_xmm03.py の classify_read / classify_fn をそのまま使う (新しい規則は入れない)。
選抜条件 (固定):
  - xmm0〜3 の入口 livein が 1 つ以上あり、xmm4/5 の入口 livein は 0 (mx33 の母集合と同じ条件)
  - 関数の範囲 [RVA, end) が 600 バイト以下
  - 関数内に RIP 相対の読み (定数テーブル) がある
  - classify_fn が 'scalar'
  - 逆アセンブル上の float 演算 (*ss/*sd。movss/movsd を含む) を 1 つ以上含む
各候補について、入口 livein の読み命令 (位置・mnemonic・分類・理由) と線形 P 読みの有無を出す。

usage: mx55_nonvec_float.py <pe> <vectorcall.json> <out.json>
"""
import json
import sys

import pefile

from mx6_vectorcall import analyze, effects
from mx33_xmm03 import new_md, classify_fn, classify_read


def main(pe_path, vc_path, out_path):
    vc = json.load(open(vc_path))
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]

    def off(r):
        return text.PointerToRawData + (r - text.VirtualAddress)

    def read_abs(va, n):
        try:
            return pe.get_data(va - base, n)
        except pefile.PEFormatError:
            return None

    md = new_md()
    cands = []
    counts = {}
    for label in ('seeds', 'one_round'):
        for x in vc[label]['rows']:
            if not x['livein0_3'] or x['livein45']:
                continue
            va, e = int(x['rva'], 16), int(x['end'], 16)
            if e - va > 600:
                continue
            code = data[off(va):off(va) + (e - va)]
            r = analyze(md, code, base + va, base + e, read_abs)
            if r is None:
                continue
            cls, per_k, reads = classify_fn(md, r)
            counts[cls] = counts.get(cls, 0) + 1
            if cls != 'scalar':
                continue
            ins = list(md.disasm(code, base + va))
            rip = sum(1 for i in ins if 'rip' in i.op_str)
            fl = sorted({i.mnemonic for i in ins if i.mnemonic.lstrip('v').endswith(('ss', 'sd'))})
            if rip == 0 or not fl:
                continue
            lin_p = []
            for i in ins:
                rd, _ = effects(md, i)
                for k in range(4):
                    if rd >> k & 1 and classify_read(md, i, k)[0] == 'P':
                        lin_p.append([hex(i.address), i.mnemonic, k])
            cands.append({
                'label': label, 'rva': x['rva'], 'end': x['end'], 'pdata_begin': x['pdata_begin'],
                'insns': r['insns'], 'livein_k': sorted(x['livein0_3']), 'fn_class': cls,
                'rip_rel': rip, 'float_ops': fl, 'linear_P': lin_p,
                'reads': [[hex(i.address), i.mnemonic, i.op_str, c, why]
                          for k, lst in sorted(reads.items()) for i, c, why in lst],
            })
    res = {'fn_class_counts': counts, 'candidates': cands}
    json.dump(res, open(out_path, 'w'), indent=1, ensure_ascii=False)
    print('fn_class (livein xmm0-3 only, <=600 B): %s' % counts)
    print('candidates (scalar + RIP const + float op): %d' % len(cands))
    for c in cands:
        print('| %s | %s | pdata_begin=%s | insns=%d | livein=%s | rip=%d | ops=%s | linear_P=%d |' % (
            c['rva'], c['end'], c['pdata_begin'], c['insns'], c['livein_k'], c['rip_rel'],
            ','.join(c['float_ops']), len(c['linear_P'])))
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
