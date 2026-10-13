#!/usr/bin/env python3
"""ks_rdata_class.py の value 分類 (#52 残件) を語単位で切り分ける。

.rdata 参照 (32 B) を 8 B 語ごとに対で比べ、差の出た語を次の 3 つに分ける:
  layout    : RVA 候補どうしで、同じセクション内のオフセットが一致する (配置差だけで説明できる)
  target_eq : RVA 候補どうしで、オフセットは違うが参照先の 16 B が一致する (配置差の候補)
  rva_off_found  : 参照先の 16 B が違い、SC の 16 B が KH の .rdata 内に (任意バイト位置で) 存在する
  rva_off_absent : 参照先の 16 B が違い、SC の 16 B が KH の .rdata 内に存在しない (指す先の内容が違う)
  dbl       : それ以外の倍精度候補 (定数値の差の候補)
  int       : それ以外の整数候補
  text      : 印字可能 ASCII を含む語 (文字列断片)
判定: 関数ごとに、差分語が layout / target_eq のみなら layout_only、それ以外を含めば value_differs。
注: rva_off_absent は、RVA 候補の指す 16 B 自体が相手側に無いことを示す。指す先の内部がさらにポインタを含む場合は未追跡。
usage: ks_rdata_value.py <HeartCore.core_64> <SlateCore.core_64> <ks_rdata_class.json> <ks_closure_share.json> <out.json>
"""
import sys, os, json, struct, collections, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ks_identity import Pe
from ks_closure_share import rip_data


def sec_of(pe, v):
    if v >> 32:
        return None
    for name, s in pe.secs.items():
        if s.VirtualAddress <= v < s.VirtualAddress + s.Misc_VirtualSize:
            return name, v - s.VirtualAddress
    return None


def is_text(v):
    bs = struct.pack('<Q', v)
    return all(c == 0 or 32 <= c < 127 for c in bs) and any(32 <= c < 127 for c in bs)


def pair_kind(x, y, sc, kh, kraw):
    if x == y:
        return 'same'
    if is_text(x) or is_text(y):
        return 'text'
    sx, sy = sec_of(sc, x), sec_of(kh, y)
    if sx and sy:
        if sx[0] == sy[0] and sx[1] == sy[1]:
            return 'layout'
        blk = sc.rva_bytes(x, 16)
        if blk == kh.rva_bytes(y, 16):
            return 'target_eq'
        return 'rva_off_found' if blk in kraw else 'rva_off_absent'
    dx, dy = struct.unpack('<d', struct.pack('<Q', x))[0], struct.unpack('<d', struct.pack('<Q', y))[0]
    if math.isfinite(dx) and math.isfinite(dy) and dx != 0 and dy != 0 and abs(dx) > 1e-300 and abs(dy) > 1e-300:
        return 'dbl'
    return 'int'


def main(kp, sp, cls_json, share_json, out):
    kh, sc = Pe(kp), Pe(sp)
    kr = kh.secs['.rdata']
    kraw = kh.data[kr.PointerToRawData:kr.PointerToRawData + kr.Misc_VirtualSize]
    rc = json.load(open(cls_json))
    res = {}
    tot = collections.Counter()
    for s, info in rc.items():
        if info['cls'] != 'value':
            continue
        a = rip_data(sc, int(s, 16), 32)
        b = rip_data(kh, int(info['kh_va'], 16), 32)
        kinds = collections.Counter()
        for x, y in zip(a, b):
            if x == y:
                continue
            xs, ys = struct.unpack('<4Q', x), struct.unpack('<4Q', y)
            for p, q in zip(xs, ys):
                k = pair_kind(p, q, sc, kh, kraw)
                if k != 'same':
                    kinds[k] += 1
        fn_verdict = 'layout_only' if kinds and set(kinds) <= {'layout', 'target_eq'} else 'value_differs'
        res[s] = dict(kh_va=info['kh_va'], verdict=fn_verdict, kinds=dict(kinds))
        tot.update(kinds)
        tot['fn_' + fn_verdict] += 1
        print(s, info['kh_va'], fn_verdict, dict(kinds))
    out_d = dict(sorted(tot.items()))
    print(json.dumps(out_d, sort_keys=True))
    json.dump(dict(summary=out_d, funcs=res), open(out, 'w'), indent=1, sort_keys=True)


if __name__ == '__main__':
    main(*sys.argv[1:6])
