#!/usr/bin/env python3
"""hs_vtable_gen.py — FLEngine_x64.dll の実機 TFruityHost VMT (0x1314108) から
vtable 46 スロット (VMT+0x70 .. VMT+0x1D8, offset 0x00..0x168) の関数 VA を抽出し
hs_vtable.h を生成する (CAB-195 P0b / ABI.md §2.3, §6)。

使い方: python3 hs_vtable_gen.py <FLEngine_PE> [out=hs_vtable.h]
根拠: VMT 0x1314108, ClassName=TFruityHost, InstanceSize=296 (delphi_vmt.py 実測)。
slot0 = Dispatcher 0x13173a0 (A検収 CAB-12 確定値と一致することをここで再検証する)。
"""
import struct, sys

VMT = 0x1314108
BASE_OFF = 0x70          # vtable 開始 offset (VMT+0x70 = vptr の指す先)
NSLOTS = 46              # offset 0x00..0x168
SLOT0_EXPECT = 0x13173A0  # A検収確定値


def main():
    pe_path = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else 'hs_vtable.h'
    d = open(pe_path, 'rb').read()
    import pefile
    pe = pefile.PE(data=d)
    base = pe.OPTIONAL_HEADER.ImageBase

    def rd(va, n):
        o = pe.get_offset_from_rva(va - base)
        return d[o:o + n]

    def q(va):
        return struct.unpack('<Q', rd(va, 8))[0]

    cn = q(VMT - 24)
    b = rd(cn, 64)
    name = b[1:1 + b[0]].decode('latin1')
    isize = q(VMT - 16)
    assert name == 'TFruityHost', 'VMT %x is %s (expect TFruityHost)' % (VMT, name)
    assert isize == 296, 'InstanceSize=%d (expect 296)' % isize
    slots = [q(VMT + BASE_OFF + 8 * i) for i in range(NSLOTS)]
    assert slots[0] == SLOT0_EXPECT, 'slot0=%x (expect %x)' % (slots[0], SLOT0_EXPECT)
    # VMT ヘッダ直後の TObject 仮想 14 個 (VMT+0x00..0x68) も参考として出力
    tobj = [q(VMT + 8 * i) for i in range(14)]

    with open(out, 'w') as f:
        f.write('/* hs_vtable.h — TFruityHost 実機 vtable 46 スロット (生成: hs_vtable_gen.py)\n')
        f.write(' * 根拠: %s VMT 0x1314108 (TFruityHost, InstanceSize 296), vtable=VMT+0x70, 46 slot (offset 0x00..0x168)\n' % pe_path.split('/')[-1])
        f.write(' * slot0 = Dispatcher = 0x13173a0 (A検収 CAB-12 確定値と一致)。\n')
        f.write(' * slot VAs は FLEngine_x64.dll の VA であり、framework image (0x400000..0xD02000) と\n')
        f.write(' * import 合成 VA (0xE000000..) の間に位置する → dispatch 表にそのまま登録できる。\n')
        f.write(' */\n#ifndef HS_VTABLE_H\n#define HS_VTABLE_H\n#include <stdint.h>\n\n')
        f.write('/* TObject 側仮想 14 個 (VMT+0x00..0x68) — 参考記録 */\n')
        f.write('#define HS_TObject_VMT {\\\n  ' + ', '.join('0x%06xu' % v for v in tobj) + '}\n\n')
        f.write('/* SDK vtable 46 slot: HS_HOST_VA[i] = vtable offset 8*i の実機 target VA */\n')
        f.write('static const uint32_t HS_HOST_VA[%d] = {\n' % NSLOTS)
        for i, v in enumerate(slots):
            f.write('  0x%06xu, /* slot %2d (vtable +0x%03x) */\n' % (v, i, 8 * i))
        f.write('};\n\n#endif\n')
    print('[hs_vtable] %d slots, slot0=0x%x OK -> %s' % (NSLOTS, slots[0], out))
    for i, v in enumerate(slots):
        print('  slot %2d +0x%03x = 0x%x' % (i, 8 * i, v))


if __name__ == '__main__':
    main()
