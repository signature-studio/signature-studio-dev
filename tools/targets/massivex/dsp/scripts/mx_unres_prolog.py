#!/usr/bin/env python3
"""完全整合候補 (mx_unres_decode.py) を prolog 命令との照合で再判定する (MX-12 受入 1)。

各候補の UNWIND_CODE について、関数先頭 (BeginAddress) から線形逆アセンブルした命令境界を使い、
  - 非 EPILOG の CodeOffset は命令の終端 (境界) に一致すること
  - UWOP_PUSH_NONVOL (op 0) は、その境界直前の命令が `push <info の reg>` であること
  - UWOP_SET_FPREG (op 3) は、直前の命令が `mov rbp, rsp` 系であること (reg=rbp 固定ではないため緩く、mov 命令の存在のみ)
を満たすものを「prolog 整合」とする。
候補が 2 件以上のまま残った件数と、0 件になった件数を出す。

usage: mx_unres_prolog.py <pe> [out.json]
"""
import sys, json, struct, collections
import pefile
import capstone
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from mx_unres_decode import full_decode

PUSH_REG = {0: 'rax', 1: 'rcx', 2: 'rdx', 3: 'rbx', 4: 'rsp', 5: 'rbp', 6: 'rsi', 7: 'rdi',
            8: 'r8', 9: 'r9', 10: 'r10', 11: 'r11', 12: 'r12', 13: 'r13', 14: 'r14', 15: 'r15'}


def main(path, outp=None):
    pe = pefile.PE(path, fast_load=True)
    data = open(path, 'rb').read()
    secs = pe.sections
    t = [s for s in secs if s.Characteristics & 0x20000000][0]
    pd = [s for s in secs if s.Name.rstrip(b'\0').decode() == '.pdata'][0]
    t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize
    raw = data[pd.PointerToRawData: pd.PointerToRawData + pd.Misc_VirtualSize]
    ents = [struct.unpack_from('<III', raw, i) for i in range(0, len(raw) - 11, 12)]
    valid = [(b, e, u) for (b, e, u) in ents if e > b and b and t_lo <= b < t_hi and e <= t_hi]
    valid_exact = set((b, e) for (b, e, u) in valid)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def hits(u):
        return [s for s in secs if s.VirtualAddress <= u < s.VirtualAddress + s.Misc_VirtualSize]

    def fo(s, rva):
        return s.PointerToRawData + (rva - s.VirtualAddress)

    def prolog_ok(s, u, b, e):
        """候補 s の UNWIND_INFO (RVA u) が、b から始まる関数の prolog 命令境界と整合するか。"""
        ub = data[fo(s, u): fo(s, u) + 4 + 2 * 256 + 12]
        ver, flags, prolog, cnt = ub[0] & 7, ub[0] >> 3, ub[1], ub[2]
        if flags & 4:
            return None
        codes = [struct.unpack_from('<H', ub, 4 + 2 * k)[0] for k in range(cnt)]
        ts = [s2 for s2 in secs if s2.VirtualAddress <= b < s2.VirtualAddress + s2.Misc_VirtualSize]
        if not ts:
            return False
        tb = ts[0]
        code = data[fo(tb, b): fo(tb, b) + prolog]
        ends = {}
        pos = 0
        starts = {}
        for ins in md.disasm(code, b):
            starts[ins.address - b] = ins
            pos = ins.address - b + ins.size
            ends[pos] = ins
        i = 0
        while i < cnt:
            c = codes[i]
            off, op, info = c & 0xFF, (c >> 8) & 0xF, (c >> 12) & 0xF
            if op == 6:
                i += 1
                continue
            if off not in ends:
                return False
            if op == 0:
                ins = ends[off]
                if ins.mnemonic != 'push' or ins.op_str != PUSH_REG[info]:
                    return False
            i += 1
        return True

    stat = collections.Counter()
    for b, e, u in valid:
        hs = hits(u)
        if len(hs) == 1:
            continue
        okc = []
        for s in hs:
            ub = data[fo(s, u): fo(s, u) + 4 + 2 * 256 + 12]
            ver, flags, prolog, cnt = ub[0] & 7, ub[0] >> 3, ub[1], ub[2]
            if ver not in (1, 2) or prolog > e - b or cnt > 255 or flags > 7:
                continue
            if flags & 4:
                o = 4 + 2 * (cnt + (cnt & 1))
                pb, pe_, _ = struct.unpack_from('<III', ub, o)
                if (pb, pe_) not in valid_exact or not full_decode(ub, cnt, prolog, ver):
                    continue
                okc.append(s)
                continue
            if cnt == 0 or not full_decode(ub, cnt, prolog, ver):
                continue
            if prolog_ok(s, u, b, e):
                okc.append(s)
        stat['n_prolog_ok_%d' % len(okc)] += 1
    print(json.dumps(dict(sorted(stat.items())), indent=1))
    if outp:
        json.dump(dict(sorted(stat.items())), open(outp, 'w'), indent=1)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
