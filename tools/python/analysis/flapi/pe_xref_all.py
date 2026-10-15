#!/usr/bin/env python3
"""展開先の全 *_PE.bin の .text を走査し、RIP 相対で指定 VA を参照する命令を PE ごとに列挙する (PY-312 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_xref_all.py <VA(16進)>[,<VA(16進)>...] [並列数]

pe_xref.py と同じ走査 (線形・無効バイトで 1 バイト進めて再同期)。各 PE の ImageBase を出力し、
参照先は ImageBase によらず絶対 VA として比較する (ImageBase が 0x400000 の PE だけが block00031 と同じ像)。
出力は 1 行 1 PE の要約と、ヒットした命令の一覧。
"""
import glob
import multiprocessing
import os
import sys
import time

import capstone
import pefile

CHUNK = 1 << 16


def scan(args):
    path, targets = args
    t0 = time.time()
    raw = open(path, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    n_ins = 0
    hits = []
    for s in pe.sections:
        if not s.Characteristics & 0x20000000:
            continue
        start = base + s.VirtualAddress
        data = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        off = 0
        while off < len(data):
            end = off
            for ins in md.disasm(data[off:off + CHUNK + 16], start + off):
                if ins.address - start - off + ins.size > CHUNK:
                    break
                n_ins += 1
                end = ins.address - start + ins.size
                for i, op in enumerate(ins.operands):
                    if op.type != capstone.x86.X86_OP_MEM or op.mem.base != capstone.x86.X86_REG_RIP:
                        continue
                    tgt = ins.address + ins.size + op.mem.disp
                    if tgt in targets:
                        kind = "store" if i == 0 and ins.mnemonic == "mov" else "load"
                        hits.append((ins.address, kind, ins.mnemonic, ins.op_str, tgt))
            off = end if end > off else off + 1
    return os.path.basename(path), base, n_ins, hits, time.time() - t0


def main():
    targets = {int(x, 16) for x in sys.argv[1].split(",")}
    procs = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    d = os.path.join(os.environ["FL_WIN64_DIR"], "extracted")
    files = sorted(glob.glob(os.path.join(d, "*_PE.bin")))
    with multiprocessing.Pool(procs) as pool:
        for name, base, n_ins, hits, sec in pool.imap(scan, [(f, targets) for f in files]):
            hit_names = ",".join(f"0x{t:x}" for t in sorted({h[4] for h in hits}))
            print(f"{name} base=0x{base:x} ins={n_ins} hits={len(hits)} targets=[{hit_names}] sec={sec:.1f}", flush=True)
            for addr, kind, mn, ops, tgt in hits:
                print(f"  {name} 0x{addr:x} {kind:5s} {mn} {ops} -> 0x{tgt:x}", flush=True)


if __name__ == "__main__":
    main()
