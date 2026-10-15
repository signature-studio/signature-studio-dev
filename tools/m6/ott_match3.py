#!/usr/bin/env python3
# M6 #1d: 反復照合 (pass A: 高信頼直接照合 + ctor の magic 埋め込み探索, pass B: call-graph/高い隣接性伝播)
#    - mac (nm 符号あり) の OTT DSP クラス閉包 → win64 (.pdata 境界) への対応表作成
#    - 出力: work/ott_map.json  (mac_addr → win_rva, 保証要素のイベント)
import sys, json, os, re, struct, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ottlib import Bin, Dis
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from paths import PLUGINS_DIR
MACF = f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_mac_x86_64'
WINF = f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_win64.dll'
NMLOG = f'{PLUGINS_DIR}/ott/report_logs/nm_ott_vst2_mac_x64.txt'
OUT = os.path.join(BASE, 'work', 'ott_map.json')

RESE = r'__ZN(?:K)?\d+(?:Trap(?:SVF|ZBF|Peak|HiShelf|LowShelf)|chunkware_simple::|MyVUMeter[1-3]0?set(?:Up|Dn|GRValue)?)'
SE_TARGET = re.compile(
    r'__ZN(?:K)?\d*Trap(?:SVF|ZBF|Peak|HiShelf|LowShelf|)|'
    r'__ZN(?:K)?\d*chunkware_simple\w*|'
    r'__ZN9MyVUMeter(?:1[01]set(?:Up|Dn|GRValue)|C2E)|'
    r'__ZN(?:K)?\d*FIL_Linkwitz_Riley4\w*|'
    r'__ZN(?:K)?\d*OTTProcessor(?:\d*processReplacing|\d*resume|\d*setParameter|\d*ProcessCompSettings|\d*initFilters|\d*suspend)\w*|'
    r'__ZN12OTTProcessorC2EPFxP7AEffectiixPvfE')


def nm_list():
    out = []
    for l in open(NMLOG):
        p = l.split()
        if len(p) >= 3 and p[1] in 'Tt':
            out.append((int(p[0], 16), p[2]))
    out.sort()
    return out


def main():
    mac = Bin(MACF)
    win = Bin(WINF)
    dmac = Dis(mac)
    dwin = Dis(win)
    syms = nm_list()
    va2i = {v: i for i, (v, n) in enumerate(syms)}

    # --- mac closure: シード (regex) + 仮想テーブルスロット + direct-call 展開 ---
    closure = {}
    for (va, nm) in syms:
        if SE_TARGET.match(nm):
            closure[va] = nm
    # 仮想テーブル: __ZTV 利用
    for l in open(NMLOG):
        p = l.split()
        if len(p) == 3 and p[1] in 'Ss' and p[2].startswith('__ZTV') and \
           any(tag in p[2] for tag in ('OTTProcessor', 'chunkware', 'Trap', 'FIL_Linkwitz', 'MyVUMeter')):
            va = int(p[0], 16)
            pp = va + 0x10
            for k in range(96):
                tv_val = int.from_bytes(mac.read_at(pp + k * 8, 8), 'little')
                if tv_val in mac.func_names:
                    if tv_val not in closure:
                        closure[tv_val] = mac.func_names[tv_val] + '   [vtable:' + p[2][5:] + ']'
                else:
                    break
    # direct-call 展開 (内部関数のみ; _stubs は外部要素として名前だけ残す)
    externs = {}
    work = list(closure.keys())
    while work:
        va = work.pop()
        j = va2i.get(va)
        sz = (syms[j + 1][0] - va) if (j is not None and j + 1 < len(syms)) else 0x800
        f = dmac.features(va, sz)
        if f is None:
            continue
        for t in f['calls']:
            b = mac.read_at(t, 3)
            if b and b[:2] == b'\xff\x25':
                rel = int.from_bytes(b[2:6], 'little', signed=True)
                s2 = mac.stub_names.get(t + 6 + rel)
                if s2:
                    externs[s2] = t
                continue
            if mac.func_names.get(t) and t not in closure:
                closure[t] = mac.func_names[t]
                work.append(t)
    print('[m] closure:', len(closure), ' externs:', len(externs))
    for e in sorted(externs):
        print('     X', e)

    # --- win: .pdata features/call ---
    wfeat, wcall, wadj = {}, {}, defaultdict(list)
    wfns = win.fns
    for idx, (rva, sz) in enumerate(wfns):
        fw = dwin.features(rva, sz)
        if fw is None:
            continue
        wfeat[rva] = fw
        wcall[rva] = fw['calls']
    for (rva, cs) in wcall.items():
        for c in cs:
            wadj[c].append(rva)
    # mac: 閉包 features/call
    mfeat, mcall = {}, {}
    for (va, nm) in closure.items():
        j = va2i.get(va)
        sz = (syms[j + 1][0] - va) if (j is not None and j + 1 < len(syms)) else 0x800
        f = dmac.features(va, sz)
        if f is None:
            continue
        mfeat[va] = f
        mcall[va] = [c for c in f['calls'] if c in closure or c in mac.func_names]
    # --- 汎用スコア ---
    def fs_adjust(fa, fb):
        da, db = fa['data'], fb['data']
        if not da or not db:
            return 0.35
        common = set(k for k in da.keys() if k in db and not k.startswith('4:0000'))
        if not common:
            return 0.2
        c0 = sum(min(da[k], db[k]) for k in common)
        denom = min(sum(da.values()), sum(db.values()))
        return c0 / denom

    # --- pass A: anchor (injective assign): score 降順に席を配る ---
    ctor_win = None
    for (rva, sz) in wfns:
        if sz == 0:
            continue
        code = win.read_at(rva, sz)
        if code is None:
            continue
        if code.find(struct.pack('<I', 0x56737450)) >= 0:
            ctor_win = rva
            break
    assert ctor_win is not None, 'ctor (magic 0x56737450) 未発見'
    print('[w] ctor (magic):', hex(0x400000 + ctor_win))

    anchor = {}
    mac_ctor = [va for (va, nm) in closure.items() if nm.startswith('__ZN12OTTProcessorC2EPFx')]
    for va in mac_ctor:
        anchor[va] = ctor_win

    # anchor を feature score でも採用 (injective: 全仮ペアを整列して席それぞれ 1 回)
    all_pairs = []
    for (mva, f_m) in mfeat.items():
        for (rva, f_w) in wfeat.items():
            s = fs_adjust(f_w, f_m)
            if s > 0.55:
                # size 差ペナルティ
                rs = f_m['size'] / max(1, f_w['size'])
                if rs < 0.55 or rs > 1.8:
                    continue
                all_pairs.append((s, mva, rva))
    all_pairs.sort(reverse=True)
    used_m, used_w = set(), set()
    for (s, mva, rva) in all_pairs:
        if mva in used_m or rva in used_w:
            continue
        if s >= 0.82:
            anchor[mva] = rva
            used_m.add(mva)
            used_w.add(rva)
    # --- pass B: call-graph/隣接性伝播 ---
    # すべての m closure に call list を derive して win 内の anchor を propagate
    mcall_in = defaultdict(list)
    mcall_out = {}
    for (va, cs) in mcall.items():
        mcall_out[va] = cs
        for c in cs:
            mcall_in[c].append(va)
    call_out_win = defaultdict(list)    # win fn → 呼ばれる win fn
    call_in_win = defaultdict(list)
    for (rva, cs) in wcall.items():
        for c in cs:
            call_out_win[c].append(rva)
            call_in_win[rva].append(c)
    winscore_cache_ = {}
    anchor_win_by_m_ = anchor
    changed = True
    while changed:
        changed = False
        # 1) m fn f が既に anchor で, f の calleeであり closure 内なら, 対応 win の callee 一致を探す
        for (mva, best) in list(anchor.items()):
            cand = None
            for c in mcall_out[mva]:
                if c in anchor or c not in closure:
                    continue
                # c の対応: call_out_win[best] に c の match スコア候補がいるか
                target_list = call_out_win[best]
                if c in anchor:
                    continue
                # c の win 候補: もっとも fscore が高いもの
                if c in winscore_cache_:
                    cands = winscore_cache_[c]
                else:
                    cands = adj_cands(c, anchor, mfeat, wfeat, fs_adjust, call_in_win, anchor_win_by_m_, call_out_win)
                    winscore_cache_[c] = cands
                # c の一致は 1 つだけなら採用
                if len(cands) == 1:
                    anchor[c] = cands[0]
                    changed = True
            # anchor に含まれる callee が未設でも対応可能な場合も propagate: 後から精査
        # 2) 推定: anchor 内で未決 — 隣接ミラー (mac の sq, win の sq)
    for (mva, wva) in sorted(anchor.items()):
        print('    %08x → %08x' % (mva, 0x400000 + wva), mac.func_names.get(mva, '')[:58])
    # 未 match 一覧
    for (mva, nm) in sorted(closure.items()):
        if mva not in anchor:
            print('    UNC %08x %s' % (mva, nm[:64]))
    return anchor


# ヘルパ: c の win 採用案決定
def adj_cands(c, anchor, mfeat, wfeat, fs_adjust, call_in_win, anchor_win_by_m, call_out_win):
    """mac c の win 候補集合を返す (call for anchor で呼ばれている win fn のうち, c とフィーチャ一致が良い順)."""
    moves = defaultdict(int)
    for (mva, wva) in anchor.items():
        # mva が c を呼ぶ? (mcall_out[mva] を元に)
        pass
    # caller 逆: anchor で既に c の, m 上 caller (と win 上 caller) がいるなら,
    #   anchor_win_by_m[caller] の callees に一致する c の win 候補を返す
    out = set()
    for (mva, wva) in anchor.items():
        if c in call_out_win.get(wva, []):
            out.add(c)
        if c in call_in_win.get(wva, []):
            out.add(c)
    return list(out)


if __name__ == '__main__':
    main()
