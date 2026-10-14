#!/usr/bin/env python3
"""解決不能 entry (RVA の section hit が 0 件・2 件以上) の UNWIND_INFO 読み方の候補検証 (MX-10 受入 1)。

候補: UNWIND_INFO の RVA を VirtualSize の範囲に持つ section ごとに file offset を求め、
各候補を次の整合条件で判定する (どれも候補選択の証拠としては弱い。内訳を見るための検証):
  - Version ∈ {1, 2}
  - SizeOfProlog <= 関数長
  - CountOfCodes <= 255 かつ (CHAININFO でない場合) CountOfCodes > 0
  - CHAININFO (Flags & 4) なら親 RUNTIME_FUNCTION が valid .pdata に完全一致で在る

usage: mx_unres_probe.py <pe> [out.json]
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

    def hits(u):
        return [s for s in pe.sections if s.VirtualAddress <= u < s.VirtualAddress + s.Misc_VirtualSize]

    def check(s, u, b, e):
        off = s.PointerToRawData + (u - s.VirtualAddress)
        ub = data[off: off + 4 + 2 * 256 + 12]
        ver, flags, prolog, cnt = ub[0] & 7, ub[0] >> 3, ub[1], ub[2]
        if ver not in (1, 2) or prolog > e - b or cnt > 255:
            return 'bad', None
        if flags & 4:
            o = 4 + 2 * (cnt + (cnt & 1))
            pb, pe_, _ = struct.unpack_from('<III', ub, o)
            return ('chain_exact' if (pb, pe_) in valid_exact else 'chain_parent_absent'), (pb, pe_)
        if cnt == 0:
            return 'bad', None
        return 'plain', None

    unres = [(b, e, u) for (b, e, u) in valid if len(hits(u)) != 1]
    summary = collections.Counter()
    sane_hist = collections.Counter()
    for b, e, u in unres:
        hs = hits(u)
        summary['hits_%d' % len(hs)] += 1
        verdicts = [check(s, u, b, e)[0] for s in hs]
        ok = [v for v in verdicts if v != 'bad']
        sane_hist['sane_%d' % len(ok)] += 1
        if len(ok) == 1:
            summary['unique_sane_' + ok[0]] += 1
    out = {
        'pe': path,
        'valid_in_text': len(valid),
        'unresolved': len(unres),
        'hit_hist': {k: v for k, v in sorted(summary.items()) if k.startswith('hits_')},
        'sane_candidate_hist': dict(sorted(sane_hist.items())),
        'unique_sane_verdict': {k: v for k, v in sorted(summary.items()) if k.startswith('unique_sane_')},
    }
    if outp:
        json.dump(out, open(outp, 'w'), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
