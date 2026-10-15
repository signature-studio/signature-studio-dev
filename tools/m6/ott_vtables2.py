#!/usr/bin/env python3
# M6 #1e: RTTI 経由で win64 側 vftable を発見し, mac __ZTV の仮想関数と slot 対応させる.
# (MSVC: typeinfo 名 ".?AV<cls>@@" → typeinfo(-16) → COL(RVA 4B) を参照する .rdata 値 → その +8 が vftable slot 0)
# 出力: work/ott_vtables2.json, work/ott_slot_map.txt
import sys, os, re, struct, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ottlib import Bin, Dis

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from paths import PLUGINS_DIR
MACF = f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_mac_x86_64'
WINF = f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_win64.dll'
NMLOG = f'{PLUGINS_DIR}/ott/report_logs/nm_ott_vst2_mac_x64.txt'
CLASSES = ['FIL_Linkwitz_Riley4', 'OTTProcessor', 'AudioEffectX', 'AudioEffect',
           'MyVUMeter', 'OTTVST', r'EnvelopeDetector@chunkware_simple',
           r'AttRelEnvelope@chunkware_simple', r'SimpleComp@chunkware_simple',
           r'SimpleCompRms@chunkware_simple']


def main():
    mac = Bin(MACF)
    win = Bin(WINF)
    dmac, dwin = Dis(mac), Dis(win)
    wbase = 0x180000000
    wt_lo, wt_hi = 0x1000, 0x1000 + 1966312

    # --- win: typeinfo 名アドレス ---
    ti_addr = {}
    for cl in CLASSES:
        pat = ('.?AV' + cl + re.escape('@@')).encode()
        for (n, lo, data) in win.sections:
            i = data.find(pat)
            if i >= 0:
                ti_addr[cl] = 0x400000 + lo + i - 16  # typeinfo 先頭
                break
    print('[w] typeinfo:', {k: hex(v) for k, v in ti_addr.items()})

    # --- win: COL を探す (COL 内 pTypeDescriptor == ti RVA (image-relative 4B) の .data/.rdata 位置) ---
    col_of = {}
    for cl, ti in ti_addr.items():
        ti_rva = ti - 0x400000
        pat = struct.pack('<I', ti_rva)  # MSVC x64: IMAGE-DOS 相対 (RVA 値)
        for (n, lo, data) in win.sections:
            if n not in ('.rdata', '.data'):
                continue
            i = data.find(pat)
            while i >= 0:
                v4 = struct.unpack_from('<I', data, i)[0]
                # COL[pTypeDescriptor] == ti RVA (COL 先頭は 12B 前)
                # sanity: COL の pClassDescriptor 前 16B が 0x180000000+rdata 内 or RVA 形式
                col_rva = lo + (i & ~7) - 12
                v1, v2, v3, v4b, v5, v6 = struct.unpack_from('<IIIIII', data, (i & ~7) - 12)
                if v1 == 0 and (v4b & 0xffff) == (ti_rva & 0xffff):
                    col_of.setdefault(cl, []).append(col_rva)
                    break
                    break
                i = data.find(pat, i + 4)
    print('[w] COL:', {k: [hex(x) for x in v] for k, v in col_of.items()})

    # --- win: vftable 参照探し (vft-1 → COL への絶対 0x180000000+RVA) ---
    slots_w = {}
    for cl, cols in col_of.items():
        for col in cols:
            pat = struct.pack('<Q', wbase + col)
            for (n, lo, data) in win.sections:
                i = data.find(pat)
                while i >= 0:
                    vft = lo + (i & ~7) + 8
                    slots = []
                    j = vft
                    while j + 8 <= len(data):
                        v = struct.unpack_from('<Q', data, j)[0] - wbase
                        if wt_lo <= v < wt_hi and (v & 7) == 0:
                            slots.append(v)
                            j += 8
                        else:
                            break
                    if len(slots) >= 3:
                        slots_w.setdefault(cl, []).append((0x400000 + vft, slots))
                    i = data.find(pat, i + 4)
    for cl in slots_w:
        print('[w] %s vftable@%s slots=%d' % (cl, hex(slots_w[cl][0][0]), len(slots_w[cl][0][1])))

    # --- mac: __ZTV (classes) ---
    vt_m = {}
    for l in open(NMLOG):
        p = l.split()
        if len(p) == 3 and p[2].startswith('__ZTV'):
            nm = p[2][5:]
            key = None
            for cl in CLASSES:
                cn = cl.split('@')[0].replace('_', '@')
                if nm == cl or nm.replace('@', '@') == '@'.join(cl.split('@')) or nm == cl:
                    key = cl
                if cl == 'FIL_Linkwitz_Riley4' and nm == '19FIL_Linkwitz_Riley4':
                    key = cl
                if cl == 'OTTProcessor' and nm == '12OTTProcessor':
                    key = cl
                if cl == 'AudioEffectX' and nm == '12AudioEffectX':
                    key = cl
                if cl == 'AudioEffect' and nm == '11AudioEffect':
                    key = cl
                if cl == 'MyVUMeter' and nm == '9MyVUMeter':
                    key = cl
                if cl == 'OTTVST' and nm == '6OTTVST':
                    key = cl
                if cl == 'EnvelopeDetector@chunkware_simple' and nm == 'N16chunkware_simple16EnvelopeDetectorE':
                    key = cl
                if cl == 'AttRelEnvelope@chunkware_simple' and nm == 'N16chunkware_simple14AttRelEnvelopeE':
                    key = cl
                if cl == 'SimpleComp@chunkware_simple' and nm == 'N16chunkware_simple10SimpleCompE':
                    key = cl
                if cl == 'SimpleCompRms@chunkware_simple' and nm == 'N16chunkware_simple13SimpleCompRmsE':
                    key = cl
            if key:
                va = int(p[0], 16)
                slots = []
                for k in range(96):
                    v = int.from_bytes(mac.read_at(va + 0x10 + k * 8, 8), 'little')
                    if v in mac.func_names:
                        slots.append(v)
                    else:
                        break
                if slots:
                    vt_m[key] = slots
    print('[m] mac vtable:', {k: len(v) for k, v in vt_m.items()})

    # --- slot 対応: フィーチャで slot 一致 ---
    def fscore(fa, fb):
        da, db = fa['data'], fb['data']
        if not da or not db:
            return 0.35
        common = [k for k in da.keys() if k in db and not k.startswith('4:0000')]
        if not common:
            return 0.18
        c0 = sum(min(da[k], db[k]) for k in common)
        den = min(sum(da.values()), sum(db.values()))
        return c0 / den

    out = {}
    for cl in vt_m:
        if cl not in slots_w:
            continue
        (wvft, wslots) = slots_w[cl][0]
        mslots = vt_m[cl]
        pairs = []
        if len(mslots) != len(wslots):
            print('[!] %s slot 数不一致: mac %d / win %d' % (cl, len(mslots), len(wslots)))
        n = min(len(mslots), len(wslots))
        for k in range(n):
            mva, wrva = mslots[k], wslots[k]
            f_m = dmac.features(mva, 0x800)
            # .pdata で win 関数の実 size を取る
            import bisect
            i = bisect.bisect_right([a for (a, s) in win.fns], wrva)
            self_ = win.fns[i - 1] if i else (wrva, 0x800)
            f_w = dwin.features(self_[0], min(self_[1], 0x800))
            s = fscore(f_w, f_m)
            pairs.append({'slot': k, 'mac': hex(mva), 'win_rva': hex(wrva),
                          'score': round(s, 2), 'name': mac.func_names.get(mva, '?')})
        out[cl] = {'wvft': hex(wvft), 'slots': pairs}
        print('==', cl)
        for e in pairs:
            print('    slot %2d: %s ←mac|%s  score %.2f' % (e['slot'], e['win_rva'], e['name'][:56], e['score']))
    json.dump(out, open(os.path.join(BASE, 'work', 'ott_vtables2.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
