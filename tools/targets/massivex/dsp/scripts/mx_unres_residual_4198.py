#!/usr/bin/env python3
"""MX-15/MX-50: 親 18 件 (REPORT_MX5 §2 の「親が valid 外」) の所在分類。

母集団 (REPORT_MX5 §2 と同じ): valid entry (.text 内・e>b) のうち、UNWIND_INFO の RVA が
section 1 つに一意に解決 (hit == 1) し、Flags に CHAININFO (&4) が立つもの。
その親 RUNTIME_FUNCTION (末尾の 12 B) の (begin, end) が valid .pdata に完全一致で無いものを親 "valid 外" とし、
(begin, end) で束ねて所在を分類する:
  - pdata_in / pdata_out: 親 (begin,end) が全 .pdata 内に在るか
  - text_in / text_out  : 親 begin が .text 内か
usage: mx_unres_residual.py <pe> [out.json]
"""
import sys, json, struct, collections
import pefile


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
    all_exact = set((b, e) for (b, e, u) in ents if e > b and b)
    secs = pe.sections

    def hits(u):
        return [s for s in secs if s.VirtualAddress <= u < s.VirtualAddress + s.Misc_VirtualSize]

    def ui_bytes(s, u):
        off = s.PointerToRawData + (u - s.VirtualAddress)
        return data[off: off + 4 + 2 * 256 + 12]

    n_unique = 0
    n_chain = 0
    parents = collections.Counter()
    for b, e, u in valid:
        hs = hits(u)
        if len(hs) != 1:
            continue
        n_unique += 1
        ub = ui_bytes(hs[0], u)
        flags = ub[0] >> 3
        if not (flags & 4):
            continue
        n_chain += 1
        cnt = ub[2]
        o = 4 + 2 * (cnt + (cnt & 1))
        pb, pe_, _ = struct.unpack_from('<III', ub, o)
        if (pb, pe_) not in valid_exact:
            parents[(pb, pe_)] += 1

    cls = collections.Counter()
    rows = []
    for (pb, pe_), n in sorted(parents.items()):
        pin = (pb, pe_) in all_exact
        tin = t_lo <= pb < t_hi
        key = ('pdata_in' if pin else 'pdata_out') + '/' + ('text_in' if tin else 'text_out')
        cls[key] += n
        rows.append({'parent_begin': hex(pb), 'parent_end': hex(pe_), 'refs': n,
                     'in_all_pdata': pin, 'in_text': tin, 'class': key})
    out = {
        'pe': path,
        'unique_resolved_valid': n_unique,
        'chainino_refs': n_chain,
        'parent_outside_valid_refs': sum(parents.values()),
        'distinct_parents': len(parents),
        'class_refs': dict(sorted(cls.items())),
        'parents': rows,
    }
    if outp:
        json.dump(out, open(outp, 'w'), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != 'parents'}, indent=1))
    for r in rows:
        print(r['parent_begin'], r['parent_end'], r['refs'], r['class'])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
