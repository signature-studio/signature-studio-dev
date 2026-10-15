#!/usr/bin/env python3
"""PY-188 (#3338): 0x8ed012 の Self (G1 = 0x8ecbc0 の rcx) の出所を直接呼出し元から 3 段まで辿り、VMT を確かめる (実機不要)。

  python3 analysis/py188_self.py <PE.bin>

.text を 1 回線形走査して直接 call の一覧を作る (py67_callers.py と同じ走査)。G1 の呼出し元ごとに:
- 呼出しの直前で rcx を設定した命令を読む: `mov rcx, [rip+d]` は大域 G (次命令 + d)、
  `mov rcx, rax` は直前の `mov rax, [rip+d]`、`mov rcx, [rbp+K]` は入口で rcx を K に保存した slot。
  slot なら呼出し元 (その関数への direct call) へ上がる (最大 3 段)。
- dl の設定を読む: `mov dl, N`・`xor edx, edx`・`mov al, N; mov edx, eax`・`mov r8b, N; mov edx, r8d`。
- 大域 G の値 V = qword(G)。V-0xc8 が V を指せば VMT 自己ポインタ (py71_vmt.py と同じ判定)。
  クラス名・親鎖 (親 VMT = 格納値 + 0xc8) を出し、親鎖に TChannel があれば chan。
ネガティブコントロールとして非 VMT の 0xebef68 を同じ判定に通す。
"""
import re
import sys
from collections import defaultdict

import capstone
import pefile

G1 = 0x8ecbc0
CONTROLS = [0xebef68]
path = sys.argv[1]
pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
ib = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
toff, tsize = text.PointerToRawData, text.SizeOfRawData
tbase = ib + text.VirtualAddress
tdata = data[toff:toff + tsize]
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
X = capstone.x86

pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
FUNCS = [(ib + f.struct.BeginAddress, ib + f.struct.EndAddress) for f in pe.DIRECTORY_ENTRY_EXCEPTION]
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
SLOT = re.compile(r"\[rbp \+ (0x[0-9a-f]+)\]")
STORE_RCX = re.compile(r"qword ptr \[rbp \+ (0x[0-9a-f]+)\], rcx$")


def va_to_off(va):
    for s in pe.sections:
        lo = ib + s.VirtualAddress
        if lo <= va < lo + s.Misc_VirtualSize:
            if va - lo >= s.SizeOfRawData:
                return None
            return va - lo + s.PointerToRawData
    return None


def qword(va):
    off = va_to_off(va)
    if off is None or off + 8 > len(data):
        return None
    return int.from_bytes(data[off:off + 8], "little")


def shortstr(va):
    off = va_to_off(va)
    if off is None:
        return None
    n = data[off]
    return data[off + 1:off + 1 + n].decode("latin-1")


def func_of(va):
    best = None
    for b, e in FUNCS:
        if b <= va < e and (best is None or e - b < best[1] - best[0]):
            best = (b, e)
    return best


_cache = {}


def insns(fb, fe):
    if fb not in _cache:
        off = va_to_off(fb)
        _cache[fb] = list(md.disasm(data[off:off + (fe - fb)], fb))
    return _cache[fb]


def rip_target(ins):
    m = RIP.search(ins.op_str)
    if not m:
        return None
    d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
    return ins.address + ins.size + d


def scan_calls():
    calls = defaultdict(list)
    off = 0
    while off < len(tdata):
        ins = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
        if ins is None:
            off += 1
            continue
        off += ins.size
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == X.X86_OP_IMM:
            calls[ins.operands[0].imm].append(ins.address)
    return calls


def rcx_src(prev):
    for k in range(len(prev) - 1, -1, -1):
        i = prev[k]
        if i.mnemonic == "mov" and i.op_str.startswith("rcx, "):
            s = i.op_str[5:]
            if "[rip" in s:
                return ("global", rip_target(i))
            m = SLOT.search(s)
            if m:
                return ("slot", int(m.group(1), 16))
            if s == "rax":
                for j in reversed(prev[:k]):
                    if j.mnemonic == "mov" and j.op_str.startswith("rax, "):
                        if "[rip" in j.op_str:
                            return ("global", rip_target(j))
                        return ("other", "rax <- " + j.op_str)
                return ("other", "rax")
            return ("other", s)
    return ("none", None)


def dl_src(prev):
    for k in range(len(prev) - 1, -1, -1):
        i = prev[k]
        s = i.op_str
        if i.mnemonic == "xor" and s == "edx, edx":
            return ("imm", 0)
        if i.mnemonic == "mov" and s.startswith(("dl, ", "edx, ")):
            if s == "edx, eax" or s == "edx, r8d":
                names = ("al, ",) if s == "edx, eax" else ("r8b, ", "r8d, ")
                for j in reversed(prev[:k]):
                    if j.mnemonic == "mov" and j.op_str.startswith(names):
                        return ("imm", int(j.op_str.split(", ")[1], 0))
                return ("other", s)
            return ("imm", int(s.split(", ")[1], 0))
        if i.mnemonic == "movzx" and s.startswith("rdx, byte ptr [rbp"):
            m = SLOT.search(s)
            return ("slot", int(m.group(1), 16))
    return ("none", None)


def entry_stored(fb, fe, site, K):
    for i in insns(fb, fe):
        if i.address >= site:
            break
        m = STORE_RCX.search(i.op_str) if i.mnemonic == "mov" else None
        if m and int(m.group(1), 16) == K:
            return True
    return False


def vmt_check(V):
    rec = {"V": V, "self_ok": False, "name": None, "instsize": None, "chain": []}
    if V is None or qword(V - 0xc8) != V:
        return rec
    rec["self_ok"] = True
    cn = qword(V - 0x88)
    rec["name"] = shortstr(cn) if cn is not None else None
    rec["instsize"] = qword(V - 0x80)
    p = qword(V - 0x78)
    for _ in range(30):
        if not p:
            break
        pv = p + 0xc8
        nm = qword(pv - 0x88)
        nm = shortstr(nm) if nm is not None else None
        rec["chain"].append(nm)
        if nm is None:
            break
        p = qword(pv - 0x78)
    rec["chan"] = "TChannel" in rec["chain"] or rec["name"] == "TChannel"
    return rec


def fmt_vmt(rec):
    if not rec["self_ok"]:
        return f"VMT NG (V={rec['V']:#x} の自己ポインタ不一致)" if rec["V"] is not None else "VMT NG (値なし)"
    chain = " -> ".join(c or "?" for c in rec["chain"])
    kind = "TChannel 系 (対象)" if rec["chan"] else "非 chan (除外)"
    return f"VMT OK {rec['V']:#x} name={rec['name']} instsize={rec['instsize']:#x} 親鎖={chain} => {kind}"


def trace(site, depth, calls, hops):
    fb, fe = func_of(site)
    L = insns(fb, fe)
    idx = next(k for k, i in enumerate(L) if i.address == site)
    prev = L[:idx]
    kind, val = rcx_src(prev)
    dk, dv = dl_src(prev)
    hop = {"site": site, "func": fb, "rcx": (kind, val), "dl": (dk, dv), "depth": depth}
    hops.append(hop)
    if kind == "slot" and entry_stored(fb, fe, site, val) and depth < 3:
        ups = calls.get(fb, [])
        hop["up"] = ups
        if not ups:
            hop["end"] = "直接呼出し元なし (間接参照のみ・未確定)"
        for up in ups:
            trace(up, depth + 1, calls, hops)
        return
    if kind == "global":
        hop["vmt"] = vmt_check(qword(val))
        hop["global_value"] = qword(val)


def main():
    calls = scan_calls()
    g1 = calls.get(G1, [])
    print(f"# direct calls to G1 {G1:#x}: {len(g1)}")
    print("== 受入 1・2: G1 の呼出し元 5 件 (rcx の出所を 3 段まで・dl と VMT)")
    for site in g1:
        hops = []
        trace(site, 0, calls, hops)
        fb, fe = func_of(site)
        print(f"-- 呼出し {site:#x} (関数 {fb:#x}..{fe:#x})")
        for h in hops:
            print(f"   [{h['depth']}] call {h['site']:#x} in {h['func']:#x}: rcx={h['rcx'][0]} {h['rcx'][1] if h['rcx'][0] != 'slot' else hex(h['rcx'][1])}  dl={h['dl'][0]} {h['dl'][1]}")
            if "global_value" in h:
                print(f"       大域 {h['rcx'][1]:#x} の値 {h['global_value']:#x}: {fmt_vmt(h['vmt'])}")
            if "end" in h:
                print(f"       {h['end']}")
    print("== ネガティブコントロール (非 VMT)")
    for c in CONTROLS:
        print(f"   {c:#x}: {fmt_vmt(vmt_check(c))}")


main()
