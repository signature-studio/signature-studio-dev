#!/usr/bin/env python3
"""SR-3d #867 (受入 2): 窓外 muParser 6 関数の VA を指す参照を、形式別に全 PE 走査する (静的)。

形式: (a) 8 バイト絶対ポインタ (ImageBase+RVA, LE) / (b) 4 バイト RVA (LE) / (c) RIP 相対オペランド (.text の線形走査)。
出力: 形式ごとの所属セクション・件数・ヒット位置 (RVA)。(c) の線形走査はセクションごとに被覆率 (c0) を出す (無効バイトで止まらないよう再開する)。
usage: python3 scripts/sr3d_fnptr_scan.py work/Serum2_win64.vst3
"""
import os
import sys
import pefile
import capstone

TARGETS = [0x1809E3240, 0x1809EB7B0, 0x1809EF030, 0x1809EF7B0, 0x180A0A3E0, 0x180A0F3F0]
NAMES = [0x180FDC5DC, 0x180FDC880, 0x180FDC69C, 0x180FDC5B0, 0x180FDC890]  # acos log2 sinh sqrt log10 (6 関数の lea 先)


def sec_of_off(pe, off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return s.Name.rstrip(b"\0").decode(errors="replace"), s.VirtualAddress + (off - s.PointerToRawData)
    return "(header)", off


def sec_of_rva(pe, rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.Name.rstrip(b"\0").decode(errors="replace")
    return "(none)"


def sweep(md, code, va):
    """線形走査。capstone は無効バイトに当たると出力を止めるため、止まった次の 1 バイトから再開する。
    返り値: (命令列, デコード済みバイト数, 未デコードのバイトの VA 列)。"""
    insns = []
    off = 0
    skipped = []
    while off < len(code):
        pos = off
        for ins in md.disasm(memoryview(code)[off:], va + off):
            insns.append(ins)
            pos = ins.address - va + ins.size
        if pos >= len(code):
            break
        skipped.append(va + pos)
        off = pos + 1
    return insns, sum(i.size for i in insns), skipped


def main(path):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, "rb").read()
    print(f"ImageBase 0x{base:x} sections {len(pe.sections)}")
    for t in TARGETS + NAMES:
        rva = t - base
        print(f"\n== target 0x{t:x} (rva 0x{rva:x}) sec {sec_of_rva(pe, rva)}")
        pat8 = t.to_bytes(8, "little")
        hits8 = []
        i = data.find(pat8)
        while i != -1:
            hits8.append(sec_of_off(pe, i))
            i = data.find(pat8, i + 1)
        print(f"  (a) abs8 hits: {len(hits8)} " + " ".join(f"{s}:0x{r:x}" for s, r in hits8[:10]))
        pat4 = rva.to_bytes(4, "little")
        hits4 = []
        i = data.find(pat4)
        while i != -1:
            hits4.append(sec_of_off(pe, i))
            i = data.find(pat4, i + 1)
        print(f"  (b) rva4 hits: {len(hits4)} " + " ".join(f"{s}:0x{r:x}" for s, r in hits4[:10]))

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    tset = set(TARGETS + NAMES)
    rip_hits = {t: [] for t in TARGETS + NAMES}
    n_rip = 0
    cov = []
    for s in pe.sections:
        if not (s.Characteristics & 0x20000000):
            continue
        code = s.get_data()
        va = base + s.VirtualAddress
        insns, dec, skipped = sweep(md, code, va)
        if code:
            cov.append((s.Name.rstrip(b"\0").decode(errors="replace"), len(code), dec, skipped))
        for ins in insns:
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                    n_rip += 1
                    tgt = ins.address + ins.size + op.mem.disp
                    if tgt in tset:
                        rip_hits[tgt].append((ins.address, ins.mnemonic))
                if op.type == capstone.x86.X86_OP_IMM and op.imm in tset:
                    rip_hits[op.imm].append((ins.address, "imm:" + ins.mnemonic))
    print("\n(c0) 線形走査の被覆率 (実行可能セクション。デコード済みバイト / セクション長、再開 = 無効バイトからの再開回数、未デコード位置 = 無効バイトの VA)")
    for name, n, dec, skipped in cov:
        pos_txt = (" 位置 " + " ".join(f"0x{a:x}" for a in skipped[:20])) if skipped else ""
        print(f"  {name:<8} {dec}/{n} B = {100 * dec / n:.2f}% 未デコード {n - dec} B 再開 {len(skipped)} 回{pos_txt}")
    tot_n = sum(n for _, n, _, _ in cov)
    tot_dec = sum(dec for _, _, dec, _ in cov)
    print(f"  合計 {tot_dec}/{tot_n} B = {100 * tot_dec / tot_n:.2f}% 未デコード {tot_n - tot_dec} B")
    print(f"\n(c) .text RIP-relative operands scanned: {n_rip}")
    for t in TARGETS + NAMES:
        h = rip_hits[t]
        print(f"  0x{t:x}: {len(h)} " + " ".join(f"0x{a:x}({m})" for a, m in h[:10]))
    cut = []
    cut_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "sr3_cut_table.tsv")
    with open(cut_path) as f:
        next(f)
        for line in f:
            va, nbytes, lib, _tag = line.rstrip("\n").split("\t")
            cut.append((int(va, 16), int(nbytes), lib))
    print("\n(d) 6 関数の直接呼出元の所属 (cut 表 = 区分済みの OSS 境界 1,510 関数)。call/jmp と jcc (条件分岐) を分けて数える")
    for t in TARGETS:
        calls = [a for a, m in rip_hits[t] if m in ("imm:call", "imm:jmp")]
        jccs = [(a, m) for a, m in rip_hits[t] if m.startswith("imm:j") and m != "imm:jmp"]
        libs = {}
        for c in calls:
            lib = next((lb for v, n, lb in cut if v <= c < v + n), "(cut 外)")
            libs[lib] = libs.get(lib, 0) + 1
        jcc_txt = " ".join(f"0x{a:x}({m[4:]})" for a, m in jccs)
        print(f"  0x{t:x}: call/jmp {len(calls)} 件 → " + ", ".join(f"{k} {v}" for k, v in sorted(libs.items()))
              + f" / jcc {len(jccs)} 件 {jcc_txt}".rstrip())


if __name__ == "__main__":
    main(sys.argv[1])
