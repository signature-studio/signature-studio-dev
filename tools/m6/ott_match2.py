#!/usr/bin/env python3
# M6 #1c: 反復照合 (2-pass)：win64 と mac (nm 符号あり) の x86_64 関数群について
#   pass A: フィーチャ (rip 相対 data 定数群 + 即値群) でアンカー選別 (score≥THR)
#   pass B: call-graph 整合と構造近接で他関数を伝播 (Mac 閉包内の関数群に映像)
# 出力: work/ott_match2.json (mac va → win rva と名前の対応表)
import sys, json, os, re, struct, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ottlib import Bin, Dis

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from paths import PLUGINS_DIR
MACF = f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_mac_x86_64'
WINF = f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_win64.dll'
NMLOG = f'{PLUGINS_DIR}/ott/report_logs/nm_ott_vst2_mac_x64.txt'
OUT_JSON2 = os.path.join(BASE, 'work', 'ott_match2.json')

SERE = re.compile(r'__ZN(?:K)?(?:\d+)?(?:7Trap|8Trap|11Trap|12Trap|TrapSVF|TrapZBF|TrapPeak|TrapHiShelf|TrapLowShelf|TrapSVF)|'
                  r'__ZN(?:K)?\d*(?:chunkware_simple|OTTProcessor|FIL_Linkwitz_Riley4|MyVUMeter|AudioEffect)|'
                  r'__ZN8BetaBugs|__ZN[0-9]*ProcessCompSettings|__ZN[0-9]*processReplacing|__ZNK1[12]OTTProcessor')

def nm_syms():
    arr = []
    for l in open(NMLOG):
        p = l.split()
        if len(p) >= 3 and p[1] in ('T','t'):
            arr.append((int(p[0], 16), p[2]))
    arr.sort()
    return arr

def main():
    mac = Bin(MACF); win = Bin(WINF)
    dmac = Dis(mac); dwin = Dis(win)
    syms = nm_syms()
    va2i = dict((va, i) for i, (va, nm) in enumerate(syms))

    # 閉包の seed: DSP 関数 + ctor 系
    closure = {}
    for (va, nm) in syms:
        # processReplacing / resume / setParameter / ctor / initFilters / ProcessCompSettings /
        # chunkware_simple / FIL_LR4 / Trap* / MyVUMeter setter系 / BetaBugs / AudioEffect::__
        m = SERE.match(nm)
        if m:
            j = va2i[va]
            e2 = syms[j+1][0] if j+1 < len(syms) else va+0x1000
            closure[va] = nm
    # 仮想テーブル関連: mac __ZTV からスロット取得 (class key をまとめ)
    vt_for = {}
    for line in open(NMLOG):
        p = line.split()
        if len(p) == 3 and p[1] in 'SsBbVv' and p[2].startswith('__ZTV'):
            va = int(p[0], 16)
            if p[2].find('OTTProcessor') > 0 or p[2].find('chunkware') > 0 or p[2].find('Trap') > 0 or \
               p[2].find('FIL_Linkwitz') > 0 or p[2].find('MyVUMeter') > 0:
                slots = []
                pp = va + 0x10  # [offtop][typeinfo] 後
                for k in range(96):
                    v = int.from_bytes(mac.read_at(pp + k*8, 8), 'little')
                    if v in mac.func_names:
                        slots.append(v)
                    else:
                        break
                vt_for[p[2]] = slots
    for (k, slots) in vt_for.items():
        for v in slots:
            if v not in closure and v in mac.func_names:
                closure[v] = mac.func_names[v] + ' (vtable:' + k + ')'
    print('[m] closure (seed):', len(closure))

    # closure 展開 (direct call; __stubs は extern 表現 → retdec 段で解決)
    externs = {}
    work = list(closure.keys())
    seen = list(closure.keys())
    while work:
        va = work.pop()
        j = va2i.get(va)
        if j is not None:
            e2 = syms[j+1][0] if j+1 < len(syms) else va+0x1000
            sz = e2-va
        else:
            sz = 0x800
        f = dmac.features(va, sz)
        if f is None:
            continue
        for t in f['calls']:
            b = mac.read_at(t, 3)
            if b and b[0:2] == b'\xff\x25':
                rel = int.from_bytes(b[2:6], 'little', signed=True)
                nm2 = mac.stub_names.get(t+6+rel)
                if nm2:
                    externs[nm2] = t
                continue
            if mac.func_names.get(t) and t not in closure:
                closure[t] = mac.func_names.get(t)
                work.append(t)
    print('[m] closure (final):', len(closure), ' externs:', len(externs))

    # --- win 関数群 features ---
    from collections import defaultdict
    wfeat = {}
    wcall = {}
    winfo = defaultdict(dict)
    for (rva, sz) in win.fns:
        fw = dwin.features(rva, sz)
        if fw is None:
            continue
        wfeat[rva] = fw
        wcall[rva] = fw['calls']
    # --- mac 関数群 features ---
    feats_m = {}
    for va, nm in closure.items():
        j = va2i.get(va)
        if j is not None:
            e2 = syms[j+1][0] if j+1 < len(syms) else va+0x1000
            sz = e2-va
        else:
            sz = 0x800
        f = dmac.features(va, sz)
        if f: feats_m[va] = f
    print('[m] feats:', len(feats_m))
    # --- スコア演算関数 ---
    def fscore(fa, fb):
        da, db = fa['data'], fb['data']
        if not da or not db:
            return 0.35
        common = [k for k in da.keys() if k in db and not k.startswith('4:0000')]
        if not common:
            return 0.2
        c0 = sum(min(da[k], db[k]) for k in common)
        denom = min(sum(da.values()), sum(db.values()))
        return c0/denom
    winscore = {}
    for (mva, f_m) in feats_m.items():
        arr = []
        for (rva, f_w) in wfeat.items():
            s = fscore(f_w, f_m)
            if s > 0.3:
                arr.append((s, rva))
        arr.sort(reverse=True)
        winscore[mva] = arr

    # pass A として信頼あるものだけ採用 (アンカー)
    TH1, TH2 = 0.82, 0.9
    anchor = {}
    for (mva, arr) in winscore.items():
        if arr and arr[0][0] >= TH1:
            # 次点との差
            en2 = arr[1][0] if len(arr) > 1 else 0
            if arr[0][0] >= TH2 or (arr[0][0] - en2) > 0.045:
                anchor[mva] = arr[0][1]
    for (mva, best) in sorted(anchor.items()):
        print('    %08x → %08x  %s' % (mva, 0x400000+best, mac.func_names.get(mva, '')[:50]))
    return (anchor, winscore, closure, wcall, dwin, feats_m)
