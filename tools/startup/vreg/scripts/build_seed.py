#!/usr/bin/env python3
"""build_seed.py — REGISTRY.csv (読取専用) + 手書き仕様 から vreg の seed / キー目録を生成する。
出力: ../data/seed.json (全値名の初期値 + confidence), ../data/keys.json (REGISTRY.csv の win キー → 具象キー展開)
usage: python3 build_seed.py   (入力: ../../REGISTRY.csv, ../../data/vreg_seed.json)

方針 (REPORT 参照):
  * apply=true  : 起動時に仮想レジストリへ書く値。コード由来の既定値 (ReadInt/ReadBool 既定) か、ゲート通過に必要な値のみ。
  * apply=false : カタログのみ (値は記録するが書かない = エンジン内蔵の既定に任せる)。キー不明 (wrapper 経由の section) の値名はここ。
  * confidence  : 確定 = キー/値名がバイナリのリテラルで、値もコード既定 or 実在 OS 値 / 推定 = キー・値のどちらかが推定・選択値
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

out_entries = []
for k in sorted(entries, key=lambda t: (t[0], t[1], t[2])):
    e = dict(entries[k]); e.pop('_core', None)
    out_entries.append(e)

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
print('keys(csv rows)=%d concrete=%d classes=%s' % (len(seen), len(keys), dict(collections.Counter(k['class'] for k in keys))))
