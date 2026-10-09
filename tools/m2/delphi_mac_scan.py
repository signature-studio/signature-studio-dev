#!/usr/bin/env python3
# M2-5 (delphi_inventory): mac FLEEngine x86_64 slice の Delphi RTTI/VMT スキャン。
#
# mac slice では Delphi x64 の VMT が __const (.__TEXT/__DATA) に実アドレス表として
# 埋め込まれる (file offset == vmaddr のため file bytes を直接走査できる)。
# 検出方式は tools/m2/delphi_scan.py (win PE 版) と同一規約:
#   vmtClassName (-112) 保管先 QWORD → Pascal 文字列 (Len+name) 参照を検出
#   し、class pointer P = storage + 112 を採取する。
#
# 出力: work/delphi_mac.json + 標準出力サマリ
#
#   python3 delphi_mac_scan.py --input work/FLEngine_x86_64.dylib --out work/delphi_mac.json

import argparse
import json
import re
import struct
import sys

# macho x86_64 slice: file offset == vm address (本 slice の segment layout)
def die(msg):
    print(f"[delphi_mac] FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="走査バイト上限 (0=全部)")
    args = ap.parse_args()

    data = open(args.input, "rb").read()
    limit = args.limit if args.limit else len(data)

    shortstr = re.compile(rb"\x00([\x01-\x30])([A-Z][A-Za-z0-9_]{2,63})\x00")
    name_by_rva = {}
    for m in shortstr.finditer(data[:limit]):
        L = m.group(1)[0]
        nm = m.group(2).decode("latin1")
        if L == len(nm):
            r = m.start(1)
            if r < limit:
                name_by_rva[r] = nm

    vmts = []
    seen = set()
    scan_end = min(len(data) - 8, limit)
    for o in range(0, scan_end, 4):
        v = struct.unpack("<Q", data[o:o + 8])[0]
        if v in name_by_rva:
            a = o                      # vmtClassName 保管先アドレス (P - 112)
            P = a + 112
            if P not in seen:
                seen.add(P)
                vmts.append({"class_ptr": P, "name": name_by_rva[v],
                             "name_addr": v})
    # bss 等に置かれる class var (storage of P) → __const 走査で恒常 (data も同様)
    out = {
        "file": args.input,
        "pascal_strings": len(name_by_rva),
        "vmt_class_pointers": len(vmts),
        "vmts_example": vmts[:60],
    }
    with open(args.out, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(f"[delphi_mac] Pascal strings candidates: {len(name_by_rva)}")
    print(f"[delphi_mac] VMT class pointers: {len(vmts)}")
    for v in vmts[:30]:
        print(f"  - {v['name']} @ 0x{v['class_ptr']:x}")
    print(f"[delphi_mac] wrote {args.out}")


if __name__ == "__main__":
    main()
