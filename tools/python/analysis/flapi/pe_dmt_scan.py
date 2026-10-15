#!/usr/bin/env python3
"""FLEngine PE の Delphi 動的メッセージ表 (DMT) から、窓メッセージ ID のハンドラを引く (PY-197 / #3440 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_dmt_scan.py [--chain <VMT VA(16進)>] <メッセージ ID(16進)> ...

- VMT: 自己参照スロット ([VMT-0xc8] == VMT) を持つ位置を .text/.data/.rdata から集め、クラス名 (VMT-0x88 の
  ShortString) が読めるものだけを対象にする。DMT ポインタは VMT-0x90 (Delphi x64 の vmtDynamicTable)。
- DMT の形式: Word count、Word msgid[count]、QWORD handler[count] (絶対 VA)。命令 0x40ff70 の検索と一致する。
- --chain: VMT の継承鎖を出す。vmtParent (VMT-0x78) は親 VMT へのポインタの番地なので、一段デリファレンスして読む。
  各 VMT の slot 0x1d0 (窓生成の仮想呼出し先) と 0x288 (窓プロシージャ) を出す。

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> extracted/block00031_PE.bin
"""
import os
import struct
import sys
from array import array

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def load():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(base + s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData), s.PointerToRawData,
             s.SizeOfRawData, s.Name.rstrip(b"\0").decode()) for s in pe.sections]

    def v2o(va):
        for lo, sz, po, rsz, _ in secs:
            if lo <= va < lo + sz and va - lo < rsz:
                return po + (va - lo)
        return None

    def q(va):
        o = v2o(va)
        return struct.unpack_from("<Q", raw, o)[0] if o is not None else 0

    def cname(vmt):
        p = q(vmt - 0x88)
        o = v2o(p) if p else None
        if o is None or not 0 < raw[o] < 100:
            return None
        s = raw[o + 1:o + 1 + raw[o]]
        return s.decode("latin1") if all(32 <= c < 127 for c in s) else None

    return raw, base, secs, v2o, q, cname


def named_vmts(raw, base, secs, cname):
    out = set()
    for lo, sz, po, rsz, name in secs:
        if name not in (".text", ".data", ".rdata"):
            continue
        arr = array("Q")
        arr.frombytes(raw[po:po + rsz - rsz % 8])
        for i, w in enumerate(arr):
            if w == lo + i * 8 + 0xc8:
                vmt = lo + i * 8 + 0xc8
                if cname(vmt):
                    out.add(vmt)
    return sorted(out)


def main():
    args = sys.argv[1:]
    chain_vmt = None
    if "--chain" in args:
        i = args.index("--chain")
        chain_vmt = int(args[i + 1], 16)
        del args[i:i + 2]
    msgs = [int(a, 16) for a in args]
    raw, base, secs, v2o, q, cname = load()
    vmts = named_vmts(raw, base, secs, cname)
    print(f"named VMTs (self-pointer + class name): {len(vmts)}")
    total = 0
    for vmt in vmts:
        dmt = q(vmt - 0x90)
        if not dmt or v2o(dmt) is None:
            continue
        total += 1
        o = v2o(dmt)
        cnt = struct.unpack_from("<H", raw, o)[0]
        words = struct.unpack_from(f"<{cnt}H", raw, o + 2)
        hp = o + 2 + 2 * cnt
        for m in msgs:
            for idx, w in enumerate(words):
                if w == m:
                    h = struct.unpack_from("<Q", raw, hp + 8 * idx)[0]
                    print(f"msg {m:#x}: {cname(vmt)} VMT {vmt:#x} DMT {dmt:#x} count {cnt} idx {idx} -> handler {h:#x}")
    print(f"VMTs with DMT: {total}")
    if chain_vmt is not None:
        v = chain_vmt
        for _ in range(40):
            if not v or not cname(v):
                break
            pp = q(v - 0x78)
            print(f"  {cname(v)} VMT {v:#x} slot0x1d0 {q(v + 0x1d0):#x} slot0x288 {q(v + 0x288):#x}")
            v = q(pp) if pp else 0


if __name__ == "__main__":
    main()
