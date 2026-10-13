#!/usr/bin/env python3
"""Massive X.vst3 — .pdata の chained 分割と leaf 境界近似の定量化 (MX-5 受入 2・3)。

algo:
  1. .pdata の RUNTIME_FUNCTION (begin, end, unwind) を全数読む。
  2. chained 判定 = begin == 直前 entry の end (D11 の 70,533 件の再現対象)。
  3. UNWIND_INFO (unwind RVA) を読み、UNW_FLAG_CHAININFO (Flags & 4) なら
     末尾の RUNTIME_FUNCTION を親 (primary) とする。親が pdata に在る entry を
     「chain 親が実在」と数える。
  4. leaf 近似 (旧 mx_closure.py の「次の pdata begin まで」) と pdata end の差を数える。
     差 = 0 なら近似は正しい。差 > 0 は近似が区間を過大評価 (次 begin が遠い) した件数、
     差 < 0 は pdata end が次 begin を超える (重なり) 件数。

usage: mx_pdata_quant.py <pe> <out.json>
"""
import sys, json, struct, collections
import pefile


def main(path, outp):
    pe = pefile.PE(path, fast_load=True)
    data = open(path, 'rb').read()
    base = pe.OPTIONAL_HEADER.ImageBase
    t = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0').decode() == '.pdata'][0]
    t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize
    raw = data[pd.PointerToRawData: pd.PointerToRawData + pd.Misc_VirtualSize]

    ents = []
    for i in range(0, len(raw) - 11, 12):
        b, e, u = struct.unpack_from('<III', raw, i)
        ents.append((b, e, u))
    n_all = len(ents)

    def in_text_rva(r):
        return t_lo <= r < t_hi

    # RVA → file offset の規則: VirtualSize の範囲 [VA, VA+VirtualSize) に当たる section が
    # ちょうど 1 つのときだけ解決する。0 件・2 件以上は「解決不能」として読まない
    # (この PE は .qtmimed が .xdata と VA 範囲で重なり、先頭一致では件数が揺れる)。
    def unwind_bytes(u):
        hits = [s for s in pe.sections if s.VirtualAddress <= u < s.VirtualAddress + s.Misc_VirtualSize]
        if len(hits) != 1:
            return None, len(hits)
        s = hits[0]
        off = s.PointerToRawData + (u - s.VirtualAddress)
        return data[off: off + 4 + 2 * 256 + 12], 1

    valid = [(b, e, u) for (b, e, u) in ents if e > b and b and in_text_rva(b) and e <= t_hi]
    by_begin = {b: (b, e, u) for (b, e, u) in valid}
    srt = sorted(valid)

    chained = 0
    chain_member = set()
    chained_parent_hit = 0
    chain_flag = 0
    chain_parent_in_pdata = 0
    unres = collections.Counter()
    approx_eq = approx_over = approx_under = 0
    over_sum = 0
    lens = collections.Counter()
    prev_end = None
    for idx, (b, e, u) in enumerate(srt):
        if prev_end is not None and b == prev_end:
            chained += 1
        prev_end = e
        ub, nhit = unwind_bytes(u)
        unres[nhit] += 1
        if ub:
            flags = ub[0] >> 3
            if flags & 0x4:
                chain_flag += 1
                cnt = ub[2]
                cnt_pad = cnt + (cnt & 1)
                off = 4 + 2 * cnt_pad
                pb, pe_, pu = struct.unpack_from('<III', ub, off)
                if pb in by_begin:
                    chain_parent_in_pdata += 1
                    if by_begin[pb][1] == pe_:
                        chained_parent_hit += 1
                        if pb != b:
                            chain_member.add(b)
        nxt = srt[idx + 1][0] if idx + 1 < len(srt) else t_hi
        approx = nxt - b
        if approx == e - b:
            approx_eq += 1
        elif approx > e - b:
            approx_over += 1
            over_sum += approx - (e - b)
        else:
            approx_under += 1
        lens[min((e - b) // 256 * 256, 4096)] += 1

    out = {
        'pe': path, 'base': hex(base),
        'pdata_entries_total': n_all,
        'pdata_entries_valid_in_text': len(valid),
        'chained_begin_eq_prev_end': chained,
        'unwind_resolve_section_hits_hist': {str(k): v for k, v in sorted(unres.items())},
        'unwind_chaininfo_flag': chain_flag,
        'chain_parent_in_pdata': chain_parent_in_pdata,
        'chain_parent_exact_match': chained_parent_hit,
        'chain_member_bound': len(chain_member),
        'function_roots_after_chain_bind': len(valid) - len(chain_member),
        'leaf_approx_eq_pdata': approx_eq,
        'leaf_approx_over_pdata': approx_over,
        'leaf_approx_over_bytes_sum': over_sum,
        'leaf_approx_under_pdata': approx_under,
        'len_hist_256B': {str(k): v for k, v in sorted(lens.items())},
    }
    json.dump(out, open(outp, 'w'), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
