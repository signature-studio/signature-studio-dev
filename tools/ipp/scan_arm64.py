#!/usr/bin/env python3
"""arm64 Mach-O (FPC) の ipp 関数ポインタ変数テーブルと参照を命令語レベルで静的抽出。
   ローダ idiom: adrp/add x1=VAR ; mov w3,#0 ; adrp/add/add(+0x18) x2=LIT ; mov x0,x29 ; bl LoadProc
   参照分類: CALL (ldr Rt,[VAR]; blr Rt) / CHECK (ldr; cbz|cmp #0) / OTHER。ローダ関数内は除外。"""
import sys, os, json, struct
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared', 'scripts'))
from macho_util import MachO

def u16str(m, va):
    o = m.va2off(va)
    if o is None or o < 24: return None
    ln = struct.unpack_from('<q', m.d, o - 8)[0]
    if not (0 < ln < 80): return None
    try: return m.d[o:o + ln * 2].decode('utf-16le')
    except Exception: return None

def analyze(path):
    m = MachO(path)
    tx = m.section('__TEXT', '__text')
    if not tx: return None
    t0, tsz, tva = tx[4], tx[3], tx[2]
    w = np.frombuffer(m.d, dtype='<u4', count=tsz // 4, offset=t0).astype(np.int64)
    n = len(w); pc = tva + 4 * np.arange(n, dtype=np.int64)
    # ADRP
    isadrp = (w & 0x9F000000) == 0x90000000
    immlo = (w >> 29) & 3; immhi = (w >> 5) & 0x7FFFF
    imm = (immhi << 2) | immlo; imm = np.where(imm >= (1 << 20), imm - (1 << 21), imm)
    page = (pc & ~0xFFF) + (imm << 12)
    rd = w & 31
    # ADD imm 64bit (no shift or lsl12)
    isadd = (w & 0xFF000000) == 0x91000000
    addimm = ((w >> 10) & 0xFFF) << (12 * ((w >> 22) & 1))
    addrn = (w >> 5) & 31
    # LDR x (unsigned off) / LDUR x
    isldr = (w & 0xFFC00000) == 0xF9400000
    ldrimm = ((w >> 10) & 0xFFF) * 8
    isldur = (w & 0xFFE00C00) == 0xF8400000
    ldurimm = (w >> 12) & 0x1FF; ldurimm = np.where(ldurimm >= 256, ldurimm - 512, ldurimm)
    isstur = (w & 0xFFE00C00) == 0xF8000000
    isstr = (w & 0xFFC00000) == 0xF9000000
    isblr = (w & 0xFFFFFC1F) == 0xD63F0000
    iscbz = (w & 0x7E000000) == 0x34000000
    iscmp0 = (w & 0xFFFFFC1F) == 0xF100001F  # cmp xN,#0 (subs xzr,xn,#0)
    # 1) 全 (adrp[,add[,add]]) → 候補アドレス列
    cand = []  # (site_idx, addr, final_reg, next_idx)
    ia = np.where(isadrp)[0]
    for i in ia:
        r = int(rd[i]); a = int(page[i]); k = i + 1; cur = a; 
        # direct ldr x,[r,#imm]
        for step in range(1, 5):
            j = i + step
            if j >= n: break
            if isadd[j] and int(addrn[j]) == r:
                cur = cur + int(addimm[j]); r2 = int(rd[j])
                cand.append((i, cur, r2, j + 1, 'add'))
                r = r2
            elif (isldr[j] or isstr[j]) and int(addrn[j]) == r:
                cand.append((i, cur + int(ldrimm[j]), int(rd[j]), j, 'direct'))
    # ローダ表
    table = {}  # name -> var
    sites = []
    cdict = {}
    for c in cand: cdict.setdefault(c[0], []).append(c)
    for i, cs in cdict.items():
        for (_, a, r2, nx, kind) in cs:
            if kind != 'add': continue
            s = u16str(m, a)
            if s and s.startswith('ipp') and (a & 7) == 0 and False: pass
    # lit = adrp x2 ; add ; add #0x18 → string at (..+0x18) になっているものを探す
    lits = {}
    for i, cs in cdict.items():
        if int(rd[i]) != 2: continue
        for (_, a, r2, nx, kind) in cs:
            if kind == 'add':
                s = u16str(m, a)
                if s and s.startswith('ipp') and s.isprintable() and ' ' not in s: lits[i] = (s, a)
    loader_lo, loader_hi = None, None
    for i, (s, a) in lits.items():
        # 直前 6 命令内の adrp x1 + add → VAR
        var = None
        for j in range(i - 1, max(i - 8, 0), -1):
            if isadrp[j] and int(rd[j]) == 1:
                for c in cdict.get(j, []):
                    if c[4] == 'add' and c[2] == 1: var = c[1]
                break
        if var is None: continue
        table[s] = var; sites.append(i)
    if not table: return {'entries': 0, 'table': []}
    lo, hi = min(sites) - 8, max(sites) + 12
    byvar = {v: k for k, v in table.items()}
    # 二段間接: データ領域の &VAR 保持スロット
    q = np.frombuffer(m.d, dtype='<u8', count=len(m.d) // 8)
    vs = np.array(sorted(byvar), dtype=np.uint64)
    slots = {}
    for i in np.where(np.isin(q, vs))[0]:
        va = m.off2va(int(i) * 8)
        if va is not None: slots[va] = byvar[int(q[i])]
    byslot = dict(slots)
    refs = {k: {'call': 0, 'check': 0, 'other': 0, 'store': 0} for k in table}
    callsites = {k: [] for k in table}
    for i, cs in cdict.items():
        if lo <= i <= hi: continue
        for (_, a, r2, nx, kind) in cs:
            if a not in byvar and a not in byslot: continue
            indirect = a in byslot
            name = byslot[a] if indirect else byvar[a]
            if kind == 'direct':
                j = nx
                if isstr[j]: refs[name]['store'] += 1; continue
                rt = int(rd[j])
            else:
                # 次の ldr/ldur
                j = nx; found = None
                for jj in range(nx, min(nx + 4, n)):
                    if (isldur[jj] and int(addrn[jj]) == r2 and ldurimm[jj] == 0) or (isldr[jj] and int(addrn[jj]) == r2 and ldrimm[jj] == 0):
                        found = jj; break
                    if (isstur[jj] or isstr[jj]) and int(addrn[jj]) == r2: found = -jj; break
                if found is None: refs[name]['other'] += 1; continue
                if found < 0: refs[name]['store'] += 1; continue
                rt = int(rd[found]); j = found + 1
            if indirect:
                j2 = None
                for jj in range(j, min(j + 4, n)):
                    if (isldur[jj] and int(addrn[jj]) == rt and ldurimm[jj] == 0) or (isldr[jj] and int(addrn[jj]) == rt and ldrimm[jj] == 0):
                        j2 = jj; break
                if j2 is None: refs[name]['other'] += 1; continue
                rt = int(rd[j2]); j = j2 + 1
            kindc = 'other'
            for jj in range(j, min(j + 14, n)):
                if isblr[jj] and ((w[jj] >> 5) & 31) == rt: kindc = 'call'; break
                if (iscbz[jj] and int(rd[jj]) == rt) or (iscmp0[jj] and int((w[jj] >> 5) & 31) == rt): kindc = 'check'; break
                if (w[jj] & 0x7C000000) == 0x14000000 or (w[jj] & 0xFFFFFC1F) == 0xD65F0000: break  # b/bl/ret
                if int(rd[jj]) == rt and not (isadrp[jj]): 
                    # rt が上書きされた
                    if not (isldr[jj] or isldur[jj] or isadd[jj]) : pass
            refs[name][kindc] += 1
            if kindc == 'call': callsites[name].append(int(pc[i]))
    out = [{'name': k, 'var': hex(table[k]), **refs[k], 'call_sites': callsites[k][:3]} for k in table]
    return {'entries': len(table), 'slots': len(slots), 'table': out}

if __name__ == '__main__':
    path = sys.argv[1]
    r = analyze(path)
    print(r['entries'], 'entries; call>0:', sum(1 for e in r['table'] if e['call'] > 0))
