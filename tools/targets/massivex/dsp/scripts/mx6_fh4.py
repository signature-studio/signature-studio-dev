#!/usr/bin/env python3
"""MX-6 (#1123) U4a: __CxxFrameHandler4 の FuncInfo4 の固定部を読み、全 entry で検証する。

構造は MSVC 公式記事 "Making C++ Exception Handling Smaller On x64" (C++ Team Blog, 2019-03-07) の
FuncInfo4 定義に従う (ehdata4_export.h の抜粋):
  header (1 byte): bit0 isCatch / bit1 isSeparated / bit2 BBT / bit3 UnwindMap / bit4 TryBlockMap /
                   bit5 EHs / bit6 NoExcept / bit7 reserved
  bbtFlags (可変長・BBT のとき) → dispUnwindMap (4B・UnwindMap のとき) → dispTryBlockMap (4B・TryBlockMap のとき)
  → dispIPtoStateMap (4B・常に) → dispFrame (可変長・isCatch のとき・末尾)
未解明 (本スクリプトは扱わない): 可変長整数の符号化、unwind map / try map / IP map の中身、funclet RVA の取り出し。

usage: mx6_fh4.py <pe> <out.json>        (census: 1 本目 .pdata の FH4 entry 全数)
       mx6_fh4.py --selftest <pe>        (NC: 1 件の RVA を壊すと FAIL することを数値で示す)
"""
import bisect
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pefile  # noqa: E402
from mx6_pdata_eh import make_rva_reader, walk_imports, EHANDLER, UHANDLER  # noqa: E402

BITS = ('isCatch', 'isSeparated', 'BBT', 'UnwindMap', 'TryBlockMap', 'EHs', 'NoExcept', 'reserved')


def parse_header(h):
    return {n: (h >> i) & 1 for i, n in enumerate(BITS)}


def fixed_fields(rd, fi):
    """FuncInfo4 の固定部のポインタ位置 {name: (offset, value)}。BBT が立つと bbtFlags (可変長) の長さが
    分からず位置が決まらないので None を返す。isCatch の dispFrame は末尾なので固定部に影響しない。"""
    hb = rd(fi, 1)
    if hb is None:
        return None, None
    hd = parse_header(hb[0])
    if hd['BBT']:
        return hd, None
    out = {}
    off = 1
    names = []
    if hd['UnwindMap']:
        names.append('dispUnwindMap')
    if hd['TryBlockMap']:
        names.append('dispTryBlockMap')
    names.append('dispIPtoStateMap')
    for n in names:
        b = rd(fi + off, 4)
        if b is None:
            return hd, None
        out[n] = (off, int.from_bytes(b, 'little'))
        off += 4
    return hd, out


def validate(rd, fi, in_image):
    """固定部の検査 (独立した 3 条件): (a) 固定部が読める (BBT なし) (b) 各ポインタが画像内 (c) ポインタの順序が
    構造の並び (dispUnwindMap < dispTryBlockMap < dispIPtoStateMap は必須ではないが、各ポインタは重ならない)。
    戻り値は違反の list (空なら OK)。"""
    hd, f = fixed_fields(rd, fi)
    if hd is None:
        return ['header_unreadable'], None, None
    if f is None:
        return ['fixed_part_unresolved(BBT)' if hd['BBT'] else 'pointer_unreadable'], hd, None
    probs = []
    for n, (o, v) in f.items():
        if not in_image(v):
            probs.append('%s_outside_image' % n)
    vals = sorted(v for (_, v) in f.values())
    if len(set(vals)) != len(vals):
        probs.append('pointer_duplicate')
    return probs, hd, f


def image_checker(pe):
    secs = [(s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData)) for s in pe.sections]

    def in_image(rva):
        return any(va <= rva < va + n for va, n in secs)
    return in_image


def fh4_entries(pe, data, rd):
    base = pe.OPTIONAL_HEADER.ImageBase
    iat = walk_imports(rd, pe.OPTIONAL_HEADER.DATA_DIRECTORY[1].VirtualAddress)
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    praw = pdata.get_data()
    rows = []
    for i in range(0, len(praw) - 11, 12):
        st, e, ui = (int.from_bytes(praw[i + j:i + j + 4], 'little') for j in (0, 4, 8))
        if not (st and e > st):
            continue
        hdr = rd(ui, 4)
        if hdr is None or hdr == b'\0\0\0\0':
            continue
        flags = hdr[0] >> 3
        if not flags & (EHANDLER | UHANDLER):
            continue
        cnt = hdr[2]
        hoff = 4 + 2 * ((cnt + 1) & ~1)
        hb = rd(ui + hoff, 8)
        h = int.from_bytes(hb[0:4], 'little')
        code = rd(h, 6) or b''
        name = 'direct'
        if code[:2] == b'\xff\x25':
            slot = h + 6 + int.from_bytes(code[2:6], 'little', signed=True)
            name = iat.get(slot, 'iat?')
        if name.endswith('__CxxFrameHandler4'):
            rows.append((st, e, int.from_bytes(hb[4:8], 'little')))
    return base, rows


def census(pe_path):
    pe = pefile.PE(pe_path, fast_load=False)
    data = open(pe_path, 'rb').read()
    rd = make_rva_reader(pe, data)
    in_image = image_checker(pe)
    base, rows = fh4_entries(pe, data, rd)
    bits = collections.Counter()
    probs = collections.Counter()
    fi_set = set()
    ptr_after = collections.Counter()
    for st, e, fi in rows:
        fi_set.add(fi)
        pr, hd, f = validate(rd, fi, in_image)
        for p in pr:
            probs[p] += 1
        if hd is None:
            continue
        bits[','.join(k for k in BITS if hd[k]) or '-'] += 1
        if f:
            for n, (o, v) in f.items():
                if n == 'dispIPtoStateMap' and not hd['UnwindMap'] and not hd['TryBlockMap']:
                    ptr_after['IP_at_fi+5' if v == fi + 5 else 'IP_elsewhere'] += 1
                if n == 'dispUnwindMap':
                    ptr_after['unwind_at_fi+9' if v == fi + 9 else ('unwind_forward' if v > fi else 'unwind_backward_or_shared')] += 1
    res = {
        'fh4_entries': len(rows),
        'fh4_fi_distinct': len(fi_set),
        'header_bit_sets': dict(bits.most_common()),
        'fixed_part_problems': dict(probs),
        'pointer_position_census': dict(ptr_after),
    }
    return pe, rd, in_image, rows, res


KNOWN_OPEN = 2  # 画像外の dispUnwindMap を持つ 2 件 (原因未確定・REPORT_MX6 §8)


def selftest(pe_path):
    pe, rd, in_image, rows, res = census(pe_path)
    ok = []
    # 正例: 2,542 件のうち既知の 2 件以外は固定部が読めて画像内を指す (既知 2 件は dispUnwindMap のみ画像外)
    fp = res['fixed_part_problems']
    ok.append(('positive: 2542 entries, only the %d known dispUnwindMap-outside-image remain' % KNOWN_OPEN,
               res['fh4_entries'] == 2542 and set(fp) == {'dispUnwindMap_outside_image'} and fp['dispUnwindMap_outside_image'] == KNOWN_OPEN))
    # 負例: 問題の無い 1 件の dispIPtoStateMap を画像外 (0) に壊すと FAIL する
    st, e, fi = next(r for r in rows if not validate(rd, r[2], in_image)[0])
    hd, f = fixed_fields(rd, fi)
    o, v = f['dispIPtoStateMap']

    def rd_bad(rva, n):
        b = rd(rva, n)
        if b is not None and rva <= fi + o < rva + n:
            b = bytearray(b)
            k = fi + o - rva
            b[k:k + 4] = b'\0\0\0\0'
            return bytes(b)
        return b
    pr, _, _ = validate(rd_bad, fi, in_image)
    ok.append(('negative: one corrupted IP pointer (set to 0) -> FAIL', 'dispIPtoStateMap_outside_image' in pr))
    # 負例 2: BBT を立てた合成ヘッダは固定部未解決として扱われる
    def rd_bbt(rva, n):
        b = rd(rva, n)
        if rva == fi and b is not None:
            b = bytes([b[0] | 0x04]) + b[1:]
        return b
    pr2, _, _ = validate(rd_bbt, fi, in_image)
    ok.append(('negative: BBT bit set -> fixed part unresolved (not guessed)', 'fixed_part_unresolved(BBT)' in pr2))
    for name, passed in ok:
        print('   %s %s' % ('PASS' if passed else 'FAIL', name))
    print('   corrupted-entry problems: %s' % pr)
    return 0 if all(p for _, p in ok) else 1


def main(argv):
    if argv[1] == '--selftest':
        return selftest(argv[2])
    pe, rd, in_image, rows, res = census(argv[1])
    with open(argv[2], 'w') as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
