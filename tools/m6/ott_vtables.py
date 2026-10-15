#!/usr/bin/env python3
# M6 #1b: mac __ZTV (Itanium ABI: [offtop][typeinfo][slots...]) を win64 側の
# 関数ポインタ配列 (.rdata/.data 内 8B 走歩) とスロット数+各スロットのフィーチャ一致で対応付けて
# 仮想関数群 (Tick 等 direct-call で追えないもの) の win64 側アドレスを確定する.
import sys, json, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ottlib import Bin, Dis

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from paths import PLUGINS_DIR
MAC = f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_mac_x86_64'
WIN = f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_win64.dll'
NMLOG = f'{PLUGINS_DIR}/ott/report_logs/nm_ott_vst2_mac_x64.txt'
OUT = os.path.join(BASE, 'work', 'ott_vtables.json')


def mac_syms():
    out = []
    for line in open(NMLOG):
        p = line.split()
        if len(p) >= 3:
            out.append((int(p[0], 16), p[1], p[2]))
    out.sort()
    return out


def main():
    mac = Bin(MAC)
    win = Bin(WIN)
    dmc, dw = Dis(mac), Dis(win)
    syms = mac_syms()
    mymap = dict((a, (ty, nm)) for (a, ty, nm) in syms if nm.startswith('__ZTV'))
    text_lo = mac.sections[0][1]
    text_hi = text_lo + len(mac.sections[0][2])

    # mac vtable
    vt_m = {}
    for va, (ty, nm) in mymap.items():
        slots = []
        p = va + 0x10
        for k in range(96):
            v = int.from_bytes(mac.read_at(p + k * 8, 8), 'little')
            if v in mac.func_names:
                slots.append(v)
            else:
                break
        key = nm.replace('__ZTV', '')
        if slots:
            vt_m[key] = {'va': va, 'slots': slots}
    print('[m] mac vtables:', {k: len(v['slots']) for k, v in vt_m.items()})

    # win 候補ポインタ配列 (base 0x180000000)
    wbase = 0x180000000
    wt_lo, wt_hi = 0x1000, 0x1000 + 1966312
    featcache = {}
    feats_w = {}
    for (n, lo, data) in win.sections:
        if n not in ('.rdata', '.data'):
            continue
        i = 0
        while i + 8 <= len(data):
            cnt = 0
            while i + cnt * 8 + 8 <= len(data) and cnt < 120:
                v = struct.unpack_from('<Q', data, i + cnt * 8)[0] - wbase
                if wt_lo <= v < wt_hi and (v & 7) == 0 and (i + cnt * 8) % 8 == 0:
                    cnt += 1
                else:
                    break
            if cnt >= 3:
                feats_w[lo + i] = [struct.unpack_from('<Q', data, i + k * 8)[0] - wbase for k in range(cnt)]
                i += cnt * 8
            else:
                i += 8
    print('[w] candidate arrays:', len(feats_w))

    def wfeat(va, szcap=0x2400):
        if va not in featcache:
            # .pdata 内の関数境界
            import bisect
            i = bisect.bisect_left([a for (a, s) in win.fns], va)
            b = win.fns[i] if i < len(win.fns) and win.fns[i][0] == va else (va, 0x800)
            f = dw.features(b[0], min(b[1], szcap))
            featcache[va] = f
        return featcache[va]

    def mfeat(va, szcap=0x2400):
        import bisect
        i = bisect.bisect_left([a for (a, s) in mac.fns], va)
        b = mac.fns[i] if i < len(mac.fns) and mac.fns[i][0] == va else (va, 0x800)
        f = dmc.features(b[0], min(b[1], szcap))
        return f

    def mfeat_size(va):
        import bisect
        i = bisect.bisect_left([a for (a, s) in mac.fns], va)
        b = mac.fns[i] if i < len(mac.fns) and mac.fns[i][0] == va else (va, 0x800)
        return b

    def score(fa, fb):
        if not fa or not fb:
            return 0.0
        da, db = fa['data'], fb['data']
        if not da or not db:
            return 0.35
        common = [k for k in da.keys() if k in db]
        if not common:
            return 0.2
        cnum = sum(min(da[k], db[k]) for k in common)
        denom = min(sum(da.values()), sum(db.values()))
        return cnum / denom

    out = {}
    for cls, mv in vt_m.items():
        msz = len(mv['slots'])
        results = []
        for wva, slots in feats_w.items():
            if len(slots) != msz:
                continue
            tot = 0.0
            for (mva, wva2) in zip(mv['slots'], slots):
                f_m = mfeat(mva)
                f_w = wfeat(wva2)
                tot += score(f_w, f_m)
            results.append((tot / msz, wva))
        results.sort(reverse=True)
        if results and results[0][0] > 0.62:
            (s, wva) = results[0]
            out[cls] = {'wva': wva, 'score': round(s, 3),
                        'slots': [{'mac': hex(a), 'win_rva': hex(b),
                                   'mac_name': mac.func_names.get(a, '?')}
                                  for (a, b) in zip(mv['slots'], feats_w[wva])]}
            print('[+] %s → win %s (score %.2f,超高: 参照)' % (cls, hex(wva), s))
            for e in out[cls]['slots']:
                print('    %s → win %s' % (e['mac_name'][:52], e['win_rva']))
        else:
            print('[-] %s score未達 (top %.2f)' % (cls, results[0][0] if results else 0.0))
            for (s, wva) in results[:3]:
                print('      %.2f @ %s' % (s, hex(wva)))
    with open(OUT, 'w') as fh:
        json.dump({'mac': {k: v['va'] for k, v in vt_m.items()},
                   'win_candidates': feats_w, 'match': out}, fh, indent=1)


if __name__ == '__main__':
    main()
