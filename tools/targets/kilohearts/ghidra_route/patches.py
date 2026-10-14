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
}
