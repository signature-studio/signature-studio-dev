#!/usr/bin/env python3
"""ks_rdata_class.py の value 分類 (#52 残件) の内訳を出す。

内容が違う .rdata 参照 (32 B 先頭) を 8 B 語ごとに次のどれかへ分ける:
  text  : 印字可能 ASCII (0 終端を含む) の断片を含む参照
  rva32 : 上位 32 bit が 0 で、下位 32 bit が image 内 RVA として妥当な語 (4 B 形の参照先の疑い)
  abs   : image 範囲の 8 B 絶対アドレス (ks_rdata_class.py の ptr 判定に入る)
  dbl   : それ以外 (倍精度・整数定数など)
usage: ks_rdata_detail.py <HeartCore.core_64> <SlateCore.core_64> <ks_rdata_class.json> <ks_closure_share.json>
"""
import sys, os, json, struct, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ks_identity import Pe
from ks_closure_share import rip_data


def is_text(blob):
    return any(32 <= c < 127 for c in blob) and all(c == 0 or 32 <= c < 127 for c in blob)


def words(blob, pe):
    cnt = collections.Counter()
    for v in struct.unpack('<4Q', blob):
        if v == 0:
            continue
        if pe.base <= v < pe.img_hi:
            cnt['abs'] += 1
        elif v >> 32 == 0 and v < pe.img_hi - pe.base:
            cnt['rva32'] += 1
        else:
            cnt['dbl'] += 1
    return cnt


def main(kp, sp, cls_json, share_json):
    kh, sc = Pe(kp), Pe(sp)
    rc = json.load(open(cls_json))
    tot = collections.Counter()
    per = {}
    for s, info in rc.items():
        if info['cls'] != 'value':
            continue
        a = rip_data(sc, int(s, 16), 32)
        b = rip_data(kh, int(info['kh_va'], 16), 32)
        for x, y in zip(a, b):
            if x == y:
                continue
            for tag, blob, pe in (('sc', x, sc), ('kh', y, kh)):
                if is_text(blob):
                    tot[tag + '.text_ref'] += 1
                    continue
                tot[tag + '.ref'] += 1
                for k, n in words(blob, pe).items():
                    tot[tag + '.' + k] += n
        per[s] = info['cls']
    out = dict(sorted(tot.items()))
    print(json.dumps(out, sort_keys=True))


if __name__ == '__main__':
    main(*sys.argv[1:5])
