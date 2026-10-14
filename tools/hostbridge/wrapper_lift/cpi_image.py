#!/usr/bin/env python3
"""cpi_image.py: PE の mapped image を out に書き、ImageBase を 16 進で標準出力する (#829 受入 2)。

x64c_wrapper.py は SHIFT=0 (VA をそのまま linear address に使う) で生成するため、この image を wasm の同じ VA に敷く。
usage: cpi_image.py <block.bin> <out.bin>   (stdout 例: 0x400000)
"""
import sys

import pefile

pe = pefile.PE(sys.argv[1])
with open(sys.argv[2], "wb") as fh:
    fh.write(pe.get_memory_mapped_image())
print(hex(pe.OPTIONAL_HEADER.ImageBase))
