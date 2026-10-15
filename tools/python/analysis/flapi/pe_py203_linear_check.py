#!/usr/bin/env python3
"""PY-203 (#3476): 線形走査の限界を検算する (REPORT_PY203.md §0・§4)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py203_linear_check.py <edx_sites.tsv>

<edx_sites.tsv> は pe_py203_edx_sites.py の stdout (setter_va 列を使う)。
- 全体: 直接 jmp/jcc (即値の飛び先) のうち、線形走査の命令境界に一致しない飛び先の件数と割合。
- 各 site: setter から site まで前向きに新規に復号し、境界に整列するか、途中に jmp/jcc/call/ret が無いかを見る。
- 各 site: 飛び先が (setter, site] に入り、飛び元が [setter, site) の外にある直接 jmp/jcc を数える (境界外の飛び先を含む)。
終了 0 = 全 site が整列・途中に分岐なし・外からの飛び込み 0 件。1 件でも外れれば終了 1。
"""
import csv
import os
import sys

import capstone
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as cg  # noqa: E402


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    ins = cg.load()
    boundary = {a for a, _, _ in ins}
    jumps = [(a, int(o, 16)) for a, m, o in ins if m.startswith("j") and o.startswith("0x")]
    nb = sum(1 for _, t in jumps if t not in boundary)
    print(f"直接 jmp/jcc (即値の飛び先) {len(jumps)} 件、境界に一致しない飛び先 {nb} 件 ({100 * nb / len(jumps):.1f}%)")

    raw = open(cg.PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    va0 = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    n = min(text.Misc_VirtualSize, text.SizeOfRawData)
    data = raw[text.PointerToRawData:text.PointerToRawData + n]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def decode(va):
        return next(md.disasm(data[va - va0:va - va0 + 16], va), None)

    with open(sys.argv[1]) as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    checked = aligned = branch_free = entry_sites = entry_jumps = 0
    for r in rows:
        if r["setter_va"] == "-":
            continue
        site = int(r["call_va"], 16)
        s = int(r["setter_va"], 16)
        checked += 1
        cur, branches, ok = s, [], True
        while cur < site:
            d = decode(cur)
            if d is None:
                ok = False
                break
            if d.mnemonic.startswith("j") or d.mnemonic in ("call", "ret"):
                branches.append(cur)
            cur += d.size
        aligned += ok and cur == site
        branch_free += not branches
        inside = [a for a, t in jumps if s < t <= site and not (s <= a < site)]
        entry_sites += bool(inside)
        entry_jumps += len(inside)
        if not (ok and cur == site and not branches and not inside):
            print(f"NG {r['call_va']} setter={r['setter_va']} aligned={ok and cur == site} "
                  f"branches={[hex(b) for b in branches]} entry={[hex(a) for a in inside]}")
    print(f"setter あり {checked} 箇所: setter から site への前向き復号が境界に整列 {aligned}/{checked}、"
          f"途中に jmp/jcc/call/ret なし {branch_free}/{checked}")
    print(f"(setter, site] に外から入る直接 jmp/jcc: {entry_jumps} 件 (該当 site {entry_sites}/{checked})")
    sys.exit(0 if aligned == checked and branch_free == checked and entry_jumps == 0 else 1)


if __name__ == "__main__":
    main()
