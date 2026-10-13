#!/usr/bin/env python3
"""LD-39 (#1194): i128 引数・%tagPOINT 値渡しの対象 11 関数について、PE の機械語入口を逆アセンブルする。

  python3 tools/liftdiff/tests/ld39_abi_dump.py <PE> [boot_final3.ll] > work/ld39_abi.txt

入力: PE (既定 $FL_WIN64_DIR/extracted/block00031_PE.bin。targets/m11.json の pe と同じ)。
      IR (既定 tools/m11/work/boot_final3.ll) の define 行から署名を引く。
出力: 関数ごとの IR 署名・先頭命令列・単純な jmp thunk の解決結果。
ABI の想定 (未検証の仮説。出典は未確認で、判定は REPORT_LD39.md §2 で人が行う):
  MS x64 の整数/ポインタ引数は rcx,rdx,r8,r9 (第 3 以降は stack)、double 引数は xmm0..3 と想定する。
  i128 (16 バイト) の渡し方は未確定で、候補を 2 つ残す:
    (a) 2 レジスタ分解 (低 64bit・高 64bit を連続するレジスタに入れる)
    (b) ポインタ渡し (実体へのポインタ 1 本。LLVM の Win64 規約の想定として挙がっているが、本 script では確認していない)
  この script は候補のどちらも選ばない。入口の命令列を並べるだけ。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'liftdiff'))
import capstone  # noqa: E402
from ldlib import pe as P  # noqa: E402
from ldlib import irtool  # noqa: E402

TARGETS = [
    ('40c660', 'i64 (i128)'), ('40c750', 'i64 (i128)'), ('4256c0', 'ptr (%tagPOINT)'),
    ('664890', 'i64 (i128)'), ('6649b0', 'i64 (i128)'), ('6649c0', 'i64 (i128)'),
    ('664a80', 'i64 (i128)'), ('442a50', 'i64 (i128)'), ('442b90', 'i64 (i128)'),
    ('653c80', 'i64 (i64,i64,i128)'), ('691dd0', 'i64 (i64,i128,i64)'),
]
N_INS = 8


def main():
    pe_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block00031_PE.bin')
    ir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'tools', 'm11', 'work', 'boot_final3.ll')
    p = P.PE(pe_path)
    txt = [s for s in p.sections if s['name'] == '.text'][0]
    base = p.base + txt['rva']
    data = txt['data']
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    sigs = irtool.parse_sigs(ir)
    print('# LD-39 ABI 入口ダンプ (PE=%s, image base=%#x)' % (os.path.basename(pe_path), p.base))
    for va_s, note in TARGETS:
        va = int(va_s, 16)
        name = 'function_' + va_s
        sig = sigs.get(name, {})
        print()
        print('== %s  IR: ret=%s params=%s  (LD-24 表の想定: %s)' % (
            va_s, sig.get('ret'), ','.join(sig.get('params', [])), note))
        cur = va
        for hop in range(3):
            off = cur - base
            if off < 0 or off >= len(data):
                print('  (image 外)')
                break
            ins = list(md.disasm(data[off:off + 64], cur))
            if not ins:
                break
            print('  %x: %s %s' % (ins[0].address, ins[0].mnemonic, ins[0].op_str))
            # jmp [rip+x] は IAT 経由の import thunk か、別関数への tail jump。先頭命令だけ解決して次へ進む。
            m = re.match(r'qword ptr \[rip \+ (0x[0-9a-f]+)\]', ins[0].op_str) if ins else None
            if ins[0].mnemonic == 'jmp' and m:
                ptr_va = ins[0].address + ins[0].size + int(m.group(1), 16)
                poff = ptr_va - base
                tgt = int.from_bytes(data[poff:poff + 8], 'little') if 0 <= poff < len(data) - 8 else 0
                print('    -> IAT slot %#x -> %#x (import thunk: 以降は呼び先の ABI に従う)' % (ptr_va, tgt))
                break
            if ins[0].mnemonic == 'jmp' and ins[0].op_str.startswith('0x'):
                cur = int(ins[0].op_str, 16)
                continue
            for i in ins[1:N_INS]:
                print('  %x: %s %s' % (i.address, i.mnemonic, i.op_str))
            break
    return 0


if __name__ == '__main__':
    sys.exit(main())
