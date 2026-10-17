#!/usr/bin/env python3
"""selectOneChannel の判定フラグ F1・F2・Z の書込み関数の境界・呼出し元・set/clear 対を PE から再現する (PY-5413 / #6014)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/py5413_flag_writers.py

- 関数境界は .pdata (例外テーブル) から取る。線形走査の関数先頭推定は使わない。
- 呼出し元は .text 内の E8 (call rel32) の全走査。間接呼出し (vtable 等) は拾えない。
- 状態名は PE の文字列からは得られなかった (関数内の RIP 参照の文字列は確認した範囲で無し)。
"""
import bisect
import struct

import py248_gate_chain as g

SITES = {
    "F1": [0xC4DEA0, 0xC4EA3B, 0xD1CB19, 0xD1A2AC],
    "F2": [0xF520EB, 0xFEFBD3, 0xFFF311, 0x1042E47, 0x11D6145, 0xF46338, 0xF53F20,
           0xFEFCD7, 0x11D6310, 0x11D631F, 0xFFF3C3, 0x10440AF],
    "Z": [0x11C761C, 0x1262977],
}
VALUE = {"F1": 0x16BAFF0, "F2": 0x16BAFF1, "Z": 0x13E7628}


def load_pdata():
    dd = g.PEF.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    off = g.fo(g.BASE + dd.VirtualAddress)
    rf = []
    for k in range(dd.Size // 12):
        b, e, _ = struct.unpack_from("<III", g.RAW, off + k * 12)
        if b:
            rf.append((g.BASE + b, g.BASE + e))
    rf.sort()
    return rf


def main():
    rf = load_pdata()
    starts = [a for a, _ in rf]

    def containing(va):
        i = bisect.bisect_right(starts, va) - 1
        return rf[i] if i >= 0 and rf[i][0] <= va < rf[i][1] else None

    text = [s for s in g.PEF.sections if s.Name.rstrip(b"\0") == b".text"][0]
    t0 = g.BASE + text.VirtualAddress
    buf = g.RAW[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]

    print(f"== 1. .pdata 関数数 {len(rf)}")
    print("== 2. 書込み箇所 → 含む関数 (.pdata の境界)")
    fn_sites = {}
    for name, lst in SITES.items():
        for site in lst:
            f = containing(site)
            if f is None:
                print(f"  {name} {site:#x} 関数境界なし")
                continue
            fn_sites.setdefault(f[0], []).append((name, site))
            print(f"  {name} {site:#x} in {f[0]:#x}..{f[1]:#x} (size {f[1] - f[0]:#x})")

    print("== 3. 含む関数の E8 呼出し元 (直接呼出しのみ)")
    callers = {t: [] for t in fn_sites}
    i = buf.find(b"\xe8")
    while i != -1:
        if i + 5 <= len(buf):
            tgt = t0 + i + 5 + struct.unpack_from("<i", buf, i + 1)[0]
            if tgt in callers:
                callers[tgt].append(t0 + i)
        i = buf.find(b"\xe8", i + 1)
    for fs, lst in fn_sites.items():
        cs = ", ".join(f"{c:#x}" for c in callers[fs][:10]) or "(直接呼出し無し)"
        print(f"  fn {fs:#x} sites {[(n, hex(s)) for n, s in lst]} callers: {cs}")

    print("== 4. set/clear の対 (同一関数内)")
    for fs, lst in fn_sites.items():
        names = {n for n, _ in lst}
        if len(names) == 1 and len(lst) >= 2:
            print(f"  fn {fs:#x} {sorted(names)[0]}: {len(lst)} 件 (set/clear 両方がある関数)")
    print("  注: 状態名は未確認 (PE の文字列から特定できず)。")


if __name__ == "__main__":
    main()
