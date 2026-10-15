#!/usr/bin/env python3
# M6 #1f: vtable 主導の win↔mac 関数対応作成
#   - 各クラス: mac __ZTV (nm log) → slots / win: typeinfo(.?AV<..>@@) → COL (pTD==ti RVA) → vftable[-1] 参照 → slots
#   - mapping: mac slot0(D1),slot1(D0) → win slot0; mac slot i≥2 → win slot i-1
#   - fscore (data 定数) で確認 (参照根拠は REPORT に記載)
# 出力: work/ott_map.json
import sys, os, re, struct, json, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ottlib import Bin, Dis

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from paths import PLUGINS_DIR
MACF = f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_mac_x86_64'
WINF = f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_win64.dll'
NMLOG = f'{PLUGINS_DIR}/ott/report_logs/nm_ott_vst2_mac_x64.txt'
OUT = os.path.join(BASE, 'work', 'ott_map.json')

CLASSES = [
    ('FIL_Linkwitz_Riley4',   '19FIL_Linkwitz_Riley4',      'FIL_Linkwitz_Riley4@@'),
    ('OTTProcessor',          '12OTTProcessor',             'OTTProcessor@@'),
    ('AudioEffectX',          '12AudioEffectX',             'AudioEffectX@@'),
    ('AudioEffect',           '11AudioEffect',              'AudioEffect@@'),
    ('MyVUMeter',             '9MyVUMeter',                 'MyVUMeter@@'),
    ('OTTVST',                '6OTTVST',                    'OTTVST@@'),
    ('EnvelopeDetector',      'N16chunkware_simple16EnvelopeDetectorE', 'EnvelopeDetector@chunkware_simple@@'),
    ('AttRelEnvelope',        'N16chunkware_simple14AttRelEnvelopeE',   'AttRelEnvelope@chunkware_simple@@'),
    ('SimpleComp',            'N16chunkware_simple10SimpleCompE',       'SimpleComp@chunkware_simple@@'),
    ('SimpleCompRms',         'N16chunkware_simple13SimpleCompRmsE',    'SimpleCompRms@chunkware_simple@@'),
]


def nm_list():
    arr = []
    for l in open(NMLOG):
        p = l.split()
        if len(p) >= 3:
            arr.append((int(p[0], 16), p[1], p[2]))
    # T/t のみを保持し address 順
    out = [t for t in arr if t[1] in 'Tt']
    out.sort()
    return out


def fscore(fa, fb):
    da, db = fa['data'], fb['data']
    if not da or not db:
        return 0.5
    common = [k for k in da.keys() if k in db and not k.startswith('4:0000')]
    if not common:
        return 0.2
    c0 = sum(min(da[k], db[k]) for k in common)
    denom = min(sum(da.values()), sum(db.values()))
    return c0 / denom


def main():
    mac = Bin(MACF)
    win = Bin(WINF)
    dmac, dwin = Dis(mac), Dis(win)
    syms = nm_list()
    va2i = {v: i for i, (v, t, n) in enumerate(syms)}
    text_lo_m = mac.sections[0][1]
    text_hi_m = text_lo_m + len(mac.sections[0][2])
    WT_LO, WT_HI, WBASE = 0x1000, 0x1000 + 1966312, 0x180000000

    tv_by_name = {}
    for l in open(NMLOG):
        p = l.split()
        if len(p) == 3 and p[1] in 'Ss' and p[2].startswith('__ZTV') and len(p[2]) > 5:
            tv_by_name[p[2][5:]] = int(p[0], 16)

    def macslots(tv):
        out = []
        for k in range(140):
            v = int.from_bytes(mac.read_at(tv + 0x10 + k * 8, 8), 'little')
            if not (text_lo_m <= v < text_hi_m and v in mac.func_names):
                break
            out.append(v)
        return out

    mapping = {}
    for (cl, mm, suffix) in CLASSES:
        tv_m = tv_by_name.get(mm)
        if not tv_m:
            print('[-]', cl, 'mac __ZTV 未検出')
            continue
        slots_m = macslots(tv_m)
        print('[m] %s: mac vtable@%x slots=%d' % (cl, tv_m, len(slots_m)))
        # win typeinfo
        ti_va = None
        pat = (('.?AV' + suffix) if not suffix.startswith('?') else suffix).encode()
        for (n, lo, data) in win.sections:
            i = data.find(pat)
            if i >= 0:
                ti_va = 0x400000 + lo + i - 16
                break
        if ti_va is None:
            print('[!]', cl, 'win typeinfo 未検出')
            continue
        ti_rva = ti_va - 0x400000
        # COL
        cols = []
        for (n, lo, data) in win.sections:
            if n not in ('.rdata', '.data'):
                continue
            p4 = struct.pack('<I', ti_rva)
            i = data.find(p4)
            while i >= 0:
                j = i - 12
                if j >= 0 and (j + 24 <= len(data)):
                    v1, v2, v3, v4, v5, v6 = struct.unpack_from('<IIIIII', data, j)
                    if v1 in (0, 1) and v4 == ti_rva:
                        cols.append(j + lo)
                i = data.find(p4, i + 4)
        # vftable
        vfts = []
        for colrva in cols:
            p8 = struct.pack('<Q', 0x180000000 + colrva)
            for (n, lo, data) in win.sections:
                if n not in ('.rdata', '.data'):
                    continue
                i = data.find(p8)
                while i >= 0:
                    vft_rva = lo + (i & ~7) + 8
                    vfts.append(vft_rva)
                    i = data.find(p8, i + 4)
        vfts = sorted(set(vfts))
        if not vfts:
            print('[!]', cl, 'win COL/vftable 未検出')
            continue
        if len(vfts) > 1:
            print('[!]', cl, '複数 COL 有り:', [hex(v) for v in vfts])
        vf = vfts[0]
        slots_w = []
        for k in range(140):
            v = struct.unpack_from('<Q', win.read_at(vf + k * 8, 8), 0)[0]
            r = v - 0x180000000
            if not (WT_LO <= r < WT_HI):
                break
            slots_w.append(r)
        print('[w] %s: win vftable@%x slots=%d  (mac %d)' % (cl, vf, len(slots_w), len(slots_m)))

        results = []
        def feature(mva, cap=0x2600):
            j = va2i.get(mva)
            sz = (syms[j + 1][0] - mva) if (j is not None and j + 1 < len(syms)) else 0x800
            return dmac.features(mva, max(4, min(sz, cap)))

        def feature_win(rva, cap=0x2600):
            k = bisect.bisect_right([a for (a, s) in win.fns], rva)
            (ba, bs) = win.fns[k - 1]
            return (ba, bs, dwin.features(ba, min(bs, cap)))

        for mi in range(len(slots_m)):
            j = {0: 0, 1: 0}.get(mi, mi - 1)
            if j < 0 or j >= len(slots_w):
                results.append({'mac_slot': mi, 'mac': hex(slots_m[mi]), 'win_rva': None,
                                'name': mac.func_names.get(slots_m[mi], '?'), 'score': None,
                                'win_size': None, 'mac_size': sz0(mi)})
                continue
            f_m = feature(slots_m[mi])
            (ba, bs, f_w) = feature_win(slots_w[j])
            s = fscore(f_w, f_m)
            results.append({'mac_slot': mi, 'mac': hex(slots_m[mi]), 'win_rva': hex(slots_w[j]),
                            'score': round(s, 3), 'name': mac.func_names.get(slots_m[mi], '?'),
                            'win_size': bs, 'mac_size': (syms[mi and 0 or 0], 0)[0] if False else 0})
        mapping[cl] = {'win_vft': hex(vf), 'win_slot_n': len(slots_w), 'mac_slot_n': len(slots_m),
                       'pairs': results}
        for r in results:
            sc = ('%.0f%%' % (r['score'] * 100)) if r['score'] is not None else '—'
            if r.get('win_rva'):
                print('    slot %2d: %08x ← %s   %s   win_rva %s' % (
                    r['mac_slot'], 0x400000 + int(r['mac'], 16), sc, r['name'][:56], r['win_rva']))
            else:
                print('    slot %2d: %08x [大主size?]  %s' % (r['mac_slot'], 0x400000 + int(r['mac'], 16), r['name'][:60]))
    json.dump(mapping, open(OUT, 'w'), indent=1)


def sz0(x):
    return None


if __name__ == '__main__':
    main()
