"""手作業パッチ表 (assoc): Ghidra の印字が落とした結合括弧を、実機 x86 の演算順に合わせて戻す。
(snap-in 名, 正規表現, 置換)。1 行 = 手作業 1 件。件数は REPORT の「手作業の工数」に使う。
ramp 形 `(b - a) * pos * inc + a` は実機 (Gain 1804b0473..0485) で `(b-a) * (pos*inc) + a` の順 (mulss xmm2,[inc] が先)。"""
RAMP = (r'\((\*\(float \*\)\(param_1 \+ 0x\w+\)) - (\*\(float \*\)\(param_1 \+ 0x\w+\))\) \*\s+(fVar\d+) \* (\*\(float \*\)\(param_1 \+ 0x\w+\))',
        r'(\1 - \2) * (\3 * \4)')
ASSOC = {
    'gain': [('ramp (1 site)',) + RAMP],
    'haas': [('ramp (2 sites)',) + RAMP],
    # smoothstep 形: 実機 1804c3494..34a7 は x2=x*x; r=(c-2x)*x2 → (c-2x)*(x*x)。Ghidra は ((c-2x)*x)*x と印字
    'gate': [('ramp (1 site)',) + RAMP,
             ('smoothstep (1 site)', r'\(fVar4 - \(fVar23 \+ fVar23\)\) \* fVar23 \* fVar23', '(fVar4 - (fVar23 + fVar23)) * (fVar23 * fVar23)')],
}
# グローバル型表 (gtype・Delay の型不一致): Ghidra は `_DAT_<va>` の型を印字しないため、ghidra_to_c.py の infer_type が
# 使い方から float と推定する。実機の逆アセンブル (capstone・RIP 相対参照の命令の幅) で整数マスクと確認したものだけを入れる。
# 1 行 = 1 グローバル。値 = C の型。根拠の命令は REPORT_APPENDIX_3801.md の表が正本。
GTYPE = {
    'delay': {
        '182280be0': 'ulonglong',  # cmp/mov qword・Ghidra: (ulonglong)dVar12 との & 比較
        '182280c10': 'ulonglong',  # mov qword・0x000fffffffffffff (double 仮数マスク)
        '182280c30': 'ulonglong',  # and/or qword・0x0008000000000000 (bit 51) (& の 64bit 項)
        '182280c68': 'ulonglong',  # mov qword・>> の被演算子 (64bit シフト)
        '182280c70': 'ulonglong',  # mov qword・>> の被演算子 (64bit シフト)
        '182280ce0': 'ulonglong',  # cmp/mov qword・0x7ff0000000000000 との | (ulonglong)
        '182281e70': 'ulonglong',  # mov qword・| (ulonglong) の被演算子
        '182282780': 'ulonglong',  # andpd (下位 8 bytes)・0x7fffffffffffffff (abs マスク)
        '18141d060': 'ulonglong',  # xorps (下位 8 bytes)・0x8000000000000000 (符号マスク)
        '1813d1a80': 'uint',       # xorps/pxor/movaps (下位 4 bytes)・0x80000000 (符号マスク)
        '181422a10': 'uint',       # minps/movaps・& -(uint)(...) の 4 byte マスク
        '182280bc0': 'longlong',   # cmp r10,qword・(longlong) 比較
        '182280bc8': 'longlong',   # cmp r10,qword・(longlong) 比較
    },
}
# ABI 表 (resonator 残件 emcc 4 件 = param_1 不足 3・引数数不一致 1)。Ghidra が呼出元で引数・戻り値を落としたため、
# 呼出元の機械語 (capstone 逆アセンブル, HeartCore 0x180fbc1f4・0x180fbbfb8) のレジスタ設定から復元する。
#   FUN_180fcf904: 引数 float (xmm0)・戻り値 short (ax)。呼出元 180fbc1f4 は xmm0 = 入力 float (= afStackX_8[0])、
#                  180fbbfb8 は xmm0 = xmm6 = 入力 param_2。本体は FUN_180fbdfcc(&arg) の戻り値をそのまま返す。
#   FUN_180fbdfcc: 引数 short* (rcx)。呼出元 180fbbfb8 は rcx = rbx = 入力 param_1。
#   FUN_180fbdef4: 引数 2 個 (rcx, dx)。呼出元 180fbc1f4 は rcx = &afStackX_10, dx = 0。r8 は callee が読まない。
ABI = {
    'resonator': [
        ('FUN_180fcf904 decl (float arg, short ret)', r'void FUN_180fcf904\(undefined4 param_1\)', 'short FUN_180fcf904(float param_1)'),
        ('FUN_180fcf904 body bits', r'auStackX_8\[0\] = param_1;', 'auStackX_8[0] = f2u(param_1);'),
        ('FUN_180fcf904 body return', r'  (?:func_0x000|FUN_)180fbdfcc\(auStackX_8\);\n  return;\n', '  return FUN_180fbdfcc((short *)auStackX_8);\n'),
        ('caller 180fbc1f4 xmm0 = input', r'sVar1 = (?:func_0x000|FUN_)180fcf904\(\);\n  iVar2 = 0;', 'sVar1 = FUN_180fcf904(afStackX_8[0]);\n  iVar2 = 0;'),
        ('caller 180fbbfb8 xmm0 = param_2', r'sVar2 = (?:func_0x000|FUN_)180fcf904\(\);', 'sVar2 = FUN_180fcf904(param_2);'),
        ('caller 180fbbfb8 rcx = param_1', r'sVar1 = (?:func_0x000|FUN_)180fbdfcc\(\);', 'sVar1 = FUN_180fbdfcc((short *)param_1);'),
        ('caller 180fbc1f4 2 args (r8 unused)', r'(?:func_0x000|FUN_)180fbdef4\(afStackX_10,0,0\);', 'FUN_180fbdef4(afStackX_10,0);'),
    ],
    # stereo (#3071 KH-39): 引数なし呼出 8 件 + 引数数不一致 2 件 + 型誤り 1 件 (567: ulonglong を double へ数値変換していた。行番号は REPORT_APPENDIX_3071 §10-7r の表と同じ)。callee は入力を xmm0 のビット列で読む (ulonglong 引数 = d2u)。
    # 呼出し直前に xmm0 へ入る値を機械語で確認し、規則 1 件 = 呼出し 1 件 (件数 1 を assert)。
    #   元入力 param_1 = 入口の movq rdx,xmm0 (180fcd6a1 / 180fce0e1) を保持した rdx/xmm0 をそのまま使う経路。
    #   ABS(param_1) = btr r,0x3f (符号 clear) 後の値 (180fcd6b3・180fce0ed) を使う経路。C の dVar2 は ABS 側に対応。
    #   xmm1 (2 個目の double 引数) は呼出元で設定されない (入力依存・未モデル) ため 0.0 を仮置き。突合でのみ判定できる。
    # 注意: callee の戻り値は rax (四分象限) のみ C 化され、reduce 後の値 (xmm0 / 2 個目は xmm1) は C 本体に出ない。
    #       呼出元の extraout_XMM0_Qa* は未初期化のまま残る (emcc は通すが数値は未検証)。
    'stereo': [
        ('stereo 465 FUN_180fdc700 xmm0 = param_1 (movq xmm0,rdx)', r'(?:func_0x000|FUN_)180fdc700\(\)(?=;\n\s*return dVar2;\n\s*\}\n\s*uVar4 = FUN_180fdfdb0)', 'FUN_180fdc700(d2u(param_1))'),
        ('stereo 468 FUN_180fdfdb0 xmm0 = ABS (btr r10 -> movq xmm0,r10)', r'uVar4 = (?:func_0x000|FUN_)180fdfdb0\(\)(?=;\n\s*dVar5 = extraout_XMM0_Qa;)', 'uVar4 = FUN_180fdfdb0(d2u(dVar2))'),
        ('stereo 502 FUN_180fdc470 xmm0 = ABS (vmovq xmm0,r9 180fcdabd)', r'uVar4 = (?:func_0x000|FUN_)180fdc470\(\)(?=;\n\s*dVar2 = extraout_XMM0_Qa_01;)', 'uVar4 = FUN_180fdc470(d2u(dVar2))'),
        ('stereo 528 FUN_180fdc700 xmm0 = param_1 (unchanged from entry)', r'(?:func_0x000|FUN_)180fdc700\(\)(?=;\n\s*return dVar2;\n\s*\}\n\s*if \(\(longlong\)dVar2 < _DAT_1822829b0\))', 'FUN_180fdc700(d2u(param_1))'),
        ('stereo 571 FUN_180fdc470 xmm0 = param_1 (vmovq xmm0,r9 180fce528)', r'uVar3 = (?:func_0x000|FUN_)180fdc470\(\)(?=;\n\s*dVar2 = extraout_XMM0_Qa_01;)', 'uVar3 = FUN_180fdc470(d2u(param_1))'),
        ('stereo 598 FUN_180fdc6d8 xmm0 = param_1 (unchanged from entry, jg 476 path)', r'(?:func_0x000|FUN_)180fdc6d8\(\)(?=;\n\s*return dVar2;\n\s*\}\n\s*if \(\(longlong\)uVar1 < \(longlong\)_DAT_182282af0\))', 'FUN_180fdc6d8(d2u(param_1))'),
        ('stereo 631 FUN_180fdc6d8 xmm0 = param_1 (movq xmm0,rdx 180fce450)', r'(?:func_0x000|FUN_)180fdc6d8\(\)(?=;\n\s*return dVar2;\n\s*\}\n\s*uVar3 = FUN_180fdfdb0)', 'FUN_180fdc6d8(d2u(param_1))'),
        ('stereo 634 FUN_180fdfdb0 xmm0 = ABS (movq xmm0,r10 180fce0ff)', r'uVar3 = (?:func_0x000|FUN_)180fdfdb0\(\)(?=;\n\s*dVar4 = extraout_XMM0_Qa;)', 'uVar3 = FUN_180fdfdb0(d2u(dVar2))'),
        ('stereo 185 FUN_180fce0d0 2nd arg xmm1 unset (placeholder 0.0)', r'dVar11 = \(double\)FUN_180fce0d0\(dVar12\);', 'dVar11 = (double)FUN_180fce0d0(dVar12, 0.0);'),
        ('stereo 186 FUN_180fcd690 2nd arg xmm1 unset (placeholder 0.0)', r'dVar12 = \(double\)FUN_180fcd690\(dVar12\);', 'dVar12 = (double)FUN_180fcd690(dVar12, 0.0);'),
        ('stereo 567 FUN_180fdc660 arg double = param_1 bits (movq xmm0,r9 180fce528; ulonglong uVar1 を数値変換しない)', r'uVar3 = (?:func_0x000|FUN_)180fdc660\(uVar1\);', 'uVar3 = FUN_180fdc660(param_1);'),
    ],
}
