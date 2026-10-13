#!/usr/bin/env python3
"""MX-5 分母の実測: .pdata valid entry (mx_pdata_quant.py と同じ条件) の Σ(end−begin)。

usage: mx_pdata_denom.py <pe>
出力: entry 総数・valid 件数・Σ(end−begin) (entry 単位 / begin 一意化) と重複 begin の内訳。
"""
import sys, struct
import pefile


def main(path):
    pe = pefile.PE(path, fast_load=True)
    data = open(path, 'rb').read()
    t = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0').decode() == '.pdata'][0]
    t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize
    raw = data[pd.PointerToRawData: pd.PointerToRawData + pd.Misc_VirtualSize]
    ents = [struct.unpack_from('<III', raw, i) for i in range(0, len(raw) - 11, 12)]
    valid = [(b, e, u) for (b, e, u) in ents if e > b and b and t_lo <= b < t_hi and e <= t_hi]
    uniq = {b: (b, e, u) for (b, e, u) in valid}
    print('entries total', len(ents))
    print('valid', len(valid))
    print('sum(end-begin) valid entries', sum(e - b for b, e, u in valid))
    print('unique begin', len(uniq))
    print('sum(end-begin) unique begin', sum(e - b for b, e, u in uniq.values()))
    from collections import Counter
    c = Counter(b for b, e, u in valid)
    for k, v in c.items():
        if v > 1:
            print('dup begin', hex(k), [(hex(e), e - b, hex(u)) for b, e, u in valid if b == k])


if __name__ == '__main__':
    main(sys.argv[1])
