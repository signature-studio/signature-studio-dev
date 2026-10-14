#!/usr/bin/env python3
"""MX-10 の解決不能 7,498 件 (整合候補 0/2/3 件) の読み方を、完全復号 + prolog 照合で再判定する (MX-12 受入 1・2)。

母集団: mx_unres_probe.py の MX-10 条件で「整合候補」が 0/2/3 件の entry
  (MX-10 の check() は chain の親不在 (chain_parent_absent) も非 bad として数えるため、ここでも同じ定義を使う)。
再判定 (候補ごと):
  - full_decode: UNWIND_CODE 列の完全復号が成立する (mx_unres_decode.py)
  - chain: 親 RUNTIME_FUNCTION が valid .pdata に完全一致で在る
  - plain: prolog 照合 (mx_unres_prolog.py の PUSH_NONVOL / 非 EPILOG 境界)
結果 (母集団ごと): 再判定後の候補数 0 / 1 / 2 以上 を数える。

usage: mx_unres_orig7498.py <pe> [out.json]
"""
import sys, json, struct, collections
import pefile
import capstone
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from mx_unres_decode import full_decode
from mx_unres_prolog import PUSH_REG


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
    hits = lambda u: [s for s in secs if s.VirtualAddress <= u < s.VirtualAddress + s.Misc_VirtualSize]
    fo = lambda s, r: s.PointerToRawData + (r - s.VirtualAddress)

    def mx10_sane(ub, b, e):
        ver, flags, prolog, cnt = ub[0] & 7, ub[0] >> 3, ub[1], ub[2]
        if ver not in (1, 2) or prolog > e - b or cnt > 255:
            return False
        if flags & 4:
            return True
        return cnt > 0

    def redo(ub, s, b, e):
        ver, flags, prolog, cnt = ub[0] & 7, ub[0] >> 3, ub[1], ub[2]
        if not mx10_sane(ub, b, e):
            return False
        if flags & 4:
            o = 4 + 2 * (cnt + (cnt & 1))
            pb, pe_, _ = struct.unpack_from('<III', ub, o)
            return (pb, pe_) in valid_exact and full_decode(ub, cnt, prolog, ver)
        if not full_decode(ub, cnt, prolog, ver):
            return False
        ts = [s2 for s2 in secs if s2.VirtualAddress <= b < s2.VirtualAddress + s2.Misc_VirtualSize][0]
        code = data[fo(ts, b): fo(ts, b) + prolog]
        ends = {ins.address - b + ins.size: ins for ins in md.disasm(code, b)}
        for k in range(cnt):
            cc = struct.unpack_from('<H', ub, 4 + 2 * k)[0]
            off, op, info = cc & 0xFF, (cc >> 8) & 0xF, (cc >> 12) & 0xF
            if op == 6:
                continue
            if off not in ends:
                return False
            if op == 0 and (ends[off].mnemonic != 'push' or ends[off].op_str != PUSH_REG[info]):
                return False
        return True

    stat = collections.Counter()
    for b, e, u in valid:
        hs = hits(u)
        if len(hs) == 1:
            continue
        ubs = [(s, data[fo(s, u): fo(s, u) + 524]) for s in hs]
        mx10 = [s for s, ub in ubs if mx10_sane(ub, b, e)]
        if len(mx10) not in (0, 2, 3):
            continue
        stat['pop_mx10_%d' % len(mx10)] += 1
        keep = [s for s, ub in ubs if redo(ub, s, b, e)]
        stat['redo_%d' % min(len(keep), 2)] += 1
    print(json.dumps(dict(sorted(stat.items())), indent=1))
    if outp:
        json.dump(dict(sorted(stat.items())), open(outp, 'w'), indent=1)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
