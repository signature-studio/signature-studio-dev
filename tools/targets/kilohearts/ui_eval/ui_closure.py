#!/usr/bin/env python3
"""KH-7 (#59): UI 層 (Editor/Skia) のコード規模と、接続上の未実装 import を呼ぶ関数の所属を実測する。

入力: HeartCore.core_64, rtti_vtables.json / callgraph.pkl (tools/targets/kilohearts/scripts の rtti_walk.py / callgraph.py 産)
方法: 直接 call/jmp 辺のみ追跡 (間接 call は辿らない = 到達集合は下限)。
  UI roots   = 各 snap-in 名前空間の「Dsp / MasterDsp / DspModel 以外」クラスの vtable slot (Editor/EditorModel/Controller/UI*/Field)
  Skia roots = クラス名が Sk* / Gr* の vtable slot 全部
usage: ui_closure.py core cg.pkl vtables.json out.json
終了コード: 0 = 検査 PASS / 1 = 検査 FAIL (前提または不変条件の破れ)
"""
import sys, os, re, json, pickle, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))

DSP_RE = re.compile(r'(MasterDsp|Dsp|DspModel)$')
HOST_NS = ('phaseplant', 'multipass', 'micropass', 'snapingroup', 'hostproxy')


def split_class(k):
    rest = k[4:]
    rest = rest[:-2] if rest.endswith('@@') else rest
    if '?' in rest or '$' in rest:
        return None
    parts = [p for p in rest.split('@') if p]
    return (parts[0], parts[-1], len(parts)) if parts else None


def reach(res, roots):
    seen, st = set(), list(roots)
    while st:
        f = st.pop()
        if f in seen or f not in res:
            continue
        seen.add(f)
        r = res[f]
        st.extend(r['calls'])
        st.extend(r['jmps'])
    return seen


def category(k):
    if re.match(r'\.\?A[VU](Sk|Gr)', k):
        return 'skia'
    if '@pace@@' in k or 'license_services' in k:
        return 'pace'
    if '@boost@@' in k:
        return 'boost'
    if '@std@@' in k:
        return 'std'
    return 'other'


def main(core_path, cgp, vtp, outp):
    from khlib import Core
    from closures import PROD
    cg = pickle.load(open(cgp, 'rb'))
    base, res = cg['base'], cg['res']
    vt = json.load(open(vtp))
    core = Core(core_path)
    assert core.base == base
    text_total = core.tsz

    # --- クラス分類 (RTTI vtable を持つクラス数 / vtable slot 関数の bytes) ---
    cls_cnt = collections.Counter(category(k) for k in vt)
    slots_by_cat = collections.defaultdict(set)
    for k, lst in vt.items():
        for v in lst:
            for s in v['slots']:
                slots_by_cat[category(k)].add(int(s, 16) - base)

    # --- roots ---
    ui_roots = collections.defaultdict(set)
    dsp_roots = collections.defaultdict(set)
    ui_classes = collections.defaultdict(list)
    for k, lst in vt.items():
        sc = split_class(k)
        if not sc:
            continue
        name, ns, depth = sc
        if ns not in PROD or depth != 2:
            continue
        tgt = dsp_roots if DSP_RE.search(name) else ui_roots
        if tgt is ui_roots:
            ui_classes[ns].append(name)
        for v in lst:
            for s in v['slots']:
                tgt[ns].add(int(s, 16) - base)
    skia_roots = {int(s, 16) - base for k, lst in vt.items() if category(k) == 'skia' for v in lst for s in v['slots']}

    def size(fs):
        return sum(res[f]['size'] for f in fs if f in res)

    effects = [ns for ns in ui_roots if ns not in HOST_NS]
    ui_reach = {ns: reach(res, ui_roots[ns]) for ns in ui_roots}
    dsp_reach = {ns: reach(res, dsp_roots[ns]) for ns in dsp_roots}
    skia = reach(res, skia_roots)
    ui_union = set().union(*[ui_reach[ns] for ns in effects])
    cnt = collections.Counter(f for ns in effects for f in ui_reach[ns])
    ui_infra = {f for f, c in cnt.items() if c >= 8}
    per_ns = {}
    for ns in sorted(effects):
        own = ui_reach[ns] - ui_infra - skia
        per_ns[ns] = dict(id=PROD[ns][0], name=PROD[ns][1], ui_classes=len(ui_classes[ns]), ui_roots=len(ui_roots[ns]),
                          closure_funcs=len(ui_reach[ns]), closure_bytes=size(ui_reach[ns]),
                          own_nonskia_funcs=len(own), own_nonskia_bytes=size(own))
    gain = per_ns.get('gain')

    # --- 未実装 import の呼び出し元関数 → 所属 (直接辺の逆到達 → クラス) ---
    imp = json.load(open(os.path.join(os.path.dirname(outp), 'ui_imports.json')))
    xr = core.xrefs()
    rev = collections.defaultdict(set)
    for f, r in res.items():
        for c in list(r['calls']) + list(r['jmps']):
            rev[c].add(f)
    slot2cls = collections.defaultdict(set)
    for k, lst in vt.items():
        for v in lst:
            for s in v['slots']:
                slot2cls[int(s, 16) - base].add(k)

    def ancestors(fs):
        seen, st = set(), list(fs)
        while st:
            f = st.pop()
            if f in seen:
                continue
            seen.add(f)
            st.extend(rev.get(f, ()))
        return seen

    owners = {}
    watch = list(imp['gap'].keys()) + ['SetDIBitsToDevice', 'CreateDIBSection', 'BeginPaint']
    for nm in watch:
        dll = imp['gap'][nm]['dll'] if nm in imp['gap'] else ('gdi32.dll' if nm != 'BeginPaint' else 'user32.dll')
        fs = {core.func_of(a)[0] for a, _ in xr.get((dll, nm), []) if core.func_of(a)}
        anc = ancestors(fs)
        cls = collections.Counter()
        for f in anc:
            for k in slot2cls.get(f, ()):
                sc = split_class(k)
                cls[(category(k) if category(k) != 'other' else (sc[1] if sc and sc[1] in PROD else 'other'))] += 1
        owners[nm] = dict(call_funcs=sorted(hex(base + f) for f in fs), ancestors=len(anc), reached_from_class_cat=dict(cls),
                          in_ui_union=sorted(hex(base + f) for f in fs if f in ui_union), in_skia=sorted(hex(base + f) for f in fs if f in skia))

    # --- OS 境界クラス UIWindowWin32 (抽象 UIWindow の Win32 実装) と WndProc ---
    wnd = core.xrefs().get(('gdi32.dll', 'SetDIBitsToDevice'), [])
    wndproc = core.func_of(wnd[0][0])[0] if wnd else None
    regcls = [core.func_of(a)[0] for a, _ in core.xrefs().get(('user32.dll', 'RegisterClassW'), []) if core.func_of(a)]
    uiw32 = [(k, v) for k, l in vt.items() if k == '.?AVUIWindowWin32@@' for v in l]
    uiw = [(k, v) for k, l in vt.items() if k == '.?AVUIWindow@@' for v in l]
    w32_slots = {int(s, 16) - base for _, v in uiw32 for s in v['slots']}
    win_roots = set(w32_slots) | ({wndproc} if wndproc is not None else set()) | set(regcls)
    win_layer = reach(res, win_roots)
    inv_xr = collections.defaultdict(set)
    for (dll, nm), sites in core.xrefs().items():
        if dll in ('user32.dll', 'gdi32.dll'):
            for a, _ in sites:
                f = core.func_of(a)
                if f:
                    inv_xr[(dll, nm)].add(f[0])
    in_win = sorted(nm for (dll, nm), fs in inv_xr.items() if fs & win_layer)
    out_win = sorted(nm for (dll, nm), fs in inv_xr.items() if fs and not (fs & win_layer))
    gap_names = set(imp['gap'].keys())
    win = dict(uiwindow_slots=len(uiw[0][1]['slots']) if uiw else 0, uiwindowwin32_vtable_slots=max(len(v['slots']) for _, v in uiw32) if uiw32 else 0,
               uiwindowwin32_unique_funcs=len(w32_slots),
               uiwindowwin32_slot_bytes=size(w32_slots), wndproc=hex(base + wndproc) if wndproc is not None else None,
               wndproc_bytes=res[wndproc]['size'] if wndproc in res else (int(core.func_of(wnd[0][0])[1] - wndproc) if wnd else 0),
               register_class_funcs=[hex(base + f) for f in regcls], layer_funcs=len(win_layer), layer_bytes=size(win_layer),
               user32_gdi32_names_in_layer=len(in_win), user32_gdi32_names_outside_layer=out_win,
               gap_in_layer=sorted(gap_names & set(in_win)), gap_outside_layer=sorted(gap_names - set(in_win)))
    # --- Editor 層から Skia 型を引数/テンプレートに持つ非 Skia クラス (RTTI 名に Sk* を含む) の数 ---
    n_nonsk = sum(1 for k in vt if category(k) != 'skia')
    n_ref = sum(1 for k in vt if category(k) != 'skia' and re.search(r'[VU]Sk[A-Z]', k))
    n_ref_ui = sum(1 for k in vt if category(k) == 'other' and re.search(r'[VU]Sk[A-Z]', k))
    coupling = dict(non_skia_classes=n_nonsk, mention_sk_type=n_ref, other_cat_mention_sk_type=n_ref_ui)
    # --- SIMD / cpuid / 間接 call / IAT call (closure 内の命令統計; callgraph.py の記録を集計) ---
    def census(fs):
        c = collections.Counter()
        for f in fs:
            r = res.get(f)
            if not r:
                continue
            for kk, vv in r['simd'].items():
                c[kk] += vv
            c['indirect_calls'] += r['indir']
            c['iat_calls'] += r['iat']
            c['cpuid_funcs'] += 1 if r['cpuid'] else 0
        return dict(c)
    simd_tab = dict(skia=census(skia), ui_union=census(ui_union), ui_union_not_skia=census(ui_union - skia), dsp_union=census(set().union(*[dsp_reach[ns] for ns in effects])))
    out = dict(
        text_bytes=text_total, classes_with_vtable=len(vt), classes_by_cat=dict(cls_cnt),
        slot_funcs_by_cat={k: dict(funcs=len(v), bytes=size(v)) for k, v in slots_by_cat.items()},
        skia=dict(roots=len(skia_roots), closure_funcs=len(skia), closure_bytes=size(skia), pct_text=100.0 * size(skia) / text_total),
        ui=dict(effects=len(effects), union_funcs=len(ui_union), union_bytes=size(ui_union), pct_text=100.0 * size(ui_union) / text_total,
                union_in_skia_bytes=size(ui_union & skia), union_not_skia_bytes=size(ui_union - skia),
                infra_k8_funcs=len(ui_infra), infra_k8_bytes=size(ui_infra),
                infra_k8_not_skia_bytes=size(ui_infra - skia)),
        dsp_union_bytes=size(set().union(*[dsp_reach[ns] for ns in effects])),
        ui_over_dsp=size(ui_union) / max(1, size(set().union(*[dsp_reach[ns] for ns in effects]))),
        per_ns=per_ns, owners=owners, win=win, coupling=coupling, simd=simd_tab)
    json.dump(out, open(outp, 'w'), indent=1, ensure_ascii=False)

    print('classes with vtable: %d  by category: %s' % (len(vt), dict(cls_cnt)))
    print('Skia closure (direct edges, lower bound): %d funcs / %d B = %.1f%% of .text(%d B), roots=%d' % (
        len(skia), size(skia), out['skia']['pct_text'], text_total, len(skia_roots)))
    print('UI closure over %d effects: union %d funcs / %d B = %.1f%% of .text; of which Skia %d B, non-Skia %d B; infra(>=8 effects) %d funcs / %d B (non-Skia %d B)' % (
        len(effects), len(ui_union), size(ui_union), out['ui']['pct_text'], size(ui_union & skia), size(ui_union - skia),
        len(ui_infra), size(ui_infra), size(ui_infra - skia)))
    print('DSP union (same method): %d B' % out['dsp_union_bytes'])
    print('UIWindow vtable slots=%d, UIWindowWin32 vtable slots=%d (unique funcs %d, %d B), WndProc %s %d B, win layer %d funcs / %d B; coupling %s' % (
        win['uiwindow_slots'], win['uiwindowwin32_vtable_slots'], win['uiwindowwin32_unique_funcs'], win['uiwindowwin32_slot_bytes'], win['wndproc'], win['wndproc_bytes'], win['layer_funcs'], win['layer_bytes'], coupling))
    print('gap in layer: %s ; outside: %s' % (win['gap_in_layer'], win['gap_outside_layer']))
    print('simd:', json.dumps(simd_tab))
    print('UI/DSP ratio %.2f' % out['ui_over_dsp'])
    if gain:
        print('Gain UI: classes=%d closure %d funcs / %d B, own non-Skia non-infra %d funcs / %d B' % (
            gain['ui_classes'], gain['closure_funcs'], gain['closure_bytes'], gain['own_nonskia_funcs'], gain['own_nonskia_bytes']))
    for nm, o in owners.items():
        print('  %-24s funcs=%s ancestors=%d from=%s inUI=%d inSkia=%d' % (nm, ','.join(o['call_funcs']), o['ancestors'], o['reached_from_class_cat'], len(o['in_ui_union']), len(o['in_skia'])))

    # --- 検査 (不変条件) ---
    fails = []
    # C1: UI 閉包 (Editor 側) が DSP 閉包より大きい (同一手法・同一 42 効果)。比は out['ui_over_dsp'] に記録
    if not (out['ui']['union_bytes'] > out['dsp_union_bytes']):
        fails.append('C1: UI union <= DSP union')
    # C2: 別アルゴリズム検算 — 閉包バイト合計を .pdata の関数サイズ総和から独立に再計算
    import numpy as np
    sz = {int(b): int(e - b) for b, e in zip(core.fbeg, core.fend)}
    alt = sum(sz.get(f, 0) for f in ui_union)
    if alt != out['ui']['union_bytes']:
        # leaf 関数 (pdata 外) があるので、pdata にある関数のみの合計を res 側でも再計算して比較する
        in_pdata = [f for f in ui_union if f in sz]
        if sum(res[f]['size'] for f in in_pdata) != sum(sz[f] for f in in_pdata):
            fails.append('C2: res.size と .pdata サイズが pdata 内の関数で不一致')
    # C3: ネガコン — UI roots を空にすると閉包 0 になる / Gain の root を落とすと閉包が減る
    if reach(res, set()):
        fails.append('C3: 空 roots の到達集合が非空')
    g = ui_roots.get('gain')
    if g:
        full = size(reach(res, g))
        less = size(reach(res, set(sorted(g)[: max(1, len(g) // 2)])))
        if not less < full:
            fails.append('C3: roots を半分にしても Gain 閉包が減らない (%d >= %d)' % (less, full))
        print('  [nc] Gain UI roots %d -> half: closure %d B -> %d B' % (len(g), full, less))
    # C5: WndProc の関数ポインタ取得 (lea) が 1 箇所で、その関数が RegisterClassW を呼び、かつ UIWindowWin32 の vtable slot である
    lr = core.lea_refs(wndproc) if wndproc is not None else []
    lf = {core.func_of(a)[0] for a in lr if core.func_of(a)}
    c5 = len(lr) == 1 and lf == set(regcls) and lf <= w32_slots
    print('  [%s] C5: WndProc への lea 参照=%d 箇所 (所属 %s), RegisterClassW を呼ぶ関数=%s, うち UIWindowWin32 vtable slot=%s' % (
        'PASS' if c5 else 'FAIL', len(lr), [hex(base + f) for f in lf], [hex(base + f) for f in regcls], lf <= w32_slots))
    if not c5:
        fails.append('C5: WndProc 登録関数が UIWindowWin32 の slot でない')
    # C5n: ネガコン — 別関数 (UIWindowWin32 slot の先頭以外) を WndProc とみなすと lea 参照が 0 になる
    other = sorted(w32_slots - {wndproc})[0]
    lr2 = core.lea_refs(other)
    print('  [nc %s] 別の slot %s を WndProc とみなす → lea 参照 %d 箇所 (WndProc は 1 箇所)' % ('ok' if len(lr2) != 1 or {core.func_of(a)[0] for a in lr2} != set(regcls) else 'NG', hex(base + other), len(lr2)))
    if len(lr2) == 1 and {core.func_of(a)[0] for a in lr2} == set(regcls):
        fails.append('C5n: ネガコン失敗')
    # C4: ネガコン — 到達しない関数 (ランダムな孤立関数) は union に含まれない: DSP root は UI union に含まれない固有部分を持つ
    only_dsp = set().union(*[dsp_reach[ns] for ns in effects]) - ui_union
    if not only_dsp:
        fails.append('C4: DSP 固有関数が UI union に完全に含まれている (分離できていない)')
    print('  DSP-only funcs (not in UI union): %d' % len(only_dsp))
    for f in fails:
        print('FAIL', f)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:5]))
