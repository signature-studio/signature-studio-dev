#!/usr/bin/env python3
"""FL Studio win64 NSIS(BI flags=0x30) installer header から、抽出済み blockNNNNN の元インストールパスを復元する。

Usage: recover_paths.py <installer.exe> <block_manifest.json> <out.json>
  - NSIS script(entries/strings) のみ LZMA 展開 (data block は触らない)
  - EW_EXTRACTFILE(20) の (outpath, name, data offset) と block_manifest.payload_off を突合
  - SetOutPath(EW_CREATEDIR 11, flag=1) を線形に追跡し $INSTDIR 相対パスを再構築
"""
import sys, struct, lzma, json, mmap, collections

exe, manifest_p, out_p = sys.argv[1:4]
f = open(exe, 'rb'); m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
base0 = m.find(bytes.fromhex('efbeadde') + b'NullsoftInst') - 4
pay = memoryview(m)[base0:]
u32 = lambda b, o: struct.unpack_from('<I', b, o)[0]
assert u32(pay, 0) == 0x30
HeaderSize = u32(pay, 0x14)
csz = u32(pay, 0x24)
assert csz & (1 << 31)
csz &= ~(1 << 31)
props = bytes(pay[0x28:0x2d])
dict_size = struct.unpack_from('<I', props, 1)[0]
D = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{'id': lzma.FILTER_LZMA1, 'dict_size': dict_size, 'lc': 3, 'lp': 0, 'pb': 2}])
HDR = D.decompress(bytes(pay[0x2d:0x28 + csz]))
assert len(HDR) == HeaderSize, (len(HDR), HeaderSize)
DATA_BASE = 0x28 + csz  # first data block (payload-relative) = 0x61EB2
print('header', len(HDR), 'data_base', hex(DATA_BASE))

uth = lambda o: u32(HDR, o)
BH = [(uth(4 + 8 * k), uth(4 + 8 * k + 4)) for k in range(8)]
ent_off, ent_num = BH[2]
str_off = BH[3][0]
lang_off = BH[4][0]

def string_at(pos):
    # NSIS-3 Unicode string; special codes 1=lang 2=shell 3=var 4=skip
    b = bytes(HDR[str_off + 2 * pos: str_off + 2 * pos + 4096])
    w = [struct.unpack_from('<H', b, i)[0] for i in range(0, len(b) - 1, 2)]
    out = []; i = 0
    while i < len(w):
        c = w[i]; i += 1
        if c == 0: break
        if c <= 4 and i < len(w):
            n = w[i]; i += 1
            if c == 4: out.append(chr(n)); continue
            if c == 3:
                v = (n & 0x7F) | (((n >> 8) & 0x7F) << 7)
                out.append('${v%d}' % v); continue
            if c == 2:
                out.append('${shell:%d,%d}' % (n & 0xFF, n >> 8)); continue
            if c == 1:
                out.append('${lang}'); continue
        out.append(chr(c))
    return ''.join(out)

VARNAME = {20: 'CMDLINE', 21: 'INSTDIR', 22: 'OUTDIR', 23: 'EXEDIR', 24: 'LANGUAGE', 25: 'TEMP', 26: 'PLUGINSDIR'}
def norm(s):
    for k, v in VARNAME.items():
        s = s.replace('${v%d}' % k, '$' + v)
    return s

stride = (BH[3][0] - ent_off) // ent_num
print('BH', [(hex(o), n) for o, n in BH], 'entry stride', stride, (BH[3][0] - ent_off) % ent_num)
NP = stride // 4
stride = (BH[3][0] - ent_off) // ent_num
NP = stride // 4
ents = [struct.unpack_from('<%dI' % NP, HDR, ent_off + stride * i) for i in range(ent_num)]

import re
outdir = '$INSTDIR'
base = '$INSTDIR'          # ${v31} = $_OUTDIR: SetOutPath 文字列が ${v31} を含まないとき更新される基準 dir
rows = []
for i, e in enumerate(ents):
    op = e[0]
    if op == 11 and e[2] == 1:   # SetOutPath = EW_CREATEDIR(update_outdir=1)
        s_ = norm(string_at(e[1]))
        if '${v31}' in s_:
            outdir = s_.replace('${v31}', base)
        else:
            outdir = base = s_
    elif op == 20:               # File = EW_EXTRACTFILE; off = lo | hi<<32 (BI LongOffset); data base = DATA_BASE
        name = norm(string_at(e[2]))
        rows.append(dict(entry=i, outdir=outdir, name=name, payload_off=DATA_BASE + (e[3] | (e[4] << 32))))

man = json.load(open(manifest_p))
by_off = {int(m['payload_off'], 16): m for m in man}
res = {}
for r in rows:
    m = by_off[r['payload_off']]
    if re.match(r'^\$[A-Z]+\\', r['name']): full = r['name']
    else: full = r['outdir'] + '\\' + r['name']
    res.setdefault(m['idx'], []).append(full)
out = {'%05d' % idx: sorted(set(p)) for idx, p in res.items()}
json.dump(out, open(out_p, 'w'), indent=0, ensure_ascii=False)
print('blocks with path', len(out), '/', len(man), ' multi-dest blocks', sum(1 for v in out.values() if len(v) > 1))
