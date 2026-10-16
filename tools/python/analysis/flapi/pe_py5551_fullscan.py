#!/usr/bin/env python3
"""PY-5356 (#5551): 0x15e6068 と 0x1376820 の全ブロック走査 (解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py5551_fullscan.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*extracted/*_PE.bin'
  (<展開先>/extracted/*_PE.bin が存在すること。1.2 GB の展開物は commit しない)
走査: <展開先>/extracted/*_PE.bin のうち ImageBase 0x400000 のもの (165 件を期待) を
      objdump -d -M intel で逆アセンブルし、全 mnemonic の命令を見る。
      (a) RIP 相対 memory operand (`# 0xADDR` コメント)
      (b) 絶対 disp の memory operand (`ds:0xADDR`)
      (c) 直接 call/jmp の宛先
      書込み候補: op0 が memory で、cmp/test/call/jmp/push/lea/bt/nop 以外の命令、および xchg/xadd/cmpxchg。
      movs/stos 等の文字列命令の暗黙書込みは数えない。
      (参考) .text の生バイト列の 8 バイト LE 一致も数える。
終了 0 = 期待件数 (165 ブロック)・0x15e6068 の書込み候補 0・0x1376820 の命令参照 0・生バイト一致 0。違えば終了 1。
"""
import glob
import os
import re
import subprocess
import sys

import pefile

DIR = os.path.join(os.environ["FL_WIN64_DIR"], "extracted")
TARGETS = {"0x15e6068": 0x15E6068, "0x1376820": 0x1376820}
READ_ONLY = {"cmp", "test", "call", "jmp", "push", "lea", "bt", "nop"}
RMW = {"xchg", "xadd", "cmpxchg"}
EXPECT_BLOCKS = 165
INSN = re.compile(r"^\s*([0-9a-f]+):\t(\S+)\s*(.*)$")
RIP_COMMENT = re.compile(r"# 0x([0-9a-f]+)")
ABS = re.compile(r"ds:0x([0-9a-f]+)")
DIRECT = re.compile(r"^([0-9a-f]+)\s*(<|$)")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def load(path):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.startswith(b".text")]
    code = b""
    if text:
        raw = open(path, "rb").read()
        code = raw[text[0].PointerToRawData:text[0].PointerToRawData + text[0].SizeOfRawData]
    return base, code


def is_write(mn, ops):
    op0 = ops.split(",")[0]
    if mn in RMW:
        return True
    if mn in READ_ONLY:
        return False
    return "[" in op0 or "ds:" in op0


def main():
    blocks = sorted(glob.glob(os.path.join(DIR, "*_PE.bin")))
    hits = {name: {"ref": [], "write": [], "raw": []} for name in TARGETS}
    n_block = 0
    for path in blocks:
        base, code = load(path)
        if base != 0x400000:
            continue
        n_block += 1
        bn = os.path.basename(path)
        for name, t in TARGETS.items():
            off = code.find(t.to_bytes(8, "little"))
            while off >= 0:
                hits[name]["raw"].append(f"{bn} +0x{off:x}")
                off = code.find(t.to_bytes(8, "little"), off + 1)
        out = subprocess.run(
            ["objdump", "-d", "-M", "intel", "--no-show-raw-insn", path],
            check=True, capture_output=True, text=True,
        ).stdout
        for line in out.splitlines():
            m = INSN.match(line)
            if not m:
                continue
            addr, mn, ops = m.group(1), m.group(2), m.group(3)
            found = set()
            rc = RIP_COMMENT.search(ops)
            if rc:
                found.add(int(rc.group(1), 16))
            ab = ABS.search(ops)
            if ab:
                found.add(int(ab.group(1), 16))
            if mn in ("call", "jmp"):
                dm = DIRECT.match(ops)
                if dm:
                    found.add(int(dm.group(1), 16))
            for name, t in TARGETS.items():
                if t in found:
                    rec = f"{bn} 0x{addr} {mn} {ops}"
                    hits[name]["ref"].append(rec)
                    if is_write(mn, ops):
                        hits[name]["write"].append(rec)
                    print(f"{name} {rec}")
    print()
    for name in TARGETS:
        h = hits[name]
        print(f"{name}: 命令参照 {len(h['ref'])} 件 / 書込み候補 {len(h['write'])} 件 / 生バイト一致 {len(h['raw'])} 件")
        for r in h["raw"]:
            print(f"  raw {name} {r}")
    check(f"ImageBase 0x400000 のブロック数 = {EXPECT_BLOCKS}", n_block == EXPECT_BLOCKS, f"{n_block} 件")
    check("0x15e6068 の書込み候補 = 0 件", len(hits["0x15e6068"]["write"]) == 0,
          f"{len(hits['0x15e6068']['write'])} 件")
    check("0x1376820 の命令参照 = 0 件", len(hits["0x1376820"]["ref"]) == 0,
          f"{len(hits['0x1376820']['ref'])} 件")
    check("0x1376820 の生バイト一致 = 0 件", len(hits["0x1376820"]["raw"]) == 0,
          f"{len(hits['0x1376820']['raw'])} 件")
    print(f"{sum(RESULTS)}/{len(RESULTS)} PASS")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
