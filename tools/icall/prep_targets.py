#!/usr/bin/env python3
"""prep_targets.py — 監査対象 closure の関数範囲ファイルを work/ に生成する (既存の各 target 成果物を読むだけ)。
  work/bal_ranges.txt     Fruity Balance (tools/plugins closure: 本体 13 + framework frontier 54)
  work/fa_ranges.txt      Fresh Air SlateCore (tools/targets/freshair/work/clo_freshair_all.json)
  work/kh_gain_ranges.txt Kilohearts HeartCore (gain snap-in + 共通基盤 188 関数: closures_sets.pkl)
  work/fle_F.txt          FLEngine M11 closure (tools/m11/work/boot{0..4}.drc.ll の define 全部 = 7,421 関数)
  work/route/*            OTT は ott_route.sh が作る"""
import json, os, pickle, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
T = os.path.join(HERE, '..')
sys.path.insert(0, HERE)
import audit_icall as A
W = os.path.join(HERE, 'work'); os.makedirs(W, exist_ok=True)


def chain_parents(img):
    # CHAININFO 断片の UNWIND_INFO 末尾の親 RUNTIME_FUNCTION (BeginAddress) を断片 begin -> 親 begin で返す
    par = {}
    for e in getattr(img.pe, 'DIRECTORY_ENTRY_EXCEPTION', []) or []:
        st = e.struct
        b = img.base + st.BeginAddress
        if b not in img.pdata_chained:
            continue
        u = img.base + (st.UnwindData & ~1)
        h = img.read(u, 4)
        if not h:
            continue
        c = h[2]
        rf = img.read(u + 4 + 2 * (c + (c & 1)), 12)   # UnwindCode は偶数個に丸めて 2 byte ずつ
        if rf:
            par[b] = img.base + struct.unpack('<I', rf[:4])[0]
    return par


def chain_end(img, va, end, par):
    # .pdata の CHAININFO 断片 (hot/cold 分割) は親の RUNTIME_FUNCTION の直後に並ぶ。親 (chain 先) が va の断片だけを
    # 辿り、その末尾まで伸ばす (#1838)。途中で他関数の開始 VA を跨ぐ場合は伸ばさない
    e, acc = end, set()
    while e in img.pdata_chained and e in img.pdata and par.get(e) == va:
        acc.add(e)
        e = img.pdata[e]
    if e == end or any(va < b < e and b not in acc for b in img.bounds):
        return end
    return e


def ranges_with_ends(img, vas, given=None, chained=False):
    given = given or {}
    img.set_extra_starts(list(vas))
    dis = A.Disasm(img)
    par = chain_parents(img) if chained else {}
    out = []
    for va in sorted(set(vas)):
        r = (va, given[va]) if va in given else img.func_range(va)
        if not r:
            continue
        if chained and va in img.pdata and va not in img.pdata_chained:
            r = (va, chain_end(img, va, r[1], par))
        if va not in img.pdata and va not in given:   # leaf: 到達命令の末尾まで
            seen = dis.scan_function(r[0], r[1], {})
            end = max((a + i.size for a, i in seen.items()), default=r[1])
            r = (va, end)
        out.append('0x%x-0x%x' % r)
    return out


def main():
    # Balance
    d = json.load(open(os.path.join(T, 'plugins/work/closure/block18983.json')))
    img = A.Image('/home/ubuntu/work/analysis/win64/extracted/block18983_PE.bin')
    base = open(os.path.join(T, 'plugins/work/closure/block18983.ranges.txt')).read().strip().split(',')
    given = {int(r.split('-')[0], 16): int(r.split('-')[1], 16) for r in base}
    vas = list(given) + [int(x, 16) for x in d['frontier']]
    open(os.path.join(W, 'bal_ranges.txt'), 'w').write(','.join(ranges_with_ends(img, vas, given)))
    # Fresh Air
    fa = json.load(open(os.path.join(T, 'targets/freshair/work/clo_freshair_all.json')))
    img = A.Image(os.path.join(T, 'targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64'))
    open(os.path.join(W, 'fa_ranges.txt'), 'w').write(','.join(ranges_with_ends(img, [int(f['va'], 16) for f in fa['funcs']], chained=True)))
    # Kilohearts
    k = pickle.load(open(os.path.join(T, 'targets/kilohearts/work/closures_sets.pkl'), 'rb'))
    img = A.Image(os.path.join(T, 'targets/kilohearts/work/winpkg/HeartCore.core_64'))
    vas = [x if x >= k['base'] else k['base'] + x for x in (set(k['sets']['gain']) | set(k['infra']))]
    open(os.path.join(W, 'kh_gain_ranges.txt'), 'w').write(','.join(ranges_with_ends(img, vas)))
    # FLEngine
    defs = set()
    for i in range(5):
        p = os.path.join(T, 'm11/work/boot%d.drc.ll' % i)
        if os.path.exists(p):
            defs |= {int(x, 16) for x in re.findall(r'^define [^\n]*@function_([0-9a-f]+)\(', open(p, errors='replace').read(), re.M)}
    open(os.path.join(W, 'fle_F.txt'), 'w').write('\n'.join('0x%x' % v for v in sorted(defs)))
    print('prep: bal/fa/kh ranges + FLEngine F=%d funcs' % len(defs))


if __name__ == '__main__':
    main()
