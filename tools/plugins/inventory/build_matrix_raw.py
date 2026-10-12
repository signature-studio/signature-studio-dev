#!/usr/bin/env python3
"""PLUGIN_MATRIX.json / PLUGIN_MATRIX.md を生成する (全て work/ の実測 JSON から)。

入力 (inventory/*.py が生成):
  work/mac_scan.json, work/mac_unique.json, work/win_pe_scan.json, work/nsis_blockmap.json,
  work/win_unique.json, work/win_abi.json
追加実測: FL Data の .flp 使用頻度 / プリセット数 / Render tests 対応 (mac Data を走査)。
"""
import os, re, json, collections, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTD = os.path.join(HERE, '..')
WORK = os.path.join(ROOTD, 'work')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_MAC_DIR  # noqa: E402
MAC_FL = os.path.join(FL_MAC_DIR, 'pkg_extract', 'payload_out', 'Applications', 'FL Studio 2026.app', 'Contents', 'Resources', 'FL')
sys.path.insert(0, HERE)
from family_table import FAMILY, SCOPE  # noqa

J = lambda n: json.load(open(os.path.join(WORK, n)))

mac = J('mac_scan.json')
macu = J('mac_unique.json')
winpe = {r['file']: r for r in J('win_pe_scan.json')}
blk = J('nsis_blockmap.json')
winu = J('win_unique.json')
abi = {r['file']: r for r in J('win_abi.json')}

# ---------- win: plugin dir -> modules / data ----------
PLUG_RE = re.compile(r'^\$V31\\Plugins\\Fruity\\(Effects|Generators)\\([^\\]+)(?:\\(.*))?$')
win_mod = collections.defaultdict(list)
win_data = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
seen_blocks = collections.defaultdict(set)
for r in blk:
    m = PLUG_RE.match(r['outdir'])
    if not m or r['idx'] is None:
        continue
    key = (m.group(1), m.group(2).lower())
    sub = m.group(3) or ''
    if (r['idx'], sub, r['name']) in seen_blocks[key]:
        continue
    seen_blocks[key].add((r['idx'], sub, r['name']))
    if r['kind'] == 'PE':
        win_mod[key].append((r['idx'], sub, r['name']))
    else:
        ext = os.path.splitext(r['name'])[1].lower() or '(none)'
        win_data[key][ext][0] += 1
        win_data[key][ext][1] += r['dsize'] or 0

NAME_ALIAS = {'fruity db meter': 'fruity db meter'}

VENDOR_LIBS = {'Processing.NDI.Lib.x64.dll', 'SpoutLibrary.dll', 'ZGEBullet_x64.dll', 'ZgeNano_x64.dll', 'ZgeSkelet_x64.dll',
               'testdll_x64.dll', 'FLMManagedBridge_x64.dll', 'Slayer_Engine.dll'}


def win_lang(pe):
    if 'FP_DelphiPlug' in pe['hints']:
        return 'Delphi(FP_DelphiPlug)'
    if pe['delphi_marks']:
        return 'Delphi'
    try:
        lv = float(pe['linker'])
    except Exception:
        lv = 0
    if lv >= 14:
        return 'MSVC C++ (VS2019, link %s)' % pe['linker']
    return 'other(link %s)' % pe['linker']


def mac_lang(s):
    if s.get('fpc'):
        return 'FPC 3.2.3 (Pascal)'
    if 'libcxx' in s['hints']:
        return 'clang C++ (libc++)'
    return 'clang/ObjC/C'


# ---------- Data: flp usage / presets / render tests ----------
def collect_data():
    flps = []
    for dp, dn, fn in os.walk(os.path.join(MAC_FL, 'Data')):
        for f in fn:
            if f.lower().endswith('.flp') and 'Render tests' not in dp:
                flps.append(os.path.join(dp, f))
    blobs = []
    for p in flps:
        b = open(p, 'rb').read()
        blobs.append((p, b.lower(), b.decode('latin1').lower().encode('utf-16le') if False else b))
    return flps, blobs


flps, flp_blobs = collect_data()
flp_lower = [(p, b.lower()) for p, _, b in flp_blobs]
# FLP 内の文字列は ASCII または UTF-16LE。小文字化して両方探す
flp_lower16 = []
for p, _, b in flp_blobs:
    flp_lower16.append(b.lower())


def flp_usage(name):
    n8 = name.lower().encode('latin1', 'ignore')
    n16 = name.lower().encode('utf-16le', 'ignore')
    c = 0
    for (p, bl) in flp_lower:
        if n8 in bl or n16 in bl:
            c += 1
    return c


def presets(kind, name):
    n = 0
    base = os.path.join(MAC_FL, 'Data', 'Patches', 'Plugin presets', kind)
    if os.path.isdir(base):
        for d in os.listdir(base):
            if d.lower() == name.lower():
                for dp, dn, fn in os.walk(os.path.join(base, d)):
                    n += sum(1 for f in fn if f.lower().endswith(('.fst', '.fsc', '.dmpatch', '.nfo')) and f != 'Plugin.nfo')
    return n


render_tests = {os.path.splitext(f)[0].lower(): f for f in os.listdir(os.path.join(MAC_FL, 'Data', 'System', 'Render tests'))}
RT_ALIAS = {'3x osc': '3osc', 'fruity db meter': None, 'fruity drumsynth live': 'drumsynth live',
            'fruity waveshaper': 'fruity waveshaper', 'bassdrum': 'bassdrum', 'beepmap': 'beepmap', 'boobass': 'boobass',
            'directwave': 'directwave', 'minisynth': 'minisynth', 'patcher': None}


def render_test(name):
    k = name.lower()
    if k in RT_ALIAS:
        k = RT_ALIAS[k]
    if k and k in render_tests:
        return render_tests[k]
    if name == 'Patcher':
        return 'Patcher (effect).flp / Patcher (generator).flp'
    return None


# ---------- build ----------
def macho_info(m, kind, plug):
    s = m['slices']['x86_64']
    a = m['slices'].get('arm64')
    rel = m['rel']
    key = '%s/%s/%s' % (kind, plug, rel)
    u = macu.get(key, {})
    nonsys = [d for d in s['deps'] if not (d.startswith('/usr/lib') or d.startswith('/System'))]
    return {
        'file': rel, 'x86_64_size': s['size'], 'arm64_size': a['size'] if a else None,
        'text_bytes': s['text'], 'nfuncs': s['nfuncs'], 'lang': mac_lang(s),
        'exports_CreatePlugInstance': any(e == '_CreatePlugInstance' for e in s['exports']),
        'uniq_bytes': u.get('uniq_bytes'), 'uniq_funcs': u.get('uniq_funcs'), 'uniq_fp': u.get('uniq_fp'),
        'fw_bytes': u.get('fw_bytes'), 'nonsystem_deps': nonsys, 'hints': s['hints'],
        'minos': s.get('minos'), 'sdk': s.get('sdk'),
    }


def win_info(idx, sub, fname):
    f = 'block%05d_PE.bin' % idx
    pe = winpe[f]
    u = winu.get('block%05d' % idx, {})
    a = abi.get(f)
    d = {
        'block': idx, 'file': fname, 'subdir': sub, 'size': pe['size'], 'machine': pe['machine'],
        'lang': win_lang(pe), 'code_bytes': pe['code_bytes'], 'pdata_funcs': pe['pdata_funcs'],
        'exports_CreatePlugInstance': 'CreatePlugInstance' in pe['exports'],
        'fw_bytes': u.get('fw_bytes'), 'uniq_bytes': u.get('uniq_bytes'), 'uniq_funcs': u.get('uniq_funcs'),
        'uniq_fp': u.get('uniq_fp'), 'hints': pe['hints'], 'vendor': fname in VENDOR_LIBS,
        'version': {k: v for k, v in pe['version'].items() if k in ('ProductName', 'FileDescription', 'FileVersion')},
        'pdb': pe['pdb'],
    }
    if a and 'vtable' in a:
        d['abi'] = {'class': a.get('class_name'), 'nslots': a.get('nslots'), 'impl': sorted(a.get('impl', {})),
                    'info': a.get('info')}
    return d


plugins = []
for r in mac:
    kind, name = r['kind'], r['name']
    key = (kind, name.lower())
    mods = [macho_info(m, kind, name) for m in r['machos']]
    mods.sort(key=lambda x: (not x['exports_CreatePlugInstance'], x['file'].count('/'), x['file']))
    main_mac = [m for m in mods if m['exports_CreatePlugInstance']]
    wmods = [win_info(*t) for t in sorted(win_mod.get(key, []))]
    wmods.sort(key=lambda x: (not x['exports_CreatePlugInstance'], x['subdir'] != '', x['file']))
    wmain = [m for m in wmods if m['exports_CreatePlugInstance']]
    own = [m for m in wmods if not m['vendor']]
    U = sum((m['uniq_bytes'] or 0) for m in own)
    FPN = sum((m['uniq_fp'] or 0) for m in own)
    engines = [m for m in own if not (m['lang'].startswith('Delphi(FP'))]
    ENG = sum(m['size'] for m in engines)
    data_ext = {e: {'count': c[0], 'bytes': c[1]} for e, c in sorted(win_data.get(key, {}).items(), key=lambda kv: -kv[1][1])}
    fam = FAMILY.get(name, ('other', ''))
    rec = {
        'id': '%s/%s' % (kind, name), 'kind': kind, 'name': name, 'vendor': r['nfo'].replace('ps_Vendorname=', ''),
        'family': fam[0], 'desc': fam[1], 'scope': SCOPE.get(name, 'in'),
        'mac': {'dir_bytes': r['total_bytes'], 'nfiles': r['nfiles'], 'ext_counts': r['ext_counts'], 'modules': mods,
                'has_arm64': all(m['arm64_size'] for m in mods)},
        'win': {'modules': wmods, 'data': data_ext, 'data_files': sum(v['count'] for v in data_ext.values()),
                'data_bytes': sum(v['bytes'] for v in data_ext.values())},
        'metrics': {'win_uniq_bytes': U, 'win_uniq_fp_insns': FPN, 'win_engine_bytes': ENG,
                    'win_fw_shared_bytes': sum((m['fw_bytes'] or 0) for m in own),
                    'win_main_size': sum(m['size'] for m in wmain), 'n_win_modules': len(own),
                    'n_mac_modules': len(mods)},
        'usage': {'demo_flp_hits': flp_usage(name if name != 'Fruity dB meter' else 'Fruity dB Meter'),
                  'presets': presets(kind, name), 'render_test': render_test(name)},
    }
    plugins.append(rec)

json.dump({'plugins': plugins, 'n_flp_scanned': len(flp_lower)}, open(os.path.join(WORK, 'matrix_raw.json'), 'w'), indent=1)
print('records', len(plugins), 'flp scanned', len(flp_lower))
