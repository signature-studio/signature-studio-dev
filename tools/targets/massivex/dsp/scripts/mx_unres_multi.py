#!/usr/bin/env python3
"""mx_unres_decode.py の multi (完全整合候補 2 件以上) について、候補ごとの UNWIND_INFO バイト列が一致するかを数える (MX-12)。

usage: mx_unres_multi.py <pe> [out.json]
"""
import sys, json, struct, collections
import pefile
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from mx_unres_decode import full_decode


def main(path, outp=None):
    pe = pefile.PE(path, fast_load=True)
    data = open(path, 'rb').read()
    t = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0').decode() == '.pdata'][0]
    t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize
    raw = data[pd.PointerToRawData: pd.PointerToRawData + pd.Misc_VirtualSize]
    ents = [struct.unpack_from('<III', raw, i) for i in range(0, len(raw) - 11, 12)]
    valid = [(b, e, u) for (b, e, u) in ents if e > b and b and t_lo <= b < t_hi and e <= t_hi]
    valid_exact = set((b, e) for (b, e, u) in valid)

    def hits(u):
        return [s for s in pe.sections if s.VirtualAddress <= u < s.VirtualAddress + s.Misc_VirtualSize]

    def cand_bytes(s, u):
        off = s.PointerToRawData + (u - s.VirtualAddress)
        return data[off: off + 4 + 2 * 256 + 12]

    def ok(ub, b, e):
        ver, flags, prolog, cnt = ub[0] & 7, ub[0] >> 3, ub[1], ub[2]
        if ver not in (1, 2) or prolog > e - b or cnt > 255 or flags > 7:
            return False
        if flags & 4:
            o = 4 + 2 * (cnt + (cnt & 1))
            pb, pe_, _ = struct.unpack_from('<III', ub, o)
            return (pb, pe_) in valid_exact and full_decode(ub, cnt, prolog, ver)
        return cnt > 0 and full_decode(ub, cnt, prolog, ver)

    stat = collections.Counter()
    for b, e, u in valid:
        hs = hits(u)
        if len(hs) == 1:
            continue
        cands = [(s, cand_bytes(s, u)) for s in hs]
        okc = [(s, ub) for s, ub in cands if ok(ub, b, e)]
        if len(okc) < 2:
            continue
        distinct = len(set(ub[:4 + 2 * okc[0][1][2] + 12] for _, ub in okc))
        stat['multi'] += 1
        stat['same_bytes' if distinct == 1 else 'diff_bytes'] += 1
    print(json.dumps(dict(stat), indent=1))
    if outp:
        json.dump(dict(stat), open(outp, 'w'), indent=1)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
