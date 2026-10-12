#!/usr/bin/env python3
"""M11 image loader blob: FLEngine_x64.dll の .text/.data/.rdata/.didata を LVA (= RVA) 座標に敷いた生イメージ.
 m11_data_gen.py は .data/.rdata しか wasm に埋め込まない. Delphi は .text 内に定数表/InitTable/PackageInfo を
 置く (例: InitTable @RVA 0xf768b0) ため, .text も linear memory に必要 (無いと 0 読み → Count=0 で unit 初期化が空振りする).
 EULA 配慮: 実バイナリ由来のイメージは wasm に埋め込まず, 実行時にホストが work/m11_image.bin を読んで HEAPU8 に載せる.
 .reloc DIR64 の指す値 (image 内ポインタ) は VA→LVA (-0x400000) 補正する (m11_data_gen.py と同一規則).
 出力: work/m11_image.bin  (offset 0 = RVA 0)   使い方: python3 m11_image_gen.py"""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'shared'))
from paths import REPO_ROOT, FL_WIN64_DIR
sys.path.insert(0, os.path.join(REPO_ROOT, 'tools', 'm6'))
from ottlib import Bin
HERE = os.path.dirname(os.path.abspath(__file__))
WINF = os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
OUT = os.path.join(HERE, 'work', 'm11_image.bin')
KEEP = ('.text', '.data', '.rdata', '.didata')
IMG_BASE = 0x400000
b = Bin(WINF)
top = max(lo + len(d) for (n, lo, d) in b.sections if n in KEEP)
img = bytearray(top)
for (n, lo, d) in b.sections:
    if n in KEEP:
        img[lo:lo + len(d)] = d
relocs = []
for (n, lo, d) in b.sections:
    if n != '.reloc':
        continue
    i = 0
    while i + 8 <= len(d):
        page, blk = struct.unpack_from('<II', d, i)
        if blk < 8 or page == 0:
            break
        for k in range((blk - 8) // 2):
            e = struct.unpack_from('<H', d, i + 8 + k * 2)[0]
            if (e >> 12) == 10:
                relocs.append(page + (e & 0xfff))
        i += blk
fixed = 0
for r in relocs:
    if r + 8 <= top:
        v = struct.unpack_from('<Q', img, r)[0]
        if IMG_BASE < v < IMG_BASE + 0x1ac0000:
            struct.pack_into('<Q', img, r, v - IMG_BASE)
            fixed += 1
open(OUT, 'wb').write(img)
print('[image] %s: %d bytes (RVA 0..0x%x), reloc DIR64 %d / 補正 %d' % (OUT, len(img), top, len(relocs), fixed))
