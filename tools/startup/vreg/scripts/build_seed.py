#!/usr/bin/env python3
"""build_seed.py — REGISTRY.csv (読取専用) + 手書き仕様 から vreg の seed / キー目録を生成する。
出力: ../data/seed.json (全値名の初期値 + confidence), ../data/keys.json (REGISTRY.csv の win キー → 具象キー展開)
usage: python3 build_seed.py   (入力: ../../REGISTRY.csv, ../../data/vreg_seed.json)

方針 (REPORT 参照):
  * apply=true  : 起動時に仮想レジストリへ書く値。コード由来の既定値 (ReadInt/ReadBool 既定) か、ゲート通過に必要な値のみ。
  * apply=false : カタログのみ (値は記録するが書かない = エンジン内蔵の既定に任せる)。キー不明 (wrapper 経由の section) の値名はここ。
  * confidence  : 確定 = キー/値名がバイナリのリテラルで、値もコード既定 or 実在 OS 値 / 推定 = キー・値のどちらかが推定・選択値
  * OVERRIDES   : キー不明 (wrapper 経由 section, low-key) エントリの実キー上書き表。本ファイルが正本
                  (CAB-213 で tools/startup/keyfix/apply_keys.py から移設。keyfix 側の表は履歴で正本ではない)。
                  根拠は tools/startup/keyfix/REPORT.md §1 と各項目の basis
"""
import csv, json, os, re, collections, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
OUT = os.path.normpath(os.path.join(HERE, '..', 'data'))
LIT = {'literal', 'verified', 'literal(key) / value-name=inferred'}
SEED_VERSION = 1

INSTALL = 'C:\\Program Files\\Image-Line\\FL Studio 2026\\'
FLK = 'Software\\Image-Line\\FL Studio 26'
REGS = 'Software\\Image-Line\\Registrations'
CV = 'SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion'

rows = list(csv.DictReader(open(os.path.join(ROOT, 'REGISTRY.csv'), encoding='utf-8')))
win = [x for x in rows if x['platform'] in ('both', 'win')]
old = json.load(open(os.path.join(ROOT, 'data', 'vreg_seed.json'), encoding='utf-8'))


def is_name(v):
    return bool(v) and not (v.startswith('(') or v.startswith('#') or '/' in v or ';' in v)


entries = {}      # (hive, keylower, namelower) -> entry


def put(e):
    k = (e['hive'], (e['key'] or '').lower(), e['name'].lower())
    prev = entries.get(k)
    if prev and prev.get('_core'):          # 手書き (core) を CSV 由来で上書きしない
        return
    entries[k] = e


def E(hive, key, name, value, *, type='REG_SZ', apply=True, group, kc, vc, basis, pinned=False, rows_=None, core=True):
    put({'hive': hive, 'key': key, 'name': name, 'type': type, 'value': value, 'apply': apply, 'group': group,
         'confidence': '確定' if (kc == '確定' and vc == '確定') else '推定', 'key_conf': kc, 'value_conf': vc,
         'basis': basis, 'pinned': pinned, 'source': rows_ or [], '_core': core})


# ---------------- 手書き仕様 (core) ----------------
for hive in ('HKCU', 'HKLM'):
    E(hive, 'Software\\Image-Line\\Shared\\Paths', 'FL Studio engine', INSTALL + 'FLEngine_x64.dll', group='paths', kc='確定', vc='推定',
      basis='G02: 値=エンジン絶対パス (verified)。配置先は VFS 設計 (stub_plan §4) 依存のため値は推定')
    E(hive, 'Software\\Image-Line\\Shared\\Paths', 'Shared DLLs', INSTALL + 'Shared\\', group='paths', kc='確定', vc='推定',
      basis='REGISTRY.csv verified (未設定時 <exeDir>\\Shared\\)。VFS 依存')
E('HKCU', 'Software\\Image-Line\\Shared\\Paths', 'Shared data', 'C:\\Users\\webstudio\\Documents\\Image-Line\\', group='paths', kc='確定', vc='推定',
  basis='REGISTRY.csv verified (未設定時 Documents\\Image-Line\\)。G07: VFS が常に書込可')
E('HKCU', 'Software\\Image-Line\\Shared\\Paths', 'FL Studio', INSTALL, apply=False, group='paths', kc='確定', vc='推定',
  basis='エンジンが書込 (W literal)。seed しない')

# FL Cloud / 外部通信対象外 + 起動ゲート G08 (決定値)
for name, v, why in (('Browser FL CLOUD displayed', '0', 'G13: 起動時の FL CLOUD タブ preload 無効'),
                     ('Disable FL CLOUD search', '1', '外部通信対象外 (SUBAGENT_RULES)'),
                     ('CrashLoadingStartupProject', '0', 'G08: クラッシュ復帰ダイアログ回避')):
    E('HKCU', FLK + '\\General', name, v, group='gate', kc='推定', vc='推定', basis=why + ' (決定値; キーは General と推定)')

# OS 情報 (G16)。実在 Windows 10 22H2 の値
for name, v, t in (('ProductName', 'Windows 10 Pro', 'REG_SZ'), ('CurrentVersion', '6.3', 'REG_SZ'), ('CurrentBuild', '19045', 'REG_SZ'),
                   ('CurrentBuildNumber', '19045', 'REG_SZ'), ('CurrentMajorVersionNumber', 10, 'REG_DWORD'),
                   ('CurrentMinorVersionNumber', 0, 'REG_DWORD'), ('DisplayVersion', '22H2', 'REG_SZ'), ('ReleaseId', '2009', 'REG_SZ')):
    E('HKLM', CV, name, v, type=t, group='os', kc='確定', vc='確定', basis='G16 / REGISTRY.csv literal。Win10 22H2 の実在値')
E('HKLM', 'SOFTWARE\\Microsoft\\Cryptography', 'MachineGuid', '${MACHINE_GUID}', group='os', kc='確定', vc='推定',
  basis='プロファイル毎に 1 回生成 (UUIDv4)。ライセンス検証がこの値に依存するかは未確認 (G04)')
E('HKLM', CV + '\\FontSubstitutes', 'MS Shell Dlg 2', 'Tahoma', group='os', kc='確定', vc='確定', basis='REGISTRY.csv literal / Win10 既定値')
E('HKCU', 'Software\\Microsoft\\Windows\\CurrentVersion\\Internet settings', 'ProxyEnable', 0, type='REG_DWORD', group='os',
  kc='確定', vc='推定', basis='WinInet 常時オフライン方針 (G11)。Windows 実体は DWORD。FL 側の読み方 (DWORD/文字列) は未確認')
E('HKCU', 'Software\\Microsoft\\Windows\\CurrentVersion\\Internet settings', 'ProxyServer', '', apply=False, group='os',
  kc='確定', vc='推定', basis='未設定=プロキシ無し')
E('HKLM', 'Software\\VST', 'VSTPluginsPath', 'C:\\Program Files\\Common Files\\VST2', apply=False, group='os', kc='確定', vc='推定',
  basis='VST 検索補助。プラグインは事前登録モジュール表 (hostbridge) のため seed しない')
E('HKLM', 'System\\CurrentControlSet\\Control\\Keyboard Layouts\\00000409', 'Layout Text', 'US', group='os', kc='推定', vc='確定',
  basis='キーは %.8x 書式 (literal)、値名は wrapper 経由 (low-key)。US 配列の Windows 実在値')
E('HKLM', 'System\\CurrentControlSet\\Control\\Keyboard Layouts\\00000409', 'Layout File', 'KBDUS.DLL', group='os', kc='推定', vc='確定',
  basis='同上')

# ---- ライセンス (ユーザ方針: 無条件通過 / G04)。pinned=true は永続化済みの値より seed が常に優先 ----
LIC_NOTE = ('ユーザ承認「全てのライセンス機構は無力化。アクティベーションは無条件通過」。値はプレースホルダ: 存在検査 '
            '(FUN_008e6150: Registrations 配下の "FL Studio *" サブキーの ILRegKey が非空) は満たすが、'
            '0x10c7cd0 の検証を通るかは未確認 → CAB-106 で観察。cracked 資源は external モードで .reg 投入')
PLACE = 'WEBSTUDIO-ACTIVATED-PLACEHOLDER'
for hive in ('HKCU', 'HKLM'):
    E(hive, REGS + '\\FL Studio 26.1', 'ILRegKey', PLACE, group='license', kc='確定', vc='推定', pinned=True, basis=LIC_NOTE)
    E(hive, REGS + '\\FL Data', 'ILRegKey', PLACE, group='license', kc='確定', vc='推定', pinned=True, basis=LIC_NOTE)
for name, v in (('FL Studio user name', 'WebStudio User'), ('FL Studio webpass', 'webstudio'), ('FLS Info', 'webstudio'),
                ('FL Studio license plate', 'WebStudio')):
    E('HKCU', REGS, name, v, group='license', kc='確定', vc='推定', pinned=True,
      basis='License.parse の読出値 (literal)。値の書式は未解読 → 推定。' + LIC_NOTE[:60])
# Token (FL Cloud 認証) は外部通信対象外のため seed しない
E('HKCU', REGS + '\\Token', 'Key', '', apply=False, group='license', kc='確定', vc='推定', basis='FL Cloud トークン: 外部認証対象外のため seed しない')
E('HKCU', REGS + '\\Token', 'Date', '', apply=False, group='license', kc='確定', vc='推定', basis='同上 (存在検査のみ)')
E('HKLM', REGS + '\\Token', 'Key', '', apply=False, group='license', kc='確定', vc='推定', basis='同上')

# ---------------- REGISTRY.csv 由来 ----------------
def norm_default(d):
    if d in ('', '(unknown)') or d.startswith('(none'):
        return None
    return d


n_csv = 0
for x in win:
    nm = x['value']
    if not is_name(nm):
        continue
    d = norm_default(x['default'])
    low = x['confidence'] == 'low-key' or x['key'].startswith('(section')
    key = None if low else x['key'].rstrip('\\')
    if key and ('<' in key or ' / ' in key or ';' in key or '*' in key or '%' in key):
        key = None   # 展開キーは keys.json 側で扱う。値は catalog に残す
    if x['hive'] not in ('HKCU', 'HKLM'):
        continue
    kconf = '確定' if x['confidence'] in LIT else '推定'
    apply = bool(key and d is not None and x['access'] not in ('installer-W',))
    put({'hive': x['hive'], 'key': key, 'name': nm, 'type': 'REG_SZ', 'value': d if d is not None else '', 'apply': apply,
         'group': ('shared' if key and 'Shared' in key else 'settings') if key else 'catalog',
         'confidence': '確定' if (kconf == '確定' and d is not None) else '推定', 'key_conf': kconf if key else '推定',
         'value_conf': '確定' if d is not None else '推定',
         'basis': (('コード既定値 ReadInt/ReadBool=%s' % d) if d is not None else '既定値不明 (エンジン内蔵)') +
                  ('' if key else '; キー不明 (wrapper の section 経由, low-key) → 書かない'),
         'pinned': False, 'source': [x['source']], '_core': False})
    n_csv += 1

# TrialEdition は FL Studio 26\General の推定キー。ライセンス状態に関連する可能性 (ReadInt 既定 2; 0x11bddf0)
tk = ('HKCU', (FLK + '\\General').lower(), 'trialedition')
if tk in entries:
    entries[tk]['basis'] += '; ライセンス/エディション関連の可能性 (CAB-106 の観察対象)'

# ---------------- key 上書き表 (CAB-213: tools/startup/keyfix/apply_keys.py から移設) ----------------
PVS = FLK + '\\Plugin version specific'
PVS_WIN = PVS + '\\Windows'
PVS_GEN = PVS + '\\General'
PVS_DEV = PVS + '\\Devices'
RENDER = FLK + '\\General\\Render'
MIDIFORM = FLK + '\\General\\MIDIForm'

B_BASE = ('基底キー=Software\\Image-Line\\FL Studio 26: 起動時 0x1104fe0 が共有 TRegistry に OpenKey'
          '(実測 capstone)。0x11c71b0/0x11cde20 は同一関数内で GetKeyHandle(FL26)→相対 General ops の組で実証')

# (source, name) -> dict(key=, key_conf=, apply=None(変更無し)|bool, basis=)
# key_conf: '確定' = 関数内リテラル / boot 計算Cell で完全解決。'推定' = 静的前尾は確定だが動的尾部あり
Bboot = B_BASE + '。boot 0x11be0a0 が "Plugin version specific\\" (+Windows/Devices/<WxHxBPS>) を計算'


def b(tail):
    return '%s。key=%s' % (B_BASE, tail)


OVERRIDES = {}

# --- RenderOptions.save (0xeeac20) / load (0xeec630): 'General\'+'Render (master)'/'Render' ---
for n in ('Channel mode', 'Disable max poly', 'Dither', 'Enable insert effects', 'Enable master effects',
          'Enable mastering', 'Enable mastering reference A', 'Enable mastering reference B', 'Export Flac',
          'Export M4a', 'Export MP3', 'Export OGG', 'Export WAV', 'FLAC bit depth',
          'FLAC compression level', 'HQ for all plugins', 'Interpolation', 'MP3 bit rate',
          'Mastering loudness', 'Mastering loudness preset', 'Mastering reference A', 'Mastering reference B',
          'Mastering tuning A', 'Mastering tuning B', 'Mode', 'OGG bit rate', 'Save loop markers',
          'Save note markers', 'Save playlist markers', 'Save tempo', 'Split mixer tracks', 'Tail',
          'Trim PDC silence', 'WAV bit depth'):
    OVERRIDES[('RenderOptions.save', n)] = {
        'key': RENDER, 'key_conf': '確定',
        'basis': 'RenderOptions.save 0xeeac20 / load 0xeec630 が key="General\\Render" を UStrAsg+UStrCat3 で構成 '
                 '(0xeeb4a8="Render (master)" / 0xeeb4b0="Render" の 2 分岐, load は "Render" 固定)。' + b('General\\Render')}

# --- FUN_01175480: 絶対リテラル 'Software\Image-Line\FL Studio 26\General' + '\MIDIForm' ---
for n in ('MultithreadGenBox', 'MultithreadFXBox'):
    OVERRIDES[('FUN_01175480', n)] = {
        'key': MIDIFORM, 'key_conf': '確定',
        'basis': 'FUN_01175480 が新規 TRegistry Create 後 key="Software\\Image-Line\\FL Studio 26\\General"+'
                 '"\\MIDIForm" (0x11754d8/0x11754ec literal) で WriteBool(1)。' + b('FL26\\General\\MIDIForm')}

# --- LoadSettings (0x11a57c0) の動的キー群: 'General\'+[MIDIForm+0x10] ---
for n, dflt in (('SmootherUpdateBox', '1'), ('MTC offset', '0'), ('OfflineHelpBox', '0')):
    OVERRIDES[('LoadSettings', n)] = {
        'key': MIDIFORM, 'key_conf': '確定', 'apply': True,
        'basis': 'LoadSettings 0x11a6d71 が key="General\\"+[0x15e13b8(MIDIForm)+0x10] を構成。'
                 'MIDIForm+0x10=TComponent.Name="MIDIForm" (FUN_01175480 の literal と一致)。'
                 '値=ReadInt/ReadBool 既定 %s (REGISTRY.csv) → seed で既定反映。%s' % (dflt, b('General\\MIDIForm'))}

# --- FUN_0119f7e0 'Alternate undo mode': GetKeyHandle('Software\Image-Line\Shared\General') + key=nil ---
OVERRIDES[('FUN_0119f7e0', 'Alternate undo mode')] = {
    'key': 'Software\\Image-Line\\Shared\\General', 'key_conf': '確定',
    'basis': 'FUN_0119f7e0 0x119f8ab が GetKeyHandle("Software\\Image-Line\\Shared\\General", cancreate=1) の直後 '
             'に WriteBool/ReadBool(key=nil) → CurrentKey=Shared\\General (key=nil は CurrentKey を指す: '
             'IsRelative 0x5aeec0 実測)。'}

# --- Paths.sharedData 'Shared data': core seed と同一キー (重複カタログ) ---
OVERRIDES[('Paths.sharedData', 'Shared data')] = {
    'key': 'Software\\Image-Line\\Shared\\Paths', 'key_conf': '確定',
    'basis': 'FUN_00652e60 (Paths.sharedData) は core seed の paths group と同一キー (HKCU/HKLM Shared\\Paths)。'
             '本 entry は CSV 由来のカタログ重複 (apply は core 側)。'}

# --- Reg.readKey 'ILRegKey' ×2: Registrations (version サブキーは pinned license と同一) ---
for hive in ('HKCU', 'HKLM'):
    OVERRIDES[('Reg.readKey:%s' % hive, 'ILRegKey')] = {
        'key': 'Software\\Image-Line\\Registrations\\FL Studio 26.1', 'key_conf': '確定',
        'basis': 'Reg.readKey 0x8e6150 の wrapper literal "Software\\Image-Line\\Registrations\\" '
                 '(REGISTRY.csv low-key 行記載) + version サブキー "FL Studio 26.1" は FUN_01183130 系 literal。'
                 'core seed の pinned license group と同一キー (カタログ重複)。', 'hive': hive}

# --- Keyboard Layouts (HKLM): wrapper literal section ---
OVERRIDES[('FUN_00843390', 'Layout File')] = {
    'key': 'System\\CurrentControlSet\\Control\\Keyboard Layouts\\00000409', 'key_conf': '確定', 'hive': 'HKLM',
    'basis': 'FUN_00843390 の section literal "\\SYSTEM\\CurrentControlSet\\Control\\Keyboard Layouts\\" '
             '(REGISTRY.csv low-key 行)。<8hex> は Layout ID 列挙で、seed は US 配列 (00000409) を採用。'
             'core os group と同一キー (カタログ重複)。'}
OVERRIDES[('FUN_00865c90', 'Layout Text')] = {
    'key': 'System\\CurrentControlSet\\Control\\Keyboard Layouts\\00000409', 'key_conf': '確定', 'hive': 'HKLM',
    'basis': 'FUN_00865c90 同上 (Layout ID %.8x 書式 literal)。core os group と同一キー (カタログ重複)。'}

# --- FUN_0112e240 / FUN_011245e0 / FUN_01306d60: [0x15e1f00]→Cell(0x15C2608)="Plugin version specific\Windows" ---
OVERRIDES[('FUN_0112e240', 'Grid color')] = {
    'key': PVS_WIN + '\\PLForm', 'key_conf': '確定',
    'basis': 'FUN_0112e240 0x112e42b: key=[[0x15e1f00]]+"\\PLForm"。[[0x15e1f00]]=Cell 0x15C2608 は boot 0x11be0a0 '
             '(0x11be346-0x11be36e) が "Plugin version specific\\"+"Windows" を確定代入。' + Bboot}
OVERRIDES[('FUN_0112e240', 'Custom Grid Color')] = OVERRIDES[('FUN_0112e240', 'Grid color')]
OVERRIDES[('FUN_011245e0', 'Grid Contrast')] = {
    'key': PVS_WIN + '\\PRForm', 'key_conf': '確定',
    'basis': 'FUN_011245e0 0x1124d02: key=[[0x15e1f00]]+"\\prform" (write 側 0x112e240 は "\\PRForm" — レジストリは '
             '大小無視で同一キー)。' + Bboot}
OVERRIDES[('FUN_01306d60', 'Rounded')] = {
    'key': PVS_WIN + '\\EventEditForm', 'key_conf': '確定',
    'basis': 'FUN_01306d60 0x1306d7c: key=[[0x15e1f00]]+"\\EventEditForm" (0x13073c4 literal)。' + Bboot}

# --- SaveSettings (0x11af7e0) ---
SS_MIDIFORM = ('ColorfulWaves', 'ShowOnePanel', 'Delete recorded files to recycle bin', 'NoInitControlsBox',
               'ShowHelp', 'SyncType')
for n in SS_MIDIFORM:
    OVERRIDES[('SaveSettings', n)] = {
        'key': MIDIFORM, 'key_conf': '確定',
        'basis': 'SaveSettings 0x11afb79 が key="General\\"+[0x15e13b8(MIDIForm)+0x10] を構成 '
                 '(LoadSettings と対称)。' + b('General\\MIDIForm')}
for n in ('Enable MIDI sync', 'Enable MIDI input', 'Enable MIDI output', 'Template'):
    OVERRIDES[('SaveSettings', n)] = {
        'key': PVS_GEN, 'key_conf': '確定',
        'basis': 'SaveSettings 0x11afa0b/0x11b0386: key=[0x15C2620]+"General" = "Plugin version specific\\General"。'
                 + Bboot}
for n in ('Sample rate', 'Buffer length (DS)', 'Device name'):
    OVERRIDES[('SaveSettings', n)] = {
        'key': PVS_DEV + '\\Audio output', 'key_conf': '確定',
        'basis': 'SaveSettings 0x11b0cda: key=[0x15C2618]+"\\Audio output" = "Plugin version specific\\Devices'
                 '\\Audio output"。' + Bboot}
OVERRIDES[('SaveSettings', 'Sample rate')]['apply'] = True
OVERRIDES[('SaveSettings', 'Sample rate')]['value'] = '44100'
OVERRIDES[('SaveSettings', 'Sample rate')]['value_conf'] = '確定'
OVERRIDES[('SaveSettings', 'Sample rate')]['basis'] += ' 値=ReadInt 既定 44100 (REGISTRY.csv LoadSettings 行; SaveSettings 行は W のみで空のため既定を代入) → seed で既定反映。'
for n in ('Name', 'FileName', 'Params'):
    OVERRIDES[('SaveSettings', n)] = {
        'key': 'Software\\Image-Line\\Shared\\FL Studio tools\\<id>', 'key_conf': '推定',
        'basis': 'SaveSettings 0x11b0de1: key="Software\\Image-Line\\Shared\\FL Studio tools\\"+<tool id> '
                 '(0..49 を列挙する tools メニュー登録)。<id> は実行時採番のため推定。'}

# --- FUN_0117e9b0: MIDI デバイス別 ([0x15C2618]="Plugin version specific\Devices") ---
MIDI_IN = PVS_DEV + '\\MIDI input\\<device>'
MIDI_OUT = PVS_DEV + '\\MIDI output\\<device>'
for n in ('ConnectionCounter', 'Enabled', 'IDString', 'LinkedOutName', 'Port', 'ScriptFolder', 'Type'):
    OVERRIDES[('FUN_0117e9b0', n)] = {
        'key': MIDI_IN, 'key_conf': '推定',
        'basis': 'FUN_0117e9b0 0x117e9b0+: key=[0x15C2618]+"\\MIDI input"+...+<device名> (0x117e9b0 literal 群)。'
                 '<device> は列挙された MIDI デバイス名 (実行時) のため推定。' + Bboot}
for n in ('Sync', 'SendAllNotesOff'):
    OVERRIDES[('FUN_0117e9b0', n)] = {
        'key': MIDI_OUT, 'key_conf': '推定',
        'basis': 'FUN_0117e9b0: key=[0x15C2618]+"\\MIDI output"+...+<device名>。' + Bboot}

# --- ウィンドウ状態 (FUN_00ba5650 / FUN_011a5250): <metric base>\<Form名> ---
WIN_METRIC = PVS_WIN + '\\<WxHxBPP>\\<FormName>'
for n in ('Height', 'MaximizedHeight', 'MaximizedLeft', 'MaximizedTop', 'MaximizedWidth', 'State', 'Visible',
          'Width', 'Left', 'Top', 'Parent'):
    src = 'FUN_00ba5650' if n != 'Parent' else 'FUN_011a5250'
    OVERRIDES[(src, n)] = {
        'key': WIN_METRIC, 'key_conf': '推定',
        'basis': 'FUN_00ba5650: key=第5引数 or [window+0x10](TComponent.Name) を caller 基底に連結。caller '
                 'FUN_00cef380 は [0x15e2ce8]=Cell 0x15C2610 = "Plugin version specific\\Windows\\<WxHxBPP>" '
                 '(boot 0x11a35b0 が画面解像度 %dx%dx%d で計算) を渡す。<FormName> は窓別で実行時 → 推定。' + Bboot}

# --- LoadBrowserToolbars (0x11a36e0): FUN_011a3610 → [0x15C2608...]+画面計量+\Toolbars ---
for n in ('Left', 'Toolbar data', 'Top', 'Visible'):
    OVERRIDES[('LoadBrowserToolbars', n)] = {
        'key': PVS_WIN + '\\<WxHxBPP>\\Toolbars', 'key_conf': '推定',
        'basis': 'LoadBrowserToolbars 0x11ad60e (arg=NULL) → FUN_011a3610 が FUN_011a3440 (基底='
                 '[0x15C2608]+(" (<名>)")?"\\"+"%dx%dx%d" (GetSystemMetrics)) + "\\Toolbars" を構成。'
                 '解像度は実行環境依存のため推定。' + Bboot}

# --- FUN_00e42380 群: [0x15e2ce8]=Cell 0x15C2610 (計量付き) ---
for n in ('IncrementalScroll', 'LeftResizing', 'MagicLasso', 'ShiftMouseWheelNudging', 'SwapPanels'):
    OVERRIDES[('FUN_00e42380', n)] = {
        'key': PVS_WIN + '\\<WxHxBPP>\\<FormName>', 'key_conf': '推定',
        'basis': 'FUN_00e42380 が FUN_00ba4de0/write に [0x15e2ce8]=Cell 0x15C2610='
                 '"Plugin version specific\\Windows\\<WxHxBPP>" を渡し、\\"+[obj+0xc0c 名] を連結。'
                 '0xc0c 名は実行時 → 推定。' + Bboot}

# --- FUN_00eb* / FUN_00e4a1d0: [0x15C2608] (計量なし) + \<obj+0xc0c 名> ---
for src, names in (('FUN_00eb9ef0', ('Inv grid',)), ('FUN_00eba140', ('KeepLabelsOnScreen',)),
                   ('FUN_00eba6d0', ('Shadow',)), ('FUN_00ebab30', ('Time seg',)),
                   ('FUN_00e4a1d0', ('Snap',))):
    for n in names:
        OVERRIDES[(src, n)] = {
            'key': PVS_WIN + '\\<SectionName>', 'key_conf': '推定',
            'basis': '%s: key=[[0x15e1f00]]+"\\"+[obj+0xc0c 名]。"Plugin version specific\\Windows" まで確定 '
                     '(Cell 0x15C2608)、+0xc0c 名は実行時 → 推定。' % src + Bboot}

# --- FUN_01136050: [0x15C2608] + "\" + [param+0x10 名] ---
for n in ('Assign to mixer', 'Bass', 'Drums', 'Group tracks', 'Instruments', 'Limit CPU', 'Safe mode',
          'Vocals', 'When done'):
    OVERRIDES[('FUN_01136050', n)] = {
        'key': PVS_WIN + '\\<FormName>', 'key_conf': '推定',
        'basis': 'FUN_01136050 0x11360cb: key=[[0x15e1f00]]+"\\"+[param+0x10](TComponent.Name)。'
                 'Windows まで確定、Form 名は実行時 → 推定。' + Bboot}

# --- FUN_00cef380 'SortOrder': 'General\'+[param+0x10] ---
OVERRIDES[('FUN_00cef380', 'SortOrder')] = {
    'key': FLK + '\\General\\<Name>', 'key_conf': '推定',
    'basis': 'FUN_00cef380 0xcef416: key="General\\"+[param+0x10] (対象 plugin/窓の名前, 実行時) → 推定。' + B_BASE}

# --- FUN_00a4a910: Shared\Browser\<path> ---
for n in ('RememberTabSize', 'TabWidth'):
    OVERRIDES[('FUN_00a4a910', n)] = {
        'key': 'Software\\Image-Line\\Shared\\Browser\\<path>', 'key_conf': '推定',
        'basis': 'FUN_00a4a910 0xa4a910+: key="Software\\Image-Line\\Shared\\Browser\\"+[param+0x58] '
                 '(ブラウザのパス別タブ設定)。<path> は実行時 → 推定。'}

# --- FUN_012b5a10 'PPI': Shared\Plugins\<name> ---
OVERRIDES[('FUN_012b5a10', 'PPI')] = {
    'key': 'Software\\Image-Line\\Shared\\Plugins\\<name>', 'key_conf': '推定',
    'basis': 'FUN_012b5a10: key="Software\\Image-Line\\Shared\\Plugins\\"+<plugin 名> (実行時) → 推定。'}

# --- キー確定不能 (カタログのまま: 誤キー生成回避方針を維持) ---
OVERRIDES[('FUN_00dd2da0', 'Random seed')] = {
    'key': None, 'key_conf': '推定',
    'basis': 'FUN_00dd2da0 は FUN_00dd2190/FUN_00ba6150 経由で実行時生成キー (generator/patch 文脈) を使用 — '
             '静的に確定できないため「確定不能」として記録 (書かない方針を維持)。'}
OVERRIDES[('FUN_007a4e30', 'Count')] = {
    'key': None, 'key_conf': '推定',
    'basis': 'FUN_007a4e30 は新規 TRegistry + SetRoot(引数) + OpenKey(引数) で caller 渡しキーを使用 '
             '(browser URL 履歴系) — caller が実行時文字列のため「確定不能」として記録。'}
OVERRIDES[('FUN_00c526f0', 'clsid')] = {
    'key': None, 'key_conf': '推定', 'hive': 'HKLM',
    'basis': 'FUN_00c526f0 は HKLM\\software\\asio\\<driver> 配下の列挙 (driver 名は実機依存) — '
             '「確定不能」として記録 (書くと誤キーを作るため)。'}


def apply_overrides(entries):
    """key 不明 (key=None) のエントリへ OVERRIDES の実キーを反映し、同一座標の重複カタログを削除する (in place)。"""
    low = [e for e in entries if e.get('key') is None]
    applied = 0
    matched = set()
    for e in low:
        src = e['source'][0]
        hit = None
        for s_ in (src, 'Reg.readKey:%s' % e['hive'], 'Reg.readKey'):   # Reg.readKey の HKCU/HKLM 2 エントリを吸収
            o = OVERRIDES.get((s_, e['name']))
            if o:
                hit = (s_, o)
                break
        if not hit:
            print('NO OVERRIDE: %s %s' % (src, e['name']), file=sys.stderr)
            continue
        s_, o = hit
        matched.add((s_, e['name']))
        if o.get('hive') and o['hive'] != e['hive']:
            continue
        e['key'] = o['key']
        e['key_conf'] = o['key_conf']
        e['basis'] = o['basis']
        e['confidence'] = '確定' if (o['key_conf'] == '確定' and e['value_conf'] == '確定') else '推定'
        if o.get('apply') is True and not e['apply']:
            e['apply'] = True
            e['group'] = e.get('group') or 'settings'
            if o.get('value') is not None and not e['value']:
                e['value'] = o['value']
            if o.get('value_conf'):
                e['value_conf'] = o['value_conf']
                e['confidence'] = '確定' if (o['key_conf'] == '確定' and e['value_conf'] == '確定') else '推定'
            applied += 1
        if e['group'] == 'catalog' and o['key']:    # key 確定したカタログは group を settings 化
            e['group'] = 'settings'
    # (hive,key,name) 重複解消: apply=true の既存 entry と重複するカタログ entry は削除
    #   (coverage テストが「catalog 値は書かれない」ことを require するため、同一座標の二重登録は不許可)
    bycoord = {}
    for e in entries:
        if e.get('key'):
            bycoord.setdefault((e['hive'], e['key'].lower(), e['name'].lower()), []).append(e)
    removed = 0
    for group in bycoord.values():
        if len(group) > 1:
            keep = next((e for e in group if e['apply']), group[0])
            for e in group:
                if e is not keep:
                    entries.remove(e)
                    removed += 1
    return {'low_key': len(low), 'overrides_defined': len(OVERRIDES), 'overrides_matched': len(matched),
            'apply_promoted': applied, 'removed_duplicates': removed,
            'null_key_after': sum(1 for e in entries if e.get('key') is None)}


out_entries = []
for k in sorted(entries, key=lambda t: (t[0], t[1], t[2])):
    e = dict(entries[k]); e.pop('_core', None)
    out_entries.append(e)

# 整列は上書き前の key で行う (CAB-213 成果物と並びをバイト同一に保つ)
ov = apply_overrides(out_entries)

seed = {
    '_comment': 'vreg seed (generated by tools/startup/vreg/scripts/build_seed.py). entries[].apply=true のみ起動時に書込。',
    'version': SEED_VERSION,
    'license': {
        'flag_bit0': 0,
        '_doc': 'FLEngine byte[0x14f84a8] bit0 に対応させる registry 側の状態。0=登録済み値(pinned license group)を書く / 1=license group を書かず削除(Trial)。'
                '語義 (bit0=1 が未登録) は推定。external: Vreg.create({licenseMode:"external"}) で .reg を適用',
        'engine_flag': {'va': '0x14f84a8', 'bit': 0, 'semantic': '0=登録済み / 1=未登録 (読み側ログ分岐から。推定)', 'confidence': '推定'},
        'groups': ['license'],
    },
    'machine_guid': '${GENERATE_ONCE_PER_PROFILE}',
    'env': old.get('_env', {}), 'known_folders': old.get('_known_folders', {}),
    'entries': out_entries,
}
json.dump(seed, open(os.path.join(OUT, 'seed.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# ---------------- keys.json: win キー → 具象キー ----------------
EXPAND = {
    'Software\\Classes\\.flp / .fst / .fsc / flstudio': ['Software\\Classes\\.flp', 'Software\\Classes\\.fst', 'Software\\Classes\\.fsc', 'Software\\Classes\\flstudio\\shell\\open\\command'],
    'Software\\Classes\\FL64.flp / .fst / .fsc / FL64.exe\\DefaultIcon': ['Software\\Classes\\FL64.flp\\DefaultIcon', 'Software\\Classes\\FL64.fst\\DefaultIcon', 'Software\\Classes\\FL64.fsc\\DefaultIcon', 'Software\\Classes\\FL64.exe\\DefaultIcon'],
    'Software\\Image-Line\\Capabilities\\FL64 / FL32': ['Software\\Image-Line\\Capabilities\\FL64', 'Software\\Image-Line\\Capabilities\\FL32'],
    'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\<ProductGUID>': ['Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{0F1E1D00-0000-4000-8000-0000574542AD}'],
    'Software\\Image-Line\\Shared\\Browser\\*': ['Software\\Image-Line\\Shared\\Browser\\Sounds'],
    'Software\\Image-Line\\FL Studio <n-1..> (旧版)': ['Software\\Image-Line\\FL Studio 25'],
    'Software\\Borland\\Delphi\\Locales; Software\\Borland\\Locales; Software\\CodeGear\\Locales; Software\\Embarcadero\\Locales': ['Software\\Borland\\Delphi\\Locales', 'Software\\Borland\\Locales', 'Software\\CodeGear\\Locales', 'Software\\Embarcadero\\Locales'],
    'System\\CurrentControlSet\\Control\\Keyboard Layouts\\%.8x': ['System\\CurrentControlSet\\Control\\Keyboard Layouts\\00000409'],
}
HIVES = {'HKCU/HKLM': ['HKCU', 'HKLM']}
seeded_keys = {(e['hive'], e['key'].lower()) for e in out_entries if e['apply'] and e['key']}
seeded_keys.add(('HKLM', (CV + '\\FontSubstitutes').lower()))
keys = []
seen = set()
for x in win:
    if x['confidence'] == 'low-key' or x['key'].startswith('('):
        continue
    kk = (x['hive'], x['key'])
    if kk in seen:
        continue
    seen.add(kk)
    cls = 'literal' if x['confidence'] in LIT else ('inferred' if x['confidence'] == 'inferred-base' else 'installer')
    for h in HIVES.get(x['hive'], [x['hive']]):
        for c in EXPAND.get(x['key'], [x['key']]):
            c = c.rstrip('\\')
            if any(k['hive'] == h and k['key'].lower() == c.lower() for k in keys):
                continue
            keys.append({'hive': h, 'csv_key': x['key'], 'key': c, 'class': cls,
                         'seeded': (h, c.lower().rstrip('\\')) in seeded_keys or (h, c.lower()) in seeded_keys})
json.dump({'version': SEED_VERSION, 'keys': keys}, open(os.path.join(OUT, 'keys.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

names = {e['name'] for e in out_entries}
print('entries=%d distinct_names=%d apply=%d catalog_only=%d' % (len(out_entries), len(names), sum(e['apply'] for e in out_entries),
                                                                  sum(not e['apply'] for e in out_entries)))
print('overrides: low_key=%(low_key)d defined=%(overrides_defined)d matched=%(overrides_matched)d apply_promoted=%(apply_promoted)d '
      'removed_duplicates=%(removed_duplicates)d null_key_after=%(null_key_after)d' % ov)
print('keys(csv rows)=%d concrete=%d classes=%s' % (len(seen), len(keys), dict(collections.Counter(k['class'] for k in keys))))
