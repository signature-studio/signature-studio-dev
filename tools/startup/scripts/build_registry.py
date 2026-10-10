#!/usr/bin/env python3
"""build_registry.py — REGISTRY.csv 生成。
入力: work/reg_raw.csv (reg_inventory.py 出力), work/func_index.tsv
出力: REGISTRY.csv
行種別:
  engine  : FLEngine_x64.dll の TRegistry 呼出 (CallSiteStrings で抽出した literal)
  launcher: FL64.exe (Ghidra decompile + 逆アセンブル確認済)
  installer: NSIS スクリプト由来 (analysis/win64/REPORT.md §3/§6/§14 + block25162 strings。FLEngine は読まない)
  os      : Windows 標準キー (FLEngine が参照)
  mac     : OsxFL / libwinbridge (CFPreferences / reg.xml)
"""
import csv, collections, sys, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fidx import Idx
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, 'work')
APPKEY = r'Software\Image-Line\FL Studio 26'
FUNCNAMES = {
    '011a57c0': 'LoadSettings', '011af7e0': 'SaveSettings', '00eeac20': 'RenderOptions.save', '00eec630': 'RenderOptions.load',
    '010c7cd0': 'License.parse', '010c2010': 'License.check', '010d1ab0': 'License.inapp', '00f00d10': 'License.download',
    '008e6020': 'Reg.writeKey', '008e6150': 'Reg.readKey', '008e8990': 'FLData.read', '008e8b00': 'Token.read',
    '010d46f0': 'Token.touch', '010d4810': 'Token.exists', '00652830': 'Paths.engine', '00652e60': 'Paths.sharedData',
    '00652ff0': 'Paths.setSharedData', '011b3810': 'Splash.check', '011ef180': 'FirstTimeStuff',
    '011a36e0': 'LoadBrowserToolbars', '01105350': 'Migrate.find', '011054c0': 'Migrate.copy',
}
def hexdef(s):
    if s.startswith('#'):
        try: return str(int(s[1:], 16))
        except: return ''
    return ''
def main():
    ix = Idx(os.path.join(WORK, 'func_index.tsv'))
    raw = [r for r in csv.DictReader(open(os.path.join(WORK, 'reg_raw.csv'))) if r['op'] not in ('Create', 'SetRoot')]
    known_rel = {r['key'] for r in raw if r['key'] and not r['key'].startswith(('<', '#', 'Software', 'SOFTWARE', 'software', 'HKEY'))}
    agg = collections.OrderedDict()
    def put(plat, root, key, value, access, default, cat, src, conf, note=''):
        k = (plat, root, key, value)
        e = agg.setdefault(k, dict(platform=plat, hive=root, key=key, value=value, type='REG_SZ', default='', access=set(), category=cat, source=set(), confidence=conf, note=note))
        e['access'].update(access)
        if default != '' and not e['default']: e['default'] = default
        e['source'].add(src)
    for r in raw:
        op = r['op']; fn = r['func']
        root = 'HKLM' if r['root'].startswith('HKLM') else 'HKCU'
        key = r['key']; val = r['value']
        sec = False
        if key in ('', '#0') or key.startswith('<'):
            sec = True
            cands = [s for s in ix.by_addr[fn]['strs'] if s in known_rel or s.endswith('\\') or s.startswith('General')]
            key = '(section via wrapper in %s: %s)' % (FUNCNAMES.get(fn, 'FUN_' + fn), ' | '.join(dict.fromkeys(cands)) or '?')
            conf = 'low-key'
        elif key in known_rel:
            key = APPKEY + '\\' + key; conf = 'inferred-base'
        else:
            conf = 'literal'
        if val.startswith('<'): val = '(dynamic)'
        if op in ('OpenKey', 'OpenKeyRO', 'CreateKey'):
            put('both', root, key, '', {'open' if op != 'CreateKey' else 'create'}, '', 'key', FUNCNAMES.get(fn, 'FUN_' + fn), conf); continue
        if op == 'DeleteKey':
            put('both', root, key, '', {'delete-key'}, '', 'key', FUNCNAMES.get(fn, 'FUN_' + fn), conf); continue
        acc = {'R'} if op.startswith('Read') else {'W'} if op.startswith('Write') else {'exists'} if op == 'ValueExists' else {'delete'}
        dflt = ''
        if op in ('ReadInt', 'ReadBool'):
            dflt = hexdef(r['arg3'])
            if dflt == '' and r['arg3'] == '': dflt = '(unknown)'
        cat = 'license' if 'Registrations' in key else 'paths' if 'Shared\\Paths' in key else 'shared-settings' if 'Shared\\' in key else 'settings'
        put('both', root, key, val, acc, dflt, cat, FUNCNAMES.get(fn, 'FUN_' + fn), conf)
    # --- launcher (確定: FL64.exe 0x140005000 / 0x140005480) ---
    for rt in ('HKCU', 'HKLM'):
        put('win', rt, r'Software\Image-Line\Shared\Paths', 'FL Studio engine', {'R'}, '(none -> <exeDir>\\FLEngine_x64.dll)', 'paths', 'FL64.exe:140005000', 'verified', '値=インストール先内のファイルパス (親dir=SetCurrentDirectoryW, 親+FLEngine_x64.dll=engine)。HKLM は KEY_WOW64_32KEY(0x20219)')
        put('win', rt, r'Software\Image-Line\Shared\Paths', 'Shared DLLs', {'R'}, '(none -> <exeDir>\\Shared\\)', 'paths', 'FL64.exe:140005480', 'verified', 'ILTools_x64.dll の所在確認後 SetCurrentDirectoryW')
    # --- engine 追加 (decompile 確認) ---
    put('win', 'HKCU', r'Software\Image-Line\Shared\Paths', 'Shared data', {'R', 'W'}, '(none -> Documents\\Image-Line\\)', 'paths', 'engine:00652e60/00652ff0', 'verified', 'ExpandEnvironmentStringsW 後に使用。無ければ SHGetFolderPath(CSIDL_PERSONAL=5 / APPDATA=0x1a)+\\Image-Line\\')
    # --- OS keys ---
    OS = [
        ('HKLM', r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'CurrentMajorVersionNumber', 'R', 'FUN_00454090/0044a9a0/007a62d0 (decompile 確認)'),
        ('HKLM', r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'CurrentMinorVersionNumber', 'R', 'FUN_00454090/0044a9a0/007a62d0 (decompile 確認)'),
        ('HKLM', r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'CurrentVersion', 'R', 'FUN_00454090/0044a9a0/007a62d0 (decompile 確認)'),
        ('HKLM', r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'CurrentBuild', 'R', 'FUN_00454090/0044a9a0/007a62d0 (decompile 確認)'),
        ('HKLM', r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'CurrentBuildNumber', 'R', 'FUN_00454090/0044a9a0/007a62d0 (decompile 確認)'),
        ('HKLM', r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'DisplayVersion', 'R', 'FUN_00454090/0044a9a0/007a62d0 (decompile 確認)'),
        ('HKLM', r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'ReleaseId', 'R', 'FUN_00454090/0044a9a0/007a62d0 (decompile 確認)'),
        ('HKLM', r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'ProductName', 'R', 'FUN_00454090/0044a9a0/007a62d0 (decompile 確認)'),
        ('HKLM', r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\FontSubstitutes', 'MS Shell Dlg 2', 'R', 'FUN_005d1ac0'),
        ('HKLM', r'Software\Microsoft\Windows NT\CurrentVersion\Fonts', '(enumerate)', 'R', 'FUN_00664fd0'),
        ('HKLM', r'SOFTWARE\Microsoft\Cryptography', 'MachineGuid', 'R', 'inline license/HWID code x25 (e.g. FUN_00f2dbb0, FUN_010c7cd0)'),
        ('HKCU', r'Software\Microsoft\Windows\CurrentVersion\Internet settings', 'ProxyEnable/ProxyServer (WinInet 設定)', 'R', 'FUN_009d65d0'),
        ('HKCU', r'Software\Classes\http\shell\open\command', '(default) 既定ブラウザ', 'R', 'FUN_007a6c80'),
        ('HKCU', r'SOFTWARE\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice', 'ProgId', 'R', 'FUN_007a6c80'),
        ('HKLM', r'Software\Microsoft\Windows\CurrentVersion\App Paths\Cubase.exe', '(default)/Path (VST 検索補助)', 'R', 'FUN_00acfea0'),
        ('HKLM', r'Software\VST', 'VSTPluginsPath', 'R', 'FUN_00acfea0'),
        ('HKLM', r'software\asio', r'(enumerate drivers) + CLSID\<guid>', 'R', 'FUN_00c526f0/00c522f0'),
        ('HKLM', r'System\CurrentControlSet\Control\Keyboard Layouts\%.8x', 'Layout Text', 'R', 'FUN_00865c90'),
        ('HKCU', r'Software\Classes\.flp / .fst / .fsc / flstudio', '(default)/shell\\open\\command (関連付け書込)', 'R/W', 'FUN_0081b490/0081b710/0081b910'),
        ('HKCU', r'Software\Wow6432Node', '(redirect probe)', 'R', 'FUN_007a6bc0'),
        ('HKLM', r'Software\Borland\Delphi\Locales; Software\Borland\Locales; Software\CodeGear\Locales; Software\Embarcadero\Locales', '(locale override; Delphi RTL)', 'R', 'FUN_00419990'),
        ('HKCU/HKLM', r'Software\Image-Line\FL Studio <n-1..> (旧版)', '(全値コピー: 設定移行)', 'R', 'FUN_01105350/011054c0 (CreateFruityInstance -> 0x13752f0)'),
        ('HKCU', r'Software\Image-Line\FL Plugin Scanner', '(scanner state)', 'R/W', 'FUN_0090dbf0'),
        ('HKCU', r'Software\Image-Line\Shared\Plugin search paths', '(per-path values)', 'R/W', 'FUN_0090d9a0'),
        ('HKCU', r'Software\Image-Line\Shared\Plugin list window', '(window state)', 'R/W', 'FUN_010e0010'),
        ('HKCU', r'Software\Image-Line\Shared\Browser\*', '(browser state)', 'R/W', 'FUN_00a48ff0/00a4a910'),
        ('HKCU', r'Software\Image-Line\FL Studio 26\Favorite dirs', '(favorite folders)', 'R/W', 'FUN_00dab3b0'),
    ]
    for rt, k, v, a, s in OS:
        put('win', rt, k, v, set(a.split('/')), '', 'os-or-misc', s, 'literal(key) / value-name=inferred' if 'Image-Line' in k else 'literal', 'FLEngine が参照 (OS 側キー)' if 'Image-Line' not in k else '')
    # --- installer ---
    INST = [
        ('HKLM', r'Software\Image-Line\Shared\Paths', 'FL Studio engine; Shared DLLs; Shared data (他 path 値)', 'インストール先を記録'),
        ('HKCU', r'Software\Image-Line\Registrations\FL Studio', '(serial/regcode; 旧形式)', 'REPORT §6.2'),
        ('HKLM', r'Software\Image-Line\Shared\General', 'Persist', 'REPORT §14'),
        ('HKLM', r'Software\SoftVoice\ImageLine', '(SAPI/SoftVoice 登録)', 'REPORT §3'),
        ('HKLM', r'Software\Classes\FL64.flp / .fst / .fsc / FL64.exe\DefaultIcon', '(default)', 'ファイル関連付け'),
        ('HKLM', r'Software\Classes\flstudio', 'URL Protocol', 'flstudio:// ハンドラ'),
        ('HKLM', r'Software\Microsoft\Windows\CurrentVersion\App Paths\FL64.exe', '(default)', ''),
        ('HKLM', r'Software\Microsoft\Windows\CurrentVersion\Uninstall\<ProductGUID>', 'DisplayName/HelpLink=http://www.image-line.com', ''),
        ('HKLM', r'Software\Image-Line\Capabilities\FL64 / FL32', 'ApplicationName/FileAssociations', 'block25162 strings'),
        ('HKCU', r'Software\Classes\.flp\OpenWithProgids', '', ''),
    ]
    for rt, k, v, n in INST:
        put('win', rt, k, v, {'installer-W'}, '', 'installer', 'NSIS script (REPORT §3/§6/§14)', 'report-based', n)
    # --- mac ---
    MAC = [
        ('CFPrefs', 'com.image-line.shared', 'FL Studio engine', 'OsxFL -setenginepath が書込。libwinbridge 探索のフォールバック', 'verified'),
        ('file', '~/Library/Preferences/Image-Line/reg.xml', '(XML: Key%d ノード; TXmlRegistry)', 'libwinbridge の Reg* 全体の実体 (HKCU 相当)。NSLibraryDirectory(5)/user domain + /Preferences/Image-Line/reg.xml', 'verified'),
        ('regcall', 'HKCU(2)\\Software\\Image-Line\\Shared\\Paths', 'FL Studio engine', 'OsxFL が RegWriteStringValue(2,...) で <bundle>/Contents/Libs/FLEngine_x64.dylib を書込', 'verified'),
        ('plist', 'Info.plist CFBundleURLTypes', 'flstudio:// + com.googleusercontent.apps.881717225491-… (OAuth)', 'URL scheme', 'verified'),
        ('plist', 'Info.plist CFBundleDocumentTypes', '.flp / .fst', 'ドキュメント関連付け', 'verified'),
        ('dir', '~/Library/Caches/com.image-line.flstudio/WebKit; ~/Library/HTTPStorages/com.image-line.flstudio; ~/Library/WebKit/com.image-line.flstudio/WebsiteData', '(WKWebView data)', 'WebView 用', 'strings'),
    ]
    for t, k, v, n, c in MAC:
        put('mac', t, k, v, {'R/W'}, '', 'mac-storage', 'OsxFL/libwinbridge', c, n)
    cols = ['platform', 'hive', 'key', 'value', 'type', 'default', 'access', 'category', 'source', 'confidence', 'note']
    out = os.path.join(ROOT, 'REGISTRY.csv')
    rows = sorted(agg.values(), key=lambda e: (e['platform'], e['category'], e['key'], e['value']))
    with open(out, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(cols)
        for e in rows:
            e['access'] = '/'.join(sorted(e['access'])); e['source'] = ';'.join(sorted(e['source']))[:160]
            w.writerow([e[c] for c in cols])
    winrows = [e for e in rows if e['platform'] in ('both', 'win')]
    keyset = {(e['hive'].split('/')[0], e['key'].lower()) for e in winrows if not e['key'].startswith('(section')}
    secvals = {e['value'] for e in winrows if e['key'].startswith('(section') and e['value']}
    litvals = {(e['key'].lower(), e['value']) for e in winrows if not e['key'].startswith('(section') and e['value']}
    engvals = {e['value'] for e in winrows if e['platform'] == 'both' and e['value']}
    print('csv rows', len(rows))
    print('win distinct keys (literal/inferred, section 除く):', len(keyset))
    print('win value rows with literal key:', len(litvals), '| section-wrapper value names:', len(secvals))
    print('engine distinct value names (全体):', len(engvals))
    print('mac storage rows:', sum(1 for e in rows if e['platform'] == 'mac'))
    print('by category', dict(collections.Counter(e['category'] for e in rows)))
main()
