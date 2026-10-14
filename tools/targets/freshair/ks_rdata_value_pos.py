#!/usr/bin/env python3
"""value 17 関数の .rdata 参照を 8 B 語の位置ごとに対応させ、一致 / 不一致を集計する (#2024)。

- 対象: ks_rdata_class.json で cls == value の関数。参照 (rip 相対 32 B) を SC/KH で位置対応させる。
- 語の分類 (位置ごと、SC 語 x と KH 語 y):
  same      : x == y
  rva_pair  : 両側とも .rdata 内の RVA 候補 (上位 32 bit が 0、セクション範囲内)。
              delta = sc_off - kh_off を記録 (配置差なら関数内で delta が揃う)
  dbl_pair  : 両側とも有限な非ゼロの倍精度。ulp 差 (符号付き bit 差の絶対値) を記録
  text      : 片側または両側が印字可能 ASCII を含む
  other     : それ以外 (整数・絶対アドレス・片側だけ RVA 等)
- 出力: 関数ごとの集計 + 全体の集計 (JSON)。stdout は要約のみ。
usage: ks_rdata_value_pos.py <HeartCore.core_64> <SlateCore.core_64> <ks_rdata_class.json> <out.json>
"""
import sys, os, json, struct, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ks_identity import Pe
from ks_closure_share import rip_data
from ks_rdata_value import sec_of, is_text


def ulp_bucket(d):
    if d == 1:
        return '1'
    if d < 4:
        return '2_3'
    if d < 16:
        return '4_15'
    return '16_plus'


def main(kp, sp, cls_json, out):
    kh, sc = Pe(kp), Pe(sp)
    rc = json.load(open(cls_json))
    tot = collections.Counter()
    ulp = collections.Counter()
    deltas_all = collections.Counter()
    funcs = {}
    for s, info in sorted(rc.items()):
        if info['cls'] != 'value':
            continue
        a = rip_data(sc, int(s, 16), 32)
        b = rip_data(kh, int(info['kh_va'], 16), 32)
        per = collections.Counter()
        delta = collections.Counter()
        for x, y in zip(a, b):
            xs, ys = struct.unpack('<4Q', x), struct.unpack('<4Q', y)
            for p, q in zip(xs, ys):
                if p == q:
                    per['same'] += 1
                    continue
                sx, sy = sec_of(sc, p), sec_of(kh, q)
                sx = sx if sx and sx[0] == '.rdata' else None
                sy = sy if sy and sy[0] == '.rdata' else None
                if sx and sy and not sx[3] and not sy[3]:
                    per['rva_pair'] += 1
                    d = sx[1] - sy[1]
                    delta[d] += 1
                    continue
                if is_text(p) or is_text(q):
                    per['text'] += 1
                    continue
                dp = struct.unpack('<d', struct.pack('<Q', p))[0]
                dq = struct.unpack('<d', struct.pack('<Q', q))[0]
                ok = all(v == v and abs(v) != float('inf') and v != 0 for v in (dp, dq))
                if ok and dp * dq > 0:
                    per['dbl_pair'] += 1
                    ulp[ulp_bucket(abs(p - q))] += 1
                    continue
                per['other'] += 1
        # 同じ関数内で最頻の rva delta (配置差なら多く揃う)
        top = delta.most_common(1)
        funcs[s] = dict(kh_va=info['kh_va'], counts=dict(per),
                        rva_delta_distinct=len(delta),
                        rva_delta_top=(hex(top[0][0]) if top else None, top[0][1] if top else 0))
        tot.update(per)
        deltas_all.update(delta)
        print(s, dict(per), 'rva_delta_distinct', len(delta), 'top', funcs[s]['rva_delta_top'])
    summary = dict(sorted(tot.items()))
    summary['dbl_ulp'] = dict(sorted(ulp.items()))
    summary['rva_delta_distinct_all'] = len(deltas_all)
    summary['rva_delta_top_all'] = [(hex(d), c) for d, c in deltas_all.most_common(5)]
    print(json.dumps(summary, sort_keys=True))
    json.dump(dict(summary=summary, funcs=funcs), open(out, 'w'), indent=1, sort_keys=True)


if __name__ == '__main__':
    main(*sys.argv[1:5])
