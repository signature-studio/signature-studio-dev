#!/usr/bin/env python3
"""ks_closure_share.py の .rdata 不一致 20 関数を分類する (#52 残件)。

各関数の [rip+disp] → .rdata 参照 (出現順・先頭 16 B) を SlateCore / HeartCore で対にし、分類:
  count  : 参照数が違う
  order  : 参照内容の多重集合は一致し、出現順だけ違う (配置差)
  ptr    : 内容が違う参照のうち、少なくとも 1 つが image 内の絶対アドレス (8 B) を含む (配置差由来の疑い)
  value  : 内容が違い、どの参照も絶対アドレスを含まない (定数値の差)
usage: ks_rdata_class.py <HeartCore.core_64> <SlateCore.core_64> <ks_closure_share.json> <out.json>
"""
import sys, os, json, struct, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ks_identity import Pe, vtables
from ks_closure_share import rip_data, h


def refs(pe, va):
    return rip_data(pe, va)


def has_abs_ptr(blob, lo, hi):
    for k in range(0, len(blob) - 7, 8):
        v = struct.unpack_from('<Q', blob, k)[0]
        if lo <= v < hi:
            return True
    return False


def classify(sc, kh, sva, kva):
    a, b = refs(sc, sva), refs(kh, kva)
    if len(a) != len(b):
        return 'count', {'sc_refs': len(a), 'kh_refs': len(b)}
    if collections.Counter(a) == collections.Counter(b):
        return 'order', {}
    lo_s, hi_s = sc.base, sc.img_hi
    lo_k, hi_k = kh.base, kh.img_hi
    diff = [(x, y) for x, y in zip(a, b) if x != y]
    ptr = any(has_abs_ptr(x, lo_s, hi_s) or has_abs_ptr(y, lo_k, hi_k) for x, y in diff)
    return ('ptr' if ptr else 'value'), {'mismatch_refs': len(diff)}


def main(kp, sp, share_json, out):
    kh, sc = Pe(kp), Pe(sp)
    share = json.load(open(share_json))
    diff = share['union']['rdata_check']['differ_vas']
    kmap = share['union']['shared_map_sc_to_kh']
    res = {}
    for s in diff:
        sva = int(s, 16)
        kva = int(kmap[s][0], 16)
        cls, info = classify(sc, kh, sva, kva)
        res[s] = dict(kh_va=hex(kva), cls=cls, **info)
        print(s, hex(kva), cls, info)
    print(dict(collections.Counter(v['cls'] for v in res.values())))
    json.dump(res, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main(*sys.argv[1:5])
