#!/usr/bin/env python3
"""ipp_target_ident.py の照合のネガティブコントロール (T-SH-80 / #3420)。

宛先 0x1803c4710 の 1 命令 `addps xmm0, xmm2` (0f 58 c2) を `subps xmm0, xmm2` (0f 5c c2) に変えた入力を作り、
同じ照合 (ipp_target_ident.copies_in_ipp: 先頭 7 byte の位置 + ipp_entries.tokens の SHA-1 一致) で dsp_ippv2 を照合する。
元の入力は一致が出て、変えた入力は一致 0 件になることを確認する。変えた入力に一致が出たら終了 1 (FAIL)。
変更は入力のメモリ上だけで行い、ファイルは書かない。出力は標準出力のみ。
入力: ELASTIQUE_DLL・DSP_IPP_DLL (ipp_entries.py と同じ)。
"""
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_64

import ipp_entries as ie
import ipp_target_ident as tid

ADDPS = bytes.fromhex('0f58c2')
SUBPS = bytes.fromhex('0f5cc2')


def main():
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    elq = ie.load(ie.ELQ)
    dsp = ie.load(ie.DSP)
    base, dbase = elq['base'], dsp['base']
    tgt = tid.TARGET - base

    hits = []
    for ins in md.disasm(elq['mem'][tgt:tgt + ie.MAXINS * 15], tid.TARGET):
        if ins.bytes == ADDPS:
            hits.append(ins.address - base)
        if ins.mnemonic == 'ret':
            break
    assert len(hits) == 1, f'addps xmm0,xmm2 が宛先に {len(hits)} 件 (1 件を期待)'
    pos = hits[0]

    mem_bad = bytearray(elq['mem'])
    assert bytes(mem_bad[pos:pos + 3]) == ADDPS
    mem_bad[pos:pos + 3] = SUBPS
    bad = dict(elq, mem=bytes(mem_bad))

    tok_ok = ie.tokens(elq, md, tgt)
    tok_bad = ie.tokens(bad, md, tgt)
    diff = [(i, a, b) for i, (a, b) in enumerate(zip(tok_ok, tok_bad)) if a != b]
    pre_ok = bytes(elq['mem'][tgt:tgt + 7])
    pre_bad = bytes(bad['mem'][tgt:tgt + 7])

    print(f'elastique: {ie.ELQ}')
    print(f'dsp_ippv2: {ie.DSP}')
    print(f'変更: {base + pos:#x} の {ADDPS.hex()} (addps xmm0, xmm2) → {SUBPS.hex()} (subps xmm0, xmm2)')
    print(f'  正規化命令列の差分: {len(diff)} 行 {diff}')
    print(f'  先頭 7 byte は同一: {pre_ok == pre_bad}')
    counts = {}
    for label, tok, pre in (('元の入力', tok_ok, pre_ok), ('変えた入力', tok_bad, pre_bad)):
        m = tid.copies_in_ipp(dsp, md, pre, ie.sha(tok))
        counts[label] = len(m)
        print(f'[{label}] 正規化 {len(tok)} 命令 SHA-1 {ie.sha(tok)}')
        print(f'  dsp 完全一致 {len(m)} 件 {[hex(dbase + c) for c in m]}')
    ok = counts['元の入力'] > 0 and counts['変えた入力'] == 0
    print(f'判定: {"PASS" if ok else "FAIL"} (元 {counts["元の入力"]} 件・変えた入力 {counts["変えた入力"]} 件)')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
