#!/usr/bin/env python3
"""crosscheck.py — moe.py の別算法による検算 + ネガティブコントロール (ST-T14 / #39)。

usage: crosscheck.py <FLEngine_x64.dll> <file.moe>...
別算法:
  - RSA: pow(c, 3, n) の代わりに c*c%n*c%n
  - XOR ストリーム: バイト単位の moe.decrypt の代わりに、逆アセンブル通りの 64 bit ワード演算 (状態を 2 qword + byte 変異で保持)
  - .mo 構造: 自前パーサの代わりに標準ライブラリ gettext.GNUTranslations で読み、非複数形 msgid の全件が自前パーサの値と一致
ネガコン (いずれも失敗しなければ exit 1):
  RSA ヘッダ 1 byte 反転 / 法 n を 1 byte 反転 / 本体先頭 1 byte 反転 (magic 破壊) / 末尾切り詰め
"""
import gettext
import io
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import moe  # noqa: E402


def decrypt_words(blob, modulus):
    n = struct.unpack_from('<I', blob, 0)[0]
    N = int.from_bytes(modulus, 'big')
    c = int.from_bytes(blob[4:4 + n], 'big')
    m = (c * c % N * c % N).to_bytes(n, 'big').lstrip(b'\0')
    key = bytes.fromhex(m.decode('ascii'))
    q = list(struct.unpack('<2Q', key))
    body = blob[4 + n:]
    out = bytearray(body)
    for i in range(len(body) // 8):
        w = struct.unpack_from('<Q', body, i * 8)[0] ^ q[i & 1]
        struct.pack_into('<Q', out, i * 8, w)
        raw = bytearray(struct.pack('<2Q', *q))
        raw[i & 0xF] ^= i & 0xFF
        q = list(struct.unpack('<2Q', bytes(raw)))
    return bytes(out)


def expect_fail(label, fn):
    try:
        fn()
    except ValueError as e:
        print(f'  NC {label}: 失敗を検出 ({str(e)[:40]})')
        return 0
    print(f'  NC {label}: 失敗を検出できなかった')
    return 1


def main(argv):
    dll, files = argv[1], argv[2:]
    modulus = moe.extract_modulus(open(dll, 'rb').read())
    bad = 0
    for f in files:
        blob = open(f, 'rb').read()
        a, _ = moe.decrypt(blob, modulus)
        b = decrypt_words(blob, modulus)
        t = gettext.GNUTranslations(io.BytesIO(a))
        r = moe.parse_mo(a)
        n_plain = 0
        n_diff = 0
        o_off, t_off = r['o_off'], r['t_off']
        for i in range(r['n']):
            lo, oo = struct.unpack_from('<2I', a, o_off + 8 * i)
            lt, ot = struct.unpack_from('<2I', a, t_off + 8 * i)
            mid = a[oo:oo + lo]
            if lo == 0 or b'\0' in mid:
                continue
            n_plain += 1
            if t._catalog.get(mid.decode('utf-8')) != a[ot:ot + lt].decode('utf-8'):
                n_diff += 1
        ok = (a == b) and n_diff == 0
        bad += 0 if ok else 1
        print(f'{os.path.basename(f)}: words==bytes {a == b} / gettext 照合 {n_plain} 件中 不一致 {n_diff}')
    f0 = open(files[0], 'rb').read()
    flip = lambda d, i: d[:i] + bytes([d[i] ^ 1]) + d[i + 1:]
    nbad = bytearray(modulus); nbad[100] ^= 1
    bad += expect_fail('RSA header 1byte', lambda: moe.parse_mo(moe.decrypt(flip(f0, 10), modulus)[0]))
    bad += expect_fail('modulus 1byte', lambda: moe.parse_mo(moe.decrypt(f0, bytes(nbad))[0]))
    bad += expect_fail('body magic 1byte', lambda: moe.parse_mo(moe.decrypt(flip(f0, 260), modulus)[0]))
    bad += expect_fail('truncate', lambda: moe.parse_mo(moe.decrypt(f0[:len(f0) // 2], modulus)[0]))
    print('crosscheck', 'PASS' if bad == 0 else f'FAIL({bad})')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
