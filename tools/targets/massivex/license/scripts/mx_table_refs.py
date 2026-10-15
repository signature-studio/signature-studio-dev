#!/usr/bin/env python3
# usage: 実行はこのディレクトリ (tools/targets/massivex) から。
#   python3 license/scripts/mx_table_refs.py ["work/key/extracted/VST3/Massive X.vst3"] [--entries N] [--control]
#   python3 license/scripts/mx_table_refs.py --selftest
"""N6 読み手 5 関数と N5/N6 文字列 10 VA への「テーブル基準」参照 (E) を総当たりする (#1613 / MX-11)。

  E. 表先頭 base からの 4B 符号付き差分: entry_i = t - base。
     base 候補 = .text の命令が RIP 相対 mem の実効先・即値として指す VA のうち、
     .rdata / .data に入るもの (表を指すコードの参照点)。
     各 base から先頭 N 個の 4B 符号付き値 d を読み、base + d が対象 VA に一致すれば hit。
  一貫性: hit の前後 WINDOW 個 (範囲内) の entry のうち、d != 0 で対象と同じセクションを指すものが 1/2 以上なら OK。
     表として隣接 entry が同じ領域を指すかを見る (周辺が別セクション・セクション外に散るなら誤検出の疑い)。
     d == 0 (base 自身) は所属を示さないので除外し、周辺がすべて 0 埋めなら NG。
  対照 (--control): 対象 15 VA の代わりに、.rdata 内のランダム VA CONTROL_N 件 (seed CONTROL_SEED) を同じ走査で照合する。
    偶然一致の水準 (1 対象あたり平均 hit) を測る。

限界: base は .text の直接参照で得られる VA に限る。表の先頭を別の表・構造体の
ポインタ経由でしか指さない場合は base 候補に入らない (未走査として REPORT に残す)。
自己検査 (--selftest) は既知の表 entry が一貫 OK で検出され、周辺が別セクションに散る同形の表 entry が一貫 NG になることを確かめ、
どちらか違えば exit 1。
"""
import random
import struct
import sys

import capstone
import numpy as np
import pefile

from mx_indirect_refs import IMAGE_BASE, READERS, STRINGS

NAMED = {**{k: v for k, v in READERS.items()}, **{f"string {k}": v for k, v in STRINGS.items()}}
TARGETS = {v: k for k, v in NAMED.items()}
WINDOW = 4
CONTROL_N = 40
CONTROL_SEED = 3154


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


def section_of(va, sections):
    for n, lo, hi in sections:
        if lo <= va < hi:
            return n
    return None


def consistent(row, base, ci, t, sections):
    """row の ci 番目 (hit) の前後 WINDOW 個 (範囲内) のうち、d != 0 の entry が t と同じセクションを指す割合が 1/2 以上か。
    d == 0 は base 自身を指す (表の 0 埋め・自己参照) ため所属を判定できず除外する。hit 自体が d == 0 なら NG。"""
    if int(row[ci]) == 0:
        return False
    ts = section_of(t, sections)
    near = [int(row[j]) for j in range(max(0, ci - WINDOW), min(len(row), ci + WINDOW + 1)) if j != ci and row[j] != 0]
    same = sum(section_of(base + d, sections) == ts for d in near)
    return bool(near) and 2 * same >= len(near)


def scan_tables(bases, sec_va, sec_raw, entries, targets=None, sections=None):
    """sec_raw (VA sec_va から) 内の各 base について先頭 entries 個の 4B 符号付き値を読み、targets (省略時は TARGETS) と照合。
    一貫性判定に sections (セクション名・VA 範囲の列) を使うため必須。
    hit は (対象名, base, idx, entry VA, base 参照元, 一貫性) で返す。"""
    if sections is None:
        raise ValueError("scan_tables: sections は必須 (一貫性判定に使う)")
    if targets is None:
        targets = TARGETS
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
    sums = bva[:, None] + vals
    for t, name in targets.items():
        r, c = np.nonzero(sums == t)
        for ri, ci in zip(r, c):
            base = int(bva[ri])
            hits.append((name, base, int(ci), base + 4 * int(ci), bases[base], consistent(vals[ri], base, int(ci), t, sections)))
    return hits, len(cand_bases)


def selftest():
    text_va = 0x180001000
    rd_va = 0x180100000
    rd_size = 0x1000
    sections = [(".rdata", rd_va, rd_va + rd_size)]
    t_syn = rd_va + 0x800
    good = rd_va + 16
    bad = rd_va + 0x80
    zero = rd_va + 0x100
    table = bytearray(b"\x00" * rd_size)
    for j in range(8):
        table[16 + 4 * j:20 + 4 * j] = (rd_va + 0x900 + 0x10 * j - good).to_bytes(4, "little", signed=True)
        table[0x80 + 4 * j:0x84 + 4 * j] = (0x40000000 + 0x10 * j).to_bytes(4, "little", signed=True)
    table[16 + 12:32] = (t_syn - good).to_bytes(4, "little", signed=True)
    table[0x80 + 12:0x90] = (t_syn - bad).to_bytes(4, "little", signed=True)
    table[0x100 + 12:0x110] = (t_syn - zero).to_bytes(4, "little", signed=True)
    selfb = rd_va + 0x200
    for j in range(8):
        table[0x200 + 4 * j:0x204 + 4 * j] = (rd_va + 0x900 + 0x10 * j - selfb).to_bytes(4, "little", signed=True)
    table[0x200 + 12:0x210] = b"\x00\x00\x00\x00"
    code = bytearray(b"\x90" * 0x10)
    for dst in (good, bad, zero, selfb):
        at = len(code)
        code += b"\x48\x8d\x05" + (dst - (text_va + at + 7)).to_bytes(4, "little", signed=True)  # lea rax,[rip+dst]
        code += b"\x90" * 0x10
    bases = collect_bases(bytes(code), text_va, rd_va, rd_va + rd_size)
    hits, n = scan_tables(bases, rd_va, bytes(table), 8, {t_syn: "synthetic", selfb: "self"}, sections)
    got = {(h[1], h[2]): h[5] for h in hits}
    ok = got == {(good, 3): True, (bad, 3): False, (zero, 3): False, (selfb, 3): False}
    global TARGETS
    keep = TARGETS
    TARGETS = {t_syn: "synthetic"}
    try:
        hits_def, _ = scan_tables(bases, rd_va, bytes(table), 8, sections=sections)
    finally:
        TARGETS = keep
    ok = ok and any(h[0] == "synthetic" and h[1] == good and h[2] == 3 for h in hits_def)
    print(f"selftest bases={n} hits={[(hex(h[1]), h[2], h[5]) for h in hits]} (期待 4 件: base={hex(good)} i=3 一貫 OK / base={hex(bad)} i=3 一貫 NG / base={hex(zero)} i=3 (周辺 0 埋め) 一貫 NG / base={hex(selfb)} i=3 (d=0 の自己参照) 一貫 NG)")
    print("selftest:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    entries = 512
    if "--entries" in sys.argv:
        entries = int(sys.argv[sys.argv.index("--entries") + 1])
        args = [a for a in args if a != str(entries)]
    control = "--control" in sys.argv
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
    sections = [(n, IMAGE_BASE + s.VirtualAddress, IMAGE_BASE + s.VirtualAddress + s.Misc_VirtualSize) for n, s in secs.items()]
    if control:
        rd = secs[".rdata"]
        rd_lo = IMAGE_BASE + rd.VirtualAddress
        vas = random.Random(CONTROL_SEED).sample(range(rd_lo, rd_lo + rd.Misc_VirtualSize), CONTROL_N)
        targets = {va: f"control {i:02d} {va:#x}" for i, va in enumerate(vas)}
        print(f"対照: .rdata {rd_lo:#x}..{rd_lo + rd.Misc_VirtualSize:#x} 内のランダム VA {CONTROL_N} 件 (seed {CONTROL_SEED})")
    else:
        targets = TARGETS
    print(f"base 候補 (.text 参照・.rdata/.data 内): {len(bases)} 件, entries/base = {entries}")
    all_hits = []
    for n, s in secs.items():
        if s not in ro:
            continue
        sva = IMAGE_BASE + s.VirtualAddress
        raw = data[s.PointerToRawData: s.PointerToRawData + s.SizeOfRawData]
        hits, nb = scan_tables(bases, sva, raw, entries, targets, sections)
        print(f"section {n:8s} base 内候補 {nb} 件 -> hit {len(hits)} 件")
        all_hits += hits
    for name in targets.values():
        hs = [h for h in all_hits if h[0] == name]
        print(f"\n{name}: {len(hs)} 件 (一貫性 OK {sum(h[5] for h in hs)} 件)")
        for h in hs[:8]:
            print(f"  base {h[1]:#x} idx {h[2]} entry@{h[3]:#x} base 参照元 {h[4]} 一貫性 {'OK' if h[5] else 'NG'}")
    n_t = len(targets)
    raw_n = len(all_hits)
    ok_n = sum(h[5] for h in all_hits)
    print(f"\n合計: 対象 {n_t} 件・hit {raw_n} 件 (1 対象あたり平均 {raw_n / n_t:.3f})・一貫性 OK {ok_n} 件 (1 対象あたり平均 {ok_n / n_t:.3f})")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
