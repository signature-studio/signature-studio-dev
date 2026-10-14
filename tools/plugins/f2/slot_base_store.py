#!/usr/bin/env python3
"""#1656 (PLG-F3-13): indirect_resolve.py の `slot_no_store` (.bss slot) の書込み元を 2 段目まで追う。

1 段目: indirect_resolve.py が見る `mov [rip+slot], X` は PE 内に 0 件。
2 段目: slot を含むグローバル構造体の先頭 base を `lea reg,[rip+base]` で取り、
        同じ関数内の `mov [reg+disp], X` (disp = slot - base) を格納元として集める。
        base は slot の手前 0x100 byte から slot までの範囲の rip 相対 lea 先とする。

出力: 標準出力 (slot ごとの候補 base と格納元) と work/f2/slot_base_store_<block>.json。
使い方: python3 tools/plugins/f2/slot_base_store.py <block> <slot_hex> [<slot_hex> ...]
"""
import json, os, sys, struct, bisect, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP

W = os.path.join(HERE, '..', 'work')
SPAN = 0x100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('block', type=int)
    ap.add_argument('slots', nargs='+')
    a = ap.parse_args()
    pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % a.block), fast_load=True)
    pe.parse_data_directories()
    base = pe.OPTIONAL_HEADER.ImageBase
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    funcs = {}
    for i in range(len(pd) // 12):
        b, e, u = struct.unpack_from('<III', pd, 12 * i)
        if b and not (u & 1):
            funcs[base + b] = base + e
    starts = sorted(funcs)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    slots = [int(s, 16) for s in a.slots]

    # 全関数を 1 回ずつ逆アセンブルし、lea/mov の rip 参照先と [reg+disp] 格納を集める
    leas = {}      # target VA -> [(func, site)]
    stores = []    # (func, site, reg, disp, src_text)
    for fs in starts:
        fins = list(md.disasm(pe.get_data(fs - base, funcs[fs] - fs), fs))
        for k, ins in enumerate(fins):
            for o in ins.operands:
                if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP and ins.mnemonic == 'lea':
                    t = ins.address + ins.size + o.mem.disp
                    leas.setdefault(t, []).append((fs, ins.address, ins.operands[0].reg))
            if ins.mnemonic == 'mov' and len(ins.operands) == 2 and ins.operands[0].type == X86_OP_MEM:
                m = ins.operands[0].mem
                if m.base and m.base != X86_REG_RIP and m.index == 0:
                    stores.append((fs, ins.address, md.reg_name(m.base), m.disp, ins.op_str))

    out = {'block': a.block, 'slots': {}}
    for slot in slots:
        cands = []
        for b_ in range(slot - SPAN, slot + 1):
            for fs, site, reg in leas.get(b_, []):
                disp = slot - b_
                # 同じ関数内で、その lea 先レジスタを base とする格納 (disp 一致) を探す
                hits = []
                for sf, ssite, sreg, sdisp, sop in stores:
                    if sf != fs or sdisp != disp:
                        continue
                    if abs(ssite - site) > 0x400:
                        continue
                    if sreg != md.reg_name(reg):
                        continue
                    hits.append([hex(ssite), sop])
                cands.append({'base': hex(b_), 'disp': disp, 'lea_func': hex(fs), 'lea_site': hex(site),
                              'stores_same_func': hits})
        out['slots'][hex(slot)] = cands
        print('slot %s: base 候補 %d 件' % (hex(slot), len(cands)))
        for c in cands:
            print(json.dumps(c, ensure_ascii=False))

    os.makedirs(os.path.join(W, 'f2'), exist_ok=True)
    json.dump(out, open(os.path.join(W, 'f2', 'slot_base_store_%d.json' % a.block), 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
