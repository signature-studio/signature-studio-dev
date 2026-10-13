#!/usr/bin/env python3
# #742: REPORT_LEA.md L-3 の x87 突合表を再現する。 指定 PE の各 VA について
#   func_bounded   = f80_split.x87_of (.pdata の関数終端、無ければ ret まで。 range 外は None)
#   old_range_400B = 旧方式相当 (va から 0x400 B を固定で逆アセンブル、pdata も ret も使わない)
# の x87 mnemonic を出す。 [] = 検査済みで x87 なし、None = range 外で未検査。
#   python3 sampler/x87_check.py <PE> <VA> [<VA> ...]   (VA は 16 進)
import sys
import capstone, pefile
from f80_split import func_ends, x87_of

def old_range_400b(pe, base, md, va):
    code = pe.get_data(va - base, 0x400)
    return sorted({i.mnemonic for i in md.disasm(code, va) if i.mnemonic.startswith('f')})

def main():
    pe_path, vas = sys.argv[1], [int(v, 16) for v in sys.argv[2:]]
    pe = pefile.PE(pe_path, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
    base = pe.OPTIONAL_HEADER.ImageBase
    ends = func_ends(pe, base)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    print(f'PE={pe_path} ImageBase=0x{base:x} pdata_funcs={len(ends)}')
    for va in vas:
        rng = [(va, ends[va] if va in ends else va + 0x400)]
        print(f'0x{va:x} in_pdata={va in ends} func_bounded={x87_of(pe, base, md, rng, va, ends)} '
              f'old_range_400B={old_range_400b(pe, base, md, va)}')

if __name__ == '__main__':
    main()
