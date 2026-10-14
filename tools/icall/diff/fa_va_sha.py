#!/usr/bin/env python3
"""fa_va_sha.py — 2 つの PE の同じ VA 範囲の bytes を sha256 で照合する (ICALL-80 #2675)。
用法: python3 tools/icall/diff/fa_va_sha.py <PE_A> <PE_B> <VA_LO> <VA_HI>   (VA は 16 進・VA_HI は排他的)
既定の対象 (REPORT_APPENDIX_2675.md): SlateCore.core_64 (plugins-freshair) と rw.dll (work-icall) の 181057b38 181057c05 (205 B)。
出力: 各 PE の ImageBase・file offset・sha256 と判定。不一致なら最初の差分 offset。終了 0 = 一致 / 1 = 不一致。"""
import hashlib, sys
import pefile

def raw_range(path, lo, hi):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    off = pe.get_offset_from_rva(lo - base)
    data = open(path, 'rb').read()[off:off + (hi - lo)]
    assert len(data) == hi - lo, '%s: VA 範囲が 1 セクションに収まらない' % path
    return base, off, data

if __name__ == '__main__':
    pa, pb = sys.argv[1], sys.argv[2]
    lo, hi = int(sys.argv[3], 16), int(sys.argv[4], 16)
    ra, rb = raw_range(pa, lo, hi), raw_range(pb, lo, hi)
    for p, (base, off, d) in ((pa, ra), (pb, rb)):
        print('%s  ImageBase=%#x  fileoff=%#x  size=%d  sha256=%s' % (p, base, off, len(d), hashlib.sha256(d).hexdigest()))
    diff = [k for k, (x, y) in enumerate(zip(ra[2], rb[2])) if x != y]
    if diff:
        print('first diff at +%d (VA %#x)' % (diff[0], lo + diff[0]))
    same = ra[2] == rb[2]
    print('一致' if same else '不一致')
    sys.exit(0 if same else 1)
