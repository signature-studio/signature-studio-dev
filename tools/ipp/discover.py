#!/usr/bin/env python3
"""dsp_ippv2 ローダ表 (UTF-16 'ippMalloc' リテラル) を持つモジュールを mac .app / win 抽出ツリーから自前探索し、
   mac は x86_64/arm64 両スライスを work/mac/ に抽出。 tools/shared に依存しない (独立再現用)。"""
import os, sys, json, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'shared')); from paths import FL_MAC_DIR, FL_WIN64_DIR
APP = f"{FL_MAC_DIR}/pkg_extract/payload_out/Applications/FL Studio 2026.app"
WIN = f"{FL_WIN64_DIR}/extracted"
PAT = "ippMalloc".encode("utf-16le")

def slices(path):
    with open(path, "rb") as f:
        h = f.read(8)
        if len(h) < 8: return {}
        magic = struct.unpack(">I", h[:4])[0]
        if magic == 0xCAFEBABE:
            n = struct.unpack(">I", h[4:8])[0]; out = {}
            for _ in range(n):
                ct, cs, off, size, al = struct.unpack(">iiIII", f.read(20))
                out[{0x01000007: "x86_64", 0x0100000C: "arm64"}.get(ct & 0xffffffff, hex(ct))] = (off, size)
            return out
        if struct.unpack("<I", h[:4])[0] == 0xFEEDFACF:
            cpu = struct.unpack("<I", h[4:8])[0]; return {{0x01000007: "x86_64", 0x0100000C: "arm64"}.get(cpu, hex(cpu)): (0, os.path.getsize(path))}
    return {}

def mac():
    out = os.path.join(HERE, "work", "mac"); os.makedirs(out, exist_ok=True)
    idx = {}; i = 0
    for root, _, files in os.walk(APP):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            if os.path.islink(p) or os.path.getsize(p) < 4096: continue
            try: sl = slices(p)
            except Exception: continue
            if "x86_64" not in sl: continue
            with open(p, "rb") as f:
                off, size = sl["x86_64"]; f.seek(off); b = f.read(size)
            if PAT not in b or p.endswith("dsp_ippv2_x64.dylib"): continue
            rec = {"path": os.path.relpath(p, APP)}
            for arch, (o, s) in sl.items():
                dst = os.path.join(out, f"{i:03d}.{arch}")
                with open(p, "rb") as f: f.seek(o); open(dst, "wb").write(f.read(s))
                rec[arch] = dst
            idx[i] = rec; i += 1
    json.dump(idx, open(os.path.join(out, "index.json"), "w"), indent=0)
    print("mac modules with ipp loader table:", len(idx), " with arm64 slice:", sum(1 for v in idx.values() if "arm64" in v))

def win():
    out = []
    for fn in sorted(os.listdir(WIN)):
        if not fn.endswith("_PE.bin"): continue
        b = open(os.path.join(WIN, fn), "rb").read()
        if PAT in b and not (b"ippsFFTFwd" in b):   # dsp_ippv2 本体 (export 名が ASCII で入る) を除外
            out.append(fn)
    os.makedirs(os.path.join(HERE, "work"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "work", "win_modules.json"), "w"))
    print("win modules with ipp loader table:", len(out))

if __name__ == "__main__":
    mac(); win()
