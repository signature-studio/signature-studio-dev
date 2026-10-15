#!/usr/bin/env python3
# #2220: QuickFontCache 範囲の GetProcAddress 呼出しを、hModule の由来モジュール名と戻り値で集計する。
# hModule は LoadLibrary/GetModuleHandle の Ret 行の戻り値と、PE DLL の module= から名前に対応づける。
# relay の Call/Ret は thread ごとのスタックで組む (Ret は同名の最も近い Call を閉じる)。
# usage: attrib_gpa.py TRACE IMAGE BASE_HEX
import re
import sys
from collections import Counter, defaultdict

from filter_gpa import size_of_image

CALL_RE = re.compile(r"^([0-9a-f]+):Call\s+(.+?)\((.*?)\)(?: ret=([0-9a-f]+))?\s*$")
RET_RE = re.compile(r"^([0-9a-f]+):Ret\s+(.+?)\(.*?\) retval=([0-9a-f]+)")
LOADERS = {"LoadLibraryA", "LoadLibraryW", "GetModuleHandleA", "GetModuleHandleW"}


def basename(p):
    return re.sub(r"\.dll$", "", p.replace("\\", "/").split("/")[-1].lower())


def main():
    trace, image, base_s = sys.argv[1:4]
    base = int(base_s, 16)
    end = base + size_of_image(image)
    stacks = defaultdict(list)
    recs = []
    handles = {}
    with open(trace, errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            m = CALL_RE.match(line)
            if m:
                thr, name, args, ret = m.groups()
                rec = {
                    "name": name.strip(),
                    "args": args,
                    "ret": int(ret, 16) if ret else None,
                    "retval": None,
                }
                recs.append(rec)
                stacks[thr].append(rec)
                if rec["name"] == "PE DLL":
                    pm = re.search(r'module=([0-9A-Fa-f]+) L?"([^"]*)"', args)
                    if pm:
                        handles[int(pm.group(1), 16)] = basename(pm.group(2))
                continue
            m = RET_RE.match(line)
            if not m:
                continue
            thr, name, retval = m.group(1), m.group(2).strip(), int(m.group(3), 16)
            st = stacks[thr]
            for i in range(len(st) - 1, -1, -1):
                if st[i]["name"] == name:
                    rec = st[i]
                    rec["retval"] = retval
                    del st[i:]
                    if name.split(".")[-1] in LOADERS and retval:
                        nm = re.search(r'L?"([^"]*)"', rec["args"])
                        if nm:
                            handles[retval] = basename(nm.group(1))
                    break

    gpa = []
    for rec in recs:
        if rec["name"].split(".")[-1] != "GetProcAddress":
            continue
        if rec["ret"] is None or not base <= rec["ret"] < end:
            continue
        hm = int(rec["args"].split(",", 1)[0], 16)
        nm = re.search(r'"([^"]*)"\s*$', rec["args"])
        gpa.append(
            {
                "mod": handles.get(hm, f"hmod={hm:#x}"),
                "name": nm.group(1) if nm else None,
                "retval": rec["retval"],
                "ret": rec["ret"],
            }
        )

    print(f"GetProcAddress (ret in [{base:#x}, {end:#x}), Call 行) = {len(gpa)} 件")
    for mod, cnt in Counter(g["mod"] for g in gpa).most_common():
        sub = [g for g in gpa if g["mod"] == mod]
        n_name = sum(1 for g in sub if g["name"] is not None)
        n_null = sum(1 for g in sub if g["retval"] == 0)
        print(
            f"  {mod}: {cnt} 件 (名前 {n_name} / 名前でない {cnt - n_name} / 戻り値 NULL {n_null})"
        )
    ft = [g for g in gpa if g["name"] and g["name"].startswith("FT_")]
    rvas = sorted({hex(g["ret"] - base) for g in ft})
    print(
        f"  FT_* 名 {len(ft)} 件 / 戻り値 NULL {sum(1 for g in ft if g['retval'] == 0)} 件"
        f" / 戻り番地 (RVA) {rvas}"
    )
    for rec in recs:
        if rec["name"] == "PE DLL" and "reason=PROCESS_ATTACH" in rec["args"]:
            pm = re.search(r"module=([0-9A-Fa-f]+)", rec["args"])
            if pm and int(pm.group(1), 16) == base:
                state = "戻る" if rec["retval"] is not None else "戻らない (Ret 行なし)"
                print(f"  DllMain (PROCESS_ATTACH, {basename(image)}): {state}")


if __name__ == "__main__":
    main()
