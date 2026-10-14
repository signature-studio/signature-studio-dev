#!/usr/bin/env python3
"""LD-53 (#1546): i128 引数の呼出し側を PE 全体で数える (命令境界の線形逆アセンブル)。

  python3 tools/liftdiff/tests/ld53_callers_linear.py <PE> > work/ld53_callers.txt

.text を先頭から命令境界で逆アセンブルし、call rel32 (E8) の呼び先が対象 VA のものを集める。
各 call について直前 12 命令を見て、引数の準備を分類する:
  - xmm0 に書き込みがあれば「xmm0 に double」
  - 無ければ「準備が見えない」
対象 653c80 は r8 / r9 への書き込み有無を別に数える (i128 の高位が r9 に入るかの確認)。
判定 ((a) 2 レジスタ分解 / (b) ポインタ渡し) は人が REPORT_APPENDIX_LD53.md で行う。
"""
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'liftdiff'))
import capstone  # noqa: E402
from ldlib import pe as P  # noqa: E402

TARGETS = [0x40c660, 0x40c750, 0x653c80]
WINDOW = 12


def writes(ins, reg):
    """命令 ins が reg (小文字) を宛先に書くかを粗く判定する (先頭オペランド)。"""
    ops = ins.op_str.split(',')[0].strip().lower()
    return ops == reg or (reg.startswith('r') and ops.startswith(reg))


def main():
    pe_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block00031_PE.bin')
    p = P.PE(pe_path)
    txt = [s for s in p.sections if s['name'] == '.text'][0]
    base = p.base + txt['rva']
    data = txt['data']
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False

    # 線形走査: 命令境界を先頭から追い、各命令を保持する (直前 12 命令の参照用)。
    insns = []
    off = 0
    while off < len(data):
        got = list(md.disasm(data[off:off + 16], base + off, 1))
        if got:
            insns.append(got[0])
            off += got[0].size
        else:
            off += 1
    print('# LD-53 呼出し側の線形走査 (PE=%s, .text=%d bytes, 命令数=%d)' % (
        os.path.basename(pe_path), len(data), len(insns)))

    stats = {t: Counter() for t in TARGETS}
    for i, ins in enumerate(insns):
        if ins.mnemonic != 'call' or len(ins.bytes) != 5 or ins.bytes[0] != 0xE8:
            continue
        tgt = ins.address + ins.size + int.from_bytes(ins.bytes[1:5], 'little', signed=True)
        if tgt not in stats:
            continue
        prev = []
        for x in reversed(insns[max(0, i - WINDOW):i]):
            if x.mnemonic in ('call', 'jmp', 'ret') or x.mnemonic.startswith('j'):
                break
            prev.append(x)
        st = stats[tgt]
        st['call'] += 1
        if tgt == 0x653c80:
            r8 = [x for x in prev if writes(x, 'r8')]
            r9 = [x for x in prev if writes(x, 'r9')]
            st['r8_written' if r8 else 'r8_none'] += 1
            st['r9_written' if r9 else 'r9_none'] += 1
            continue
        if any(writes(x, 'xmm0') for x in prev):
            st['xmm0_double'] += 1
        else:
            st['no_visible_prep'] += 1

    for t in TARGETS:
        print('%x: %s' % (t, dict(stats[t])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
