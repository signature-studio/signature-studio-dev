#!/usr/bin/env python3
"""probe_f552a0_6246.py — #6246 (CI-258): function_f552a0 の f55396 間接 call と脱出後の第 1 引数を照合する.

機械語 (boot3.drc.dsm の f5538d〜f553a1) と IR (boot_final3.ll の function_f552a0) を読み、次を出す:
  M1: 機械語 f5538d〜f5539c は `this = [arg1]`・vtable `[this]`・`call [vtable+0x18]` (this = rcx)・
      その後 `rcx = [arg1]` で `call 0x12df760` (第 1 引数 = *arg1)。
  M2: IR の脱出ブロック dec_label_pc_f5538c に間接 call が無く、直接 call @function_12df760 の第 1 引数だけがある。
  M3: IR の第 1 引数の値 (loop-carry の reload) の表示のみ。判定には含めない (終了コードに影響しない)。
      出所の機械確認は judge_arg1_5999.py が行う。

終了コード: M1 と M2 が機械語・IR の記述どおりなら 0 (= 間接 call の欠落がまだ残っている)。
想定と違えば 1 (fail-closed。修正が入った、または素材が違う)。

使い方: python3 probe_f552a0_6246.py [DSM] [IR]   (既定は work/boot3.drc.dsm と work/boot_final3.ll)
"""
import re
import sys

ASM_LINE = re.compile(r'^0x([0-9a-f]+):[^\t]*\t(.*)$')
IR_FN = re.compile(r'^define (?:weak )?i64 @function_f552a0\(', re.M)
EXIT_BLOCK = 'dec_label_pc_f5538c:'
DSM_START, DSM_END = 0xf5538d, 0xf553a1


def machine(dsm_path):
    insns = {}
    with open(dsm_path, errors='replace') as f:
        for line in f:
            m = ASM_LINE.match(line.rstrip('\n'))
            if not m:
                continue
            va = int(m.group(1), 16)
            if DSM_START <= va < DSM_END:
                insns[va] = m.group(2).strip()
    return insns


def ir_exit_block(ir_path):
    src = open(ir_path, errors='replace').read()
    hit = IR_FN.search(src)
    assert hit, 'function_f552a0 が IR に無い'
    i = hit.start()
    j = src.find('\n}\n', i)
    body = src[i:j]
    k = body.find(EXIT_BLOCK)
    assert k >= 0, '脱出ブロック dec_label_pc_f5538c が無い'
    end = body.find('\n\n', k)
    return body[k:end if end >= 0 else None]


def main():
    dsm = sys.argv[1] if len(sys.argv) > 1 else 'work/boot3.drc.dsm'
    ir = sys.argv[2] if len(sys.argv) > 2 else 'work/boot_final3.ll'
    m = machine(dsm)
    want = {
        0xf5538d: 'mov rax, qword ptr [rbx]',
        0xf55390: 'mov rcx, rax',
        0xf55393: 'mov rsi, qword ptr [rax]',
        0xf55396: 'call qword ptr [rsi + 0x18]',
        0xf55399: 'mov rcx, qword ptr [rbx]',
        0xf5539c: 'call 0x12df760 <function_12df760>',
    }
    m1 = all(m.get(va, '').startswith(text) for va, text in want.items())
    print('M1 機械語 f5538d〜f5539c:', 'OK' if m1 else 'NG')
    for va, text in sorted(want.items()):
        print('   0x%x: %s' % (va, m.get(va, '(無し)')))

    block = ir_exit_block(ir)
    calls = [ln.strip() for ln in block.split('\n') if ' call ' in ln]
    indirect = [c for c in calls if '@function_' not in c]
    direct = [c for c in calls if '@function_12df760(' in c]
    m2 = not indirect and len(direct) == 1 and len(calls) == 1
    print('M2 IR 脱出ブロックの間接 call 件数:', len(indirect), '/ 直接 call:', direct)
    print('M2:', 'OK (間接 call 欠落のまま)' if m2 else 'NG')

    m3 = [ln.strip() for ln in block.split('\n') if 'function_12df760' in ln]
    print('M3 第 1 引数:', m3[0] if m3 else '(無し)')
    print('   IR 上の出所は judge_arg1_5999.py で確認 (loop-carry rcx.1.reload)')
    return 0 if (m1 and m2) else 1


if __name__ == '__main__':
    sys.exit(main())
