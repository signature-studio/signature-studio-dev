#!/usr/bin/env python3
"""MX-26 (#1946) 診断: mx_tail_check.py の SHORT を原因別に分ける。

各 .pdata 関数について、入口から分岐を辿った到達末尾 (code_end) が真の末尾を下回るもの (SHORT) を、
次の 3 つに分類する。
  indirect : 到達経路に間接 jmp (jump table 等) があり、辿れない
  pad      : 到達末尾の後ろが int3/nop/0 だけ (アライメント埋め。実害なし)
  real     : 到達末尾の後ろに実コードがあり、直接分岐でも届かない (真の末尾の判定に code/data 区別が要る)
real のうち、末尾位置が直接 rel32 分岐の目標になっている件数も数える。

usage: mx_tail_diag.py <pe>
"""
import sys, struct, collections, re
import capstone, pefile

THUNK_LO, THUNK_HI = 0x396e000, 0x3970200
MAXFN = 0x8000


def main(path):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, 'rb').read()
    t = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize
    t_raw = t.PointerToRawData
    pds = sorted([s for s in pe.sections if s.Name.rstrip(b'\0').decode() == '.pdata'],
                 key=lambda s: -s.Misc_VirtualSize)
    raw = data[pds[0].PointerToRawData: pds[0].PointerToRawData + pds[0].Misc_VirtualSize]
    fsz = {}
    for i in range(0, len(raw) - 11, 12):
        st, e, _u = struct.unpack_from('<III', raw, i)
        if e > st and st and 0x1000 <= st < t_hi and e <= t_hi:
            fsz[st] = e - st
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def off(r):
        return t_raw + (r - t_lo)

    def code_end(e):
        work, seen, hi, ind = [e], set(), e, 0
        while work:
            a = work.pop()
            if a in seen:
                continue
            seen.add(a)
            if len(seen) > MAXFN or not (t_lo <= a < t_hi):
                return None, ind
            ins = next(md.disasm(data[off(a):off(a) + 16], base + a, count=1), None)
            if ins is None:
                return None, ind
            hi = max(hi, a + ins.size)
            m, ops = ins.mnemonic, ins.op_str
            if m.startswith('ret') or m in ('int3', 'ud2', 'hlt'):
                continue
            if m.startswith('j'):
                if not ops.startswith('0x'):
                    ind += 1
                    continue
                tg = int(ops, 16) - base
                if t_lo <= tg < t_hi and not (THUNK_LO <= tg < THUNK_HI):
                    work.append(tg)
                if m != 'jmp':
                    work.append(a + ins.size)
                continue
            work.append(a + ins.size)
        return hi, ind

    branch_tg = collections.Counter()
    txt = data[t_raw: t_raw + t.Misc_VirtualSize]
    for m in re.finditer(rb'(?=[\xe8\xe9]....|\x0f[\x80-\x8f]....)', txt):
        i = m.start()
        k = 1 if txt[i] in (0xe8, 0xe9) else 2
        tg = t_lo + i + k + 4 + struct.unpack_from('<i', txt, i + k)[0]
        if t_lo <= tg < t_hi:
            branch_tg[tg] += 1

    cls = collections.Counter()
    real_hit = 0
    for b, s in fsz.items():
        ce, ind = code_end(b)
        if ce is not None and ce >= b + s:
            cls['ok'] += 1
            continue
        if ce is None:
            cls['unresolved'] += 1
            continue
        if ind:
            cls['indirect'] += 1
            continue
        gap = data[off(ce): off(b + s)]
        if all(c in (0xcc, 0x90, 0x00) for c in gap):
            cls['pad'] += 1
        else:
            cls['real'] += 1
            if ce in branch_tg:
                real_hit += 1
    print('pdata funcs %d' % len(fsz))
    for k in ('ok', 'indirect', 'pad', 'real', 'unresolved'):
        print('  %-10s %d' % (k, cls[k]))
    print('  real かつ末尾位置が直接分岐の目標: %d' % real_hit)


if __name__ == '__main__':
    main(sys.argv[1])
