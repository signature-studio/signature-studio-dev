#!/usr/bin/env python3
"""RTL (Delphi System/SysUtils/... ) の .text 上 VA 範囲を RTTI から確定する (#129)。

Delphi は unit ごとに code を連続配置し、class の VMT をその unit の code 内に置く。
typeinfo(tkClass=7): kind u8, name shortstr, ClassType u64, ParentInfo u64, PropCount u16, UnitName shortstr。
手順: .text から tkClass typeinfo (kind=7 + shortstring 名) を走査し、ClassType(VMT) の [VMT-0xa8]==typeinfo で相互確認 → UnitName。
unit ごとの VMT 最小/最大 VA を集め、InitTable の init proc VA と合わせて RTL 帯 (低 VA) を出す。

usage: rtl_range.py <PE> [--json out.json]
"""
import json, re, struct, sys
import pefile

VMT_TYPEINFO = 0xa8   # 本バイナリ実測: VMT-0xa8 に typeinfo ptr (2,958/2,958 クラスで ClassType と相互参照一致)


def main():
    pe = pefile.PE(sys.argv[1], fast_load=True)
    B = pe.OPTIONAL_HEADER.ImageBase
    img = pe.get_memory_mapped_image()
    t = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    lo, hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize

    def rd(va, n):
        o = va - B
        return img[o:o + n] if 0 <= o < len(img) - n else b''

    def q(va):
        b = rd(va, 8)
        return struct.unpack('<Q', b)[0] if len(b) == 8 else None

    def sstr(va):
        b = rd(va, 1)
        if not b:
            return None
        s = rd(va + 1, b[0])
        return s.decode('latin1') if len(s) == b[0] else None

    vmts = []  # (vmt, class, unit)
    ident = re.compile(rb'^[A-Za-z_][A-Za-z0-9_.<>,]*$')
    text = img[lo:hi]
    for m in re.finditer(rb'\x07([\x01-\x40])', text):
        o = lo + m.start()
        n = m.group(1)[0]
        nm = text[m.start() + 2:m.start() + 2 + n]
        if len(nm) != n or not ident.match(nm):
            continue
        ti = B + o
        td = ti + 2 + n
        ct = q(td)
        if ct is None or not (B + lo <= ct < B + hi) or q(ct - VMT_TYPEINFO) != ti:
            continue
        # ClassType u64, ParentInfo u64, PropCount u16, UnitName shortstring
        vmts.append((ct, nm.decode('latin1'), sstr(td + 18)))

    units = {}
    for X, c, u in vmts:
        e = units.setdefault(u, [X, X, 0])
        e[0] = min(e[0], X); e[1] = max(e[1], X); e[2] += 1
    order = sorted(units.items(), key=lambda kv: kv[1][0])
    out = {'vmt_count': len(vmts), 'units': [
        {'unit': u, 'vmt_lo': hex(v[0]), 'vmt_hi': hex(v[1]), 'classes': v[2]} for u, v in order]}
    if '--json' in sys.argv:
        json.dump(out, open(sys.argv[sys.argv.index('--json') + 1], 'w'), indent=1)
    print('VMT 総数', len(vmts), ' unit 数', len(units))
    for u, v in order:
        print('%-40s vmt %#x..%#x classes=%d' % (u, v[0], v[1], v[2]))


if __name__ == '__main__':
    main()
