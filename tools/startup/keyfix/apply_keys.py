#!/usr/bin/env python3
"""apply_keys.py — CAB-213: vreg seed の low-key 112 エントリへ実キーを反映する後処理。

入力: tools/startup/vreg/data/seed.json (build_seed.py 生成物; 本ツリーポスト処理のみで
       tools/startup/vreg/scripts/build_seed.py 本体は読取専用の範囲)
出力: 同 seed.json を上書き (key / key_conf / value_conf / basis / apply 更新)
      + work/keyfix_report.json (確定数等の集計)

根拠 (静的解析; 詳細は tools/startup/keyfix/REPORT.md):
  * TRegistry 群 (0x5ae000-0x5b4000) の意味は Reg* IAT thunk への call で確定:
    OpenKey(0x5af5e0)=RegOpenKeyExW/RegCreateKeyExW, OpenKeyRO(0x5af7c0), CreateKey(0x5af470),
    OpenKeyHandle(0x5b0cd0), GetKeyHandle(0x5b16a0→0x5b1750), WriteData(0x5b0b30)=RegSetValueExW,
    ReadData(0x5b0bd0)=RegQueryValueExW。ReadStr(0x5b1820) は rdx=返値変数 / key=r8 / value=r9。
  * key 引数が nil/空 → CurrentKey そのもの (IsRelative 0x5aeec0: 空 or 先頭≠'\\' → 相対)。
  * 共有 TRegistry 管理オブジェクト ([0x6510F0]) の CurrentKey は OpenKey/OpenKeyRO/GetKeyHandle で
    永続変化。起動時 0x1104fe0 が 'Software\\Image-Line\\FL Studio 26' を開く
    (0x11c71b0/0x11cde20 は同一関数内で GetKeyHandle(FL26)→相対 'General' ops の組で実証)。
  * 相対キーの基底 = FL26。セクションは 'General\\<Form名>' / 'General\\Render' /
    'Plugin version specific\\...' (boot 0x11be0a0 が
    [0x15C2620]='Plugin version specific\\', [0x15C2608]=+'Windows',
    [0x15C2618]=+'Devices', [0x15C2610]=+'Windows\\<WxHxBPP>' を計算)。
"""
import json, os, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = '/home/ubuntu/work/webstudio/tools/startup/vreg/data/seed.json'

FLK = 'Software\\Image-Line\\FL Studio 26'
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


def main():
    seed = json.load(open(SEED))
    entries = seed['entries']
    low = [e for e in entries if e.get('key') is None]
    # source 表記ゆれ (Reg.readKey: HKCU/HKLM 2 エントリ) を吸収
    applied = 0
    matched = set()
    for e in low:
        src = e['source'][0]
        cand = [(s, OVERRIDES.get((s, e['name']))) for s in
                (src, 'Reg.readKey:%s' % e['hive'], 'Reg.readKey')]
        hit = None
        for s, o in cand:
            if o:
                hit = (s, o)
                break
        if not hit:
            print('NO OVERRIDE: %s %s' % (src, e['name']), file=sys.stderr)
            continue
        s, o = hit
        matched.add((s, e['name']))
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
        # カタログ key が確定したものは group を settings 化 (catalog のままでも可だが分類を正す)
        if e['group'] == 'catalog' and o['key']:
            e['group'] = 'settings'
    missing = [k for k in OVERRIDES if k not in matched]
    # (hive,key,name) 重複解消: apply=true の既存 entry と重複するカタログ entry は削除
    #   (coverage テストが「catalog 値は書かれない」ことを require するため、同一座標の二重登録は不許可)
    bycoord = {}
    for e in entries:
        if e.get('key'):
            bycoord.setdefault((e['hive'], e['key'].lower(), e['name'].lower()), []).append(e)
    removed = []
    for coord, group in bycoord.items():
        if len(group) > 1:
            keep = next((e for e in group if e['apply']), group[0])
            for e in group:
                if e is not keep:
                    removed.append({'hive': e['hive'], 'key': e['key'], 'name': e['name'],
                                    'value': e['value'], 'basis': e['basis']})
                    entries.remove(e)
    nulls = sum(1 for e in entries if e.get('key') is None)
    konf = collections.Counter(e['key_conf'] for e in entries)
    summary = {
        'low_key_before': len(low), 'overrides_defined': len(OVERRIDES), 'overrides_matched': len(matched),
        'missing_overrides': ['%s|%s' % m for m in missing],
        'apply_promoted': applied, 'null_key_after': nulls,
        'key_conf': dict(konf), 'removed_duplicates': removed,
        'seed_entries_after': len(entries),
    }
    json.dump(summary, open(os.path.join(HERE, 'work', 'keyfix_report.json'), 'w'), ensure_ascii=False, indent=1)
    json.dump(seed, open(SEED, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
