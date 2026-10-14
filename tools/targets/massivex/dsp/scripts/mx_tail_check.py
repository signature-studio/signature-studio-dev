#!/usr/bin/env python3
"""MX-18 検証: 「入口から分岐を辿った到達末尾」が .pdata の真の末尾を下回らないかを確認する。

各 .pdata 関数 (真の末尾が分かるもの) について、入口から jcc/jmp の即値先と fall-through を辿り、
到達できる命令の末尾 (最大) を求める。真の末尾より短い (SHORT) 関数があれば、その方式は
closure を過小評価する (jump table 先などを辿れないため) ので、.pdata 無し入口の区間末尾には使えない。

usage: mx_tail_check.py <pe>
"""
import sys, struct
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
        work, seen, hi = [e], set(), e
        while work:
            a = work.pop()
            if a in seen:
                continue
            seen.add(a)
            if len(seen) > MAXFN or not (t_lo <= a < t_hi):
                return None
            ins = next(md.disasm(data[off(a):off(a) + 16], base + a, count=1), None)
            if ins is None:
                return None
            hi = max(hi, a + ins.size)
            m, ops = ins.mnemonic, ins.op_str
            if m.startswith('ret') or m in ('int3', 'ud2', 'hlt'):
                continue
            if m.startswith('j'):
                if not ops.startswith('0x'):
                    return None
                tg = int(ops, 16) - base
                if t_lo <= tg < t_hi and not (THUNK_LO <= tg < THUNK_HI):
                    work.append(tg)
                if m != 'jmp':
                    work.append(a + ins.size)
                continue
            work.append(a + ins.size)
        return hi

    ok = short = unres = 0
    ex = []
    for b, s in fsz.items():
        ce = code_end(b)
        if ce is None:
            unres += 1
        elif ce < b + s:
            short += 1
            ex.append((hex(b), s, hex(ce - b)))
        else:
            ok += 1
    print('pdata funcs %d / ok(ce>=end) %d / SHORT %d / unresolved %d' % (len(fsz), ok, short, unres))
    for x in ex[:10]:
        print('  SHORT entry=%s pdata_size=%d reach=%s' % x)


if __name__ == '__main__':
    main(sys.argv[1])
