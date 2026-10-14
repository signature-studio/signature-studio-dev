#!/usr/bin/env python3
"""対照 Gain の before 一覧 (gain_before_160.tsv) の人手検証用ダンプ (KH-34, #2155).

これは検証結果ではない。人が各行を確認するための材料を出すだけで、verified 列は変更しない。
行ごとに出す内容:
  root 行: 関数先頭の命令 (vtable 経由で呼ばれる入口の確認用)
  非 root 行: 親関数の call_site 直前後の命令 (呼び出しが閉包に入る経路の確認用)
usage: gain_manual_dump.py <HeartCore.core_64> <gain_before_160.tsv>
"""
import csv, sys

import pefile
import capstone


def main(corep, tsvp):
    pe = pefile.PE(corep, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    t = pe.sections[0]
    data = t.get_data()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def ins_at(rva, n):
        off = rva - t.VirtualAddress
        return list(md.disasm(data[off:off + n], base + rva))

    rows = list(csv.DictReader(open(tsvp), delimiter='\t'))
    rva_set = {int(r['func_rva'], 16) for r in rows}
    for i, r in enumerate(rows, 1):
        f = int(r['func_rva'], 16)
        print(f"#{i} {r['func_rva']} size={r['size']} root={r['root_class'] or '-'}")
        if not r['parent_rva']:
            print("  ROOT")
            for x in ins_at(f, 4)[:3]:
                print(f"    {x.address - base:#x}: {x.mnemonic} {x.op_str}")
            continue
        p = int(r['parent_rva'], 16)
        c = int(r['call_site_rva'], 16)
        print(f"  parent={r['parent_rva']} in_set={p in rva_set} call_site={r['call_site_rva']}")
        seq = []
        for x in ins_at(p, c - p + 16):
            seq.append(x)
            if x.address - base > c:
                break
        idx = [k for k, x in enumerate(seq) if x.address - base == c]
        if not idx:
            print("    (call site not on instruction boundary)")
            continue
        k = idx[0]
        for x in seq[max(0, k - 3):k + 2]:
            mark = '>>' if x.address - base == c else '  '
            print(f"    {mark} {x.address - base:#x}: {x.mnemonic} {x.op_str}")


if __name__ == '__main__':
    main(*sys.argv[1:3])

