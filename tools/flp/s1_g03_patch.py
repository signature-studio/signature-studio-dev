#!/usr/bin/env python3
# #113 S1: G03 (Authenticode 検査, tools/startup/GATES.md) を oracle 用ローカルコピー上で通すための 3 箇所のパッチ。
# 対象: FL64.exe の検査分岐 (VA 0x140006eaf, je→jmp) と FLEngine_x64.dll の 2 つの検査分岐
# (自身 VA 0x1375ee9 / ホスト EXE VA 0x137633e, jne→jmp)。
# 各分岐の飛び先は検査成功側、フォールスルーは戻り値 -2 の失敗側 (objdump で確認)。
# 書換えは飛び先を変えない無条件 jmp で、検査結果を無視し成功側へ継続させる。
# 期待バイトを照合してから書き換える。入力はインストール木のコピー (commit・配布しない)。
import sys
import pefile

PATCHES = {
    "FL64.exe": [(0x140006EAF, b"\x74\x0b", b"\xeb\x0b")],
    "FLEngine_x64.dll": [
        (0x1375EE9, b"\x75\x0f", b"\xeb\x0f"),
        (0x137633E, b"\x75\x0f", b"\xeb\x0f"),
    ],
}


def main(path):
    name = path.replace("\\", "/").split("/")[-1]
    if name not in PATCHES:
        sys.exit(f"no patch recipe for {name}")
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = bytearray(open(path, "rb").read())
    for va, expect, new in PATCHES[name]:
        off = pe.get_offset_from_rva(va - base)
        got = bytes(data[off:off + len(expect)])
        if got != expect:
            sys.exit(f"{name}: VA {va:#x} expected {expect.hex()} got {got.hex()}")
        data[off:off + len(new)] = new
        print(f"{name}: VA {va:#x} off {off:#x} {expect.hex()} -> {new.hex()}")
    open(path, "wb").write(bytes(data))


if __name__ == "__main__":
    main(sys.argv[1])
