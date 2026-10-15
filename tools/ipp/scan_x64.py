#!/usr/bin/env python3
"""x86_64 Mach-O (FPC) の ipp 変数テーブルと参照を分類。
   F (tools/shared) の表 (var/name) を再利用せず自前で idiom から抽出し、参照を capstone で CALL/CHECK/OTHER 分類。
   CALL: call [VAR] / lea r,[VAR]; call [r] / mov r,[VAR]; call r / mov r,[VAR]; ... call r
   CHECK: cmp [VAR],0 / test/ cmp after mov"""
import sys, os, json, struct
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared', 'scripts'))
from macho_util import MachO
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import *
cs = Cs(CS_ARCH_X86, CS_MODE_64); cs.detail = True

class PEImg:
    def __init__(self, path):
        import pefile
        pe = pefile.PE(path, fast_load=True); self.base = pe.OPTIONAL_HEADER.ImageBase
        self.d = open(path, 'rb').read()
        self.secs = [(s.Name.rstrip(b'\0').decode(errors='replace'), s.VirtualAddress, max(s.Misc_VirtualSize, 0), s.PointerToRawData, s.SizeOfRawData) for s in pe.sections]
    def va2off(self, v):
        r = v - self.base
        for n, va, vs, po, ps in self.secs:
            if va <= r < va + max(vs, ps) and ps: return po + (r - va)
        return None
    def off2va(self, o):
        for n, va, vs, po, ps in self.secs:
            if po <= o < po + ps and ps: return self.base + va + (o - po)
    def text(self):
        s = [s for s in self.secs if s[0] == '.text'][0]
        return (None, None, self.base + s[1], s[4], s[3])

def table_pe(m, d, arr, t0, tva):
    n = len(arr) - 22
    k = ((arr[:n] == 0x48) & (arr[1:n+1] == 0x8D) & (arr[2:n+2] == 0x15) & (arr[7:n+7] == 0x4C) & (arr[8:n+8] == 0x8D) & (arr[9:n+9] == 0x05) &
         (((arr[14:n+14] == 0x4D) | (arr[14:n+14] == 0x45)) & (arr[15:n+15] == 0x33) & (arr[16:n+16] == 0xC9)))
    table = {}; lsites = []
    for i in np.where(k)[0]:
        va = tva + int(i); o = t0 + int(i)
        var = va + 7 + struct.unpack_from('<i', d, o + 3)[0]
        lit = va + 14 + struct.unpack_from('<i', d, o + 10)[0]
        lo = m.va2off(lit)
        if lo is None: continue
        ln = struct.unpack_from('<i', d, lo - 4)[0]
        if not (0 < ln < 80): continue
        try: name = d[lo:lo + ln * 2].decode('utf-16le')
        except Exception: continue
        if name.startswith('ipp'): table[name] = var; lsites.append(va)
    return table, lsites

def find_slots(m, d, varset):
    """データ領域に置かれた『var 先頭アドレスそのもの』の 8byte 値 (= &VAR を保持するポインタスロット) を探す。
       Delphi は他ユニット変数を mov r,[slot]; call [r] の二段間接で参照する。ファイルイメージ全体を 8byte 整列で走査。"""
    n8 = len(d) // 8
    q = np.frombuffer(d, dtype='<u8', count=n8)
    vs = np.array(sorted(varset), dtype=np.uint64)
    idx = np.where(np.isin(q, vs))[0]
    slots = {}
    for i in idx:
        va = m.off2va(int(i) * 8)
        if va is not None: slots[va] = int(q[i])
    return slots

def analyze(path, kind='macho'):
    if kind == 'pe':
        m = PEImg(path); d = m.d; tx = m.text()
    else:
        m = MachO(path); d = m.d
        tx = m.section('__TEXT', '__text')
    if not tx: return None
    t0, tsz, tva = tx[4], tx[3], tx[2]
    arr = np.frombuffer(d, dtype=np.uint8, count=tsz, offset=t0)
    if kind == 'pe':
        table, lsites = table_pe(m, d, arr, t0, tva)
        n = 0
    else:
        table = {}; lsites = []
    n = len(arr) - 20
    mk = ((arr[:n] == 0x48) & (arr[1:n+1] == 0x8D) & (arr[2:n+2] == 0x35) & (arr[7:n+7] == 0x30) & (arr[8:n+8] == 0xC9) &
          (arr[9:n+9] == 0x48) & (arr[10:n+10] == 0x8D) & (arr[11:n+11] == 0x15))
    for i in (np.where(mk)[0] if kind != 'pe' else []):
        o = t0 + int(i); va = tva + int(i)
        var = va + 7 + struct.unpack_from('<i', d, o + 3)[0]
        lit = va + 16 + struct.unpack_from('<i', d, o + 12)[0]
        lo = m.va2off(lit)
        if lo is None or lo < 24: continue
        ln = struct.unpack_from('<q', d, lo - 8)[0]
        if not (0 < ln < 80): continue
        try: name = d[lo:lo + ln * 2].decode('utf-16le')
        except Exception: continue
        if name.startswith('ipp'): table[name] = var; lsites.append(va)
    if not table: return {'entries': 0, 'table': []}
    byvar = {v: k for k, v in table.items()}
    slots = find_slots(m, d, set(byvar))
    for loc, v in slots.items():
        if loc not in byvar: byvar[loc] = byvar[v]
    lo_s, hi_s = min(lsites) - 16, max(lsites) + 64
    refs = {k: {'call': 0, 'check': 0, 'other': 0} for k in table}
    callfun = {k: [] for k in table}
    # rip-rel 候補
    pos = np.where((arr[:-4] & 0xC7) == 0x05)[0] + 1
    pos = pos[pos + 4 < len(arr)]
    bb = [arr[pos + k].astype(np.int64) for k in range(4)]
    rel = bb[0] | (bb[1] << 8) | (bb[2] << 16) | (bb[3] << 24)
    rel = np.where(rel >= 2**31, rel - 2**32, rel)
    va0 = tva + pos
    varset = np.array(sorted(byvar), dtype=np.int64)
    hits = []
    for k in (0, 1, 2, 4):
        tg = va0 + 4 + k + rel
        for j in np.where(np.isin(tg, varset))[0]:
            hits.append((int(va0[j]), int(tg[j]), k))
    seen = set()
    for dispva, var, k in hits:
        # 命令開始を後ろ 1..8 バイトで探す (capstone で再同期)
        name = byvar[var]
        for back in (5, 4, 3, 2):
            st = dispva - back
            if lo_s <= st <= hi_s: break
            off = m.va2off(st)
            if off is None: continue
            ins = list(cs.disasm(d[off:off + 40], st, 6))
            if not ins or ins[0].address != st: continue
            i0 = ins[0]
            if i0.size != back + 4 + k: continue
            if not any(op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP for op in i0.operands): continue
            if (st, var) in seen: break
            seen.add((st, var))
            mn = i0.mnemonic
            kind = 'other'
            if mn == 'call': kind = 'call'
            elif mn in ('cmp', 'test') and k in (0, 1, 2, 4): kind = 'check'
            elif mn in ('lea', 'mov'):
                r = i0.operands[0].reg
                if i0.operands[0].type == X86_OP_REG:
                    for ii in cs.disasm(d[off + i0.size:off + i0.size + 90], st + i0.size, 14):
                        ops = ii.operands
                        if ii.mnemonic == 'call':
                            if ops and ((ops[0].type == X86_OP_MEM and ops[0].mem.base == r and ops[0].mem.disp == 0) or (ops[0].type == X86_OP_REG and ops[0].reg == r)):
                                kind = 'call'
                            break
                        if ii.mnemonic in ('ret', 'jmp') or ii.mnemonic.startswith('j'):
                            if ii.mnemonic.startswith('j') and ii.mnemonic != 'jmp' and kind == 'other': continue
                            break
                        if ii.mnemonic in ('cmp', 'test') and ops and any((o.type == X86_OP_REG and o.reg == r) or (o.type == X86_OP_MEM and o.mem.base == r) for o in ops):
                            kind = 'check'; break
                        if ops and ops[0].type == X86_OP_REG and ops[0].reg == r and ii.mnemonic in ('mov', 'lea', 'xor', 'movzx', 'movsx', 'movsxd', 'pop'):
                            break
            refs[name][kind] += 1
            if kind == 'call': callfun[name].append(st)
            break
    out = [{'name': k, 'var': hex(table[k]), **refs[k], 'call_sites': callfun[k][:3]} for k in table]
    return {'entries': len(table), 'slots': len(slots), 'table': out}

if __name__ == '__main__':
    r = analyze(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'macho')
    t = r['table']
    print(r['entries'], 'entries; call>0:', sum(1 for e in t if e['call'] > 0), ' check>0:', sum(1 for e in t if e['check'] > 0), ' other>0:', sum(1 for e in t if e['other'] > 0))
