#!/usr/bin/env python3
"""win PE (Delphi) から dsp_ippv2 ローダ表を静的抽出し、各 IPP 関数 var への参照数 (呼出箇所) を実測する。

  ローダ idiom (FLEngine_x64.dll 0x653fb7 付近で確認):
      mov rcx, rbp ; lea rdx,[rip+VAR] ; lea r8,[rip+NAMELIT] ; xor r9,r9 ; call LoadProc
  NAMELIT は Delphi UnicodeString リテラル (…/ffffffff / refcnt / len(4B) / UTF-16 本体)。
  その後 .text 全体を走査して VAR の rip 相対参照 (call [VAR] / mov r,[VAR] / lea 等) を分類計数する。
"""
import sys, os, struct, json
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import pefile

def analyze(path):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    d = open(path, "rb").read()
    secs = [(s.Name.rstrip(b"\0").decode(errors="replace"), s.VirtualAddress, max(s.Misc_VirtualSize, 0), s.PointerToRawData, s.SizeOfRawData) for s in pe.sections]
    def off2va(o):
        for n, va, vs, po, ps in secs:
            if po <= o < po + ps and ps: return base + va + (o - po)
    def va2off(v):
        r = v - base
        for n, va, vs, po, ps in secs:
            if va <= r < va + max(vs, ps) and ps: return po + (r - va)
        return None
    text = [s for s in secs if s[0] == ".text"][0]
    t0, tsz = text[3], text[4]
    arr = np.frombuffer(d, dtype=np.uint8, count=tsz, offset=t0)
    # lea rdx,[rip+X] ; lea r8,[rip+Y] ; xor r9,r9 (4D 33 C9 | 45 33 C9)
    n = len(arr) - 22
    m = ((arr[:n] == 0x48) & (arr[1:n+1] == 0x8D) & (arr[2:n+2] == 0x15) &
         (arr[7:n+7] == 0x4C) & (arr[8:n+8] == 0x8D) & (arr[9:n+9] == 0x05) &
         (((arr[14:n+14] == 0x4D) | (arr[14:n+14] == 0x45)) & (arr[15:n+15] == 0x33) & (arr[16:n+16] == 0xC9)))
    idx = np.where(m)[0]
    table = []  # (name, var_va, site_va)
    for i in idx:
        o = t0 + int(i)
        va = off2va(o)
        r1 = struct.unpack_from("<i", d, o + 3)[0]
        r2 = struct.unpack_from("<i", d, o + 10)[0]
        var = va + 7 + r1
        lit = va + 14 + r2
        lo = va2off(lit)
        if lo is None: continue
        ln = struct.unpack_from("<i", d, lo - 4)[0]
        cp = struct.unpack_from("<H", d, lo - 10)[0] if lo >= 10 else 0
        if not (0 < ln < 80): continue
        try:
            name = d[lo:lo + ln * 2].decode("utf-16le")
        except Exception:
            continue
        if not name.startswith("ipp"): continue
        table.append((name, var, va))
    # var -> 参照集計 (.text 全体)
    vars_ = {}
    for name, var, site in table:
        vars_.setdefault(var, []).append(name)
    refs = {v: {"call": 0, "mov": 0, "lea": 0, "other": 0, "sites": []} for v in vars_}
    if vars_:
        # 全 rel32 候補: ModRM(mod=00,rm=101) の直後 4B。命令末尾までの追加 imm 長 k=0,1,2,4 を試す
        modrm_ok = (arr[:-4] & 0xC7) == 0x05
        pos = np.where(modrm_ok)[0] + 1  # rel32 開始位置 (text 内)
        rel = np.frombuffer(d, dtype="<i4", count=0)  # placeholder
        # 取り出しを vectorize: 各 pos の 4B を little-endian int32 化
        b0 = arr[pos].astype(np.int64); b1 = arr[pos+1].astype(np.int64)
        b2 = arr[pos+2].astype(np.int64); b3 = arr[pos+3].astype(np.int64)
        relv = (b0 | (b1 << 8) | (b2 << 16) | (b3 << 24))
        relv = np.where(relv >= 2**31, relv - 2**32, relv)
        va0 = base + text[1] + pos  # rel32 の VA
        varset = np.array(sorted(refs.keys()), dtype=np.int64)
        for k in (0, 1, 2, 4):
            tgt = va0 + 4 + k + relv
            hit = np.isin(tgt, varset)
            for j in np.where(hit)[0]:
                p = int(pos[j])
                v = int(tgt[j])
                modrm = int(arr[p-1]); op = int(arr[p-2]); op3 = int(arr[p-3]) if p >= 3 else 0
                # 命令 VA
                site = int(va0[j]) - 2
                if op == 0xFF and (modrm & 0x38) in (0x10, 0x18):  # call/…
                    kind = "call" if k == 0 else "other"
                elif op == 0xFF and (modrm & 0x38) == 0x20:
                    kind = "call"  # jmp [rip+x] (tail)
                elif op in (0x8B, 0x89, 0x3B, 0x39): kind = "mov"
                elif op == 0x8D: kind = "lea"
                else: kind = "other"
                # ローダ自身の lea rdx は除外 (site が table の site+0)
                if kind == "lea" and any(abs(site - s) <= 3 for (_, vv, s) in table if vv == v):
                    continue
                refs[v][kind] += 1
                if len(refs[v]["sites"]) < 4: refs[v]["sites"].append(hex(site))
    out = []
    for name, var, site in table:
        r = refs.get(var, {})
        out.append({"name": name, "var": hex(var), "loader_site": hex(site), "call": r.get("call", 0), "mov": r.get("mov", 0), "lea": r.get("lea", 0), "other": r.get("other", 0)})
    return out

if __name__ == "__main__":
    p = sys.argv[1]
    res = analyze(p)
    print(len(res), "loader entries")
    used = [r for r in res if r["call"] + r["mov"] + r["other"] > 0]
    print("with refs:", len(used))
    for r in res[:12]: print(r)
