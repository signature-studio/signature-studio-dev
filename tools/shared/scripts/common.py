#!/usr/bin/env python3
"""tools/shared 共通: 素材パス・fat 分割・コマンド実行"""
import os, struct, subprocess, json, sys, re

ANALYSIS = "/home/ubuntu/work/analysis"
MAC_FL = f"{ANALYSIS}/mac/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL"
MAC_SHARED = f"{MAC_FL}/Shared"
MAC_APP = f"{ANALYSIS}/mac/pkg_extract/payload_out/Applications/FL Studio 2026.app"
WIN_EXTRACTED = f"{ANALYSIS}/win64/extracted"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, "work")
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(WORK, "raw")   # 大きい中間 JSON (gitignore)
os.makedirs(WORK, exist_ok=True); os.makedirs(DATA, exist_ok=True); os.makedirs(RAW, exist_ok=True)

def fat_slice(path, arch="x86_64", out=None):
    """universal2 から arch スライスを切出して out に書く (既存ならスキップ)。thin ならそのまま path を返す。"""
    with open(path, "rb") as f:
        head = f.read(8)
        magic = struct.unpack(">I", head[:4])[0]
        if magic != 0xCAFEBABE:
            return path
        n = struct.unpack(">I", head[4:8])[0]
        want = {"x86_64": 0x01000007, "arm64": 0x0100000C}[arch]
        for i in range(n):
            ct, cs, off, size, al = struct.unpack(">iiIII", f.read(20))
            if (ct & 0xffffffff) == want:
                if out is None:
                    out = os.path.join(WORK, "slices", os.path.basename(path).replace(".dylib", f".{arch}.dylib"))
                os.makedirs(os.path.dirname(out), exist_ok=True)
                if not os.path.exists(out) or os.path.getsize(out) != size:
                    f.seek(off)
                    with open(out, "wb") as o:
                        o.write(f.read(size))
                return out
    raise RuntimeError(f"arch {arch} not in {path}")

def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kw)
