#!/usr/bin/env python3
# DLL 向けの (E) テーブル基準走査。既存 mx_table_refs のロジックを DLL の VA 集合で実行する (既存スクリプトは変更しない)。
import sys

sys.path.insert(0, "license/scripts")
import mx_table_refs as T  # noqa: E402
import pefile  # noqa: E402

DLL_READERS = {
    "N6-1 0x180167a70": 0x180167A70,
    "N6-2 0x180f84920": 0x180F84920,
    "N6-3 0x181130b20": 0x181130B20,
    "N6-4 0x181130d30": 0x181130D30,
    "N6-5 0x181131000": 0x181131000,
    "N6-6 0x1811325c0": 0x1811325C0,
    "N6-7 0x181132f30": 0x181132F30,
    "N6-8 0x181133db0": 0x181133DB0,
}
DLL_STRINGS = {
    "N6 0x184fe8fa0": 0x184FE8FA0,
    "N6 0x184fe83b7": 0x184FE83B7,
    "N6 0x184fe83fc": 0x184FE83FC,
    "N6 0x184fe845c": 0x184FE845C,
    "N6 0x184fe84b3": 0x184FE84B3,
    "N6 0x184fe8506": 0x184FE8506,
    "N6 0x184fe854a": 0x184FE854A,
    "N6 0x184fe7870": 0x184FE7870,
    "N5 demoExpired 0x184862e67": 0x184862E67,
    "N5 demoExpiredChanged 0x184862d19": 0x184862D19,
    "N5 subscriptionExpired 0x184862e7a": 0x184862E7A,
}
NAMED = {**DLL_READERS, **{f"string {k}": v for k, v in DLL_STRINGS.items()}}
T.NAMED = NAMED
T.TARGETS = {v: k for k, v in NAMED.items()}

path = sys.argv[1] if len(sys.argv) > 1 else "work/key/extracted/Native Instruments/Massive X.dll"
data = open(path, "rb").read()
pe = pefile.PE(data=data, fast_load=True)
IMG = pe.OPTIONAL_HEADER.ImageBase
secs = {s.Name.rstrip(b"\0").decode(errors="replace"): s for s in pe.sections}
text = secs[".text"]
text_va = IMG + text.VirtualAddress
text_raw = data[text.PointerToRawData: text.PointerToRawData + text.SizeOfRawData]
ro = [s for n, s in secs.items() if n in (".rdata", ".data")]
lo = min(IMG + s.VirtualAddress for s in ro)
hi = max(IMG + s.VirtualAddress + s.Misc_VirtualSize for s in ro)
bases = T.collect_bases(text_raw, text_va, lo, hi)
print(f"base 候補 (.text 参照・.rdata/.data 内): {len(bases)} 件, entries/base = 512")
all_hits = []
for n, s in secs.items():
    if s not in ro:
        continue
    sva = IMG + s.VirtualAddress
    raw = data[s.PointerToRawData: s.PointerToRawData + s.SizeOfRawData]
    hits, nb = T.scan_tables(bases, sva, raw, 512)
    print(f"section {n:8s} base 内候補 {nb} 件 -> hit {len(hits)} 件")
    all_hits += hits
for name in NAMED:
    hs = [h for h in all_hits if h[0] == name]
    print(f"{name}: {len(hs)} 件")
    for h in hs[:8]:
        print(f"  base {h[1]:#x} idx {h[2]} entry@{h[3]:#x} base 参照元 {h[4]}")
