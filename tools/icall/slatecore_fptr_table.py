#!/usr/bin/env python3
"""SlateCore.core_64 の encoded 関数ポインタ表 (api-set 相当) の範囲を調べる (ICALL-57 #2081)。

入力は `objdump -d -M intel --no-show-raw-insn <PE>` の出力 (RIP 相対の参照先が `# 0x...` で出る)。

1. decode 候補: `ror <reg>,cl` の直前 8 命令以内にある `xor <reg>,QWORD PTR [rip+..]` の参照先 (.data)
   を slot として集める (cookie 由来の rot count `cl` で ror する decode 形式)。
2. zero-fill 部 (raw 無しの .data 末尾) への全 RIP 相対参照を命令種別つきで集める。
3. 参照アドレスを 8 byte 単位で並べ、連続クラスタ (隣接 slot の gap が 0x40 以下) を出す。
4. 既知の 12 slot (REPORT_APPENDIX_1921.md §2) が含まれるかを確認する。

使い方:
  objdump -d -M intel --no-show-raw-insn "<SlateCore.core_64>" > $RUNNER_TEMP/sc_text.s
  python3 tools/icall/slatecore_fptr_table.py $RUNNER_TEMP/sc_text.s
"""
import re
import sys
from collections import Counter, defaultdict

ZF_LO = 0x18128F400  # .data raw 末尾 (zero-fill 開始)
ZF_HI = 0x18130A000  # .data 末尾
COOKIE = 0x18125EAA8
KNOWN = [
    0x1813068D0, 0x1813068F8, 0x181306900, 0x181306908, 0x181306910, 0x1813072B0,
    0x1813073F0, 0x1813073F8, 0x181307400, 0x181307408, 0x181307410, 0x181307418,
]

LINE = re.compile(r"^\s*([0-9a-f]+):\t(\S+)\s*(.*)$")
RIP_TGT = re.compile(r"# 0x([0-9a-f]+)")


def parse(path):
    insns = []
    with open(path, errors="replace") as f:
        for line in f:
            m = LINE.match(line.rstrip("\n"))
            if not m:
                continue
            addr = int(m.group(1), 16)
            mnem = m.group(2)
            rest = m.group(3)
            tgt = None
            if "[rip+" in rest:
                t = RIP_TGT.search(rest)
                if t:
                    tgt = int(t.group(1), 16)
            insns.append((addr, mnem, rest, tgt))
    return insns


def main():
    insns = parse(sys.argv[1])
    print(f"命令数: {len(insns)}")

    decode_slots = Counter()
    decode_sites = []
    for i, (addr, mnem, rest, tgt) in enumerate(insns):
        if mnem == "ror" and rest.endswith(",cl"):
            for j in range(max(0, i - 8), i):
                a2, m2, r2, t2 = insns[j]
                if m2 == "xor" and t2 is not None and ZF_LO <= t2 < ZF_HI:
                    decode_slots[t2] += 1
                    decode_sites.append((addr, t2))
                    break
    print(f"decode 候補 (ror ,cl の直前 8 命令内に zero-fill slot の xor): {len(decode_sites)} 箇所")
    print(f"decode 候補の slot 種数: {len(decode_slots)}")
    for s in sorted(decode_slots):
        print(f"  0x{s:x}  x{decode_slots[s]}  known={s in KNOWN}")

    zf_refs = defaultdict(list)
    for addr, mnem, rest, tgt in insns:
        if tgt is not None and ZF_LO <= tgt < ZF_HI:
            zf_refs[tgt].append((addr, mnem))
    print(f"zero-fill への RIP 相対参照先の種数: {len(zf_refs)}")
    kinds = Counter(m for lst in zf_refs.values() for _, m in lst)
    print("  命令種別:", dict(kinds))

    print("既知 12 slot の確認:")
    for k in KNOWN:
        refs = zf_refs.get(k, [])
        kind = ",".join(sorted({m for _, m in refs})) or "-"
        print(f"  0x{k:x} refs={len(refs)} ({kind}) decode={k in decode_slots}")

    addrs = sorted(zf_refs)
    clusters = []
    for a in addrs:
        if clusters and a - clusters[-1][-1] <= 0x40:
            clusters[-1].append(a)
        else:
            clusters.append([a])
    print(f"連続クラスタ (gap <= 0x40): {len(clusters)} 個")
    for c in clusters:
        known = sum(1 for k in KNOWN if c[0] <= k <= c[-1])
        dec = sum(1 for s in decode_slots if c[0] <= s <= c[-1])
        print(f"  0x{c[0]:x}-0x{c[-1]:x} slots={len(c)} known={known} decode={dec}")

    lea_zf = [(a, r) for a, m, r, t in insns if m == "lea" and t is not None and ZF_LO <= t < ZF_HI]
    print(f"lea で zero-fill を指す命令: {len(lea_zf)} 件")
    for a, r in lea_zf[:20]:
        print(f"  {a:x}: lea {r}")


if __name__ == "__main__":
    main()
