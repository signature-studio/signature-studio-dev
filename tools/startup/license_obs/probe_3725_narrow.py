#!/usr/bin/env python3
"""#3725 (ST-1) 受入 1: 0x7fffffff の書込みを g1 (0x14f852c) に届く経路まで絞る (読取専用・静的)。

手順:
  (a) g1 の dword (0x14f852c) を指す 8 バイトポインタを素材全体から探す (.data のスロットを特定)
  (b) そのスロット (0x15e14a8) を rip 相対で読む命令を持つ関数を数える
  (c) 即値 0x7fffffff の dword 書込みを全件数え、(b) の関数内にあるものを列挙する
  (d) g1 への書込み (スロット経由の mov [reg], reg) の格納元 eax の直前の代入を表示する

注: (d) は「スロットを読んだ直後 1 命令」だけを見る。離れた命令・別レジスタ経由は見ない (下限)。
広い列挙は probe_3725_taint.py。

usage: python probe_3725_narrow.py --write   (要 FL_WIN64_DIR・venv: tools/startup/license_obs/env.sh)
出力: results/probe_3725_narrow.json (--write 時)
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from peidx import Image, rip_target  # noqa: E402

G1 = 0x14f852c


def slot_of_g1(img):
    raw = img.raw
    pat = struct.pack('<Q', G1)
    hits = []
    i = raw.find(pat)
    while i != -1:
        hits.append(i)
        i = raw.find(pat, i + 1)
    out = []
    for off in hits:
        for s in img.pe.sections:
            if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
                out.append(img.base + s.VirtualAddress + (off - s.PointerToRawData))
    return out


def main():
    img = Image()
    slots = slot_of_g1(img)
    slot = slots[0] if len(slots) == 1 else None
    readers, imm, inside, g1_writes = set(), [], [], []
    for lo, hi, insns in img.iter_insns():
        ins_list = list(insns)
        for k, ins in enumerate(ins_list):
            if slot is not None and rip_target(ins) == slot:
                readers.add(lo)
            if ins.mnemonic == 'mov' and 'dword ptr' in ins.op_str and ', 0x7fffffff' in ins.op_str:
                imm.append((lo, ins.address, ins.op_str))
        if slot is not None:
            for k, ins in enumerate(ins_list):
                if rip_target(ins) == slot and k + 1 < len(ins_list):
                    nxt = ins_list[k + 1]
                    if nxt.mnemonic == 'mov' and nxt.op_str.startswith('dword ptr [') and ', eax' in nxt.op_str:
                        g1_writes.append({'func': hex(lo), 'at': hex(nxt.address), 'insn': nxt.op_str})
    inside = [w for w in imm if w[0] in readers]
    res = {
        'g1': hex(G1),
        'pointer_hits_qword': [hex(x) for x in slots],
        'g1_slot': hex(slot) if slot is not None else None,
        'slot_reader_funcs': len(readers),
        'imm_0x7fffffff_dword_writes': len(imm),
        'imm_writes_in_slot_reader_funcs': [{'func': hex(f), 'at': hex(a), 'insn': s} for f, a, s in inside],
        'g1_slot_store_candidates': g1_writes,
    }
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if '--write' in sys.argv:
        with open(os.path.join(HERE, 'results', 'probe_3725_narrow.json'), 'w') as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
            f.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
