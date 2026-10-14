#!/usr/bin/env python3
"""ildsp_native.c (CreateInstance の native 実行) の結果を照合する (#2528 / T-SH-38)。

usage: ildsp_native_check.py [PE] [--neg]
  既定 PE: $FL_WIN64_DIR/extracted/block24360_PE.bin (tools/shared/paths.py)
  バイナリ: tools/shared/work/native/ildsp_native (未ビルドなら gcc でビルドする)
  照合: CreateInstance を native 実行し、返った wrapper の vptr が vtable VA (0x1803dfcf8) と一致するか。
  --neg: ハーネスに --neg-lea を渡し、vptr 格納 lea を壊す (ネガティブコントロール)。FAIL (rc 1) になれば正しい。
  slot の実行 (役割・間接 call 到達) は ildsp_native 本体の出力に残す。本 checker は create 1 件だけを照合する。
"""
import sys, os, subprocess, argparse, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from paths import FL_WIN64_DIR

SRC = os.path.join(HERE, "ildsp_native.c")
BIN = os.path.join(HERE, "..", "work", "native", "ildsp_native")
VT_VA = 0x1803DFCF8


def build():
    os.makedirs(os.path.dirname(BIN), exist_ok=True)
    if not os.path.exists(BIN) or os.path.getmtime(BIN) < os.path.getmtime(SRC):
        subprocess.run(["gcc", "-O1", "-g", "-Wall", "-Wno-unused-function", "-o", BIN, SRC], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pe", nargs="?", default=os.path.join(FL_WIN64_DIR, "extracted", "block24360_PE.bin"))
    ap.add_argument("--neg", action="store_true")
    a = ap.parse_args()
    build()
    cmd = [BIN, a.pe, "--slot", "0", "0"] + (["--neg-lea"] if a.neg else [])
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    out = p.stdout
    print(out.strip())
    m = re.search(r"create wrapper=(0x[0-9a-f]+) vptr=(0x[0-9a-f]+)", out)
    fails = []
    if p.returncode != 0:
        fails.append(f"ildsp_native rc={p.returncode}")
    if not m:
        fails.append("create 行が出力に無い")
    else:
        vptr = int(m.group(2), 16)
        if vptr != VT_VA:
            fails.append(f"vptr 0x{vptr:x} != 0x{VT_VA:x}")
    if fails:
        for f in fails:
            print("FAIL", f)
        print(f"ildsp_native_check: FAIL {len(fails)} 件 (neg={a.neg})")
        sys.exit(1)
    print(f"ildsp_native_check: ALL OK (neg={a.neg})")


if __name__ == "__main__":
    main()
