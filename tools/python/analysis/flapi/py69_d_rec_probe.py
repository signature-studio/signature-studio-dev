#!/usr/bin/env python3
"""PY-5414 (#6015) の D のレコード表と dl=1 factory の確保ブロックを PE から検査する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/py69_d_rec_probe.py

- (1) D の factory `0x40fb40` が読む `[this-0xc0]` (= 0x855880) の PE 上の値。0 なら静的にレコードは無い。
- (2) 0x855880 / 0x8558c0 (728) / 0x855940 (factory this) を RIP 相対で参照する命令を全 .text から列挙する。
- (3) `0x7412af` (`[0x855878]` を rdx にして `0x40fe90` を呼ぶ) の呼出し先 `0x40fe90` → `0x410010` を読み、
  `[rcx-0x78]` の連結リストを rdx まで辿る所属判定かを確認する (`+0x168` への書込みではない)。
- 限界: (2) は RIP 相対だけを拾う。ポインタ経由・ヒープ経由の参照は拾わない。0 件は「参照なし」の証拠にならない。
"""
import os

import capstone

import py69_d_origin as base_mod  # noqa: E402  (stream / rip_target / fmt を流用)

TARGETS = {
    0x855880: "this-0xc0 (レコード表の先頭ポインタ)",
    0x8558C0: "dword 728 (factory の確保サイズ)",
    0x855940: "factory this (D の確保ブロックの先頭 qword)",
}


def disasm_at(va, n):
    out = []
    for ins in base_mod.MD.disasm(base_mod.RAW[base_mod.fo(va):base_mod.fo(va) + n], va):
        out.append(base_mod.fmt(ins))
    return out


def main():
    print("(1) PE 上の値:")
    off = base_mod.fo(0x855880)
    print(f"    [0x855880] = {int.from_bytes(base_mod.RAW[off:off + 8], 'little'):#x} (qword)")
    off = base_mod.fo(0x8558C0)
    print(f"    dword [0x8558c0] = {int.from_bytes(base_mod.RAW[off:off + 4], 'little')} (factory の確保サイズ)")

    print("(2) RIP 相対参照:")
    hits = {k: [] for k in TARGETS}
    for ins in base_mod.stream():
        t = base_mod.rip_target(ins)
        if t in hits:
            hits[t].append(base_mod.fmt(ins))
    for k, v in hits.items():
        print(f"    {k:#x} {TARGETS[k]}: {len(v)} 件")
        for x in v[:10]:
            print(f"        {x}")

    print("(3) 0x7412af の呼出し先の判定:")
    for line in disasm_at(0x40FE90, 0x10):
        print(f"    {line}")
    for line in disasm_at(0x410010, 0x18):
        print(f"    {line}")


if __name__ == "__main__":
    main()
