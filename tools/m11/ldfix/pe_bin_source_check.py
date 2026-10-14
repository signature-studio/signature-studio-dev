#!/usr/bin/env python3
# pe_bin_source_check.py: bin 表 k184/185/186/215/236 の P 値が PE 上のどこに入っているかを照合する (#942 受入 1・2)。
# 使い方: tools/m11/ldfix/work/venv/bin/python tools/m11/ldfix/pe_bin_source_check.py [PE_PATH]
#   (pefile が必要。既定 PE は $FL_WIN64_DIR/extracted/block00031_PE.bin)
# 出力: 各 P 生値 (+0x400000 補正後) の PE 出現 section/RVA と、その RVA が .reloc DIR64 対象か。
import os
import struct
import sys

import pefile

PE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block00031_PE.bin')
PE_IMAGE_BASE = 0x400000
# (k, m11_image 上の P 値 = VA - ImageBase)。REPORT_942_APPENDIX §12 の値。
CASES = [(184, 0x7a50), (185, 0x8040), (186, 0x8870), (215, 0xee), (236, 0xa027)]

pe = pefile.PE(PE, fast_load=False)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_BASERELOC']])
data = pe.__data__

dir64_rvas = set()
for block in getattr(pe, 'DIRECTORY_ENTRY_BASERELOC', []):
    for entry in block.entries:
        if entry.type == pefile.RELOCATION_TYPE['IMAGE_REL_BASED_DIR64']:
            dir64_rvas.add(block.struct.VirtualAddress + entry.struct.Offset if hasattr(entry.struct, 'Offset') else entry.rva)

print('PE:', PE)
print('ImageBase: 0x%x' % pe.OPTIONAL_HEADER.ImageBase)
for k, p in CASES:
    for cand in sorted({p, p + PE_IMAGE_BASE}):
        pat = struct.pack('<Q', cand)
        i = data.find(pat)
        hits = []
        while i != -1 and len(hits) < 4:
            for s in pe.sections:
                if s.PointerToRawData <= i < s.PointerToRawData + s.SizeOfRawData:
                    rva = s.VirtualAddress + i - s.PointerToRawData
                    name = s.Name.rstrip(b'\0').decode(errors='replace')
                    hits.append('raw=0x%x sec=%s rva=0x%x reloc_dir64=%s' % (i, name, rva, rva in dir64_rvas))
                    break
            i = data.find(pat, i + 1)
        print('k%d P=0x%x 値 0x%x: %s' % (k, p, cand, '; '.join(hits) or 'なし'))
