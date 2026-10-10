#!/usr/bin/env python3
"""Scan a binary for well-known crypto/compression constants. usage: crypto_scan.py <file>"""
import sys, struct
d = open(sys.argv[1], 'rb').read()
def find_all(pat, limit=5):
    r, i = [], 0
    while len(r) < limit:
        i = d.find(pat, i)
        if i < 0: break
        r.append(i); i += 1
    return r
sigs = {
 'MD5 T[0..1] (d76aa478 e8c7b756, LE)': struct.pack('<II', 0xd76aa478, 0xe8c7b756),
 'MD5 init (67452301 efcdab89)': struct.pack('<II', 0x67452301, 0xefcdab89),
 'SHA1 init (67452301 efcdab89 98badcfe)': struct.pack('<III', 0x67452301, 0xefcdab89, 0x98badcfe),
 'SHA256 K[0..1] (428a2f98 71374491 LE)': struct.pack('<II', 0x428a2f98, 0x71374491),
 'SHA256 K[0..1] BE': struct.pack('>II', 0x428a2f98, 0x71374491),
 'SHA256 init (6a09e667 bb67ae85)': struct.pack('<II', 0x6a09e667, 0xbb67ae85),
 'SHA512 K[0] 428a2f98d728ae22 LE': struct.pack('<Q', 0x428a2f98d728ae22),
 'SHA512 init 6a09e667f3bcc908 LE': struct.pack('<Q', 0x6a09e667f3bcc908),
 'AES Sbox (63 7c 77 7b f2 6b 6f c5)': bytes.fromhex('637c777bf26b6fc5'),
 'AES Te0 (c66363a5 f87c7c84)': struct.pack('<II', 0xa56363c6, 0x847c7cf8),
 'ChaCha "expand 32-byte k"': b'expand 32-byte k',
 'Curve25519 p (2^255-19) LE low': bytes.fromhex('edffffffffffffff'),
 'Ed25519 L order LE (ed d3 f5 5c 1a 63 12 58)': bytes.fromhex('edd3f55c1a631258'),
 'Ed25519 d const LE (a3 78 59 13 ca 4d eb 75)': bytes.fromhex('a3785913ca4deb75'),
 'Ed25519/ref10 basepoint y (58 66 66 66 66 66 66 66)': bytes.fromhex('5866666666666666'),
 'CRC32 table (00000000 77073096 ee0e612c)': struct.pack('<III', 0, 0x77073096, 0xee0e612c),
 'zlib/zstd magic zstd (28 b5 2f fd)': bytes.fromhex('28b52ffd'),
 'RSA OID/ASN.1 SHA256 prefix (3031300d06096086480165030402010500)': bytes.fromhex('3031300d060960864801650304020105000420'),
 'base64 alphabet': b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',
 'PEM -----BEGIN': b'-----BEGIN',
 'sqlite format 3': b'SQLite format 3',
 'SQLite version string': b'SQLite version',
 'Mersenne MT19937 (9908b0df)': struct.pack('<I', 0x9908b0df),
 'FLAC': b'fLaC', 'OGG': b'OggS', 'RIFF': b'RIFF',
}
for k, v in sigs.items():
    hits = find_all(v)
    print(f"{'HIT ' if hits else 'no  '} {k}: {[hex(h) for h in hits]}")
import re
m = re.search(rb'SQLite version[^\0]{0,40}|3\.\d+\.\d+\.?\d* 20\d\d-\d\d-\d\d[^\0]{0,60}', d)
print('sqlite ver:', m.group(0)[:100] if m else None)
