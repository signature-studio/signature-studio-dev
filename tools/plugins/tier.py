#!/usr/bin/env python3
"""matrix_raw.json → Tier 分類 + PLUGIN_MATRIX.json / PLUGIN_MATRIX.md。

Tier 規則 (全て実測値ベース, 閾値は work/win_unique.json の分布の自然な切れ目):
  U      = win プラグイン所有モジュールの固有コード量 (framework 共通部を除外; vendor 同梱 lib 除外)
  ENG    = U のうち FP_DelphiPlug 以外のエンジン DLL (MSVC C++ 等) の固有コード
  T0 : U <  45 KB                    (単一 Delphi 本体モジュール, 純 DSP/UI の小規模)
  T1 : 45 KB <= U < 160 KB           (中規模 DSP / 状態機械; engine 無し〜小)
  T2 : 160 KB <= U < 700 KB          (engine 分離型 / 大型 DSP / スクリプト・エディタ系)
  T3 : U >= 700 KB, or 単一 engine >= 2 MB, or scope == big3p, or synth-big
効果工数 (推定; 人日, P0=framework+パイプライン確立後の 1 本あたり): T0 0.5 / T1 1.5 / T2 4 / T3 15。
"""
import json, os, sys, collections, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
WORK = os.path.join(ROOT, 'work')
raw = json.load(open(os.path.join(WORK, 'matrix_raw.json')))
plugins = raw['plugins']

EST = {'T0': 0.5, 'T1': 1.5, 'T2': 4, 'T3': 15}


def tier_of(p):
    U = p['metrics']['win_uniq_bytes']
    own = [m for m in p['win']['modules'] if not m['vendor']]
    eng_max = max([m['size'] for m in own if not m['lang'].startswith('Delphi(FP')] + [0])
    reasons = []
    if p['scope'] == 'big3p':
        return 'T3', 'scope=big3p (巨大/第三者エンジン)'
    if p['family'] == 'synth-big':
        return 'T3', 'synth-big (Sytrus/Harmor 級)'
    if eng_max >= 2_000_000:
        return 'T3', 'engine 単体 %.1f MB' % (eng_max / 1e6)
    if U >= 700_000:
        return 'T3', 'U=%d KB >= 700 KB' % (U // 1000)
    if U >= 160_000:
        return 'T2', 'U=%d KB (160-700 KB)' % (U // 1000)
    if U >= 45_000:
        return 'T1', 'U=%d KB (45-160 KB)' % (U // 1000)
    return 'T0', 'U=%.1f KB < 45 KB' % (U / 1000)


def deps_of(p):
    d = []
    own = [m for m in p['win']['modules'] if not m['vendor']]
    hints = set(h for m in own for h in m['hints'])
    if 'elastique' in hints:
        d.append('elastique(str)')
    if 'DirectWave' in hints:
        d.append('DirectWave(str)')
    if 'sqlite' in hints:
        d.append('sqlite')
    if 'OpenGL' in hints or 'ZGE' in hints:
        d.append('OpenGL/ZGE')
    if 'ws2' in hints:
        d.append('winsock')
    if 'FLEX' in hints:
        d.append('FLEX')
    vend = [m['file'] for m in p['win']['modules'] if m['vendor']]
    if vend:
        d.append('vendor:' + ','.join(vend))
    return d


WU = json.load(open(os.path.join(WORK, 'win_unique.json')))
_df = collections.Counter()
for _k, _v in WU.items():
    for _i in _v['uniq_imports']:
        _df[_i] += 1
_CAT = {
    'file_io': re.compile(r'(CreateFile|ReadFile|FindFirstFile|GetFileSize|SetFilePointer|CreateFileMapping|GetFileAttr|DeleteFile|CopyFile|MoveFile|CreateDirectory|GetTempPath|SHGetFolder|SHGetSpecial|SHFileOperation|GetOpenFileName|GetSaveFileName)', re.I),
    'network': re.compile(r'(wininet|ws2_32|wsock32|winhttp|urlmon|InternetOpen|HttpOpen|WSAStartup|URLDownload|iphlpapi)', re.I),
    'registry': re.compile(r'(Reg(Open|Query|Set|Close|Create|Enum))', re.I),
    'threads': re.compile(r'(CreateThread|_beginthread|WaitForSingle|WaitForMultiple|CreateEvent|CreateMutex|CreateSemaphore|timeSetEvent|SetTimer|CreateWaitableTimer|QueueUserWorkItem)', re.I),
    'dynload': re.compile(r'(LoadLibrary)', re.I),
    'gdi_direct': re.compile(r'(BeginPaint|CreateWindowEx|DrawText|BitBlt|StretchDIBits|StretchBlt|CreateDIBSection|SetPixel|LineTo)', re.I),
    'clipboard_dnd': re.compile(r'(Clipboard|DragQueryFile|RegisterDragDrop|DoDragDrop)', re.I),
    'audio_codec_midi': re.compile(r'(acm[A-Z]|waveOut|waveIn|midiOut|midiIn|mmio|PlaySound|DirectSound|mci)', re.I),
    'process': re.compile(r'(CreateProcess|ShellExecute|WinExec)', re.I),
}


def io_flags(p):
    """プラグイン固有コード (framework 共通を除く) が直接呼ぶ Win32 API の分類 (他プラグインで稀 = df<=30% のみ)。
    ホスト経由の I/O (Dispatcher ID) は含まない。"""
    fl = collections.Counter()
    for m in p['win']['modules']:
        if m['vendor']:
            continue
        u = WU.get('block%05d' % m['block'])
        if not u:
            continue
        for imp, n_ in u['uniq_imports'].items():
            if _df[imp] > 0.30 * len(WU):
                continue
            for c, rx in _CAT.items():
                if rx.search(imp):
                    fl[c] += n_
    return dict(fl)


CS = json.load(open(os.path.join(WORK, 'closure_summary.json'))) if os.path.exists(os.path.join(WORK, 'closure_summary.json')) else {}


BATCH = {}
_sp = os.path.join(WORK, 'batch', 'status.csv')
if os.path.exists(_sp):
    import csv
    for _r in csv.DictReader(open(_sp)):
        BATCH[_r['block']] = _r   # 同一 block は後勝ち (再実行)
VERIFIED = {'18983': 'kernels mix+peak bit-exact (1071/1071)'}


def fw_union(plist):
    hs = {}
    for p in plist:
        for m in p['win']['modules']:
            b = m['block']
            f = os.path.join(WORK, 'closure', 'block%05d.json' % b)
            if not (m['exports_CreatePlugInstance'] and os.path.exists(f)):
                continue
            hm = {x[0]: (x[2], x[1]) for x in json.load(open(os.path.join(WORK, 'winfuncs', 'block%05d.json' % b)))['funcs']}
            for v in json.load(open(f))['frontier']:
                r = int(v, 16) - 0x400000
                if r in hm:
                    hs[hm[r][0]] = hm[r][1]
    return len(hs), sum(hs.values())


for p in plugins:
    t, why = tier_of(p)
    p['tier'] = t
    p['tier_reason'] = why
    mb = [m['block'] for m in p['win']['modules'] if m['exports_CreatePlugInstance']]
    c = CS.get(str(mb[0])) if mb else None
    p['lift'] = ({'closure_funcs': c['unique_funcs'], 'closure_bytes': c['unique_bytes'],
                  'fw_frontier_funcs': c['framework_frontier_funcs'], 'fw_frontier_bytes': c['framework_frontier_bytes'],
                  'vcalls': c['indirect_vcall'], 'ptr_calls': c['indirect_ptr_or_vt0']} if c else None)
    if p['lift'] and mb and str(mb[0]) in BATCH:
        b_ = BATCH[str(mb[0])]
        p['lift']['batch'] = {'lift_rc': int(b_['lift_rc']), 'emcc_c_rc': int(b_['emcc_c_rc']), 'f80_funcs': int(b_['f80_funcs']),
                              'unimpl_helpers': int(b_['declares_unimpl'])}
        if str(mb[0]) in VERIFIED:
            p['lift']['verified'] = VERIFIED[str(mb[0])]
    p['est_days'] = EST[t]
    p['deps'] = deps_of(p)
    p['win_direct_api'] = io_flags(p)
    # lift 対象外/縮小
    p['dsp_lift'] = not (p['scope'] in ('gui', 'host') or p['family'] in ('gui-only', 'controller', 'vfx-midi', 'visual', 'hardware'))
    u = p['usage']
    w = 1 + 2 * u['demo_flp_hits'] + 0.1 * u['presets'] + (3 if u['render_test'] else 0)
    p['priority_score'] = round(w / EST[t], 2)

order = sorted(plugins, key=lambda p: (-p['priority_score'], p['tier'], p['name']))
for i, p in enumerate(order):
    p['priority_rank'] = i + 1

by_tier = collections.Counter(p['tier'] for p in plugins)
by_kind_tier = collections.Counter((p['kind'], p['tier']) for p in plugins)
by_scope = collections.Counter(p['scope'] for p in plugins)
by_family = collections.defaultdict(list)
for p in plugins:
    by_family[p['family']].append(p)

fwsurf = {}
for tt in ('T0', 'T1', 'T2', 'T3'):
    n_, b_ = fw_union([p for p in plugins if p['tier'] == tt and p['lift']])
    fwsurf[tt] = {'distinct_framework_callees': n_, 'bytes': b_}
fwsurf['T0+T1'] = dict(zip(('distinct_framework_callees', 'bytes'), fw_union([p for p in plugins if p['tier'] in ('T0', 'T1') and p['lift']])))
api_counts = collections.Counter()
for p in plugins:
    for c in p['win_direct_api']:
        api_counts[c] += 1
summary = {
    'framework_direct_callee_surface': fwsurf,
    'plugins_with_direct_win32_category': dict(api_counts),
    'n_plugins': len(plugins),
    'tiers': dict(by_tier),
    'tiers_by_kind': {'%s/%s' % k: v for k, v in sorted(by_kind_tier.items())},
    'scope': dict(by_scope),
    'est_days_total': sum(p['est_days'] for p in plugins),
    'est_days_by_tier': {t: EST[t] * by_tier[t] for t in EST},
    'families': {f: len(v) for f, v in sorted(by_family.items(), key=lambda kv: -len(kv[1]))},
    'n_flp_scanned': raw['n_flp_scanned'],
}
out = {'summary': summary, 'tier_rules': __doc__.strip(), 'plugins': plugins}
json.dump(out, open(os.path.join(ROOT, 'PLUGIN_MATRIX.json'), 'w'), indent=1, ensure_ascii=False)
print(json.dumps(summary, ensure_ascii=False, indent=1))


# ---------- Markdown ----------
def kb(x):
    return '-' if x is None else ('%d' % round(x / 1000))


def main_win(p):
    ms = [m for m in p['win']['modules'] if m['exports_CreatePlugInstance']]
    return ms[0] if ms else (p['win']['modules'][0] if p['win']['modules'] else None)


def main_mac(p):
    ms = [m for m in p['mac']['modules'] if m['exports_CreatePlugInstance']]
    return ms[0] if ms else p['mac']['modules'][0]


L = []
L.append('# PLUGIN_MATRIX — FL Studio 26.1.7 同梱 Fruity プラグイン 141 種 (Effects 90 + Generators 51) 実測マトリクス\n')
L.append('生成: `bash tools/plugins/build_all.sh` (inventory/*.py → lift/plugin_closure.py → tier.py)。数値は全て実測 (mac: pkg_extract, win: NSIS 展開 + 自作 NSIS ヘッダ解析で復元した名称対応)。\n')
L.append('## 0. サマリ\n')
L.append('| Tier | 個数 | うち Effects | うち Generators | 推定工数合計(人日,推定) |\n|---|---:|---:|---:|---:|')
for t in ('T0', 'T1', 'T2', 'T3'):
    L.append('| %s | %d | %d | %d | %s |' % (t, by_tier[t], by_kind_tier[('Effects', t)], by_kind_tier[('Generators', t)], EST[t] * by_tier[t]))
L.append('| 計 | %d | %d | %d | %s |\n' % (len(plugins), sum(v for (k, t), v in by_kind_tier.items() if k == 'Effects'),
                                           sum(v for (k, t), v in by_kind_tier.items() if k == 'Generators'), summary['est_days_total']))
L.append('scope 別: ' + ', '.join('%s=%d' % kv for kv in sorted(by_scope.items())) + ' (in=通常 / host=ホスト機能統合 / gui=音声処理なし / big3p=巨大第三者エンジン)\n')
L.append('## 1. Tier 規則\n')
L.append('```\n' + __doc__.strip().split('\n', 1)[1] + '\n```\n')
L.append('## 2. 全 141 プラグイン\n')
L.append('列: U=win 固有コード(KB, framework 共通 ~1.6MB を除く) / FP=その中の浮動小数演算命令数 / ENG=win エンジン DLL 合計 KB / mac=x86_64 slice KB (言語) / '
         'CL=Delphi 本体 (殻) の DSP エントリ(vtable override)から直接呼出で到達する固有コード閉包(KB; engine DLL は ENG 列) / LS=T0/T1 バッチ lift 状態 (V=差分試験で bit-exact 実証あり, ok=RetDec+pass鎖+`emcc -c` 通過, f80=x87 混入で未通過, NG=その他, -=未実施) / abi=Delphi 本体の FruityPlug 実装スロット(Eff=Eff_Render, Gen=Gen_Render, Voice=TriggerVoice) / params=Info.NumParams / '
         'pre=プリセット数 / demo=Data 内 .flp 82 本での出現数 / RT=Render test flp 有無\n')
L.append('| # | Kind | Plugin | Family | Tier | U | FP | ENG | CL | LS | win modules | mac main KB (lang) | abi | params | pre | demo | RT | scope |')
L.append('|--:|---|---|---|---|--:|--:|--:|--:|---|---|---|---|--:|--:|--:|---|---|')
for i, p in enumerate(sorted(plugins, key=lambda p: (p['kind'], p['name'].lower())), 1):
    wm = main_win(p)
    mm = main_mac(p)
    abi = ''
    npar = ''
    if wm and 'abi' in wm:
        im = wm['abi']['impl']
        abi = ('Eff ' if 'Eff_Render' in im else '') + ('Gen ' if 'Gen_Render' in im else '') + ('Voice ' if 'TriggerVoice' in im else '') + ('MIDIIn' if 'MIDIIn' in im else '')
        abi = abi.strip() or '-'
        if wm['abi'].get('info'):
            npar = wm['abi']['info']['nparams']
    wsum = '+'.join('%s%s' % (m['file'].replace('_x64.dll', '').replace('.dll', '')[:14], '(%dK)' % (m['size'] // 1000)) for m in p['win']['modules'][:3])
    ls = '-'
    if p['lift'] and 'batch' in p['lift']:
        bb = p['lift']['batch']
        ls = ('V' if 'verified' in p['lift'] else ('ok' if bb['emcc_c_rc'] == 0 and bb['lift_rc'] == 0 else ('f80' if bb['f80_funcs'] else 'NG')))
    L.append('| %d | %s | %s | %s | %s | %s | %d | %s | %s | %s | %s | %s (%s) | %s | %s | %d | %d | %s | %s |' % (
        i, p['kind'][0], p['name'], p['family'], p['tier'], kb(p['metrics']['win_uniq_bytes']), p['metrics']['win_uniq_fp_insns'],
        kb(p['metrics']['win_engine_bytes']), (kb(p['lift']['closure_bytes']) if p['lift'] else '-'), ls, wsum, kb(mm['x86_64_size']), mm['lang'].split(' ')[0], abi, npar,
        p['usage']['presets'], p['usage']['demo_flp_hits'], 'Y' if p['usage']['render_test'] else '', p['scope']))
L.append('\n## 3. Tier 別内訳\n')
for t in ('T0', 'T1', 'T2', 'T3'):
    L.append('### %s (%d)\n' % (t, by_tier[t]))
    L.append(', '.join('%s%s' % (p['name'], '' if p['kind'] == 'Effects' else '[G]') for p in sorted(plugins, key=lambda p: p['metrics']['win_uniq_bytes']) if p['tier'] == t) + '\n')
L.append('## 4. 優先度 (priority_score = (1 + 2*demo + 0.1*presets + 3*RT) / 推定工数) 上位 40\n')
L.append('| rank | Plugin | Tier | score | demo | pre | RT | family |\n|--:|---|---|--:|--:|--:|---|---|')
for p in order[:40]:
    L.append('| %d | %s | %s | %s | %d | %d | %s | %s |' % (p['priority_rank'], p['name'], p['tier'], p['priority_score'], p['usage']['demo_flp_hits'], p['usage']['presets'], 'Y' if p['usage']['render_test'] else '', p['family']))
L.append('\n## 5. ファミリ別 (lift バッチ単位)\n')
L.append('| family | n | 内訳 Tier | プラグイン |\n|---|--:|---|---|')
for f, v in sorted(by_family.items(), key=lambda kv: -len(kv[1])):
    tc = collections.Counter(p['tier'] for p in v)
    L.append('| %s | %d | %s | %s |' % (f, len(v), ' '.join('%s:%d' % kv for kv in sorted(tc.items())), ', '.join(p['name'] for p in v)))
open(os.path.join(ROOT, 'PLUGIN_MATRIX.md'), 'w').write('\n'.join(L) + '\n')
print('wrote PLUGIN_MATRIX.md', len('\n'.join(L).split('\n')), 'lines')
