#!/usr/bin/env python3
"""独立検証: capstone で .pdata 関数を全逆アセンブルし、IPP var への rip 相対オペランド参照と
   その収容関数に対する直接 call (E8) 呼出元数を数える。ipp_win_scan の byte-pattern 結果との突合用。
   usage: ipp_win_validate.py <PE> [out.json]"""
import sys, os, json, struct
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import ipp_win_scan, pefile, capstone
from capstone import x86_const as X

def main(path, out=None):
    table = ipp_win_scan.analyze(path)
    var2name = {int(e["var"], 16): e["name"] for e in table}
    pe = pefile.PE(path)
    base = pe.OPTIONAL_HEADER.ImageBase
    d = open(path, "rb").read()
    secs = [(s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData), s.PointerToRawData, s.SizeOfRawData) for s in pe.sections]
    def va2off(v):
        r = v - base
        for va, vs, po, ps in secs:
            if va <= r < va + vs and ps: return po + (r - va)
    # .pdata
    pd = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    funcs = []
    for i in range(pd.Size // 12):
        b, e, u = struct.unpack_from("<III", d, va2off(base + pd.VirtualAddress) + i * 12)
        funcs.append((base + b, base + e))
    funcs.sort()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    hits = []         # (func_start, ins_va, mnemonic, name)
    calls_to = {}     # target -> count (E8/E9 direct to func start)
    starts = set(f[0] for f in funcs)
    n_ins = 0
    for (fs, fe) in funcs:
        o = va2off(fs)
        if o is None: continue
        for ins in md.disasm(d[o:o + (fe - fs)], fs):
            n_ins += 1
            if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
                try:
                    t = int(ins.op_str, 16)
                    if t in starts: calls_to[t] = calls_to.get(t, 0) + 1
                except ValueError: pass
            for op in ins.operands:
                if op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP:
                    t = ins.address + ins.size + op.mem.disp
                    if t in var2name:
                        hits.append((fs, ins.address, ins.mnemonic, var2name[t]))
    res = []
    for fs, ia, mn, nm in hits:
        res.append({"name": nm, "func": hex(fs), "ins": hex(ia), "mn": mn, "callers_of_func": calls_to.get(fs, 0)})
    summary = {"pe": os.path.basename(path), "funcs": len(funcs), "instructions": n_ins, "refs": res}
    if out: json.dump(summary, open(out, "w"), indent=1)
    return summary

if __name__ == "__main__":
    s = main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(s["pe"], "funcs", s["funcs"], "ins", s["instructions"])
    for r in s["refs"]: print(r)
