#!/usr/bin/env python3
"""独立検証 (mac FLEngine): __text を capstone で線形逆アセンブルし、IPP var への rip 相対オペランド参照を数える。
   ipp_mac_scan (byte-pattern) の FLEngine 結果 (115 distinct / 410 call) と突合する。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from common import *
from macho_util import MachO
import ipp_mac_scan, capstone
from capstone import x86_const as X
path = fat_slice(MAC_APP + "/Contents/Libs/FLEngine_x64.dylib")
tab = ipp_mac_scan.analyze(path)
var2name = {int(e["var"], 16): e["name"] for e in tab}
m = MachO(path); tx = m.section("__TEXT", "__text")
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); md.detail = True
code = m.d[tx[4]:tx[4] + tx[3]]; va = tx[2]; off = 0; n = 0
hits = {}
while off < len(code):
    got = False
    for ins in md.disasm(code[off:], va + off):
        got = True; n += 1
        for op in ins.operands:
            if op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP:
                t = ins.address + ins.size + op.mem.disp
                if t in var2name: hits.setdefault(var2name[t], {}).setdefault(ins.mnemonic, 0); hits[var2name[t]][ins.mnemonic] += 1
        off = ins.address + ins.size - va
    if not got or off < len(code): off += 1   # data-in-text 等で止まったら 1B 進めて再同期
calls = {k: v.get("call", 0) for k, v in hits.items()}
scan = {e["name"]: e["call"] + e["mov"] + e["other"] for e in tab if e["call"] + e["mov"] + e["other"]}
lea_only = [k for k in hits if k not in scan]
print(f"instructions={n} distinct refs (capstone, call/mov, lea除く) = {sum(1 for v in hits.values() if v.get('call', 0) or v.get('mov', 0))}  byte-pattern distinct={len(scan)}  lea-only={len(lea_only)}")
print("call sites capstone =", sum(calls.values()), " byte-pattern call+mov+other =", sum(scan.values()))
json.dump({"instructions": n, "capstone_distinct_call_or_mov": sum(1 for v in hits.values() if v.get("call", 0) or v.get("mov", 0)), "scan_distinct": len(scan), "capstone_call_sites": sum(calls.values()), "scan_sites": sum(scan.values())}, open(f"{DATA}/ipp_mac_flengine_validate.json", "w"))
