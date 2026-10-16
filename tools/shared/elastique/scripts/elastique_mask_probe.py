#!/usr/bin/env python3
"""élastique の RetDec rc=1 fail 関数について、EVEX マスク付き vpshufd/vshufi32x4 の有無と診断用の lift 結果を出す (#5686)。

使い方: RETDEC=<retdec-decompiler> python3 elastique_mask_probe.py <dll> <retdec_lift_4284.csv> <range表> <作業dir>
出力 (stdout): 1 行 1 関数の TSV (key, マスク命令数, 元の rc, マスクの aaa ビットを 0 にした診断 DLL の rc)。
診断 DLL は <作業dir>/diag_probe.dll (作業 dir 内。commit しない)。マスク除去は意味を変えるため、修正ではなく原因の切り分けにだけ使う。
"""
import os
import subprocess
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_64

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from elastique_facts import parse_pe  # noqa: E402


def main():
    dll, csv, ranges, work = sys.argv[1:5]
    rd = os.environ["RETDEC"]
    raw = bytearray(open(dll, "rb").read())
    base, sections, image, _ = parse_pe(bytes(raw))
    rng = {}
    for line in open(ranges):
        b, e = line.split()
        rng[b] = e
    st = {}
    for line in open(csv):
        p = line.strip().split(",", 1)
        if len(p) == 2 and p[0].startswith("0x"):
            st[p[0]] = p[1].strip()
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    diag = os.path.join(work, "diag_probe.dll")
    out = os.path.join(work, "probe.ll")
    print("key\tmasked\trc_orig\trc_nomask")
    for k in sorted(k for k, v in st.items() if v == "fail rc=1"):
        b, e = int(k, 16), int(rng[k], 16)
        ins = list(md.disasm(bytes(image[b - base:e - base]), b))
        masked = [i for i in ins if i.mnemonic in ("vpshufd", "vshufi32x4") and "{" in i.op_str]
        r1 = subprocess.run([rd, dll, "--select-ranges", f"{k}-{rng[k]}", "--select-decode-only", "-o", out],
                            capture_output=True, timeout=120).returncode
        sec = next(s for s in sections if s["va"] + base <= b < s["va"] + base + s["vsize"])
        buf = bytearray(raw)
        for i in masked:
            buf[sec["rawptr"] + (i.address - base - sec["va"]) + 3] &= ~0x07
        open(diag, "wb").write(buf)
        r2 = subprocess.run([rd, diag, "--select-ranges", f"{k}-{rng[k]}", "--select-decode-only", "-o", out],
                            capture_output=True, timeout=120).returncode
        print(f"{k}\t{len(masked)}\t{r1}\t{r2}", flush=True)


if __name__ == "__main__":
    main()
