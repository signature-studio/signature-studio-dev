#!/usr/bin/env python3
"""KH-7 (#59): HeartCore.core_64 の UI 面 (import / 動的ロード) を実測し、M7 GUI shim (tools/gui)・shimx との被覆を判定する。

usage: ui_imports.py <HeartCore.core_64> <out.json> [--selftest-only]
終了コード: 0 = 全検査 PASS / 1 = 評価の前提 (E*) 違反またはネガコン失敗 / 2 = 前提は成立・接続準備 (R*) に未達 (gap) が残る
"""
import sys, os, re, json, collections

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, HERE)

GUI_DLLS = ('user32.dll', 'gdi32.dll')           # tools/gui の担当 (shimx は対象外と明記: tools/shimx/README.md)
UI_ADJ_DLLS = ('shell32.dll', 'ole32.dll', 'comdlg32.dll', 'winmm.dll')      # UI 周辺 (DnD / ファイル選択 / タイマ)。shimx 担当
NET_LIC_DLLS = ('ws2_32.dll', 'crypt32.dll', 'wintrust.dll', 'setupapi.dll', 'bcrypt.dll', 'rpcrt4.dll', 'psapi.dll')  # 認証/通信 (D2/D3 の対象外領域)
GPU_DLLS = ('opengl32', 'glu32', 'd3d9', 'd3d10', 'd3d11', 'd3d12', 'dxgi', 'libEGL', 'libGLESv2', 'vulkan-1', 'd2d1', 'dcomp',
            'd3dcompiler_43', 'd3dcompiler_47', 'gdiplus')
GPU_API_RE = rb'(?:wglCreateContext|wglMakeCurrent|eglGetDisplay|eglCreateContext|D3D11CreateDevice|D3D12CreateDevice|CreateDXGIFactory\d?|vkCreateInstance)'


GUI_SRC = os.path.join(REPO, 'tools', 'gui', 'src')


def impl_names(gui_dir):
    """shim が定義する lift-ABI 名 (gen_api.py の impl_names と同じ規則 `^API Name(`)"""
    out = set()
    for f in ('gui_core.c', 'gui_core_ext.inc', 'gui_gdi.c'):
        for line in open(os.path.join(gui_dir, 'src', f), encoding='utf-8'):
            m = re.match(r'^API (\w+)\(', line)
            if m:
                out.add(m.group(1))
    return out


def stub_names(gui_dir):
    """tools/gui/IMPORTS.md で STUB (fail-fast) と記録された FL import 名"""
    out = set()
    for line in open(os.path.join(gui_dir, 'IMPORTS.md'), encoding='utf-8'):
        m = re.match(r'^\| (\w+) \| \w+ \| [^|]+\| \d+ \| STUB \|', line)
        if m:
            out.add(m.group(1))
    return out


def shimx_exports(shimx_dir):
    return {l.strip() for l in open(os.path.join(shimx_dir, 'exports.txt'), encoding='utf-8') if l.strip() and not l.startswith('#')}


def shimx_status(shimx_dir):
    import csv
    return {r['api']: r['status'] for r in csv.DictReader(open(os.path.join(shimx_dir, 'data', 'inventory.csv'), encoding='utf-8'))}


# ---------- 純関数 (ネガコンで入力を差し替えて検査する) ----------
def gpu_hits(imports, blob):
    """(imports 中の GPU 系 DLL/API, blob 中の GPU DLL 名 (ASCII + UTF-16LE) と GPU API 名 (ASCII) の文字列件数)"""
    dlls = {x.lower() + '.dll' for x in GPU_DLLS}
    imp = [(d, n) for d, n, _ in imports if d in dlls or re.fullmatch(GPU_API_RE.decode(), n)]
    s = len(re.findall(GPU_API_RE, blob))
    for x in GPU_DLLS:
        s += len(re.findall(re.escape((x + '.dll').encode()), blob, flags=re.I))
        s += len(re.findall(utf16_lit(x + '.dll'), blob, flags=re.I))
    return imp, s


def utf16_lit(s):
    return re.escape(s.encode('utf-16-le'))


def dwrite_hits(blob):
    a = len(re.findall(rb'DWriteCreateFactory|DWriteCoreCreateFactory', blob))
    d = len(re.findall(rb'dwrite(?:core)?\.dll', blob, flags=re.I)) + len(re.findall(utf16_lit('dwrite.dll'), blob, flags=re.I)) \
        + len(re.findall(utf16_lit('dwritecore.dll'), blob, flags=re.I))
    rtti = len(re.findall(rb'\.\?AV(?:SkFontMgr|SkFontStyleSet|SkTypeface)_?DirectWrite|\.\?AVDWriteFontTypeface', blob))
    return a, d, rtti


def dwrite_files(root):
    out = []
    for base in ('tools', 'src'):
        for dp, dn, fn in os.walk(os.path.join(root, base)):
            dn[:] = [d for d in dn if d not in ('work', 'node_modules', 'ui_eval', '__pycache__')]
            for f in fn:
                if f.endswith(('.c', '.h', '.cc', '.cpp', '.ts', '.js', '.mjs', '.py', '.inc')):
                    try:
                        if 'DWriteCreateFactory' in open(os.path.join(dp, f), encoding='utf-8', errors='ignore').read():
                            out.append(os.path.join(dp, f))
                    except OSError:
                        pass
    return out


def repo_has_dwrite(root):
    return bool(dwrite_files(root))


def coverage(imports, impl, stub, shx_exp, shx_stat):
    """HeartCore の import を担当別に判定。戻り値 dict。"""
    r = {'gui': {}, 'other': {}}
    for dll, nm, delay in imports:
        if dll in GUI_DLLS:
            st = 'IMPL' if nm in impl else ('STUB' if nm in stub else 'ABSENT')
            r['gui'].setdefault(dll, {}).setdefault(st, []).append(nm)
        else:
            st = shx_stat.get(nm)
            if nm in shx_exp:
                k = {'F': 'shimx-F', 'S': 'shimx-S'}.get(st, 'shimx-exported')
            else:
                k = 'MISSING'
            r['other'].setdefault(dll, {}).setdefault(k, []).append(nm)
    return r


def summarize_cov(cov):
    g = {dll: {k: len(v) for k, v in d.items()} for dll, d in cov['gui'].items()}
    o = collections.Counter()
    for dll, d in cov['other'].items():
        for k, v in d.items():
            o[k] += len(v)
    return g, dict(o)


def gui_gap(cov):
    return sorted((dll, nm, st) for dll, d in cov['gui'].items() for st, v in d.items() if st != 'IMPL' for nm in v)


# ---------- 検査 ----------
def run_checks(core, impl, stub, shx_exp, shx_stat):
    chk = []
    blob = bytes(core.data)
    imp_gpu, str_gpu = gpu_hits(core.imports, blob)
    chk.append(('E1', 'GPU 系 DLL/API を import していない (static+delay)', not imp_gpu, 'hits=%d %s' % (len(imp_gpu), imp_gpu)))
    chk.append(('E2', 'GPU 系 DLL 名/API 名の文字列が無い (ASCII+UTF-16, イメージ全域)', str_gpu == 0, 'hits=%d' % str_gpu))
    xr = core.xrefs()
    sd = xr.get(('gdi32.dll', 'SetDIBitsToDevice'), [])
    chk.append(('E3', 'SetDIBitsToDevice の静的 call site が 1 箇所で、同一関数内に BeginPaint/EndPaint がある',
                len(sd) == 1 and core.func_of(sd[0][0]) is not None and all(
                    any(core.func_of(a) == core.func_of(sd[0][0]) for a, _ in xr.get(('user32.dll', n), [])) for n in ('BeginPaint', 'EndPaint')),
                'sites=%s' % [hex(core.base + a) for a, _ in sd]))
    a, d, rtti = dwrite_hits(blob)
    chk.append(('E4', 'DirectWrite (動的ロード) 依存がある: DWriteCreateFactory 文字列 ≥1 かつ dwrite.dll 名 ≥1 かつ SkFontMgr_DirectWrite RTTI ≥1',
                a >= 1 and d >= 1 and rtti >= 1, 'DWriteCreateFactory=%d dwrite.dll=%d RTTI=%d' % (a, d, rtti)))
    cov = coverage(core.imports, impl, stub, shx_exp, shx_stat)
    gap = gui_gap(cov)
    # X1: 別アルゴリズム (ソース全文の単語境界検索) で IMPL 判定を検算。未実装判定の名前は 0 件、IMPL 判定の名前は全て ≥1 件ヒットすること
    srcs = ''.join(open(os.path.join(GUI_SRC, f), encoding='utf-8', errors='ignore').read() for f in ('gui_core.c', 'gui_core_ext.inc', 'gui_gdi.c'))
    gnames = {n for d, n, _ in core.imports if d in GUI_DLLS}
    gap_n = {n for _, n, _ in gap}
    bad_gap = sorted(n for n in gap_n if re.search(r'\b%s\b' % re.escape(n), srcs))
    bad_impl = sorted(n for n in gnames - gap_n if not re.search(r'\b%s\b' % re.escape(n), srcs))
    chk.append(('X1', '別算法検算: 未実装判定 %d 名はソースに出現せず、IMPL 判定 %d 名は全て出現する (単語境界検索)' % (len(gap_n), len(gnames - gap_n)),
                not bad_gap and not bad_impl, 'gap 側で出現=%s impl 側で不在=%s' % (bad_gap, bad_impl)))
    chk.append(('R1', 'HeartCore の gdi32 import が全て tools/gui で IMPL', not [x for x in gap if x[0] == 'gdi32.dll'],
                'gdi32 %s' % cov['gui'].get('gdi32.dll', {}).keys()))
    u = [x for x in gap if x[0] == 'user32.dll']
    chk.append(('R2', 'HeartCore の user32 import が全て tools/gui で IMPL', not u, '%d 件未実装: %s' % (len(u), ','.join('%s(%s)' % (n, s) for _, n, s in u))))
    miss = sorted('%s!%s' % (dll, nm) for dll, d in cov['other'].items() if dll in UI_ADJ_DLLS for nm in d.get('MISSING', []))
    chk.append(('R3', 'UI 周辺 DLL (shell32/ole32/comdlg32/winmm) の import が全て shimx exports に存在する', not miss,
                '%d 件 shimx に無い: %s' % (len(miss), ','.join(miss))))
    chk.append(('R4', 'Skia の DirectWrite 経路 (DWriteCreateFactory) を置換する shim が repo に存在する', repo_has_dwrite(REPO),
                'repo 内 DWriteCreateFactory 参照ファイル数=%d' % len(dwrite_files(REPO))))
    return chk, cov, gap


def negative_controls(core, impl, stub, shx_exp, shx_stat):
    """検査関数が壊れた入力で FAIL することを確認 (全て期待どおりなら True)"""
    nc = []
    # NC1: GPU import を 1 つ注入 → E1 が検出
    imp, _ = gpu_hits(core.imports + [('opengl32.dll', 'glClear', False), ('kernel32.dll', 'wglCreateContext', False)], b'')
    nc.append(('NC-E1 import に opengl32!glClear と kernel32!wglCreateContext を注入 → 検出数', len(imp), len(imp) == 2))
    # NC2: 文字列注入 (ASCII / UTF-16)
    _, s1 = gpu_hits([], b'xx\x00opengl32.dll\x00yy')
    _, s2 = gpu_hits([], b'xx' + 'D3D11.DLL'.encode('utf-16-le') + b'yy')
    _, s0 = gpu_hits([], b'xx\x00Direct3D\x00vulkan\x00metal\x00yy')
    nc.append(('NC-E2 ASCII "opengl32.dll" 注入 → 検出数', s1, s1 >= 1))
    nc.append(('NC-E2 UTF-16 "D3D11.DLL" 注入 → 検出数', s2, s2 >= 1))
    nc.append(('NC-E2 SkSL の backend 名 "vulkan/metal/direct3d" は DLL 名ではない → 偽陽性数', s0, s0 == 0))
    # NC3: DirectWrite 文字列が無ければ E4 は成立しない
    a, d, r = dwrite_hits(b'nothing here')
    nc.append(('NC-E4 DirectWrite 文字列なし → (api,dll,rtti)', (a, d, r), (a, d, r) == (0, 0, 0)))
    # NC4: shim の IMPL 集合から SetDIBitsToDevice を除く → gui_gap が検出
    cov = coverage(core.imports, impl - {'SetDIBitsToDevice'}, stub, shx_exp, shx_stat)
    g = [x for x in gui_gap(cov) if x[1] == 'SetDIBitsToDevice']
    nc.append(('NC-R2 IMPL から SetDIBitsToDevice を除外 → gap 検出', len(g), len(g) == 1))
    # NC5: IMPL 空 → user32+gdi32 の全名が gap
    cov = coverage(core.imports, set(), set(), shx_exp, shx_stat)
    n_all = sum(1 for dll, _, _ in core.imports if dll in GUI_DLLS)
    nc.append(('NC-R 空 IMPL → gap 件数 == user32+gdi32 import 数', (len(gui_gap(cov)), n_all), len(gui_gap(cov)) == n_all))
    # NC7: DWriteCreateFactory を含むファイルがあれば R4 の探索が検出する
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, 'tools', 'x'))
        open(os.path.join(td, 'tools', 'x', 'dw.c'), 'w').write('void f(){ DWriteCreateFactory(0,0,0); }')
        nc.append(('NC-R4 DWriteCreateFactory を含む .c を置いた模擬 repo → 検出', repo_has_dwrite(td), repo_has_dwrite(td)))
    # NC6: shimx exports 空 → 非 GUI 全名が MISSING
    cov = coverage(core.imports, impl, stub, set(), {})
    miss = sum(len(d.get('MISSING', [])) for d in cov['other'].values())
    n_o = sum(1 for dll, _, _ in core.imports if dll not in GUI_DLLS)
    nc.append(('NC-R3 shimx exports 空 → MISSING 件数 == 非 GUI import 数', (miss, n_o), miss == n_o))
    return nc


def main():
    core_path, out = sys.argv[1], sys.argv[2]
    from khlib import Core
    core = Core(core_path)
    gui_dir, shx_dir = os.path.join(REPO, 'tools', 'gui'), os.path.join(REPO, 'tools', 'shimx')
    impl, stub = impl_names(gui_dir), stub_names(gui_dir)
    shx_exp, shx_stat = shimx_exports(shx_dir), shimx_status(shx_dir)
    chk, cov, gap = run_checks(core, impl, stub, shx_exp, shx_stat)
    nc = negative_controls(core, impl, stub, shx_exp, shx_stat)

    per_dll = collections.Counter(d for d, _, _ in core.imports)
    delay = sum(1 for *_, dl in core.imports if dl)
    xr = core.xrefs()
    gsum, osum = summarize_cov(cov)
    other_missing = {dll: sorted(d['MISSING']) for dll, d in cov['other'].items() if 'MISSING' in d}
    # 未実装 user32/gdi32 名の call site と所属関数
    gap_sites = {}
    for dll, nm, st in gap:
        sites = xr.get((dll, nm), [])
        gap_sites[nm] = {'dll': dll, 'status': st, 'xrefs': len(sites),
                         'funcs': sorted({hex(core.base + core.func_of(a)[0]) for a, _ in sites if core.func_of(a)})}
    ui_apis = {}
    for nm in ('SetCursorPos', 'ShowCursor', 'SetCursor', 'GetCursorPos', 'SetCapture', 'ReleaseCapture', 'TrackMouseEvent', 'ToUnicode',
               'GetKeyboardState', 'MapVirtualKeyW', 'SetWindowsHookExW', 'SetClipboardData', 'RegisterDragDrop', 'DoDragDrop', 'SetTimer',
               'timeBeginPeriod', 'UpdateLayeredWindow', 'SetDIBitsToDevice', 'SetDIBits', 'CreateDIBSection', 'CreateCompatibleBitmap', 'DrawTextW'):
        for (dll, n), sites in xr.items():
            if n == nm:
                ui_apis[nm] = len(sites)
    res = {
        'ui_api_xrefs': ui_apis,
        'core': os.path.basename(core_path), 'sha_bytes': len(core.data),
        'imports_total': len(core.imports), 'delay_imports': delay, 'per_dll': dict(per_dll),
        'gui_impl_count': len(impl), 'gui_cov': gsum, 'other_cov': osum,
        'user32_gdi32_xref_total': sum(len(xr.get((d, n), [])) for d, n, _ in core.imports if d in GUI_DLLS),
        'gap': gap_sites, 'other_missing_by_dll': other_missing,
        'checks': [{'id': i, 'desc': d, 'pass': bool(p), 'detail': t} for i, d, p, t in chk],
        'negative_controls': [{'name': n, 'observed': str(o), 'ok': bool(k)} for n, o, k in nc],
    }
    json.dump(res, open(out, 'w'), indent=1, ensure_ascii=False)

    print('imports: total=%d (delay=%d) DLL=%d  user32=%d gdi32=%d' % (len(core.imports), delay, len(per_dll), per_dll['user32.dll'], per_dll['gdi32.dll']))
    print('GUI coverage (tools/gui impl=%d names):' % len(impl), json.dumps(gsum))
    print('non-GUI coverage (shimx):', json.dumps(osum))
    print('UI API 静的 xref (IAT 経由の call/jmp/mov 件数):', json.dumps(ui_apis))
    for i, d, p, t in chk:
        print('  [%s] %s: %s -- %s' % ('PASS' if p else 'FAIL', i, d, t))
    bad_nc = [x for x in nc if not x[2]]
    for n, o, k in nc:
        print('  [%s] %s = %s' % ('ok' if k else 'NC-FAIL', n, o))
    if bad_nc:
        print('NEGATIVE CONTROL FAILURE'); return 1
    if any(not p for i, _, p, _ in chk if i[0] in 'EX'):
        print('EVALUATION PREMISE VIOLATED'); return 1
    if any(not p for i, _, p, _ in chk if i.startswith('R')):
        print('READINESS GAPS REMAIN'); return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
