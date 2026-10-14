#!/usr/bin/env python3
"""value 17 関数の RVA 候補語 (rva_pair) が指す先の内容を 8 B 単位で SC/KH 対比する (#2024)。

rva_pair の SC 側 RVA と KH 側 RVA の組について、指す先の 8 B 語を比べる。
- target8_eq : 指す先の先頭 8 B が一致
- target8_ne : 不一致
- 同じ関数内で RVA delta (sc_off - kh_off) が揃うかも出す (配置差なら揃う)。
usage: ks_rdata_rva_target.py <HeartCore.core_64> <SlateCore.core_64> <ks_rdata_class.json> <out.json>
"""
import sys, os, json, struct, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ks_identity import Pe
from ks_closure_share import rip_data
from ks_rdata_value import sec_of


def main(kp, sp, cls_json, out):
    kh, sc = Pe(kp), Pe(sp)
    rc = json.load(open(cls_json))
    tot = collections.Counter()
    funcs = {}
    for s, info in sorted(rc.items()):
        if info['cls'] != 'value':
            continue
        a = rip_data(sc, int(s, 16), 32)
        b = rip_data(kh, int(info['kh_va'], 16), 32)
        c = collections.Counter()
        for x, y in zip(a, b):
            xs, ys = struct.unpack('<4Q', x), struct.unpack('<4Q', y)
            for p, q in zip(xs, ys):
                if p == q:
                    continue
                sx, sy = sec_of(sc, p), sec_of(kh, q)
                sx = sx if sx and sx[0] == '.rdata' else None
                sy = sy if sy and sy[0] == '.rdata' else None
                if not (sx and sy and not sx[3] and not sy[3]):
                    continue
                c['rva_pair'] += 1
                tx = sc.rva_bytes(sx[2], 8)
                ty = kh.rva_bytes(sy[2], 8)
                if tx == ty:
                    c['target8_eq'] += 1
                else:
                    c['target8_ne'] += 1
                    # 指す先の 8 B 値の差が小さい (整数の近い値) か
                    vx, vy = struct.unpack('<Q', tx)[0], struct.unpack('<Q', ty)[0]
                    c['target8_ne_small_diff'] += int(abs(vx - vy) < 256)
        funcs[s] = dict(c)
        tot.update(c)
        print(s, dict(c))
    res = dict(sorted(tot.items()))
    print(json.dumps(res, sort_keys=True))
    json.dump(dict(summary=res, funcs=funcs), open(out, 'w'), indent=1, sort_keys=True)


if __name__ == '__main__':
    main(*sys.argv[1:5])
