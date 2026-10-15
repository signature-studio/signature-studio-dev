#!/usr/bin/env python3
# M6 #1: mac (符号あり, Apple clang) と win64 DLL (.pdata 境界) の x86_64 関数を
# フィーチャマッチ (rip 相対 data 定数 + 即値群 + 大きさ) して対応表を作る。
#
#   python3 ott_match.py > work/ott_match_report.txt   (json は work/ott_match.json)
#
import sys, json, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ottlib import Bin, Dis

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from paths import PLUGINS_DIR
MAC = f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_mac_x86_64'
WIN = f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_win64.dll'
NMLOG = f'{PLUGINS_DIR}/ott/report_logs/nm_ott_vst2_mac_x64.txt'
OUT_JSON = os.path.join(BASE, 'work', 'ott_match.json')

# DSP 関係の mac symbol (手動で指定した閉包シード) — 他は closure 展開で拾う
SEED_CLASS_RE = re.compile(r'__ZN(?:K)?(?:7|8|11|12)Trap|__ZN(?:K)?\d+Trap|'
                           r'__ZN9MyVUMeter1[01]set(?:Up|Dn|GRValue)|__ZN(?:K)?\d+chunkware_simple|'
                           r'__ZN(?:K)?19FIL_Linkwitz_Riley4|__ZN(?:K)?1[12]OTTProcessor')

def demangle_short(name):
    n = name
    for pre in ('__ZN', '__ZNK'):
        if n.startswith(pre):
            n = n[len(pre):]
    return n


def build_features(binobj, funcs, cap=0x4000):
    d = Dis(binobj)
    feats = {}
    for (va, sz) in funcs:
        if sz <= 0 or sz > cap:
            continue
        f = d.features(va, sz)
        if f is None:
            continue
        feats[va] = f
    return feats


def main():
    mac = Bin(MAC)
    win = Bin(WIN)
    d = Dis(win)
    print('[m] mac fns=%d syms=%d    [w] win .pdata fns=%d' % (len(mac.fns), len(mac.func_names), len(win.fns)))

    # --- 開始シード (mac nm 由来) 設定 ---
    def nm_sorted_syms():
        syms = []
        for line in open(NMLOG):
            p = line.split()
            if len(p) >= 3 and p[1] in ('T', 't'):
                syms.append((int(p[0], 16), p[2]))
        syms.sort()
        return syms

    syms = nm_sorted_syms()
    va2i = dict((va, i) for i, (va, nm) in enumerate(syms))
    seeds = []
    for (va, nm) in syms:
        if SEED_CLASS_RE.match(nm):
            # サイズ = 次のシンボルまで (多過ぎたら 0x3600 cap)
            i = va2i[va]
            end = syms[i + 1][0] if i + 1 < len(syms) else va + 0x1000
            # ジャンプ/ret の末尾で trim はしない (features は decode 可能分だけで集計)
            sz = min(end - va, 0x3600)
            seeds.append((va, nm, sz))
    print('[m] closure seed syms:', len(seeds))

    # --- 閉包展開 (direct call + vtable slot, 内部関数; stub/extern は externs へ) ---
    dmac = Dis(mac)

    def add_vtable(tv_va, out):
        """__ZTV (S 符号) の関数スロットを追加する (OTE: offset-to-top/typeinfo/bean ポインタ除く)."""
        p = tv_va + 0x10
        cnt = 0
        while cnt < 64:
            ptr = mac.read_le32(p) if False else int.from_bytes(mac.read_at(p, 8), 'little')
            if not ptr or mac.func_names.get(ptr) is None:
                break
            out.append((ptr, mac.func_names[ptr], 0x600))
            p += 8
            cnt += 1

    for (tva, tnm) in syms:
        if tnm.startswith('__ZTV') and any(tag in tnm for tag in
                ('OTTProcessor', 'chunkware_simple', 'FIL_Linkwitz_Riley4', 'Trap', 'MyVUMeter')):
            add_vtable(tva, work)

    closure = {}
    externs = {}
    work = list(seeds)
    # mac シンボル順序由来の境界テーブル (大ざっぱ)
    ma_fns = mac.fns
    ma_sorted = [va for (va, _sz) in ma_fns]
    import bisect

    def mac_region_end(va):
        i = bisect.bisect_left(ma_sorted, va)
        if i < len(ma_sorted) and ma_sorted[i] == va:
            sz = ma_fns[i][1]
        else:
            sz = 0x1000
        return sz

    while work:
        (va, nm, sz) = work.pop()
        if va in closure:
            continue
        closure[va] = nm
        f = dmac.features(va, min(sz if sz else mac_region_end(va), 0x3600))
        if f is None:
            continue
        for t in f['calls']:
            if mac_region_end(t) > 0 and t in mac.func_names:
                b = mac.read_at(t, 3)
                if t not in closure and not (b and b[0:2] == b'\xff\x25'):
                    j = va2i.get(t)
                    tnm = mac.func_names.get(t, '')
                    if j is not None:
                        e2 = syms[j + 1][0] if j + 1 < len(syms) else t + 0x1000
                        work.append((t, tnm, min(e2 - t, 0x3600)))
                    else:
                        work.append((t, tnm, mac_region_end(t)))
            elif t not in externs:
                b = mac.read_at(t, 6)
                if b and b[0:2] == b'\xff\x25':
                    rel = int.from_bytes(b[2:6], 'little', signed=True)
                    nm2 = mac.stub_names.get(t + 6 + rel)
                    if nm2:
                        externs[nm2] = t
    print('[m] closure fns:', len(closure), ' externs:', len(externs))
    for (va, nm) in sorted(closure.items()):
        print('    %08x %s' % (va, nm))

    # --- フィーチャ構築 ---
    feats_m = {}
    for (va, nm) in closure.items():
        j = va2i.get(va)
        if j is not None:
            e2 = syms[j + 1][0] if j + 1 < len(syms) else va + 0x1000
            sz = min(e2 - va, 0x3600)
        else:
            sz = mac_region_end(va)
        fm = dmac.features(va, max(8, sz))
        if fm:
            fm['name'] = nm
            feats_m[va] = fm
    feats_w = build_features(win, win.fns)
    print('[m] mac feats: %d   [w] win feats: %d' % (len(feats_m), len(feats_w)))

    # --- スコア計算: data 定数 Jaccard + (data 重み)  ---
    def score(fa, fb):
        da, db = fa['data'], fb['data']
        if not da or not db:
            return 0.0
        common = set(k for k in da.keys() if k in db)
        pa = sum(min(da[k], db[k]) for k in common)
        pb = sum(min(da[k], db[k]) for k in common)
        denom = min(sum(da.values()), sum(db.values()))
        if denom == 0:
            return 0.0
        s = pa / denom
        # 大きさ差のペナルティ
        ra = fa['size'] / max(1, fb['size'])
        pen = 1.0 - 0.22 * min(1.0, abs(ra - 1.0))
        return s * pen

    pairs = []
    # 各 win fn と mac fn で best match (mac 側は best に束縛)
    for (wva, fw) in sorted(feats_w.items()):
        best, bestv = None, 0.0
        for (mva, fm) in feats_m.items():
            s = score(fw, fm)
            if s > bestv:
                bestv, best = s, mva
        if best is not None and bestv > 0.55:
            pairs.append({'win': wva, 'win_size': fw['size'], 'mac': best,
                          'mac_name': fm_pair_name(feats_m, best), 'score': round(bestv, 3)})
    # mac→win 逆方向参照 (1 mac fn が複数 win fn に張る場合は, 候補先頭; 後処理で統合)
    bake = {}
    for p in pairs:
        k = p['mac']
        if k not in bake or p['score'] > bake[k]['score']:
            bake[k] = p
    pairs_final = sorted(bake.values(), key=lambda p: -p['score'])
    with open(OUT_JSON, 'w') as fh:
        json.dump(pairs_final, fh, indent=1)
    for p in pairs_final:
        print('%08x (sz%6d)  ←mac %08x %6.2f%%  %s' % (
            0x400000 + p['win'], p['win_size'], p['mac'], p['score'] * 100,
            ('.' + p['mac_name'][:60])))
    print('[m] matched:', len(pairs_final), '/ closure', len(closure))


def fm_pair_name(feats_m, va):
    return feats_m[va].get('name', '')


if __name__ == '__main__':
    main()
