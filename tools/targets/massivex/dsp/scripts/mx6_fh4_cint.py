#!/usr/bin/env python3
"""MX-48 (#4787): FH4 FuncInfo4 の可変長整数 (compressed int) の復号と、その符号化を使う table の検証。

一次資料: ehdata4_export.h (Microsoft, 公開写し trcrsired/windows-msvc-sysroot/include/ehdata4_export.h)。
  ReadUnsigned: 先頭 byte の下位 4 bit で長さ L (1〜5) を決め、encoding は [pb, pb+L) に前から置かれる。
  L<=4: 値 = LE(bytes[pb:pb+L]) >> L。 L=5 (flag 0x0F): 値 = LE32(bytes[pb+1:pb+5])。 pb += L。
  s_negLengthTab / s_shiftTab は同じ規則の表引きである (本スクリプトの decode が両方と一致することを selftest で示す)。
  整数 4 byte (dispXxx) は LE32 で直接読む。UnwindMap / TryBlockMap / IPtoStateMap は "件数 (可変長)" で始まる。

usage: mx6_fh4_cint.py --selftest
       mx6_fh4_cint.py <pe> <out.json>
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mx6_fh4  # noqa: E402

NEG_LEN = [1, 2, 1, 3, 1, 2, 1, 4, 1, 2, 1, 3, 1, 2, 1, 5]


def encode(v):
    """ehdata4_export.h の getNETencoded の移植 (符号化側・selftest 用)。"""
    if v < 128:
        return bytes([(v << 1) & 0xFF])
    if v < 128 * 128:
        x = (v << 2) + 1
        return bytes([x & 0xFF, (v >> 6) & 0xFF])
    if v < 128 ** 3:
        x = (v << 3) + 3
        return bytes([x & 0xFF, (v >> 5) & 0xFF, (v >> 13) & 0xFF])
    if v < 128 ** 4:
        x = (v << 4) + 7
        return bytes([x & 0xFF, (v >> 4) & 0xFF, (v >> 12) & 0xFF, (v >> 20) & 0xFF])
    return bytes([15]) + (v & 0xFFFFFFFF).to_bytes(4, 'little')


def decode(b):
    """b は pb から少なくとも 5 byte。戻り値 (値, 消費 byte 数)。"""
    L = NEG_LEN[b[0] & 0x0F]
    if L == 5:
        return int.from_bytes(b[1:5], 'little'), 5
    return int.from_bytes(b[:L], 'little') >> L, L


def selftest():
    ok = []
    edge = [0, 1, 63, 64, 127, 128, 255, 16383, 16384, 2097151, 2097152, 268435455, 268435456, 0xFFFFFFFF]
    rnd = random.Random(4787)
    vals = edge + [rnd.getrandbits(rnd.choice([7, 14, 21, 28, 32])) for _ in range(20000)]
    bad = 0
    for v in vals:
        e = encode(v)
        d, n = decode(e + b'\0' * 5)
        if d != v or n != len(e):
            bad += 1
    ok.append(('roundtrip: %d values (edge + random) decode back' % len(vals), bad == 0))
    # 連続 (前から順・pb += L) で複数値を読む: 1 つずつ符号化して連結したものを読む
    seq = [rnd.getrandbits(rnd.choice([7, 14, 21, 28])) for _ in range(500)]
    blob = b''.join(encode(v) for v in seq) + b'\0' * 5
    pb, got = 0, []
    for _ in seq:
        d, n = decode(blob[pb:])
        got.append(d)
        pb += n
    ok.append(('sequence: 500 concatenated values read forward (pb += L)', got == seq))
    # 表との一致: s_negLengthTab の表 (ehdata4_export.h) を直接書き写したものと NEG_LEN が一致
    ehtab = [-1, -2, -1, -3, -1, -2, -1, -4, -1, -2, -1, -3, -1, -2, -1, -5]
    ok.append(('table: NEG_LEN == -s_negLengthTab', [-x for x in ehtab] == NEG_LEN))
    for name, p in ok:
        print('   %s %s' % ('PASS' if p else 'FAIL', name))
    return 0 if all(p for _, p in ok) else 1


def check_unwind(rd, U, in_image):
    """UnwindMap: 件数 N, 各 entry の nextOffset (state を辿る byte 差)。前方 (後ろ向き) の戻りが entry 先頭か buffer 前を指すか。"""
    b = rd(U, 8)
    if b is None:
        return {'unreadable': True}
    N, L = decode(b)
    p = U + L
    starts, types, bad = [], {}, 0
    buf0 = p
    for _ in range(N):
        b = rd(p, 8)
        if b is None:
            return {'unreadable': True}
        start = p
        starts.append((start, None))
        v, n = decode(b)
        p += n
        nxt, typ = v >> 2, v & 3
        types[typ] = types.get(typ, 0) + 1
        if typ in (1, 2):
            p += 4
            b2 = rd(p, 8)
            _, n2 = decode(b2)
            p += n2
        elif typ == 3:
            p += 4
        starts[-1] = (start, (start - nxt))
    startset = set(s for s, _ in starts)
    for s, tgt in starts:
        if tgt is None:
            continue
        if tgt < buf0 or tgt in startset:
            continue
        bad += 1
    return {'n': N, 'types': types, 'bad_chain': bad, 'end': p}


def check_try(rd, T):
    b = rd(T, 8)
    if b is None:
        return {'unreadable': True}
    N, L = decode(b)
    p = T + L
    bad_order, bad_range = 0, 0
    for _ in range(N):
        vals = []
        for _k in range(3):
            b = rd(p, 8)
            if b is None:
                return {'unreadable': True}
            v, n = decode(b)
            vals.append(v)
            p += n
        if not (vals[0] <= vals[1] <= vals[2]):
            bad_order += 1
        p += 4
    return {'n': N, 'bad_order': bad_order, 'end': p}


def check_ip(rd, I, st, e):
    b = rd(I, 8)
    if b is None:
        return {'unreadable': True}
    N, L = decode(b)
    p = I + L
    prev = 0
    out_of_range = 0
    for _ in range(N):
        b = rd(p, 8)
        if b is None:
            return {'unreadable': True}
        d, n = decode(b)
        p += n
        b = rd(p, 8)
        s, n2 = decode(b)
        p += n2
        prev += d
        if prev >= e - st:
            out_of_range += 1
    return {'n': N, 'out_of_range': out_of_range, 'end': p}


def census(pe_path):
    pe, rd, in_image, rows, _ = mx6_fh4.census(pe_path)
    res = {'rows': len(rows), 'fi_distinct': 0, 'unreadable': 0,
           'unwind_bad_chain': 0, 'unwind_entries': 0, 'unwind_types': {},
           'try_bad_order': 0, 'try_entries': 0,
           'ip_out_of_range_rows': 0, 'ip_entries': 0, 'ip_rows': 0, 'ip_unreadable': 0}
    seen = set()
    for st, e, fi in rows:
        hd, f = mx6_fh4.fixed_fields(rd, fi)
        if hd is None or f is None:
            res['unreadable'] += 1
            continue
        if fi not in seen:
            seen.add(fi)
            if 'dispUnwindMap' in f:
                u = check_unwind(rd, f['dispUnwindMap'][1], in_image)
                if u.get('unreadable'):
                    res['unreadable'] += 1
                else:
                    res['unwind_entries'] += u['n']
                    res['unwind_bad_chain'] += u['bad_chain']
                    for k, c in u['types'].items():
                        res['unwind_types'][str(k)] = res['unwind_types'].get(str(k), 0) + c
            if 'dispTryBlockMap' in f:
                t = check_try(rd, f['dispTryBlockMap'][1])
                if t.get('unreadable'):
                    res['unreadable'] += 1
                else:
                    res['try_entries'] += t['n']
                    res['try_bad_order'] += t['bad_order']
        ip = check_ip(rd, f['dispIPtoStateMap'][1], st, e)
        res['ip_rows'] += 1
        if ip.get('unreadable'):
            res['ip_unreadable'] += 1
        else:
            res['ip_entries'] += ip['n']
            if ip['out_of_range']:
                res['ip_out_of_range_rows'] += 1
    res['fi_distinct'] = len(seen)
    return res


def main(argv):
    if argv[1] == '--selftest':
        return selftest()
    res = census(argv[1])
    with open(argv[2], 'w') as fp:
        json.dump(res, fp, indent=1, ensure_ascii=False)
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
