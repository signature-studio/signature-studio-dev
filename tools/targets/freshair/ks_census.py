#!/usr/bin/env python3
"""SlateCore / HeartCore の全 .pdata 関数を E 正規化 (ks_identity.py と同じ) してハッシュ照合する (#52)。
usage: ks_census.py <HeartCore.core_64> <SlateCore.core_64> <out.json> [min_insn=12]
出力: 両側で正規化ハッシュが一致する関数の数 (min_insn 命令以上)・サイズ分布・上位例。
"""
import sys, json, hashlib, collections, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ks_identity import Pe


def census(pe, min_insn):
    h = collections.defaultdict(list)
    n = 0
    for rva in pe.starts:
        if not (pe.t_lo <= rva < pe.t_hi):
            continue
        va = pe.base + rva
        ins, _ = pe.disasm(va)
        if len(ins) < min_insn:
            continue
        n += 1
        e, _, _ = pe.norm(ins)
        h[hashlib.sha1('\n'.join(e).encode()).hexdigest()].append((va, len(ins), sum(i.size for i in ins)))
    return h, n


def main(kp, sp, out, min_insn=12):
    kh, sc = Pe(kp), Pe(sp)
    kh_h, kn = census(kh, min_insn)
    sc_h, sn = census(sc, min_insn)
    common = set(kh_h) & set(sc_h)
    sc_funcs = sum(len(v) for v in sc_h.values())
    sc_common = sum(len(sc_h[k]) for k in common)
    sc_common_b = sum(x[2] for k in common for x in sc_h[k])
    sc_total_b = sum(x[2] for v in sc_h.values() for x in v)
    top = sorted(((sc_h[k][0][2], hex(sc_h[k][0][0]), hex(kh_h[k][0][0]), sc_h[k][0][1]) for k in common), reverse=True)[:15]
    r = {'min_insn': min_insn, 'kh_funcs': kn, 'sc_funcs': sn, 'distinct_hash_kh': len(kh_h), 'distinct_hash_sc': len(sc_h),
         'common_hashes': len(common), 'sc_funcs_in_common': sc_common, 'sc_bytes_in_common': sc_common_b,
         'sc_bytes_total': sc_total_b, 'top_common(bytes,sc_va,kh_va,ninsn)': top}
    json.dump(r, open(out, 'w'), indent=1)
    print(json.dumps(r, indent=1))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 12)
