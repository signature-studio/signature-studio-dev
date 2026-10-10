#!/usr/bin/env python3
"""fnscan.py — HeartCore の関数 extent を制御フロー走査で確定し、直接 call closure を列挙する。

callgraph.py の leaf サイズ推定は「最後の前方分岐先を過ぎた最初の ret/jmp」で打ち切るため、
末尾に分離ブロックを持つ関数 (例: Channel Mixer process 186B → 実 257B) を過小評価する。
ここでは .pdata があればその範囲、無ければ BB 走査 (jcc/jmp の関数内到達先すべて) で終端を決める。
usage: fnscan.py <VA> [--depth N] [--stop VA,...]    (closure を表で出す)
"""
import sys, pickle, struct, collections
import pefile, capstone
from pe_dis import pe, data, BASE, rd

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
t = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
T_LO, T_HI = BASE + t.VirtualAddress, BASE + t.VirtualAddress + t.Misc_VirtualSize
pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
_pdb = data[pd.PointerToRawData:pd.PointerToRawData + pd.Misc_VirtualSize]
PDATA = {}
for i in range(0, len(_pdb) // 12 * 12, 12):
    b, e, u = struct.unpack_from('<III', _pdb, i)
    if b:
        PDATA[BASE + b] = BASE + e


def extent(va):
    """(end_va, calls, jmps_out, insns) — pdata 優先、無ければ BB 走査"""
    if va in PDATA:
        end = PDATA[va]
        fixed = True
    else:
        end, fixed = None, False
    todo, seen, hi = [va], set(), va
    calls, tails, nins = set(), set(), 0
    while todo:
        a = todo.pop()
        while True:
            if a in seen:
                break
            if fixed and not (va <= a < end):
                break
            ins = next(md.disasm(rd(a, 16), a, 1), None)
            if ins is None:
                break
            seen.add(a)
            nins += 1
            nxt = a + ins.size
            hi = max(hi, nxt)
            mn = ins.mnemonic
            if mn == 'int3':
                break
            if mn == 'call':
                if ins.op_str.startswith('0x'):
                    calls.add(int(ins.op_str, 16))
            if mn == 'ret':
                break
            if mn == 'jmp' or mn.startswith('j'):
                if ins.op_str.startswith('0x'):
                    tg = int(ins.op_str, 16)
                    inside = (va <= tg < end) if fixed else (va <= tg < max(hi, va) + 0x2000 and tg >= va - 0 )
                    if inside and not (not fixed and tg >= T_HI):
                        todo.append(tg)
                    elif mn == 'jmp':
                        tails.add(tg)
                if mn == 'jmp':
                    break
            a = nxt
    return (end if fixed else hi), sorted(calls), sorted(tails), nins


def closure(root, stop=(), depth=6):
    out, q = collections.OrderedDict(), [(root, 0)]
    while q:
        f, d = q.pop(0)
        if f in out or f in stop or not (T_LO <= f < T_HI):
            continue
        e, c, tl, n = extent(f)
        out[f] = (e - f, c, tl, n, d)
        if d < depth:
            for x in c + tl:
                q.append((x, d + 1))
    return out


if __name__ == '__main__':
    va = int(sys.argv[1], 16)
    stop = set()
    depth = 6
    a = sys.argv[2:]
    for i, x in enumerate(a):
        if x == '--depth':
            depth = int(a[i + 1])
        if x == '--stop':
            stop = {int(s, 16) for s in a[i + 1].split(',')}
    for f, (sz, c, tl, n, d) in closure(va, stop, depth).items():
        print('%x size=%d insns=%d depth=%d pdata=%s calls=%s tails=%s' % (f, sz, n, d, f in PDATA, [hex(x) for x in c], [hex(x) for x in tl]))
