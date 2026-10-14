#!/usr/bin/env python3
# usage: 実行はこのディレクトリ (tools/targets/massivex) から。
#   python3 license/scripts/mx_table_refs.py ["work/key/extracted/VST3/Massive X.vst3"] [--entries N]
"""N6 読み手 5 関数と N5/N6 文字列 10 VA への「テーブル基準」参照 (E) を総当たりする (#1613 / MX-11)。

  E. 表先頭 base からの 4B 符号付き差分: entry_i = t - base。
     base 候補 = .text の命令が RIP 相対 mem の実効先・即値として指す VA のうち、
     .rdata / .data に入るもの (表を指すコードの参照点)。
     各 base から先頭 N 個の 4B 符号付き値 d を読み、base + d が対象 VA に一致すれば hit。

限界: base は .text の直接参照で得られる VA に限る。表の先頭を別の表・構造体の
ポインタ経由でしか指さない場合は base 候補に入らない (未走査として REPORT に残す)。
自己検査 (--selftest) は既知の表 1 件 (base 参照 + 対象 VA の entry) を検出できなければ exit 1。
"""
import struct
import sys

import capstone
import numpy as np
import pefile

from mx_indirect_refs import IMAGE_BASE, READERS, STRINGS

NAMED = {**{k: v for k, v in READERS.items()}, **{f"string {k}": v for k, v in STRINGS.items()}}
TARGETS = {v: k for k, v in NAMED.items()}


def collect_bases(text, text_va, lo, hi):
    """.text の RIP 相対 mem 実効先・即値のうち [lo, hi) に入る VA を site 付きで集める。"""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    bases = {}
    buf = bytes(text)
    pos = 0
    while pos < len(buf):
        end = 0
        for ins in md.disasm(buf[pos:pos + 0x1000], text_va + pos):
            end = ins.address - (text_va + pos) + ins.size
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                    dst = ins.address + ins.size + op.mem.disp
                elif op.type == capstone.x86.X86_OP_IMM:
                    dst = op.imm & 0xFFFFFFFFFFFFFFFF
                else:
                    continue
                if lo <= dst < hi:
                    bases.setdefault(dst, hex(ins.address))
        pos += end if end else 1
    return bases


def scan_tables(bases, sec_va, sec_raw, entries):
    """sec_raw (VA sec_va から) 内の各 base について先頭 entries 個の 4B 符号付き値を読み、TARGETS と照合。"""
    buf = np.frombuffer(bytes(sec_raw), dtype=np.uint8)
    hits = []
    cand_bases = [b for b in bases if sec_va <= b and b + 4 * entries <= sec_va + len(buf)]
    if not cand_bases:
        return hits, 0
    bva = np.array(cand_bases, dtype=np.int64)
    off = bva - sec_va
    idx = off[:, None, None] + 4 * np.arange(entries, dtype=np.int64)[None, :, None] + np.arange(4, dtype=np.int64)[None, None, :]
    b = buf[idx].astype(np.uint32)
    vals = (b[..., 0] | (b[..., 1] << 8) | (b[..., 2] << 16) | (b[..., 3] << 24)).astype(np.uint32).view(np.int32).astype(np.int64)
    for t, name in TARGETS.items():
        sums = bva[:, None] + vals
        r, c = np.nonzero(sums == t)
        for ri, ci in zip(r, c):
            hits.append((name, int(bva[ri]), int(ci), int(bva[ri]) + 4 * int(ci), bases[int(bva[ri])]))
    return hits, len(cand_bases)


def selftest():
    text_va = 0x180001000
    rd_va = 0x180100000
    t0 = list(TARGETS)[0]
    table = bytearray(b"\x00" * 64)
    base = rd_va + 16
    table[16 + 4 * 3:16 + 4 * 3 + 4] = (t0 - base).to_bytes(4, "little", signed=True)  # entry 3 of base
    code = bytearray(b"\x90" * 0x10)
    code += b"\x48\x8d\x05" + (base - (text_va + len(code) + 7)).to_bytes(4, "little", signed=True)  # lea rax,[rip+base]
    code += b"\x90" * 0x10
    bases = collect_bases(bytes(code), text_va, rd_va, rd_va + len(table))
    hits, n = scan_tables(bases, rd_va, bytes(table), 8)
    ok = any(h[0] == TARGETS[t0] and h[1] == base and h[2] == 3 for h in hits)
    print(f"selftest bases={n} hits={[(h[0], hex(h[1]), h[2]) for h in hits]} (期待 1 件: base={hex(base)} i=3)")
    print("selftest:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    entries = 512
    if "--entries" in sys.argv:
        entries = int(sys.argv[sys.argv.index("--entries") + 1])
        args = [a for a in args if a != str(entries)]
    path = args[0] if args else "work/key/extracted/VST3/Massive X.vst3"
    data = open(path, "rb").read()
    pe = pefile.PE(data=data, fast_load=True)
    assert pe.OPTIONAL_HEADER.ImageBase == IMAGE_BASE
    secs = {s.Name.rstrip(b"\0").decode(errors="replace"): s for s in pe.sections}
    text = secs[".text"]
    text_va = IMAGE_BASE + text.VirtualAddress
    text_raw = data[text.PointerToRawData: text.PointerToRawData + text.SizeOfRawData]
    ro = [s for n, s in secs.items() if n in (".rdata", ".data")]
    lo = min(IMAGE_BASE + s.VirtualAddress for s in ro)
    hi = max(IMAGE_BASE + s.VirtualAddress + s.Misc_VirtualSize for s in ro)
    bases = collect_bases(text_raw, text_va, lo, hi)
    print(f"base 候補 (.text 参照・.rdata/.data 内): {len(bases)} 件, entries/base = {entries}")
    all_hits = []
    for n, s in secs.items():
        if s not in ro:
            continue
        sva = IMAGE_BASE + s.VirtualAddress
        raw = data[s.PointerToRawData: s.PointerToRawData + s.SizeOfRawData]
        hits, nb = scan_tables(bases, sva, raw, entries)
        print(f"section {n:8s} base 内候補 {nb} 件 -> hit {len(hits)} 件")
        all_hits += hits
    for name in NAMED:
        hs = [h for h in all_hits if h[0] == name]
        print(f"\n{name}: {len(hs)} 件")
        for h in hs[:8]:
            print(f"  base {h[1]:#x} idx {h[2]} entry@{h[3]:#x} base 参照元 {h[4]}")


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
