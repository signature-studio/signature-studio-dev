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
# V128 演算 (#3108 KH-45): Ghidra は x86 の `mul r64` (rdx:rax = rax × r64) と 128bit 加算 (add/adc) を、128bit ベクタの
# `*` `+` と `SUB168(x, n)` (下位・上位 8 バイトの切出し) で印字する。stereo 180fdc470 (mul 180fdc4ba・4c8・4e6 / add 4d4)・
# 180fdfdb0 (mul 180fdfdfa・fe08・fe26 / adc fe17) で確認。両オペランドの上位 qword は 0 (`_8_8_ = 0`) なので、
# 積は 64×64→128 の符号なし積 (v128_mul64)、`+` は 128bit 整数加算 (v128_add)。件数 (第 4 要素) を assert する。
V128OPS = {
    'stereo': [
        ('stereo mul64 + add128 (180fdc470 l37, 180fdfdb0 l36)', r'(auVar\d+) = (auVar\d+) \* (auVar\d+) \+ (auVar\d+);', r'\1 = v128_add(v128_mul64(\2, \3), \4);', 2),
        ('stereo mul64 inside SUB168 (180fdc470 l29-30, 180fdfdb0 l29-30)', r'SUB168\((auVar\d+) \* (auVar\d+),', r'SUB168(v128_mul64(\1, \2),', 4),
    ],
}
