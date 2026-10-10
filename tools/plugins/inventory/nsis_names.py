#!/usr/bin/env python3
"""NSIS (Image-Line BI 拡張) ヘッダ解析 → block idx ↔ インストール先パス の対応表を作る。

win64 の extracted/blockNNNNN_*.bin にはパスが無いので、インストーラ内部スクリプト
(EW_CREATEDIR=SetOutPath / EW_EXTRACTFILE=File) をデコードして復元する。
実測した BI 拡張の構造:
  - entry = 9 x int32 (opcode + 8 param)  [標準 NSIS3 の 7 x int32 ではない]
  - EW_EXTRACTFILE(20): p[1]=flags, p[2]=name(string idx, UTF-16 char 単位), p[3]=data offset
    (data base = payload+0x61eb2 からの相対値 = block_manifest.payload_off - 0x61eb2)
  - EW_CREATEDIR(11): p[1]=path(string idx), p[2]=1 なら SetOutPath
出力: work/nsis_blockmap.json  [{idx, rel, outpath, name, path}]
"""
import lzma, struct, json, os, sys, collections

EXE = os.path.expanduser('~/ダウンロード/flstudio_win64_26.1.7.5653.exe')
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, '..', 'work')
OUT = os.path.join(WORK, 'nsis_blockmap.json')
MANIFEST = '/home/ubuntu/work/analysis/win64/block_manifest.json'
DATA0 = 0x61eb2
ES = 36

VARS = {21: '$INSTDIR', 22: '$OUTDIR', 23: '$EXEDIR', 24: '$LANGUAGE', 20: '$CMDLINE'}


def load_header():
    cache = os.path.join(WORK, 'nsis_header.bin')
    if os.path.exists(cache):
        return open(cache, 'rb').read()
    d = open(EXE, 'rb').read()
    i = d.find(b'\xef\xbe\xad\xde' + b'NullsoftInst')
    hdr_size = struct.unpack_from('<I', d, i + 16)[0]
    csz = struct.unpack_from('<I', d, i + 32)[0] & 0x7fffffff
    props = d[i + 36]
    dict_size = struct.unpack_from('<I', d, i + 37)[0]
    dec = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[
        {'id': lzma.FILTER_LZMA1, 'dict_size': dict_size, 'lc': props % 9, 'lp': (props // 9) % 5, 'pb': props // 45}])
    hdr = dec.decompress(d[i + 41: i + 36 + csz], max_length=hdr_size)
    os.makedirs(WORK, exist_ok=True)
    open(cache, 'wb').write(hdr)
    return hdr


class Strs:
    def __init__(self, hdr, off):
        self.hdr, self.off = hdr, off

    def get(self, p):
        i = self.off + p * 2
        out = []
        h = self.hdr
        while i + 1 < len(h):
            c = struct.unpack_from('<H', h, i)[0]
            i += 2
            if c == 0:
                break
            if c in (1, 2, 3, 4) and i + 1 < len(h):  # NS_LANG/SHELL/VAR/SKIP + WORD
                v = struct.unpack_from('<H', h, i)[0]
                i += 2
                idx = (v & 0x7f) | (((v >> 8) & 0x7f) << 7)
                if c == 3:
                    out.append(VARS.get(idx, '$V%d' % idx))
                elif c == 2:
                    out.append('$SHELL%d' % idx)
                elif c == 1:
                    out.append('$LANG%d' % idx)
                else:
                    pass
                continue
            out.append(chr(c))
            if len(out) > 400:
                break
        return ''.join(out)


def main():
    hdr = load_header()
    blocks = [struct.unpack_from('<II', hdr, 4 + 8 * k) for k in range(8)]
    ent_off, n_ent = blocks[2]
    S = Strs(hdr, blocks[3][0])
    M = {int(m['payload_off'], 16) - DATA0: m for m in json.load(open(MANIFEST))}
    outdir = ''
    rows = []
    seen = set()
    for k in range(n_ent):
        e = struct.unpack_from('<9i', hdr, ent_off + ES * k)
        if e[0] == 11 and e[2] == 1:
            outdir = S.get(e[1])
        elif e[0] == 20:
            name = S.get(e[2])
            rel = e[3]
            m = M.get(rel)
            rows.append({'idx': m['idx'] if m else None, 'rel': rel, 'outdir': outdir, 'name': name,
                         'kind': m['kind'] if m else None, 'dsize': m['dsize'] if m else None})
            if m:
                seen.add(m['idx'])
    json.dump(rows, open(OUT, 'w'), indent=0, ensure_ascii=False)
    print('extract entries', len(rows), 'mapped to blocks', len(seen), 'of', len(M))
    od = collections.Counter(r['outdir'] for r in rows)
    print('distinct outdirs', len(od))
    for k, v in od.most_common(15):
        print(v, k)


if __name__ == '__main__':
    main()
