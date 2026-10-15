#!/usr/bin/env python3
"""FL Studio 資産ツリーの実測インベントリ (win 抽出ブロック + 復元パス / mac .app)。

出力 (work/ = gitignore):
  work/inv_win.jsonl, work/inv_mac.jsonl   1 行 1 エントリ {p,size,sha,cat,cls,disk,..}
出力 (コミット対象):
  inventory/summary.json                    集計 (cat x 種別 / top dir / 重複 / mac-win 共通)

使い方:  python3 inventory/inventory.py [--skip-hash]
前提:    work/win_paths.json (win_paths/recover_paths.py の出力)
"""
import os, sys, json, hashlib, collections, struct, re
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, 'work')
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_MAC_DIR, FL_WIN64_DIR as _WIN64
# block_manifest.json / pe_metadata.json が無い環境は inventory/mk_inputs.py で再構成し WIN_INPUTS_DIR に置く
_INPUTS = os.environ.get('WIN_INPUTS_DIR') or _WIN64
WIN_EXTRACTED = os.path.join(_WIN64, 'extracted')
WIN_MANIFEST = os.path.join(_INPUTS, 'block_manifest.json')
WIN_PE_META = os.path.join(_INPUTS, 'pe_metadata.json')
MAC_APP = os.path.join(FL_MAC_DIR, 'pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents')

# ---- 分類 ---------------------------------------------------------------
# cls: 実行バイナリの扱い   lift    = wasm 化(lift)対象 (FL 独自/クローズド)
#                           rebuild = OSS upstream から wasm 再ビルド (lift しない方針)
#                           skip    = ブラウザでは実行しない (インストーラ/x86/ドライバ/WebView 等)
#      data = 純データ
AUDIO = {'wav', 'wv', 'flac', 'ogg', 'mp3', 'aif', 'aiff', 'wma', 'm4a', 'rex', 'rx2'}
PRESET = {'fst', 'fnv', 'ilv', 'dmpatch', 'dmptrn', 'dwp', 'fsc', 'groovepat', 'flgsynth', 'gmsynth', 'flmpst', 'flms',
          'flm', 'zla', 'zfo', 'hdprg', 'mrp', 'ilcontrol', 'dwb', 'tbio', 'fpc', 'sf2', 'sfz', 'syx', 'fxp', 'fxb'}
IMAGE = {'png', 'jpg', 'jpeg', 'bmp', 'tga', 'svg', 'ico', 'icns', 'gif', 'webp', 'zgemesh'}
FONT = {'ttf', 'otf', 'woff', 'woff2'}
TEXT = {'ini', 'nfo', 'xml', 'txt', 'json', 'html', 'htm', 'css', 'js', 'rtf', 'cfg', 'md', 'csv', 'dat', 'zgeproj',
        'flstheme', 'flsk', 'plist', 'lst', 'inf', 'yml', 'yaml', 'tsv', 'bat', 'sh', 'ps1'}
LIFT_NAME = re.compile(r'(?i)^(FLEngine_x64|FL64|OsxFL|ILSvg|ILTools|ildsp|DirectWaveCtEngine|elastique|SGv2|dsp_ippv2|beat_tracker|libreverb|libkio|ILRemoteServer|libQuickFontCache|REX Shared Library|libwinbridge|MacVclCocoa)')
REBUILD_NAME = re.compile(r'(?i)(^blend2d|^freetype|^lameenc|^oggio|^wavpackdll|^lib(freetype|blend2d|mp3lame|oggio|crypto|ssl|z|panelw|formw|menuw|ncursesw|sqlite)|^wavpack|^EasyFLAC|^avcodec|^avformat|^avfilter|^avutil|^swresample|^swscale|^avdevice|^postproc|^python3|^pythonw?|sqlite3|\.pyd$|\.so$|libcrypto|libssl|libz)')
SKIP_NAME = re.compile(r'(?i)(ILMinihostBridge|ILPluginScanner|uninstall|MicrosoftEdgeUpdateSetup|FL Cloud Plugins|uninstall|Processing\.NDI|WebView2Loader|ILWASAPI2ASIO|PluginManager|ilbridge|fldiagnostic|ControlCreator|LilyPond|lib(glib|gobject|pango|pangoft2)|ReWire|vstplugin|Zero-X|FLMManaged|python\.exe|pythonw\.exe|Setup\.exe|\.bat$|Symbiosis)')


def ext_of(name):
    b = name.rsplit('\\', 1)[-1].rsplit('/', 1)[-1]
    return b.rsplit('.', 1)[-1].lower() if '.' in b else ''


def base_of(name):
    return name.rsplit('\\', 1)[-1].rsplit('/', 1)[-1]


def classify(rel, is_exec, arch=None):
    """rel: tree 相対 (/ 区切り)。戻り (cat, cls)"""
    e = ext_of(rel)
    b = base_of(rel)
    if is_exec:
        if arch in ('x86', 'i386'):
            return 'exec', 'skip'
        if SKIP_NAME.search(b) or SKIP_NAME.search(rel):
            return 'exec', 'skip'
        if rel.startswith('Shared/Python') or rel.startswith('Shared/ffmpeg') or REBUILD_NAME.search(b):
            return 'exec', 'rebuild'
        if rel.startswith('Shared/') and re.search(r'(?i)^(DelZip64|REX Shared|svctl64|sveng64|QuickFontCache_x64|Reverb_x64|SG_x64)', b):
            return 'exec', 'lift'
        if LIFT_NAME.search(b) or rel.startswith('Plugins/'):
            return 'exec', 'lift'
        return 'exec', 'lift' if rel.startswith('Shared/') else 'skip'
    if rel.startswith('Shared/Python') or (rel.startswith('Shared/Temp') and e == 'py'):
        return 'python-lib', 'data'
    if e in AUDIO:
        return 'audio', 'data'
    if e == 'flp':
        return 'project', 'data'
    if e in ('mid', 'midi'):
        return 'midi', 'data'
    if e in PRESET:
        return 'preset', 'data'
    if e in IMAGE:
        return 'image', 'data'
    if e in FONT:
        return 'font', 'data'
    if e == 'py' or e == 'pyc':
        return 'python-lib', 'data'
    if e in TEXT:
        return 'text', 'data'
    return 'other', 'data'


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def macho_arch(path):
    try:
        with open(path, 'rb') as f:
            m = f.read(8)
    except OSError:
        return None
    if len(m) < 4:
        return None
    be = struct.unpack('>I', m[:4])[0]
    le = struct.unpack('<I', m[:4])[0]
    if be in (0xCAFEBABE, 0xBEBAFECA) or le in (0xCAFEBABE, 0xBEBAFECA):
        return 'fat'
    if le in (0xFEEDFACF, 0xFEEDFACE):
        return 'macho'
    return None


def build_win(do_hash):
    paths = json.load(open(os.path.join(WORK, 'win_paths.json')))
    man = {'%05d' % m['idx']: m for m in json.load(open(WIN_MANIFEST))}
    pemeta = {m['file']: m for m in json.load(open(WIN_PE_META))}
    ents = []
    for k, dests in paths.items():
        m = man[k]
        disk = m['path']
        fn = os.path.basename(disk)
        pm = pemeta.get(fn)
        is_exec = m['kind'] == 'PE'
        arch = pm['machine'] if pm else None
        for d in dests:
            rel = d.replace('$INSTDIR\\', '').replace('\\', '/')
            if rel.startswith('$') or rel.startswith('${'):
                continue  # $PLUGINSDIR(インストーラ内部) / user-var 配置先 (DirectWave ユーザデータ) は対象外
            cat, cls = classify(rel, is_exec, arch)
            ents.append(dict(p=rel, size=m['dsize'], disk=disk, blk=int(k), cat=cat, cls=cls, arch=arch))
    shas = {}
    if do_hash:
        uniq = sorted({e['disk'] for e in ents})
        with ThreadPoolExecutor(16) as ex:
            for d, s in zip(uniq, ex.map(sha256_file, uniq)):
                shas[d] = s
    for e in ents:
        e['sha'] = shas.get(e['disk'])
    return ents


def build_mac(do_hash):
    ents = []
    for dp, dn, fn in os.walk(MAC_APP):
        for f in fn:
            ap = os.path.join(dp, f)
            rel = os.path.relpath(ap, MAC_APP).replace(os.sep, '/')
            if os.path.islink(ap):
                ents.append(dict(p=rel, size=0, disk=None, cat='symlink', cls='symlink', link=os.readlink(ap)))
                continue
            sz = os.path.getsize(ap)
            ma = macho_arch(ap) if sz > 1000 else None
            r2 = rel[len('Resources/FL/'):] if rel.startswith('Resources/FL/') else rel
            cat, cls = classify(r2, ma is not None, None)
            ents.append(dict(p=rel, tp=r2, size=sz, disk=ap, cat=cat, cls=cls, arch=ma))
    if do_hash:
        files = [e for e in ents if e['disk']]
        with ThreadPoolExecutor(16) as ex:
            for e, s in zip(files, ex.map(lambda e: sha256_file(e['disk']), files)):
                e['sha'] = s
    return ents


def summarize(ents, label):
    S = {'label': label, 'files': len(ents), 'bytes': sum(e['size'] for e in ents)}
    uniq = {}
    for e in ents:
        k = e.get('sha') or (e['disk'], e['size'])
        uniq[k] = e['size']
    S['unique_content_files'] = len(uniq)
    S['unique_content_bytes'] = sum(uniq.values())
    by = collections.defaultdict(lambda: [0, 0])
    for e in ents:
        k = e['cat'] + '/' + e['cls']
        by[k][0] += 1
        by[k][1] += e['size']
    S['by_cat_cls'] = {k: dict(files=v[0], bytes=v[1]) for k, v in sorted(by.items(), key=lambda kv: -kv[1][1])}
    top = collections.defaultdict(lambda: [0, 0])
    for e in ents:
        p = e.get('tp') or e['p']
        parts = p.split('/')
        k = '/'.join(parts[:2]) if parts[0] in ('Plugins', 'Data') and len(parts) > 2 else parts[0]
        top[k][0] += 1
        top[k][1] += e['size']
    S['by_topdir'] = {k: dict(files=v[0], bytes=v[1]) for k, v in sorted(top.items(), key=lambda kv: -kv[1][1])}
    hist = collections.Counter()
    hbytes = collections.Counter()
    for e in ents:
        b = '0' if e['size'] == 0 else '2^%02d' % (e['size'].bit_length() - 1)
        hist[b] += 1
        hbytes[b] += e['size']
    S['size_hist'] = {k: dict(files=hist[k], bytes=hbytes[k]) for k in sorted(hist)}
    g = collections.defaultdict(list)
    for e in ents:
        if e.get('sha') and e['size'] > 0:
            g[e['sha']].append(e)
    dup_extra_files = dup_extra_bytes = 0
    for s, l in g.items():
        paths = {x['p'] for x in l}
        if len(paths) > 1:
            dup_extra_files += len(paths) - 1
            dup_extra_bytes += (len(paths) - 1) * l[0]['size']
    S['dup_extra_files'] = dup_extra_files
    S['dup_extra_bytes'] = dup_extra_bytes
    return S


def main():
    do_hash = '--skip-hash' not in sys.argv
    os.makedirs(WORK, exist_ok=True)
    win = build_win(do_hash)
    mac = build_mac(do_hash)
    for name, ents in (('win', win), ('mac', mac)):
        with open(os.path.join(WORK, 'inv_%s.jsonl' % name), 'w') as f:
            for e in ents:
                f.write(json.dumps(e, ensure_ascii=False) + '\n')
    out = {'win': summarize(win, 'win64 (NSIS 抽出ブロック + 復元パス, $PLUGINSDIR/user-var 配置を除く)'),
           'mac': summarize([e for e in mac if e['cls'] != 'symlink'], 'mac .app Contents')}
    out['mac']['symlinks'] = sum(1 for e in mac if e['cls'] == 'symlink')
    if do_hash:
        wsha = {e['sha']: e for e in win if e.get('sha')}
        msha = {e['sha']: e for e in mac if e.get('sha') and e['size'] > 0}
        common = set(wsha) & set(msha)
        out['common_win_mac'] = dict(unique_contents=len(common), bytes=sum(wsha[s]['size'] for s in common),
                                     win_unique_total=len(wsha), mac_unique_total=len(msha),
                                     win_only_bytes=sum(wsha[s]['size'] for s in set(wsha) - common),
                                     mac_only_bytes=sum(msha[s]['size'] for s in set(msha) - common))
    json.dump(out, open(os.environ.get('INVENTORY_SUMMARY_OUT') or os.path.join(HERE, 'summary.json'), 'w'), indent=1, ensure_ascii=False)
    for k in ('win', 'mac'):
        s = out[k]
        print(k, s['files'], 'files', s['bytes'], 'B; unique', s['unique_content_files'], s['unique_content_bytes'],
              'dupExtra', s['dup_extra_files'], s['dup_extra_bytes'])
    if 'common_win_mac' in out:
        print(out['common_win_mac'])


if __name__ == '__main__':
    main()
