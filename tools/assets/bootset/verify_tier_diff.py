#!/usr/bin/env python3
"""ST-T14 REPORT §4 の tier 差分 6 点が classify_bootset.py の規則に反映されたことをファイル単位で検査する (#592)。

Usage: verify_tier_diff.py <old_bootset.json> [--negcon]
  old = 変更前の bootset.json (rules の順・glob で旧 tier を再計算)。new = work/tiers.json (classify_bootset.py の出力)。
  期待差分 = tools/startup/loadpaths/REPORT.md §4 の表 (下の EXPECT)。実差分と過不足なく一致しなければ exit 1。
  --negcon: 期待表の 1 件を壊して不一致が検出される (exit 1 相当) ことを確認する。通ってしまえば exit 2。
"""
import json, os, re, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__)); WORK = os.path.join(os.path.dirname(HERE), 'work')


def rx(g):
    gg = g[:-2] + '/**' if g.endswith('/*') else g
    r, i = '', 0
    while i < len(gg):
        if gg.startswith('**', i): r += '.*'; i += 2
        elif gg[i] == '*': r += '[^/]*'; i += 1
        else: r += re.escape(gg[i]); i += 1
    return re.compile('^' + r + '$', re.I)


# (#, 旧→新, 対象 path の判定, 件数, bytes)
EXPECT = [
    (1, 'T1', 'T0p', lambda p: re.fullmatch(r'Help/(HelpPlugins|HelpAliases)\.scr', p), 2, 10949),
    (2, 'T2', 'T0', lambda p: p == 'Artwork/Wallpapers/Default.txt', 1, 97),
    (3, 'T1', 'T2', lambda p: re.fullmatch(r'System/Languages/[^/]+\.moe', p), 7, 6282124),
    (4, 'T0', 'T0p', lambda p: p == 'Artwork/Skins/Default/StartSnd.wv', 1, 72076),
    (5, 'T0', 'T1', lambda p: re.fullmatch(r'Artwork/Skins/Default/(BigFruit\.png|ClipHanger\.png|PickerChan\.png|ScopeGradient\.bmp|RenderSnd\.wv)', p), 5, 270952),
    (6, 'T0p', 'T1', lambda p: re.fullmatch(r'System/Texts/[^/]+\.txt', p), 8, None),
]


def main(a):
    neg = '--negcon' in a
    old_rules = [(r['tier'], rx(r['glob'])) for r in json.load(open(a[0]))['rules']]
    inv = [json.loads(l) for l in open(os.path.join(WORK, 'inv_win.jsonl'))]
    new = json.load(open(os.path.join(WORK, 'tiers.json')))
    size = {}
    actual = {}
    for e in inv:
        if e['cat'] == 'exec':
            continue
        p = e['p']
        o = next((t for t, r in old_rules if r.match(p)), 'T2')
        size[p] = e['size']
        if o != new[p]:
            actual[p] = (o, new[p])
    expect = list(EXPECT)
    if neg:
        n = expect[1]
        expect[1] = (n[0], n[1], 'T0p', n[3], n[4], n[5])      # #2 の新 tier を壊す
    claimed, fail = {}, []
    for no, o, n, pred, cnt, byt in expect:
        hit = [p for p in size if pred(p) and (o, n) == actual.get(p, (None, None))]
        allm = [p for p in size if pred(p)]
        b = sum(size[p] for p in hit)
        ok = len(hit) == cnt == len(allm) and (byt is None or b == byt)
        print(f'#{no} {o}->{n}: 一致 {len(hit)}/{len(allm)} 件 {b} byte (期待 {cnt} 件{"" if byt is None else f" {byt} byte"}) {"OK" if ok else "NG"}')
        if not ok:
            fail.append(f'#{no}')
        for p in hit:
            claimed[p] = no
    extra = sorted(p for p in actual if p not in claimed)
    if extra:
        fail.append(f'表に無い差分 {len(extra)} 件: {extra[:5]}')
    t0d = sum(size[p] * (-1 if actual[p][0] == 'T0' else 1) for p in actual if 'T0' in actual[p])
    print(f'実差分 計 {len(actual)} 件 (期待 {sum(e[4] for e in EXPECT)} 件) / T0 byte 増減 {t0d:+d} (期待 -342931) / 表外 {len(extra)}')
    if t0d != -342931:
        fail.append('T0 byte 増減')
    if len(actual) != sum(e[4] for e in EXPECT):
        fail.append('差分総数')
    print('FAIL: ' + ', '.join(fail) if fail else 'PASS')
    if neg:
        sys.exit(1 if fail else 2)          # ネガコンは「検出できた」= exit 1 を期待
    sys.exit(1 if fail else 0)


main(sys.argv[1:])
