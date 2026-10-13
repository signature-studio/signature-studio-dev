#!/usr/bin/env python3
"""moe.py — FL Studio の言語ファイル .moe (暗号化 GNU gettext .mo) の復号と検査 (ST-T14 / #39)。

方式 (FLEngine_x64.dll の復号関数 0x8e13f0 / 0x8d85d0 / 0x8d5670 / 0x8d8510 の逆アセンブルから確定):
  file = u32le N(=256) | RSA 暗号文 N byte (big-endian 整数) | 本体 (暗号化 .mo)
  1. m = c^3 mod n          (e = 3 の「公開鍵」復号。n = DLL 内の 256 byte 定数。big-endian・2048 bit)
  2. m を前ゼロ除去した ASCII 16 進文字列 32 字 → HexToBin → 16 byte の共通鍵 K
  3. 本体を 8 byte ブロック i=0.. で: out[i] = in[i] ^ K64[i & 1]、その後 K8[i & 15] ^= (i & 0xff)
     (末尾の 8 byte 未満は無変換)
  復号後 = 標準 GNU .mo (magic 0x950412de LE)。FL は復号後に magic を検査し、さらに Content-Type が
  charset=UTF-8 でなければ翻訳を無効化する (0x8daeb0 の診断メッセージ)。
法務: n と K は FL 由来定数なので **repo に保存しない**。n は実行時に DLL から抽出し、K・復号結果は出力しない
(出力は件数・ヘッダ値・検査結果のみ)。

usage: moe.py <FLEngine_x64.dll> <file.moe>... [--json]
exit 0 = 全ファイルが復号できて検査 (magic / 表の範囲 / UTF-8 / charset) を通過、1 = 失敗あり
"""
import json
import struct
import sys

MAGIC = 0x950412DE
# SetLength(modulus, 256) + 先頭 1 byte 書込み の機械語パターン (x64 Delphi)。? は call rel32
_SIG = bytes.fromhex('BA000100004D33C0E8') + b'\0' * 4 + bytes.fromhex('4889D9E8') + b'\0' * 4 + bytes.fromhex('C600')
_SIG_MASK = bytes.fromhex('FFFFFFFFFFFFFFFFFF') + b'\0' * 4 + bytes.fromhex('FFFFFFFF') + b'\0' * 4 + bytes.fromhex('FFFF')


def _find_sig(blob):
    hits = []
    n = len(_SIG)
    first = _SIG[0]
    i = blob.find(bytes([first]))
    while i >= 0 and i + n <= len(blob):
        if all((blob[i + j] & _SIG_MASK[j]) == _SIG[j] for j in range(n)):
            hits.append(i)
        i = blob.find(bytes([first]), i + 1)
    return hits


def extract_modulus(dll_bytes):
    """DLL の「256 byte 定数を mov [rax], imm で 1 つずつ書く関数」から n を再構成する。戻り (n_bytes, file_offset)"""
    hits = _find_sig(dll_bytes)
    if len(hits) != 1:
        raise ValueError(f'modulus 関数の署名が {len(hits)} 件 (期待 1)')
    p = hits[0] + len(_SIG) - 2          # 署名の末尾 2 byte (C6 00) の位置 = 最初の mov [rax], imm
    out = {}
    off = 0
    while True:
        b = dll_bytes[p:p + 4]
        if b[:2] == b'\xc6\x00':                     # mov byte [rax], imm8
            out[off] = bytes([b[2]]); p += 3
        elif b[:3] == b'\x66\xc7\x00':               # mov word [rax], imm16
            out[off] = dll_bytes[p + 3:p + 5]; p += 5
        elif b[:2] == b'\xc7\x00':                   # mov dword [rax], imm32
            out[off] = dll_bytes[p + 2:p + 6]; p += 6
        elif b[:3] == b'\x48\x83\xc0':               # add rax, imm8
            off += b[3]; p += 4
        elif b[:3] == b'\x48\x89\xd8':               # mov rax, rbx = 関数終端
            break
        else:
            raise ValueError(f'未知の命令列 @ file+{p:#x}: {b.hex()}')
    n = bytearray(256)
    covered = 0
    for o, v in out.items():
        n[o:o + len(v)] = v
        covered += len(v)
    if covered != 256 or max(out) + len(out[max(out)]) != 256:
        raise ValueError(f'modulus 被覆 {covered}/256 byte')
    return bytes(n)


def decrypt(blob, modulus):
    """戻り (復号後 .mo bytes, 鍵長 byte)。構造不正は ValueError"""
    if len(blob) < 4:
        raise ValueError('短すぎる')
    n = struct.unpack_from('<I', blob, 0)[0]
    if n != len(modulus) or len(blob) < 4 + n:
        raise ValueError(f'ヘッダ長 {n} != {len(modulus)}')
    c = int.from_bytes(blob[4:4 + n], 'big')
    m = pow(c, 3, int.from_bytes(modulus, 'big')).to_bytes(n, 'big').lstrip(b'\0')
    try:
        key = bytes.fromhex(m.decode('ascii'))
    except (UnicodeDecodeError, ValueError):
        raise ValueError('RSA 復号結果が 16 進文字列でない (鍵または暗号文が不正)')
    if len(key) != 16:
        raise ValueError(f'共通鍵長 {len(key)} != 16')
    body = bytearray(blob[4 + n:])
    st = bytearray(key)
    for i in range(len(body) // 8):
        k = st[(i & 1) * 8:(i & 1) * 8 + 8]
        for j in range(8):
            body[i * 8 + j] ^= k[j]
        st[i & 0xF] ^= i & 0xFF
    return bytes(body), len(key)


def parse_mo(d):
    """GNU .mo の最小パーサ (リトル/ビッグエンディアン両対応)。戻り dict(N, header, entries のうち検査結果)"""
    if len(d) < 28:
        raise ValueError('mo 短すぎる')
    magic = struct.unpack_from('<I', d, 0)[0]
    if magic == MAGIC:
        e = '<'
    elif struct.unpack_from('>I', d, 0)[0] == MAGIC:
        e = '>'
    else:
        raise ValueError(f'magic {magic:#010x} が .mo でない')
    rev, n, o_off, t_off, _hs, _ho = struct.unpack_from(e + '6I', d, 4)
    if o_off + 8 * n > len(d) or t_off + 8 * n > len(d):
        raise ValueError('記述子表が範囲外')
    nonascii = 0
    bad_utf8 = 0
    header = None
    for i in range(n):
        lo, oo = struct.unpack_from(e + '2I', d, o_off + 8 * i)
        lt, ot = struct.unpack_from(e + '2I', d, t_off + 8 * i)
        if oo + lo >= len(d) or ot + lt >= len(d) or d[oo + lo] != 0 or d[ot + lt] != 0:
            raise ValueError(f'文字列 {i} が範囲外または NUL 終端でない')
        t = d[ot:ot + lt]
        try:
            t.decode('utf-8'); d[oo:oo + lo].decode('utf-8')
        except UnicodeDecodeError:
            bad_utf8 += 1
        if any(b >= 0x80 for b in t):
            nonascii += 1
        if lo == 0 and header is None:
            header = t.decode('utf-8', 'replace')
    return {'rev': rev, 'n': n, 'o_off': o_off, 't_off': t_off, 'translated_nonascii': nonascii,
            'bad_utf8': bad_utf8, 'header': header or ''}


def _hdr(header, key):
    for line in header.split('\n'):
        if line.lower().startswith(key.lower() + ':'):
            return line.split(':', 1)[1].strip()
    return None


def summarize(path, modulus):
    blob = open(path, 'rb').read()
    mo, keylen = decrypt(blob, modulus)
    r = parse_mo(mo)
    ct = _hdr(r['header'], 'Content-Type') or ''
    return {
        'file': path.replace('\\', '/').rsplit('/', 1)[-1], 'enc_bytes': len(blob), 'mo_bytes': len(mo), 'key_bytes': keylen,
        'entries': r['n'], 'nonascii_translations': r['translated_nonascii'], 'bad_utf8': r['bad_utf8'],
        'charset_utf8': 'charset=utf-8' in ct.lower(), 'language': _hdr(r['header'], 'Language'),
        'plural_forms': _hdr(r['header'], 'Plural-Forms'),
        'enc_header_common': blob[:260],   # 呼出側で比較して捨てる (出力しない)
    }


def main(argv):
    if len(argv) < 3:
        print(__doc__); return 2
    as_json = '--json' in argv
    args = [a for a in argv[1:] if a != '--json']
    dll, files = args[0], args[1:]
    modulus = extract_modulus(open(dll, 'rb').read())
    rows, ok = [], True
    heads = set()
    for f in files:
        try:
            s = summarize(f, modulus)
            heads.add(s.pop('enc_header_common'))
            rows.append(s)
        except ValueError as ex:
            ok = False
            rows.append({'file': f.replace('\\', '/').rsplit('/', 1)[-1], 'error': str(ex)})
    for r in rows:
        if 'error' not in r and (not r['charset_utf8'] or r['bad_utf8']):
            ok = False
    out = {'files': rows, 'distinct_enc_headers': len(heads), 'ok': ok}
    if as_json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        for r in rows:
            print(r)
        print('distinct_enc_headers', len(heads), 'ok', ok)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
