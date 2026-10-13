#!/usr/bin/env python3
"""SR-2b machine-level reference patch — IR pass (authstub_irpass.py) の機械語対応版。

IR 差し替え 6 点 (N1/N2a-1/N2a-2/N2b-1/N2b-2/N3) に対応する最小バイトパッチを
PE 実バイトに対して検証 (期待原 bytes 照合) し、パッチ適用済み PE を出力する。
lift パイプラインを通さずネイティブのまま検証する場合 / 将来の lift 前提確認用の正本。

usage:
  python3 mpatch.py <pe_in> <pe_out>            # 検証 + 適用
  python3 mpatch.py <pe_in> --verify-only       # 原 bytes の照合のみ
"""
import sys, struct
import pefile

# (id, VA, expected bytes, patched bytes, 対応 IR rule)
PATCHES = [
    ("N1",    0x18004fbdd, bytes.fromhex("0f8439020000"), bytes.fromhex("e93a02000090"),
     "DSP setState: demoVersion 検出 je → jmp (復元続行) [IR: br_force !37]"),
    ("N2a-1", 0x1800c2cfc, bytes.fromhex("3401"),         bytes.fromhex("b000"),
     "Controller setState: xor al,1 → mov al,0 (demo bit store 値を定数 0 に) [IR: store_const !2624]"),
    ("N2a-2", 0x1800c2d48, bytes.fromhex("01"),           bytes.fromhex("00"),
     "Controller setState: mov byte [obj+0x22792],1 → ,0 [IR: store_const !2630]"),
    ("N2b-1", 0x1800c2d04, bytes.fromhex("7559"),         bytes.fromhex("9090"),
     "Controller setState: demo→通知 jne を nop 化 (licensed 経路へ直行; N2a-1 併用では冗長だが強化) [IR: br_force !2625]"),
    ("N2b-2", 0x1800c2d59, bytes.fromhex("0f84a9010000"), bytes.fromhex("e9aa01000090"),
     "Controller setState: 通知分岐 je → jmp (常時 skip, 強化) [IR: br_force !2633]"),
    ("N3",    0x1800c687b, bytes.fromhex("75"),           bytes.fromhex("eb"),
     "Controller getState: demo マーカ書込 jne → jmp (常時 skip) [IR: br_force !3004]"),
]

IMG_EXPECT = 0x180000000


def va_to_off(pe, va):
    rva = va - pe.OPTIONAL_HEADER.ImageBase
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, len(s.get_data())):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    raise SystemExit(f'VA {va:#x} はセクションに存在しない')


def main():
    args = [a for a in sys.argv[1:]]
    verify_only = '--verify-only' in args
    args = [a for a in args if not a.startswith('--')]
    if not args:
        raise SystemExit(__doc__)
    pe_in = args[0]
    pe = pefile.PE(pe_in, fast_load=True)
    if pe.OPTIONAL_HEADER.ImageBase != IMG_EXPECT:
        print(f'警告: ImageBase = {pe.OPTIONAL_HEADER.ImageBase:#x} (期待 {IMG_EXPECT:#x}) — VA は再計算不要 (差分で整合)')
    raw = open(pe_in, 'rb').read()
    ok = 0
    for (pid, va, exp, pat, why) in PATCHES:
        off = va_to_off(pe, va)
        cur = raw[off:off + len(exp)]
        status = 'OK' if cur == exp else 'MISMATCH'
        if cur == exp:
            ok += 1
        print(f'{pid:6s} @{va:#x} off={off:#x} expect={exp.hex()} actual={cur.hex()} [{status}] {why}')
    if ok != len(PATCHES):
        raise SystemExit(f'原 bytes 照合失敗: {ok}/{len(PATCHES)}')
    print(f'原 bytes 照合: {ok}/{len(PATCHES)} OK')
    if verify_only:
        return
    buf = bytearray(raw)
    for (pid, va, exp, pat, why) in PATCHES:
        off = va_to_off(pe, va)
        assert len(exp) == len(pat), pid
        buf[off:off + len(exp)] = pat
    open(args[1], 'wb').write(bytes(buf))
    print(f'適用済み PE を出力: {args[1]} ({len(buf)} bytes)')


if __name__ == '__main__':
    main()
