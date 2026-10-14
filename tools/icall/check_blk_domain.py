#!/usr/bin/env python3
"""BLK 域 [blk, blk+blk_reserve) の検算 (#2565)。

icall_rewrite.py の再配置範囲 (fw_map.json の func_range_new・stub・comis_stub) と BLK 域の交差を、
icall_rewrite.py とは別の算法 (開始 VA でソートして二分探索) で数える。PE を渡すと .icall 内の BLK 域を
pefile で読み、非ゼロバイト数も数える。

  python3 check_blk_domain.py fw_map.json [icall.dll]

rc 0: 交差 0 件・非重複違反 0 件 (PE 指定時は BLK 域の非ゼロ 0 バイト)。それ以外は rc 1。
"""
import bisect, json, sys


def main():
    m = json.load(open(sys.argv[1]))
    blk, rsv = m['blk'], m.get('blk_reserve', 0x280)
    iv = sorted([(int(v[0], 16), int(v[1], 16), k) for k, v in m['func_range_new'].items()]
                + [(m['stub'], m['stub'] + m.get('stub_len', 162), 'stub'),
                   (m['comis_stub'], m['comis_stub'] + m.get('comis_stub_len', 29), 'comis_stub')])
    starts = [lo for lo, _, _ in iv]
    cand = iv[:bisect.bisect_left(starts, blk + rsv)]
    cross = [k for lo, hi, k in cand if hi > blk]
    viol = sum(1 for a, b in zip(iv, iv[1:]) if b[0] < a[1])
    print('blk=%#x reserve=%#x intervals=%d cross=%d disjoint_violations=%d' % (blk, rsv, len(iv), len(cross), viol))
    if cross:
        print('cross:', ', '.join(cross[:8]))
    rc = 1 if cross or viol else 0
    if len(sys.argv) > 2:
        import pefile
        pe = pefile.PE(sys.argv[2], fast_load=True)
        s = [x for x in pe.sections if x.Name.rstrip(b'\0') == b'.icall'][0]
        off = blk - (pe.OPTIONAL_HEADER.ImageBase + s.VirtualAddress)
        dom = s.get_data()[off:off + rsv]
        nz = sum(1 for c in dom if c)
        print('.icall=%#x+%#x flags=%#x BLK domain bytes=%d nonzero=%d' % (
            pe.OPTIONAL_HEADER.ImageBase + s.VirtualAddress, s.Misc_VirtualSize, s.Characteristics, len(dom), nz))
        rc = rc or (1 if nz or len(dom) != rsv else 0)
    sys.exit(rc)


if __name__ == '__main__':
    main()
