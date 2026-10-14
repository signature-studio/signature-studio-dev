#!/usr/bin/env python3
"""FL Studio (fl-win64) の展開物から PE を列挙し、wrapper IID の 16 byte 列を走査する。

使い方:
  python3 host/fl_pe_iid_scan.py <extracted_dir> [<negative_control_pe>]

  <extracted_dir>: `tar --zstd -xf fl-win64.tar.zst` の展開先 (extracted/ を含む親)。
  手順: 1) extracted/ 以下の全ファイルを読み、先頭 MZ かつ e_lfanew 先が `PE\\0\\0` のものを PE とみなす。
        2) PE の Machine / SizeOfOptionalHeader から、セクション表がファイル内に収まることを確認する。
        3) IID の 16 byte を LE (記載どおり) / BE (GUID 各フィールドのバイト反転) の両方で検索する。
  negative control: <negative_control_pe> を指定すると、その PE の末尾 (オーバーレイ) に IID を
        LE / BE それぞれで書き足した複製を作り、同じ検索器がヒットすることを確認する (複製は一時ファイル)。
依存: 標準ライブラリのみ。
"""
import os
import shutil
import struct
import sys
import tempfile

IIDS = {
    'IVst3ToAUWrapper': 'C5C6B8A3 95C08846 B0916F0B B697AA44',
    'IVst3ToAAXWrapper': 'C69D316D C5604262 B32C951B 93BEF4C6',
}


def patterns(hex_str):
    raw = bytes.fromhex(hex_str.replace(' ', ''))
    be = b''.join(raw[i:i + 4][::-1] for i in range(0, 16, 4))
    return raw, be


def pe_valid(data):
    if len(data) < 0x40 or data[:2] != b'MZ':
        return False
    e = struct.unpack_from('<I', data, 0x3C)[0]
    if e + 24 > len(data) or data[e:e + 4] != b'PE\x00\x00':
        return False
    machine, nsec, _, _, _, opt_size, _ = struct.unpack_from('<HHIIIHH', data, e + 4)
    opt_off = e + 24
    sec_off = opt_off + opt_size
    if sec_off + nsec * 40 > len(data) or opt_size < 2:
        return False
    magic = struct.unpack_from('<H', data, opt_off)[0]
    if (machine, magic) not in ((0x8664, 0x20B), (0x14C, 0x10B)):
        return False
    for i in range(nsec):
        raw_size, raw_ptr = struct.unpack_from('<II', data, sec_off + i * 40 + 16)
        if raw_size and raw_ptr + raw_size > len(data):
            return False
    return True


def scan(root):
    files = 0
    mz = 0
    pe_paths = []
    for dp, _, fn in os.walk(root):
        for f in fn:
            p = os.path.join(dp, f)
            files += 1
            with open(p, 'rb') as fh:
                head = fh.read(2)
            if head != b'MZ':
                continue
            mz += 1
            with open(p, 'rb') as fh:
                data = fh.read()
            if pe_valid(data):
                pe_paths.append(p)
    return files, mz, sorted(pe_paths)


def count_hits(paths):
    out = {}
    for name, h in IIDS.items():
        le, be = patterns(h)
        n_le = n_be = 0
        for p in paths:
            with open(p, 'rb') as fh:
                data = fh.read()
            if le in data:
                n_le += 1
            if be in data:
                n_be += 1
        out[name] = (n_le, n_be)
    return out


def negative_control(pe_path):
    tmpdir = tempfile.mkdtemp()
    out = {}
    try:
        for idx, order in ((0, 'LE'), (1, 'BE')):
            dst = os.path.join(tmpdir, 'control_%s.bin' % order)
            shutil.copy(pe_path, dst)
            with open(dst, 'ab') as fh:
                for h in IIDS.values():
                    fh.write(patterns(h)[idx])
            out[order] = count_hits([dst])
        return out
    finally:
        shutil.rmtree(tmpdir)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    root = sys.argv[1]
    files, mz, pe_paths = scan(root)
    print('files under %s: %d' % (root, files))
    print('MZ-headed files: %d' % mz)
    print('valid PE files (PE sig + section table in-file): %d' % len(pe_paths))
    print('IID hits over valid PE files (files with hit: LE, BE):')
    for name, (n_le, n_be) in count_hits(pe_paths).items():
        print('  %s: LE=%d BE=%d' % (name, n_le, n_be))
    if len(sys.argv) >= 3:
        ctl = sys.argv[2]
        print('negative control (copy of %s with IIDs appended, one order at a time):' % os.path.basename(ctl))
        for order, res in negative_control(ctl).items():
            for name, (n_le, n_be) in res.items():
                n = n_le if order == 'LE' else n_be
                print('  wrote %s, %s: hits=%d' % (order, name, n))


if __name__ == '__main__':
    main()
