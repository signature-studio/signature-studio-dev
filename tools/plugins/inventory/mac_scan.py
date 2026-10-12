#!/usr/bin/env python3
"""mac 側 Fruity プラグイン 141 種の実測インベントリ (work/mac_scan.json)。

各プラグインフォルダ: ファイル一覧/拡張子別集計、Mach-O 全てを自前パーサで解析
(fat → 各スライス: arch/size/__text/関数数(LC_FUNCTION_STARTS)/export/undefined import/
load dylib/コンパイラ判定文字列)。
"""
import os, sys, json, struct, re, collections, hashlib
from multiprocessing import Pool

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_MAC_DIR  # noqa: E402
ROOT = os.path.join(FL_MAC_DIR, 'pkg_extract', 'payload_out', 'Applications', 'FL Studio 2026.app', 'Contents', 'Resources', 'FL', 'Plugins', 'Fruity')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'work', 'mac_scan.json')

CPU = {0x01000007: 'x86_64', 0x0100000c: 'arm64', 7: 'i386'}
LC_SEGMENT_64, LC_SYMTAB, LC_DYSYMTAB = 0x19, 2, 0xb
LC_LOAD_DYLIB, LC_LOAD_WEAK, LC_REEXPORT, LC_ID_DYLIB = 0xc, 0x80000018, 0x8000001f, 0xd
LC_RPATH, LC_FUNCTION_STARTS = 0x8000001c, 0x26
LC_BUILD_VERSION, LC_VERSION_MIN = 0x32, 0x24
LC_UUID = 0x1b


def uleb(b, i):
    r = s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7f) << s
        s += 7
        if not x & 0x80:
            return r, i


def parse_trie(b):
    out = []
    stack = [(0, '')]
    seen = set()
    while stack:
        off, pre = stack.pop()
        if off in seen and not pre:
            continue
        if off >= len(b):
            continue
        tl, i = uleb(b, off)
        if tl:
            out.append(pre)
        n = b[i + tl] if tl else b[i]
        i = i + tl if tl else i
        i += 1
        for _ in range(n):
            j = i
            while b[j]:
                j += 1
            lab = b[i:j].decode('latin1')
            j += 1
            child, j = uleb(b, j)
            stack.append((child, pre + lab))
            i = j
    return out


def parse_slice(d, base, size):
    sl = d[base: base + size]
    magic, cpu, sub, ft, ncmds, sizeofcmds, flags = struct.unpack_from('<IiiIIII', sl, 0)
    r = {'arch': CPU.get(cpu & 0xffffffff if cpu < 0 else cpu, hex(cpu)), 'size': size, 'filetype': ft,
         'deps': [], 'weak_deps': [], 'rpaths': [], 'segments': [], 'sections': {}}
    off = 32
    symoff = nsyms = stroff = strsize = fs_off = fs_size = 0
    trie = (0, 0)
    for _ in range(ncmds):
        cmd, csz = struct.unpack_from('<II', sl, off)
        if cmd == LC_SEGMENT_64:
            segname = sl[off + 8: off + 24].rstrip(b'\0').decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', sl, off + 24)
            nsect = struct.unpack_from('<I', sl, off + 64)[0]
            r['segments'].append((segname, vmsize, filesize))
            so = off + 72
            for _s in range(nsect):
                sn = sl[so: so + 16].rstrip(b'\0').decode()
                sg = sl[so + 16: so + 32].rstrip(b'\0').decode()
                addr, sz = struct.unpack_from('<QQ', sl, so + 32)
                r['sections']['%s,%s' % (sg, sn)] = sz
                so += 80
        elif cmd in (LC_LOAD_DYLIB, LC_LOAD_WEAK, LC_REEXPORT):
            nameoff = struct.unpack_from('<I', sl, off + 8)[0]
            nm = sl[off + nameoff: off + csz].split(b'\0')[0].decode()
            (r['weak_deps'] if cmd == LC_LOAD_WEAK else r['deps']).append(nm)
        elif cmd == LC_ID_DYLIB:
            nameoff = struct.unpack_from('<I', sl, off + 8)[0]
            r['id'] = sl[off + nameoff: off + csz].split(b'\0')[0].decode()
        elif cmd == LC_RPATH:
            nameoff = struct.unpack_from('<I', sl, off + 8)[0]
            r['rpaths'].append(sl[off + nameoff: off + csz].split(b'\0')[0].decode())
        elif cmd == LC_SYMTAB:
            symoff, nsyms, stroff, strsize = struct.unpack_from('<IIII', sl, off + 8)
        elif cmd in (0x80000022, 0x22):
            trie = struct.unpack_from('<II', sl, off + 40)
        elif cmd == 0x80000033:
            trie = struct.unpack_from('<II', sl, off + 8)
        elif cmd == LC_FUNCTION_STARTS:
            fs_off, fs_size = struct.unpack_from('<II', sl, off + 8)
        elif cmd == LC_BUILD_VERSION:
            plat, minos, sdk = struct.unpack_from('<III', sl, off + 8)
            r['minos'] = '%d.%d' % (minos >> 16, (minos >> 8) & 0xff)
            r['sdk'] = '%d.%d' % (sdk >> 16, (sdk >> 8) & 0xff)
        elif cmd == LC_VERSION_MIN:
            v, s = struct.unpack_from('<II', sl, off + 8)
            r['minos'] = '%d.%d' % (v >> 16, (v >> 8) & 0xff)
            r['sdk'] = '%d.%d' % (s >> 16, (s >> 8) & 0xff)
        off += csz
    exports, undef = [], []
    for k in range(nsyms):
        n_strx, n_type, n_sect, n_desc, n_value = struct.unpack_from('<IBBHQ', sl, symoff + 16 * k)
        if n_type & 0xe0:  # stab
            continue
        nm = sl[stroff + n_strx: stroff + n_strx + 200].split(b'\0')[0].decode('latin1')
        if (n_type & 0x0e) == 0 and (n_type & 1):  # N_UNDF|N_EXT
            undef.append((nm, (n_desc >> 8) & 0xff))
        elif (n_type & 1) and (n_type & 0x0e) == 0x0e:
            exports.append(nm)
    if trie[1]:
        exports = sorted(set(exports) | set(parse_trie(sl[trie[0]: trie[0] + trie[1]])))
    r['exports'] = exports
    r['nsyms'] = nsyms
    r['undef'] = undef
    nf = 0
    if fs_size:
        blob = sl[fs_off: fs_off + fs_size]
        i = 0
        while i < len(blob):
            v, i = uleb(blob, i)
            if v == 0:
                break
            nf += 1
    r['nfuncs'] = nf
    r['text'] = r['sections'].get('__TEXT,__text', 0)
    # compiler hints (strings in this slice)
    r['fpc'] = ''
    m = re.search(rb'FPC [0-9][0-9.]+ \[[0-9/]+\] for [a-z0-9_]+ - [A-Za-z]+', sl)
    if m:
        r['fpc'] = m.group(0).decode()
    r['hints'] = [k for k, pat in HINTS.items() if pat in sl]
    r['fruity_classes'] = sorted(set(x.decode() for x in re.findall(rb'\x00(TDelphiFruityPlug[A-Za-z]*|TFruityPlug[A-Za-z]*)\x00', sl)))
    m = re.search(rb'/Users/imageline/[ -~]{0,240}\.(?:dylib|framework)', sl)
    r['build_path'] = m.group(0).decode() if m else ''
    return r


HINTS = {
    'objc': b'objc_msgSend',
    'libcxx': b'libc++',
    'FP_DelphiPlug': b'FP_DelphiPlug',
    'ippv2': b'dsp_ippv2',
    'elastique': b'elastique',
    'sqlite': b'sqlite3_open',
    'ffmpeg': b'libavcodec',
    'zge': b'ZGameEditor',
    'python': b'Python.framework',
    'wk_webview': b'WKWebView',
    'coremidi': b'MIDIClientCreate',
    'vst': b'VSTPluginMain',
    'AU': b'AudioComponent',
    'curl': b'NSURLSession',
}


def parse_macho(path):
    d = open(path, 'rb').read()
    out = {'file': os.path.basename(path), 'size': len(d), 'slices': {}}
    magic = struct.unpack_from('>I', d, 0)[0]
    if magic == 0xcafebabe:
        n = struct.unpack_from('>I', d, 4)[0]
        for i in range(n):
            cpu, sub, off, sz, al = struct.unpack_from('>iiIII', d, 8 + 20 * i)
            s = parse_slice(d, off, sz)
            out['slices'][s['arch']] = s
    elif struct.unpack_from('<I', d, 0)[0] == 0xfeedfacf:
        s = parse_slice(d, 0, len(d))
        out['slices'][s['arch']] = s
    else:
        return None
    return out


def is_macho(path):
    try:
        with open(path, 'rb') as f:
            m = f.read(4)
        return m in (b'\xca\xfe\xba\xbe', b'\xcf\xfa\xed\xfe')
    except Exception:
        return False


def scan_plugin(args):
    kind, name = args
    base = os.path.join(ROOT, kind, name)
    files = []
    exts = collections.Counter()
    esz = collections.Counter()
    machos = []
    tot = 0
    for dp, dn, fn in os.walk(base):
        for f in fn:
            p = os.path.join(dp, f)
            if os.path.islink(p):
                continue
            sz = os.path.getsize(p)
            tot += sz
            rel = os.path.relpath(p, base)
            ext = os.path.splitext(f)[1].lower() or '(none)'
            exts[ext] += 1
            esz[ext] += sz
            files.append((rel, sz))
            if (ext in ('.dylib', '', '.so', '.vst', '.component') or '/MacOS/' in p) and sz > 1024 and is_macho(p):
                m = parse_macho(p)
                if m:
                    m['rel'] = rel
                    machos.append(m)
    nfo = ''
    p = os.path.join(base, 'Plugin.nfo')
    if os.path.exists(p):
        nfo = open(p, 'rb').read().decode('latin1').strip()
    return {'kind': kind, 'name': name, 'total_bytes': tot, 'nfiles': len(files), 'ext_counts': dict(exts),
            'ext_bytes': dict(esz), 'files': files, 'machos': machos, 'nfo': nfo}


def main():
    jobs = []
    for kind in ('Effects', 'Generators'):
        for n in sorted(os.listdir(os.path.join(ROOT, kind))):
            if os.path.isdir(os.path.join(ROOT, kind, n)):
                jobs.append((kind, n))
    with Pool(12) as p:
        res = p.map(scan_plugin, jobs, chunksize=1)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, 'w'))
    nm = sum(len(r['machos']) for r in res)
    print('plugins', len(res), 'machos', nm, '->', os.path.normpath(OUT))


if __name__ == '__main__':
    main()
