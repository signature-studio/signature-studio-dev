#!/usr/bin/env python3
"""k80_pe_globals.py — 0 初期化の整数 global を PE の初期化済みセクションの実値に置き換える (#3281 / P0c-20)。

  python3 k80_pe_globals.py <in.ll> <out.ll> [--report <json>]

RetDec 由来の IR は .data に初期値を持つ global を `global iN 0` に落とすことがある (#2182)。
@global_var_<VA> の VA (= image base + RVA) が raw data を持つ PE セクションに入るものは、
PE の実バイト (little-endian) の値を入れる。PE の値が 0 のものは 0 のまま。
関数本体には触れない。

ゲート (fail-closed): EXPECT 以外の置換対象が出た場合、EXPECT の global が IR に無い / PE の初期化済み範囲の外の場合は止める。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402
import pefile  # noqa: E402

PE = os.path.join(FL_WIN64_DIR, 'extracted', 'block18983_PE.bin')
EXPECT = [0x6fffb0, 0x6fc26c]  # 0x6fffb0: PE .data の (0.5, 0.5) (#2182 の kernel 0x5e03f0 の修復)。0x6fc26c: 同種の 0 初期化 i128 (PE 値は f32 x4 の表)
LINE = re.compile(r'^@global_var_([0-9a-f]+) = (.*?)global (i(8|16|32|64|128)) (-?\d+)$')


def load_pe(path):
    raw = open(path, 'rb').read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = []
    for s in pe.sections:
        n = min(s.Misc_VirtualSize, s.SizeOfRawData)
        if s.PointerToRawData and n:
            secs.append((base + s.VirtualAddress, n, s.PointerToRawData, s.Name.rstrip(b'\0').decode()))
    return raw, secs


def pe_int(raw, secs, va, nbytes):
    for sva, n, off, name in secs:
        if sva <= va and va + nbytes <= sva + n:
            o = off + (va - sva)
            return int.from_bytes(raw[o:o + nbytes], 'little'), name
    return None, None


def signed(v, bits):
    return v - (1 << bits) if v >> (bits - 1) else v


def replace_globals(text, raw, secs):
    out, done, seen = [], [], set()
    for line in text.split('\n'):
        m = LINE.match(line)
        if not m:
            out.append(line)
            continue
        va, bits = int(m.group(1), 16), int(m.group(4))
        cur = int(m.group(5))
        pv, sec = pe_int(raw, secs, va, bits // 8)
        if pv is None:
            if va in EXPECT:
                raise SystemExit('[pe_globals] 0x%x が PE の初期化済み範囲に無い' % va)
            out.append(line)
            continue
        if pv == 0 or (cur != 0 and cur != signed(pv, bits)):
            out.append(line)
            continue
        if cur == 0 and va not in EXPECT:
            raise SystemExit('[pe_globals] 想定外の置換対象 @global_var_%x (PE 値 %d)' % (va, pv))
        if va not in EXPECT:
            out.append(line)
            continue
        if cur == 0:
            state = 'replaced'
            line = '@global_var_%s = %sglobal %s %d' % (m.group(1), m.group(2), m.group(3),
                                                      signed(pv, bits))
        else:
            state = 'applied'  # 適用済み (再実行) も数える: 件数検査を冪等に保つ
        done.append({'va': '0x%x' % va, 'type': m.group(3), 'value': signed(pv, bits),
                      'section': sec, 'state': state})
        seen.add(va)
        out.append(line)
    for va in EXPECT:
        if va not in seen:
            raise SystemExit('[pe_globals] @global_var_%x が 0 初期化の整数 global として 1 本も無い' % va)
    return '\n'.join(out), done


def main():
    args = sys.argv[1:]
    report = None
    if '--report' in args:
        i = args.index('--report')
        report = args[i + 1]
        del args[i:i + 2]
    src, dst = args[0], args[1]
    raw, secs = load_pe(PE)
    text, done = replace_globals(open(src).read(), raw, secs)
    open(dst, 'w').write(text)
    if report:
        json.dump({'replaced': done}, open(report, 'w'), indent=1)
    print('pe_globals: %d (%s)' % (len(done), ' '.join('%s:%s' % (x['va'], x['state']) for x in done)))


if __name__ == '__main__':
    main()
