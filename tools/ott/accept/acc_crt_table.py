#!/usr/bin/env python3
"""acc_crt_table.py — CAB-138 独立再計算 (別アルゴリズム: PE 生バイト直接読み + ror の 3 方式検算)。

定義 (規則 36):
  - api-set 関数ポインタ表 = .data の RVA 0x26c9f0 (= VA 0x18026c9f0) から 8 B × 32 entry。
    「32 entry」= ott_crt.c の `APISET_N 32` と同じ**固定読み出し幅**で数えたもの。
  - .data 生値 = PE ファイル (ディスク) に載っている値。**ランタイムの初期値ではない**
    (元の静的値は 0 = 未解決で、PE ローダの .data 適用・reloc で変わりうる)。
  - __security_cookie = RVA 0x260ce0 の 8 B 生値 (UCRT の静的既定 0x2b992ddfa232)。
  - decode(x) = ror(x ^ cookie, cookie & 0x3f) / enc(p) = rol(p, 64-(cookie&0x3f)) ^ cookie。
    OTT の resolver (0x1801c38c8) が使う式。cookie & 0x3f = 50。
  - fail-fast 根因: ランタイム生値 0 を decode すると ror(cookie, 50) ≠ 0 になり
    「解決済みポインタ」と誤認されて CFG dispatch (0x1801d2750 `jmp rax`) が garbage jump。

使い方: python3 tools/ott/accept/acc_crt_table.py [OTT_vst2_win64.dll]
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import PLUGINS_DIR  # noqa: E402

DLL = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.join(PLUGINS_DIR, 'ott', 'binaries', 'OTT_vst2_win64.dll')
IMG = 0x180000000
COOKIE_RVA, TABLE_RVA, N = 0x260ce0, 0x26c9f0, 32
ESLOT_RVA = [0x26c028, 0x26c388, 0x26cb40, 0x26cb88]
M64 = 0xFFFFFFFFFFFFFFFF


def rva2off(pe, rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    raise SystemExit('rva 0x%x not mapped' % rva)


def ror64(v, n):                                   # 方法1: シフト合成
    n &= 63
    return ((v >> n) | (v << (64 - n))) & M64


def rol64(v, n):
    n &= 63
    return ((v << n) | (v >> (64 - n))) & M64


def main():
    import pefile
    pe = pefile.PE(DLL)
    data = open(DLL, 'rb').read()
    rd = lambda rva, n: data[rva2off(pe, rva):rva2off(pe, rva) + n]

    cookie = struct.unpack('<Q', rd(COOKIE_RVA, 8))[0]
    rot = cookie & 0x3f
    print('__security_cookie (VA 0x%x) = 0x%x  (UCRT 静的既定と一致: %s)'
          % (IMG + COOKIE_RVA, cookie, cookie == 0x2b992ddfa232))
    print('cookie & 0x3f (回転量) = %d' % rot)

    tbl = list(struct.unpack('<32Q', rd(TABLE_RVA, 8 * N)))
    nz = sum(1 for v in tbl if v)
    print('api-set 表 VA 0x%x: %d entry / 非ゼロ %d entry (ファイル生値)'
          % (IMG + TABLE_RVA, N, nz))

    print()
    print('--- decode(0) = ror(0 ^ cookie, rot) の独立検算 (同一値を 4 方式で) ---')
    b = ror64(cookie ^ 0, rot)                                    # 方法1: 関数
    c = ((cookie >> rot) | (cookie << (64 - rot))) & M64           # 方法2: 式をインライン
    bits = format(cookie, '064b')
    d = int(bits[-rot:] + bits[:-rot], 2)                          # 方法3: 2進文字列の末尾 rot 桁を前に
    e = (cookie >> rot) | ((cookie & ((1 << rot) - 1)) << (64 - rot))  # 方法4: 下位 rot bit を抽出
    for name, v in (('方法1 関数', b), ('方法2 式', c), ('方法3 文字列', d), ('方法4 下位抽出', e)):
        print('  %-12s = 0x%016x' % (name, v))
    print('  4 方式一致: %s' % (b == c == d == e))

    print()
    print('--- enc(NULL) / round-trip ---')
    enc_null = rol64(0, 64 - rot) ^ cookie
    print('  enc(NULL) = rol(0,%d) ^ cookie = 0x%x  == cookie: %s'
          % (64 - rot, enc_null, enc_null == cookie))
    print('  decode(enc(NULL)) = %d (NULL に戻る: %s)' % (ror64(enc_null ^ cookie, rot),
                                                         ror64(enc_null ^ cookie, rot) == 0))

    print()
    print('--- 個別 encoded slot (ファイル生値) ---')
    for rva in ESLOT_RVA:
        v = struct.unpack('<Q', rd(rva, 8))[0]
        print('  VA 0x%x raw=0x%016x decode=0x%x %s'
              % (IMG + rva, v, ror64(v ^ cookie, rot),
                 '(_matherr user hook)' if rva == 0x26cb88 else ''))

    print()
    print('--- 結論 (静的 vs ランタイム) ---')
    print('  ファイル生値の api-set 表は非ゼロ %d/%d (reloc/ローダ適用後)。' % (nz, N))
    print('  一方 native CRT 未初期化状態 (DllMain 未実行) ではランタイム生値 0 なので')
    print('  decode(0) = ror(cookie, %d) = 0x%016x ≠ 0 → 誤って「解決済み」と判定される。' % (rot, b))


if __name__ == '__main__':
    main()
