#!/usr/bin/env python3
"""PLG-X (#210) 12 本 (+ 付随モジュール) の方針判断用の静的事実を実測する。

  1. PE 外形: サイズ・言語・export 数・import DLL (名前 -> 関数数)・delay import
  2. API 分類: import 名を正規表現で分類 (net / process / dynload / opengl / d3d / midi / hid / registry / thread / gdi / audio / com)
  3. 文字列証跡: 第三者ライブラリ・外部 SDK・URL の文字列ヒット (ASCII + UTF-16LE; 存在 = 使用の証明ではない)
出力: work/hostx/static.json と stdout の Markdown 表。 使い方: static_facts.py [--json out.json]
"""
import os, sys, re, json, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402
import pefile  # noqa: E402

EXT = os.path.join(FL_WIN64_DIR, 'extracted')
P = os.path.join(HERE, '..')

# (plugin, role, block)
MODULES = [
    ('Fruity Wrapper (Effects)', 'shell', 19091),
    ('Fruity Wrapper (Generators)', 'shell', 23676),
    ('Patcher (Effects)', 'shell', 19220),
    ('Patcher (Generators)', 'shell', 24155),
    ('ReWired', 'shell', 24161),
    ('MIDI Out', 'shell', 23918),
    ('Razer Chroma', 'shell', 19244),
    ('Fruity Video Player', 'shell', 23674),
    ('ZGameEditor Visualizer', 'shell', 19304),
    ('ZGameEditor Visualizer', 'NDI', 19299),
    ('ZGameEditor Visualizer', 'Spout', 19300),
    ('ZGameEditor Visualizer', 'ZGEBullet', 19303),
    ('ZGameEditor Visualizer', 'ZgeNano', 19305),
    ('ZGameEditor Visualizer', 'ZgeSkelet', 19306),
    ('FL Studio Mobile Rack FX', 'engine', 18976),
    ('FL Studio Mobile', 'engine', 22444),
    ('FL Studio Mobile', 'FLMManagedBridge', 22466),
    ('FL Studio Mobile Rack', 'engine', 23605),
]

# import 名の分類 (API 名の正規表現; 大小無視)
API = collections.OrderedDict([
    ('net', r'^(WSAStartup|socket|connect|send|recv|sendto|recvfrom|bind|listen|accept|getaddrinfo|gethostbyname|WSA\w+|InternetOpen\w*|WinHttp\w+|URLDownload\w+|GetAdaptersInfo|GetAdaptersAddresses)$'),
    ('process', r'^(CreateProcess\w*|ShellExecute\w*|WinExec|OpenProcess|TerminateProcess)$'),
    ('dynload', r'^(LoadLibrary\w*|GetProcAddress|FreeLibrary|LdrLoadDll)$'),
    ('opengl', r'^(wgl\w+|gl[A-Z]\w+)$'),
    ('d3d', r'^(D3D11CreateDevice\w*|CreateDXGIFactory\w*|D3D\w+)$'),
    ('midi', r'^(midi(In|Out|Stream)\w*)$'),
    ('audio', r'^(waveOut\w+|waveIn\w+|acm\w+|timeBeginPeriod|timeGetTime)$'),
    ('registry', r'^(Reg(Open|Create|Query|Set|Close|Delete|Enum)\w*)$'),
    ('thread', r'^(CreateThread|_?beginthread\w*|CreateEvent\w*|WaitForSingleObject\w*|CreateMutex\w*|InitializeCriticalSection\w*)$'),
    ('file', r'^(CreateFile\w*|ReadFile|WriteFile|FindFirstFile\w*|CreateFileMapping\w*|MapViewOfFile)$'),
    ('com', r'^(CoCreateInstance\w*|CoInitialize\w*|OleInitialize)$'),
])
API_RE = {k: re.compile(v, re.I) for k, v in API.items()}

# 文字列証跡 (ASCII; bytes regex)
STR = collections.OrderedDict([
    ('sqlite', rb'SQLite format 3|sqlite3_[a-z_0-9]{3,30}|SQLite version [0-9.]+'),
    ('ffmpeg', rb'FFmpeg version [^\x00]{0,40}|libav(codec|format|util)-[0-9]+'),
    ('elastique', rb'.lastique[A-Za-z0-9 ._-]{0,40}'),
    ('zplane', rb'zplane[A-Za-z0-9 ._,@-]{0,40}'),
    ('openssl', rb'OpenSSL [0-9.]+[a-z]?'),
    ('libcurl', rb'libcurl/[0-9.]+'),
    ('zlib', rb'inflate [0-9.]+ Copyright|deflate [0-9.]+ Copyright'),
    ('libpng', rb'libpng version [0-9.]+'),
    ('FLAC', rb'reference libFLAC [0-9.]+'),
    ('vorbis', rb'Xiph.Org libVorbis [0-9.]+'),
    ('Bullet', rb'zbt[A-Z][A-Za-z0-9]+|btDiscreteDynamicsWorld|Bullet Physics[A-Za-z0-9. ]{0,10}'),
    ('ReWire', rb'ReWire[A-Za-z_]{0,30}|Propellerhead'),
    ('Razer', rb'Razer[A-Za-z _.]{0,30}|RzChroma[A-Za-z]*|Chroma ?SDK|RzSBStart|RzSB[A-Za-z]+'),
    ('VST/CLAP/AU', rb'VSTPluginMain|clap_entry|AudioUnit|VST3'),
    ('NDI', rb'NDIlib_[a-z_0-9]+'),
    ('Spout', rb'Spout[A-Za-z]{0,20}'),
    ('OpenGL', rb'wglCreateContext|wglGetProcAddress|glGetString'),
    ('Python', rb'python3[0-9]*\.dll|Py_[A-Za-z]{3,20}'),
    ('GoogleDrive', rb'googleapis[A-Za-z0-9./_-]{0,30}|drive\.google[A-Za-z0-9./_-]{0,20}'),
    ('FLCloud', rb'flcloud[A-Za-z0-9./_-]{0,30}|image-line\.com[A-Za-z0-9./_-]{0,30}'),
    ('DirectWave', rb'DirectWave[A-Za-z ]{0,20}'),
    ('ILVideo', rb'ILVid[eE]o_[A-Za-z]+'),
    ('RzChromaSDK', rb'RzChromaSDK[0-9]*\.dll'),
    ('ReWire.dll', rb'ReWire(Beta|Debug)?\.dll'),
])


def classify_imports(pe):
    cat = collections.OrderedDict((k, []) for k in API)
    dlls = collections.OrderedDict()
    delay = collections.OrderedDict()
    for ent, store in ((getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []), dlls), (getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', []), delay)):
        for d in ent:
            store[d.dll.decode().lower()] = len(d.imports)
            for imp in d.imports:
                nm = imp.name.decode() if imp.name else ''
                for k, rx in API_RE.items():
                    if rx.match(nm):
                        cat[k].append(nm)
    return dlls, delay, {k: sorted(set(v)) for k, v in cat.items() if v}


def facts(plugin, role, block):
    fn = os.path.join(EXT, 'block%05d_PE.bin' % block)
    d = open(fn, 'rb').read()
    pe = pefile.PE(data=d, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],
                                           pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT'],
                                           pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
    exp = [(e.name.decode() if e.name else '#%d' % e.ordinal) for e in getattr(getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', [])]
    dlls, delay, cat = classify_imports(pe)
    strs = {}
    # Delphi の string 定数は UTF-16LE なので、ASCII 文字列と UTF-16LE 文字列 (latin1 に落とす) の両方を走査する
    wide = b'\n'.join(m.group(0).decode('utf-16le').encode('latin1', 'replace') for m in re.finditer(rb'(?:[\x20-\x7e]\x00){4,}', d))
    hay = d + b'\n' + wide
    for k, rx in STR.items():
        c = collections.Counter(m.group(0)[:60].decode('latin1') for m in re.finditer(rx, hay))
        if c:
            strs[k] = {'hits': sum(c.values()), 'distinct': len(c), 'top': c.most_common(3)}
    return {'plugin': plugin, 'role': role, 'block': block, 'size': len(d), 'n_exports': len(exp), 'exports_head': exp[:8],
            'import_dlls': dlls, 'import_total': sum(dlls.values()), 'delay_dlls': delay, 'api': cat, 'strings': strs}


def main():
    out = [facts(*m) for m in MODULES]
    dst = os.path.join(P, 'work', 'hostx')
    os.makedirs(dst, exist_ok=True)
    jp = sys.argv[sys.argv.index('--json') + 1] if '--json' in sys.argv else os.path.join(dst, 'static.json')
    json.dump(out, open(jp, 'w'), indent=1, ensure_ascii=False)
    print('| plugin / role | block | size B | export | import 総数 | import DLL (非 kernel32/user32/gdi32 系の主要) | API 分類 (distinct 名) |')
    print('|---|--:|--:|--:|--:|---|---|')
    base = {'kernel32.dll', 'user32.dll', 'gdi32.dll', 'advapi32.dll', 'comctl32.dll', 'comdlg32.dll', 'shell32.dll', 'ole32.dll',
            'oleaut32.dll', 'version.dll', 'winspool.drv', 'api-ms-win-crt-string-l1-1-0.dll', 'shfolder.dll', 'imagehlp.dll', 'msacm32.dll'}
    for f in out:
        extra = ', '.join('%s:%d' % (k, v) for k, v in f['import_dlls'].items() if k not in base)
        ap = ', '.join('%s=%d' % (k, len(v)) for k, v in f['api'].items())
        print('| %s / %s | %d | %d | %d | %d | %s | %s |' % (f['plugin'], f['role'], f['block'], f['size'], f['n_exports'], f['import_total'], extra or '-', ap or '-'))
    print()
    print('| plugin / role | 文字列証跡 (種別: ヒット数 [上位 1 件]) |')
    print('|---|---|')
    for f in out:
        s = '; '.join('%s: %d hit / %d distinct [%s]' % (k, v['hits'], v['distinct'], v['top'][0][0]) for k, v in f['strings'].items())
        print('| %s / %s | %s |' % (f['plugin'], f['role'], s or '-'))


if __name__ == '__main__':
    main()
