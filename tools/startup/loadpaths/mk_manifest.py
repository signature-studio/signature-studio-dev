#!/usr/bin/env python3
"""block_manifest.json が無い環境 (Actions) 用: NSIS(BI) インストーラのデータ領域を先頭から順に歩いて
blockNNNNN (idx = 歩行順) ↔ payload_off の対応表を再構成する。

Usage: mk_manifest.py <installer.exe> <out_block_manifest.json> [<extracted_dir>]
  - 各 block = u32 ヘッダ (bit31=LZMA 圧縮, 下位 31bit = 以降の長さ) + 本体。連続配置。
  - 出力 = [{"idx": n, "payload_off": "0x..."}] (recover_paths.py が読む形式。payload_off は payload 先頭からの絶対値)
  - extracted_dir を渡すと、先頭 80 + 乱数 120 block を LZMA 展開して抽出済み blockNNNNN_* とバイト一致を検査する
    (不一致なら exit 1)。
"""
import sys, struct, lzma, json, mmap, os, re, random

exe, out_p = sys.argv[1:3]
ext = sys.argv[3] if len(sys.argv) > 3 else None
f = open(exe, 'rb'); m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
base0 = m.find(bytes.fromhex('efbeadde') + b'NullsoftInst') - 4
pay = memoryview(m)[base0:]
u32 = lambda b, o: struct.unpack_from('<I', b, o)[0]
assert u32(pay, 0) == 0x30
data_base = 0x28 + (u32(pay, 0x24) & 0x7fffffff)
total = len(pay)

walk = []
p = data_base
while p + 8 <= total:
    n = u32(pay, p) & 0x7fffffff
    if p + 4 + n > total - 4:
        break
    walk.append(p)
    p += 4 + n
json.dump([{'idx': i, 'payload_off': hex(o)} for i, o in enumerate(walk)], open(out_p, 'w'))
print('blocks', len(walk), 'data_base', hex(data_base), 'walk end', hex(p), 'payload size', hex(total))


def read_block(o):
    n = u32(pay, o)
    comp, n = bool(n & 0x80000000), n & 0x7fffffff
    if not comp:
        return bytes(pay[o + 4:o + 4 + n])
    props = pay[o + 4]
    ds = struct.unpack_from('<I', pay, o + 5)[0]
    d = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{
        'id': lzma.FILTER_LZMA1, 'dict_size': ds, 'lc': props % 9, 'lp': (props // 9) % 5, 'pb': props // 45}])
    return d.decompress(bytes(pay[o + 9:o + 4 + n]))


if ext:
    files = {}
    for fn in os.listdir(ext):
        mm = re.match(r'block(\d{5})_', fn)
        if mm:
            files[int(mm.group(1))] = fn
    assert len(files) == len(walk), (len(files), len(walk))
    rnd = random.Random(2)
    chk = list(range(80)) + rnd.sample(range(len(walk)), 120)
    bad = [i for i in chk if open(os.path.join(ext, files[i]), 'rb').read() != read_block(walk[i])]
    print('verify', len(chk), 'blocks, mismatch', len(bad))
    sys.exit(1 if bad else 0)
