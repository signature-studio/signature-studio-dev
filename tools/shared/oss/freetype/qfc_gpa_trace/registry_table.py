#!/usr/bin/env python3
# #3369 / T-SH-72: QuickFontCache (x64 block24350) の登録簿 (registry) と関数ポインタ表の静的分類。
# 登録簿の実体は DllMain (VA 0x59c1f0) → 0x419dc0 → 0x40f430 が第 2 引数 rdx = 0x59c280 として渡す構造体。
#   +0x00: u32 count, +0x08: u64 表の先頭 VA (16 B の対 (first, second) の配列)。
# first は 0x40f390 (前進走査) が呼び、second は 0x40f2f0 (後退走査) が呼ぶ。
# 出力: 表の各対について、所属 (.text か / .pdata の関数開始か = lift root か / jmp [IAT] thunk か) と
# .reloc の有無 (ポインタとして再配置されるか)。issue の範囲 (RVA 0x19c7e0〜0x19ccf0) を区別して集計する。
# usage: registry_table.py PE_FILE [--tsv OUT]
import struct
import sys

REG_RVA = 0x19C280
ISSUE_LO, ISSUE_HI = 0x19C7E0, 0x19CCF0


def main():
    path = sys.argv[1]
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    ib = struct.unpack_from("<Q", d, pe + 24 + 24)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    dd = pe + 24 + 112  # DataDirectory (PE32+)
    secs = []
    for i in range(nsec):
        s = pe + 24 + optsz + i * 40
        name = d[s : s + 8].rstrip(b"\0").decode()
        vsz, va, rsz, rp = struct.unpack_from("<IIII", d, s + 8)
        secs.append((name, va, max(vsz, rsz), rp))

    def off(rva):
        for _, va, sz, rp in secs:
            if va <= rva < va + sz:
                return rp + rva - va
        raise SystemExit(f"RVA {rva:#x} is outside all sections")

    def sec_of(rva):
        for name, va, sz, _ in secs:
            if va <= rva < va + sz:
                return name
        return "-"

    # .pdata: RUNTIME_FUNCTION (begin, end, unwind) の RVA。lift root (gen_entries.py と同じ集合) の基準。
    pd_va, pd_sz = struct.unpack_from("<II", d, dd + 3 * 8)
    pdata = []
    for o in range(off(pd_va), off(pd_va) + pd_sz, 12):
        b, e = struct.unpack_from("<II", d, o)
        if b:
            pdata.append((b, e))
    pdata_begin = {b for b, _ in pdata}
    pdata_map = sorted(pdata)

    def containing(rva):
        lo, hi = 0, len(pdata_map)
        best = None
        while lo < hi:
            m = (lo + hi) // 2
            if pdata_map[m][0] <= rva:
                best = pdata_map[m]
                lo = m + 1
            else:
                hi = m
        if best and rva < best[1]:
            return best
        return None

    # .reloc: DIR64 (type 10) の再配置先 RVA の集合。
    rl_va, rl_sz = struct.unpack_from("<II", d, dd + 5 * 8)
    relocs = set()
    o, end = off(rl_va), off(rl_va) + rl_sz
    while o < end:
        page, blk = struct.unpack_from("<II", d, o)
        if blk == 0:
            break
        for k in range(0, blk - 8, 2):
            e = struct.unpack_from("<H", d, o + 8 + k)[0]
            if e >> 12 == 10:
                relocs.add(page + (e & 0xFFF))
        o += blk

    # import: IAT slot VA -> 名前 (thunk の解決用)。
    imp_va = struct.unpack_from("<I", d, dd + 1 * 8)[0]
    iat_name = {}
    o = off(imp_va)
    while True:
        oft, _, _, name_rva, ft = struct.unpack_from("<IIIII", d, o)
        if oft == 0 and ft == 0:
            break
        dll = d[off(name_rva) : d.index(b"\0", off(name_rva))].decode()
        ilt = oft or ft
        i = 0
        while True:
            v = struct.unpack_from("<Q", d, off(ilt) + 8 * i)[0]
            if v == 0:
                break
            if not v >> 63:
                nm = d[off(v & 0x7FFFFFFF) + 2 :]
                nm = nm[: nm.index(b"\0")].decode()
            else:
                nm = f"ord{v & 0xFFFF}"
            iat_name[ib + ft + 8 * i] = f"{dll}!{nm}"
            i += 1
        o += 20

    def classify(va):
        rva = va - ib
        info = {"va": va, "sec": sec_of(rva)}
        if info["sec"] == "-":
            return {**info, "pdata_start": False, "func": "-", "thunk": "-"}
        f = containing(rva)
        info["pdata_start"] = rva in pdata_begin
        info["func"] = f"{ib + f[0]:#x}-{ib + f[1]:#x}" if f else "-"
        o2 = off(rva)
        if d[o2 : o2 + 2] == b"\xff\x25":
            slot = ib + rva + 6 + struct.unpack_from("<i", d, o2 + 2)[0]
            info["thunk"] = iat_name.get(slot, f"IAT {slot:#x}")
        else:
            info["thunk"] = "-"
        return info

    count = struct.unpack_from("<I", d, off(REG_RVA))[0]
    arr = struct.unpack_from("<Q", d, off(REG_RVA) + 8)[0]
    arr_rva = arr - ib
    print(f"registry {REG_RVA + ib:#x}: count={count} arr={arr:#x} (RVA {arr_rva:#x})")
    rows = []
    for i in range(count):
        ra = arr_rva + 16 * i
        a, b = struct.unpack_from("<QQ", d, off(ra))
        rows.append((i, ra, a, b))

    def summarize(sel, label):
        n_text = n_root = n_thunk = n_mid = n_reloc = 0
        for i, ra, a, b in sel:
            for v in (a, b):
                c = classify(v)
                n_text += c["sec"] == ".text"
                n_root += c["pdata_start"]
                n_thunk += c["thunk"] != "-"
                n_mid += (not c["pdata_start"]) and c["sec"] == ".text"
            n_reloc += (ra in relocs) + ((ra + 8) in relocs)
        print(
            f"{label}: 組 {len(sel)} / 関数 {2 * len(sel)}: .text={n_text} "
            f"pdata開始(lift root)={n_root} 途中アドレス={n_mid} jmp[IAT] thunk={n_thunk} "
            f".reloc 対象スロット={n_reloc}/{2 * len(sel)}"
        )

    issue = [r for r in rows if ISSUE_LO <= r[1] + 0 and r[1] <= ISSUE_HI]
    summarize(rows, f"全体 (count={count})")
    summarize(issue, "issue 範囲 RVA 0x19c7e0〜0x19ccf0")

    tsv = None
    if "--tsv" in sys.argv:
        tsv = open(sys.argv[sys.argv.index("--tsv") + 1], "w")
        tsv.write("idx\tslot_rva\tin_issue_range\tkind\tfn_va\tsec\tpdata_start\tfunc_range\tthunk\treloc\n")
    for i, ra, a, b in rows:
        for kind, v in (("first", a), ("second", b)):
            c = classify(v)
            line = (
                f"{i}\t{ra:#x}\t{int(ISSUE_LO <= ra <= ISSUE_HI)}\t{kind}\t{v:#x}\t{c['sec']}\t"
                f"{int(c['pdata_start'])}\t{c['func']}\t{c['thunk']}\t{int((ra if kind == 'first' else ra + 8) in relocs)}"
            )
            if tsv:
                tsv.write(line + "\n")
    if tsv:
        tsv.close()


if __name__ == "__main__":
    main()
