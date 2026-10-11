#!/usr/bin/env python3
"""mx_pefix.py — Massive X.vst3 の PE ヘッダ修復 (MX-2, work/ copy に対して実施)。

CAB-46 実測: repack インストーラ由来の PE はヘッダに不整合があり、RetDec のローダが
"Invalid virtual address of a section" (Loadable anyway: No) で拒否する。
原因: 2 つ目の .pdata (VA 0x06176000) の VirtualSize (0x26ce8) が後続セクション
(.qtmimed/.retplne/.tls/.xdata) の VA と重複している。
本スクリプトは各セクションの VA+VS が次セクション VA を超えないよう VirtualSize を
クランプする (.text/.rdata の実データは無変更、ヘッダのみ)。

usage: mx_pefix.py <in.vst3> <out.vst3>
"""
import sys

import pefile

# .text 内の 2 バイト修復 (0x18115dec2): repack によるインプレース改変で
# movups store の canonical encoding `0f 11` が `e1 26` に化けている。
# 根拠 (MX-2 実測):
#  - 直後 5 バイト `00 c6 40 10 00` = mov byte [rax+0x10],0 (16 文字文字列の NUL) は
#    両バイナリで完全一致し、直前の movups load (7B) と合わせた store+NUL の
#    テンプレートの中央 2 バイトだけが VST3/VST2 で異なる値に化けている
#  - 同一ソース (VST2 Massive X.dll, 同一文字列ビルド 27 文字版) は canonical
#    `0f 11 00` + `0f 11 40 0b` + `c6 40 1b 00` を実測
#  - 化けたままだと RetDec が loope (e1) を生成し IR 生成が関数冒頭で打ち切られる
TEXT_VA = 0x181000000 - 0x180000000 + 0x1000  # 0x101000 (未使用, 記録用)
PATCHES = [  # (VA, original, fixed, why)
    (0x18115dec2, bytes.fromhex('e126'), bytes.fromhex('0f11'),
     'movups [rax],xmm0 store opcode (repack 改変修復)'),
]


def main():
    src, dst = sys.argv[1], sys.argv[2]
    pe = pefile.PE(src)
    secs = pe.sections
    changed = []
    for i, s in enumerate(secs):
        va, vs = s.VirtualAddress, s.Misc_VirtualSize
        nxt = min((x.VirtualAddress for x in secs[i + 1:] if x.VirtualAddress > va), default=None)
        if nxt is None:
            continue
        if va + vs > nxt:
            new_vs = min(vs, nxt - va)
            name = s.Name.rstrip(b'\0').decode(errors='replace')
            changed.append((name, hex(va), hex(vs), hex(new_vs)))
            s.Misc_VirtualSize = new_vs
    pe.OPTIONAL_HEADER.CheckSum = 0   # 再計算は不要 (wasm lift 用 copy のため)
    pe.write(dst)
    for c in changed:
        print('clamped %s VA=%s VS %s -> %s' % c)
    # .text バイト修復 (work copy のみ。元 PE は無変更)
    data = bytearray(open(dst, 'rb').read())
    t = next(s for s in secs if s.Name.rstrip(b'\0').decode() == '.text')
    base = pe.OPTIONAL_HEADER.ImageBase
    nfix = 0
    for va, orig, fixed, why in PATCHES:
        off = t.PointerToRawData + (va - base - t.VirtualAddress)
        cur = bytes(data[off:off + len(orig)])
        if cur == fixed:
            continue
        assert cur == orig, 'patch site %s: bytes %s != expected %s' % (hex(va), cur.hex(), orig.hex())
        data[off:off + len(fixed)] = fixed
        print('text-patch %s: %s -> %s (%s)' % (hex(va), cur.hex(), fixed.hex(), why))
        nfix += 1
    open(dst, 'wb').write(bytes(data))
    print('written:', dst, '(%d sections, %d text bytes fixed)' % (len(changed), nfix))


if __name__ == '__main__':
    main()
