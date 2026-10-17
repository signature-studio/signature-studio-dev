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
        '18436cd18': 'longlong',   # mov qword [..],rax (FUN_181327120/181327348 の GS 失敗経路)・puVar3+0x40 の 8 byte 書込み (#4685)
        '184162118': 'ulonglong',  # xor qword (180fd1b1a)・uint64 として読む (qword 幅)
        '184162a88': 'ulonglong',  # xor qword (180fe2496)・mov qword 書込 (180fe24f6)
        '184162a98': 'ulonglong',  # xor qword (180fe2791・180fe27bc)・mov qword 書込 (180fe27a8)
        '182989380': 'ulonglong',  # mov qword (180fd1b0e・180fe248a 等)・& 0x3f と ^ の被演算子
        # 関数ポインタ slot (#4671 KH-106)。呼出し 44 箇所は全て `call/jmp [rip+slot]` (CFG dispatch) で、呼び先は直前に rax へ入る値で決まる。
        # slot の PE 初期値は CFG thunk (`jmp [rip+..]`→`jmp rax`) で、データとして使わない。型は `int (*)()` (引数は呼出し側で決まる。戻り値は呼出元が eax しか読まない・読まない箇所があるため int。#4693 KH-112)。
        '1813a1d40': 'FNPTR',
    },
    # stereo 閉包 (#4911 KH-134): 型不一致 12 → 2 (emcc error 10 件の解消。本規則が効く C の行は 6 箇所)。
    # 型は同じ PE の同じ VA を delay の表 (上) で機械語確定済みのものを流用する。stereo 側の命令の幅は逆アセンブルで確認済み (REPORT_APPENDIX_4911.md)。
    #   stereo.c 行 1318・1869・1870・1884・1885: `_DAT_182989380`・`_DAT_184162a98` の xor/shift (64bit) → ulonglong。
    #   stereo.c 行 2290: `_DAT_18436cd18 = puVar3 + 0x40` (8 byte 書込み) → longlong。
    # 残り (1300・1888): `(*_DAT_1813a1d40)(param_1)` の間接呼出し。delay と同じ slot (同じ PE の同じ VA) なので FNPTR (int (*)()) を流用する (#5868)。
    'stereo': {
        '182989380': 'ulonglong',
        '184162118': 'ulonglong',
        '184162a98': 'ulonglong',
        '18436cd18': 'longlong',
        '1813a1d40': 'FNPTR',
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
        # KH-113 (#4704): FUN_180fdc470 の戻り xmm0 (縮約値) を kh_fn_180fdc470 (kh_xmm0.h・KH-76) で出す。呼出しと読出しを 1 組で置換する
        # (呼出しを kh_fn に変えないと kh_xmm0_180fdc470 が書かれず、読出しが未初期化値になる。callee 本体は kh_fn を呼ばない)。
        # 直前の 502・571 規則で `FUN_180fdc470(d2u(x))` になった呼出しを読む。件数 1 を assert する。
        ('stereo 502 caller 180fcd690 reads xmm0 of 470 (extraout_XMM0_Qa_01)', r'uVar4 = FUN_180fdc470\(d2u\(dVar2\)\);\n(\s*)dVar2 = extraout_XMM0_Qa_01;', r'uVar4 = kh_fn_180fdc470(dVar2);\n\1dVar2 = kh_xmm0_180fdc470;'),
        ('stereo 571 caller 180fce0d0 reads xmm0 of 470 (extraout_XMM0_Qa_01)', r'uVar3 = FUN_180fdc470\(d2u\(param_1\)\);\n(\s*)dVar2 = extraout_XMM0_Qa_01;', r'uVar3 = kh_fn_180fdc470(param_1);\n\1dVar2 = kh_xmm0_180fdc470;'),
        ('stereo 598 FUN_180fdc6d8 xmm0 = param_1 (unchanged from entry, jg 476 path)', r'(?:func_0x000|FUN_)180fdc6d8\(\)(?=;\n\s*return dVar2;\n\s*\}\n\s*if \(\(longlong\)uVar1 < \(longlong\)_DAT_182282af0\))', 'FUN_180fdc6d8(d2u(param_1))'),
        ('stereo 631 FUN_180fdc6d8 xmm0 = param_1 (movq xmm0,rdx 180fce450)', r'(?:func_0x000|FUN_)180fdc6d8\(\)(?=;\n\s*return dVar2;\n\s*\}\n\s*uVar3 = FUN_180fdfdb0)', 'FUN_180fdc6d8(d2u(param_1))'),
        ('stereo 634 FUN_180fdfdb0 xmm0 = ABS (movq xmm0,r10 180fce0ff)', r'uVar3 = (?:func_0x000|FUN_)180fdfdb0\(\)(?=;\n\s*dVar4 = extraout_XMM0_Qa;)', 'uVar3 = FUN_180fdfdb0(d2u(dVar2))'),
        ('stereo 185 FUN_180fce0d0 2nd arg xmm1 unset (placeholder 0.0)', r'dVar11 = \(double\)FUN_180fce0d0\(dVar12\);', 'dVar11 = (double)FUN_180fce0d0(dVar12, 0.0);'),
        ('stereo 186 FUN_180fcd690 2nd arg xmm1 unset (placeholder 0.0)', r'dVar12 = \(double\)FUN_180fcd690\(dVar12\);', 'dVar12 = (double)FUN_180fcd690(dVar12, 0.0);'),
        ('stereo 567 FUN_180fdc660 arg double = param_1 bits (movq xmm0,r9 180fce528; ulonglong uVar1 を数値変換しない)', r'uVar3 = (?:func_0x000|FUN_)180fdc660\(uVar1\);', 'uVar3 = FUN_180fdc660(param_1);'),
        # KH-74 (#3853): FUN_180fdc660 の戻り xmm0 = t2 を kh_xmm0.h の helper で出す (機械語 180fdc6c5 vmovapd xmm0,xmm2)。
        # 本体の rax 式は helper と同じ値 (k&3) なので置換する。呼出元の extraout_XMM0_Qa_00 は kh_xmm0_180fdc660 を読む。
        ('stereo FUN_180fdc660 body = kh_fn_180fdc660 (rax と xmm0 を 1 式で出す)', r'return \(int\)\(\(param_1 \* _DAT_18228a860 \+ _DAT_18228a8a0\) - _DAT_18228a8a0\) & 3;', 'return kh_fn_180fdc660(param_1);'),
        ('stereo 82 caller 180fcd690 reads xmm0 of 660 (extraout_Qa_00)', r'uVar4 = FUN_180fdc660\(dVar2\);\n(\s*)dVar2 = extraout_XMM0_Qa_00;', r'uVar4 = FUN_180fdc660(dVar2);\n\1dVar2 = kh_xmm0_180fdc660;'),
        ('stereo 24 caller 180fce0d0 reads xmm0 of 660 (extraout_Qa_00)', r'uVar3 = FUN_180fdc660\(param_1\);\n(\s*)dVar2 = extraout_XMM0_Qa_00;', r'uVar3 = FUN_180fdc660(param_1);\n\1dVar2 = kh_xmm0_180fdc660;'),
        # KH-77 (#3885): FUN_180fdfdb0 (三角関数の引数縮約・ret 180fdffb6・機械語 132 命令) の戻り xmm0 (縮約値) を kh_xmm0.h の helper で出す。
        # 呼出元 2 箇所の extraout_XMM0_Qa は kh_xmm0_180fdfdb0 を読む。呼出し (rax 側) は既存の ABS 規則のまま残す。
        # KH-115 (#4722): 呼出元 180fcd9c8・180fce43e の `movapd xmm4, xmm1` (xmm1 = 戻り残差) を、C の残差項 param_2 に配線する。
        # 機械語: 残差は [rsp+0x30] (180fcd7ac) へ退避し、最終式 R + (x + poly) の R に入る。C の `param_2 + (...) + dVar5` の param_2 と一致。
        ('stereo 603 caller 180fcd690 reads xmm0 of dfdb0 (extraout_XMM0_Qa)', r'uVar4 = FUN_180fdfdb0\(d2u\(dVar2\)\);\n(\s*)dVar5 = extraout_XMM0_Qa;', r'uVar4 = FUN_180fdfdb0(d2u(dVar2));\n\1dVar5 = kh_xmm0_180fdfdb0;\n\1param_2 = kh_xmm1_180fdfdb0;'),
        ('stereo 769 caller 180fce0d0 reads xmm0 of dfdb0 (extraout_XMM0_Qa)', r'uVar3 = FUN_180fdfdb0\(d2u\(dVar2\)\);\n(\s*)dVar4 = extraout_XMM0_Qa;', r'uVar3 = FUN_180fdfdb0(d2u(dVar2));\n\1dVar4 = kh_xmm0_180fdfdb0;\n\1param_2 = kh_xmm1_180fdfdb0;'),
    ],
    # delay (#3800 KH-64): 引数過不足のうち、呼出先 FUN_180fd4f30 (longlong 1 引数) の 22 件 = FUN_180fe3690 13 件・FUN_180fe3310 4 件・FUN_180fe3cd0 5 件。
    #   呼出元の機械語 (180fe3690 の capstone): `mov rcx,[rbx+off]` → `cmp rcx,[global]` → `je` → `call FUN_180fd4f30` (rbx = 入力 param_1)。
    #   rcx = *(param_1 + off)。off は C の条件式の添字と一致 (0x18〜0x48・0x68〜0x90 の 13 個、番地順 = C 行順)。
    #   FUN_180fe3310: 直線部 6779・6783 は `mov rcx,[rbx+0xf0]`・`[rbx+0xe8]`。ループ部 6801・6805 は `mov rcx,[rdi]`・`[rdi-8]` (rdi = puVar6、
    #   ループ末 `add rdi,0x20` まで不変)。FUN_180fe3cd0: `mov rcx,[rcx]` (= *param_1)・`[rbx+8]`・`[rbx+0x10]`・`[rbx+0x58]`・`[rbx+0x60]` (= param_1[1]・[2]・[0xb]・[0xc])。
    #   FUN_180fcf904 の 2 件 (2667・2760): 宣言は undefined4 (bit 列)。float 式をそのまま渡すと C が数値変換するので f2u() で包み bit を渡す (resonator の float 宣言とは逆)。
    #   規則 1 件 = 呼出し 1 件 (件数 1 を assert)。残り 86 件は REPORT_APPENDIX_3800.md の分類を参照。
    'delay': [
        # #5862 (KH-177): 戻り値を読む呼出元が有る callee の宣言 (void → 戻り値型)。機械語で呼出元の読みを確認済み。
        #   FUN_180fcf904 (short・ax): 呼出元 180fbbfb8 (2667) と 180fbc1f4 (2759) が call 直後に ax を読む。本体は FUN_180fbdfcc の ax を素通しする。
        #   FUN_180f878e0 (rax) は本体の値付けが意味の補正に当たるため本規則に入れない (子 issue へ切り出し・PR 本文の未解決表)。
        ('delay 5862 FUN_180fcf904 def void → short (ax)', r'void FUN_180fcf904\(undefined4 param_1\)(?=\s*\{)', 'short FUN_180fcf904(undefined4 param_1)'),
        ('delay 5862 FUN_180fcf904 body return = FUN_180fbdfcc result (ax)', r'(?:func_0x000|FUN_)180fbdfcc\(auStackX_8\);\n  return;\n', 'return FUN_180fbdfcc((short *)auStackX_8);\n'),
        ('delay 2667 FUN_180fbbfb8 xmm0 = param_2 bits (FUN_180fcf904 undefined4 arg)', r'sVar2 = (?:func_0x000|FUN_)180fcf904\(\);', 'sVar2 = FUN_180fcf904(f2u(param_2));'),
        ('delay 2760 FUN_180fbc1f4 xmm0 = input float bits (afStackX_8 source)', r'sVar1 = (?:func_0x000|FUN_)180fcf904\(\);', 'sVar1 = FUN_180fcf904(f2u(fVar4));'),
        ('delay 6939 FUN_180fe3690 rcx=[param_1+0x18]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x18\) != _DAT_182989698\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x18));'),
        ('delay 6942 FUN_180fe3690 rcx=[param_1+0x20]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x20\) != _DAT_1829896a0\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x20));'),
        ('delay 6945 FUN_180fe3690 rcx=[param_1+0x28]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x28\) != _DAT_1829896a8\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x28));'),
        ('delay 6948 FUN_180fe3690 rcx=[param_1+0x30]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x30\) != _DAT_1829896b0\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x30));'),
        ('delay 6951 FUN_180fe3690 rcx=[param_1+0x38]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x38\) != _DAT_1829896b8\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x38));'),
        ('delay 6954 FUN_180fe3690 rcx=[param_1+0x40]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x40\) != _DAT_1829896c0\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x40));'),
        ('delay 6957 FUN_180fe3690 rcx=[param_1+0x48]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x48\) != _DAT_1829896c8\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x48));'),
        ('delay 6960 FUN_180fe3690 rcx=[param_1+0x68]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x68\) != _DAT_1829896e8\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x68));'),
        ('delay 6963 FUN_180fe3690 rcx=[param_1+0x70]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x70\) != _DAT_1829896f0\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x70));'),
        ('delay 6966 FUN_180fe3690 rcx=[param_1+0x78]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x78\) != _DAT_1829896f8\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x78));'),
        ('delay 6969 FUN_180fe3690 rcx=[param_1+0x80]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x80\) != _DAT_182989700\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x80));'),
        ('delay 6972 FUN_180fe3690 rcx=[param_1+0x88]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x88\) != _DAT_182989708\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x88));'),
        ('delay 6975 FUN_180fe3690 rcx=[param_1+0x90]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x90\) != _DAT_182989710\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x90));'),
        ('delay 6779 FUN_180fe3310 rcx=[param_1+0xf0]', r'(if \(\(\*\(int \*\*\)\(param_1 \+ 0xf0\) != \(int \*\)0x0\) && \(\*\*\(int \*\*\)\(param_1 \+ 0xf0\) == 0\)\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0xf0));'),
        ('delay 6783 FUN_180fe3310 rcx=[param_1+0xe8]', r'(if \(\(\*\(int \*\*\)\(param_1 \+ 0xe8\) != \(int \*\)0x0\) && \(\*\*\(int \*\*\)\(param_1 \+ 0xe8\) == 0\)\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0xe8));'),
        ('delay 6801 FUN_180fe3310 loop rcx=*puVar6', r'(if \(\(\(puVar6\[-2\] != 0x1829899d8\) && \(\(int \*\)\*puVar6 != \(int \*\)0x0\)\) && \(\*\(int \*\)\*puVar6 == 0\)\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*puVar6);'),
        ('delay 6805 FUN_180fe3310 loop rcx=puVar6[-1]', r'(if \(\(\(puVar6\[-3\] != 0\) && \(\(int \*\)puVar6\[-1\] != \(int \*\)0x0\)\) && \(\*\(int \*\)puVar6\[-1\] == 0\)\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(puVar6[-1]);'),
        ('delay 6990 FUN_180fe3cd0 rcx=*param_1', r'(if \(\*param_1 != _DAT_182989680\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*param_1);'),
        ('delay 6993 FUN_180fe3cd0 rcx=param_1[1]', r'(if \(param_1\[1\] != _DAT_182989688\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(param_1[1]);'),
        ('delay 6996 FUN_180fe3cd0 rcx=param_1[2]', r'(if \(param_1\[2\] != _DAT_182989690\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(param_1[2]);'),
        ('delay 6999 FUN_180fe3cd0 rcx=param_1[0xb]', r'(if \(param_1\[0xb\] != _DAT_1829896d8\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(param_1[0xb]);'),
        ('delay 7002 FUN_180fe3cd0 rcx=param_1[0xc]', r'(if \(param_1\[0xc\] != _DAT_1829896e0\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(param_1[0xc]);'),
        # #4835 (KH-118): 引数数不一致 (too few) の呼出し 1 件。呼出元の機械語で rcx の源を確定 (rcx = rbx = 入口の param_1)。
        #   180fbbfb8: mov rbx,rcx (180fbbfdb) → call FUN_180fbdfcc (180fbbfde)。直線で rbx 不変。callee 宣言 short FUN_180fbdfcc(short *) は REPORT_APPENDIX_4835.md。
        ('delay 2666 FUN_180fbbfb8 rcx=param_1 (FUN_180fbdfcc)', r'sVar1 = (?:func_0x000|FUN_)180fbdfcc\(\);', 'sVar1 = FUN_180fbdfcc((short *)param_1);'),
        # KH-147 (#4835): FUN_180fbde90 の生成宣言 `short FUN_180fbde90(short *param_1)` を Ghidra 出力 (DecompEach・12.1.4) で確認。
        #   呼出元 180fcdbfc の機械語: 180fcdc1f `mov rbx,rcx` → 180fcdc22 `call 0x180fbde90` (間に rcx を書く命令なし) = 入口 param_1。
        #   本体は param_1[3] を 16bit 単位で読むので、呼出元の double* を (short *) で渡すのが bit の意味どおり (harness の _dtest rcx=double* と一致)。
        ('delay 4329 FUN_180fbde90 rcx=param_1 (180fcdc22)', r'sVar1 = (?:func_0x000|FUN_)180fbde90\(\);', 'sVar1 = FUN_180fbde90((short *)param_1);'),
        # #4883 (KH-127): FUN_180fb5c6c (3 引数・C 宣言は int, undefined4, undefined4) の呼出し 2 件。
        #   2573 は 180fb5f8c の `mov r8d,1; lea ecx,[r8+1]` (rcx=2)・`mov edx,0xc0000417` → call 180fb5fb5 → r8 = 1。
        #   5014 は 180fd2a60 の `mov r8d,1; lea ecx,[r8+2]` (rcx=3)・`mov edx,0x40000015` → call 180fd2aa6 → r8 = 1。
        ('delay 2573 FUN_180fb5c6c r8=1 (180fb5f8c 180fb5fb5)', r'(?:func_0x000|FUN_)180fb5c6c\(2,0xc0000417\);', 'FUN_180fb5c6c(2,0xc0000417,1);'),
        ('delay 5014 FUN_180fb5c6c r8=1 (180fd2a60 180fd2aa6)', r'(?:func_0x000|FUN_)180fb5c6c\(3,0x40000015\);', 'FUN_180fb5c6c(3,0x40000015,1);'),
        # #4883 (KH-127): FUN_180fb5f8c は引数 0 件 (C 宣言 void (void))。機械語 (180fb5f8c〜) は rcx・rdx・r8・r9 を読まず、先に書き換えてから使う。
        #   よって呼出し側の 5 引数 (rcx・rdx・r8・r9・[rsp+0x20]) は実行に影響しない。宣言に合わせて引数を落とす。
        #   2521 = 180fb5f35 (rcx=rbp, rdx=rsi, r8=rdi, r9=ebx, [rsp+0x20]=rax)、2547 = 180fb5f85 (全部 0)。
        ('delay 2521 FUN_180fb5f8c 5 args dropped (180fb5f35)', r'(?:func_0x000|FUN_)180fb5f8c\(param_1,param_2,param_3,param_4,param_5\);', 'FUN_180fb5f8c();'),
        ('delay 2547 FUN_180fb5f8c 5 args dropped (180fb5f85)', r'(?:func_0x000|FUN_)180fb5f8c\(0,0,0,0,0\);', 'FUN_180fb5f8c();'),
        # #4917 (KH-135): FUN_180fb5dd0 は C 宣言 void (void)。呼出し 2 件 (2535・2546) の 5 引数はすべて 0 (機械語 180fb5f40〜180fb5f85 で
        #   rcx・rdx・r8・r9・[rsp+0x20] を 0 にしてから call)。callee 本体は [rbp+0x30] (= 呼出側 [rsp+0x20] = 0) を読むが、C 本体には
        #   この読出しが無い (Ghidra 出力から落ちている)。よって引数を落としても生成 C の意味は変わらない。文脈 (直後の文) で 1 件ずつ特定する。
        ('delay 2535 FUN_180fb5dd0 5 args (0) dropped (180fb5f3c 180fb5f50)', r'FUN_180fb5dd0\(0,0,0,0,0\);\n  return;', 'FUN_180fb5dd0();\n  return;'),
        ('delay 2546 FUN_180fb5dd0 5 args (0) dropped (180fb5f5c 180fb5f70)', r'FUN_180fb5dd0\(0,0,0,0,0\);\n  FUN_180fb5f8c\(\);', 'FUN_180fb5dd0();\n  FUN_180fb5f8c();'),
        # #5401 (KH-160): FUN_180fe3510 (longlong 1 引数・rcx 入力) の呼出し 1 件 (FUN_180fd2f20 内 5129 行)。
        #   機械語: 180fd2f2a `mov rdi,rcx` → 180fd2f30 `mov rcx,[rcx+0x90]` → 180fd2f3c `call 180fe3510`。rcx = [param_1+0x90]。
        #   callee 180fe3510 は入口で rcx を読む (test rcx,rcx・[rcx+0x10])。よって引数は *(param_1+0x90)。
        ('delay 5129 FUN_180fe3510 rcx=[param_1+0x90] (180fd2f3c)', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x90\) != 0\) \{\n\s*)FUN_180fe3510\(\);', r'\1FUN_180fe3510(*(longlong *)(param_1 + 0x90));'),
        # #5401 (KH-160・2 件目): FUN_180fe4394 (longlong 1 引数・rcx 入力) の呼出し 1 件 (FUN_180fe34b0 内 6887 行)。
        #   機械語: 180fe34d3 `call 180fe4394` の直前は rcx = 入口 param_1 (180fe34b1 `mov rbx,rcx` で保持・180fe34c1)。callee 180fe4394 は入口で test rcx,rcx・rbx = rcx。
        #   よって引数は FUN_180fe34b0 の入力 param_1 (undefined *)。
        ('delay 6887 FUN_180fe4394 rcx=param_1 (180fe34d3)', r'(\(\*\(int \*\)\(param_1 \+ 0x15c\) == 0\)\) \{\n\s*)FUN_180fe4394\(\);', r'\1FUN_180fe4394((longlong)param_1);'),
        # #5361 (KH-153): FUN_180fe4020 (undefined8 *・配列先頭 + 要素数 int) の呼出し 10 件 (FUN_180fe4394 内)。
        #   機械語 (180fe4394〜180fe4457・capstone): rcx = rbx + off (rbx = 入口 param_1)、edx = 件数 (7・12・2)。
        #   off と件数は C の添字と一致 (0x00・0x38・0x70・0xd0・0x130・0x160・0x198・0x1d0・0x230・0x290)。
        #   C 宣言は longlong (整数) で、本体は rcx を qword 配列の先頭ポインタとして読む。整数の param_1 + off をそのまま渡す。
        #   規則 1 件 = 呼出し 1 件 (件数 1 を assert)。
        ('delay 5361 FUN_180fe4394 FUN_180fe4020 rcx=param_1+0x00 (180fe43b6, n=7)', r'FUN_180fe4020\(param_1,7\);', 'FUN_180fe4020((undefined8 *)param_1,7);'),
        ('delay 5361 FUN_180fe4394 FUN_180fe4020 rcx=param_1+0x38 (180fe43c1, n=7)', r'FUN_180fe4020\(param_1 \+ 0x38,7\);', 'FUN_180fe4020((undefined8 *)(param_1 + 0x38),7);'),
        ('delay 5361 FUN_180fe4394 FUN_180fe4020 rcx=param_1+0x70 (180fe43cf, n=12)', r'FUN_180fe4020\(param_1 \+ 0x70,0xc\);', 'FUN_180fe4020((undefined8 *)(param_1 + 0x70),0xc);'),
        ('delay 5361 FUN_180fe4394 FUN_180fe4020 rcx=param_1+0xd0 (180fe43dd, n=12)', r'FUN_180fe4020\(param_1 \+ 0xd0,0xc\);', 'FUN_180fe4020((undefined8 *)(param_1 + 0xd0),0xc);'),
        ('delay 5361 FUN_180fe4394 FUN_180fe4020 rcx=param_1+0x130 (180fe43ec, n=2)', r'FUN_180fe4020\(param_1 \+ 0x130,2\);', 'FUN_180fe4020((undefined8 *)(param_1 + 0x130),2);'),
        ('delay 5361 FUN_180fe4394 FUN_180fe4020 rcx=param_1+0x160 (180fe441e, n=7)', r'FUN_180fe4020\(param_1 \+ 0x160,7\);', 'FUN_180fe4020((undefined8 *)(param_1 + 0x160),7);'),
        ('delay 5361 FUN_180fe4394 FUN_180fe4020 rcx=param_1+0x198 (180fe442c, n=7)', r'FUN_180fe4020\(param_1 \+ 0x198,7\);', 'FUN_180fe4020((undefined8 *)(param_1 + 0x198),7);'),
        ('delay 5361 FUN_180fe4394 FUN_180fe4020 rcx=param_1+0x1d0 (180fe443a, n=12)', r'FUN_180fe4020\(param_1 \+ 0x1d0,0xc\);', 'FUN_180fe4020((undefined8 *)(param_1 + 0x1d0),0xc);'),
        ('delay 5361 FUN_180fe4394 FUN_180fe4020 rcx=param_1+0x230 (180fe4448, n=12)', r'FUN_180fe4020\(param_1 \+ 0x230,0xc\);', 'FUN_180fe4020((undefined8 *)(param_1 + 0x230),0xc);'),
        ('delay 5361 FUN_180fe4394 FUN_180fe4020 rcx=param_1+0x290 (180fe4457, n=2)', r'FUN_180fe4020\(param_1 \+ 0x290,2\);', 'FUN_180fe4020((undefined8 *)(param_1 + 0x290),2);'),
        # #5401 (KH-160・3 件目): FUN_180fd0ac8 (undefined4 1 引数を rcx で読む) の呼出し 3 件。宣言は 4 引数のまま。
        #   callee 180fd0ac8 は入口で `mov ebx,ecx` のみ rcx を読み、rdx・r8・r9 は `lea` で書いてから使う (読まない)。
        #   よって呼出し側は rcx = param_1 だけが意味を持つ。3 件とも `FUN_180fd0ac8(param_1);` で字句が同じため、直前の文脈で 1 件ずつ特定する。
        #   4694 = FUN_180fd099c 内 (GetModuleHandle の if の中)・4727 = FUN_180fd0a64 (TerminateProcess 後・ExitProcess の前)・4801 = FUN_180fd0b50 (if の中)。
        ('delay 4694 FUN_180fd0ac8 rcx=param_1 (FUN_180fd099c 内)', r'(\(piVar3\[0x3e\] != 0\)\)\)\) \{\n      )FUN_180fd0ac8\(param_1\);\n    \}\n  \}\n  auStackX_20\[0\] = 0;', r'\1FUN_180fd0ac8(param_1,0,0,0);\n    }\n  }\n  auStackX_20[0] = 0;'),
        ('delay 4727 FUN_180fd0ac8 rcx=param_1 (FUN_180fd0a64 内)', r'(    TerminateProcess\(uVar2,param_1\);\n  \}\n  )FUN_180fd0ac8\(param_1\);', r'\1FUN_180fd0ac8(param_1,0,0,0);'),
        ('delay 4801 FUN_180fd0ac8 rcx=param_1 (FUN_180fd0b50 内)', r'(\(piVar3\[0x3e\] != 0\)\)\)\) \{\n    )FUN_180fd0ac8\(param_1\);\n  \}\n  auStackX_20\[0\] = 0;', r'\1FUN_180fd0ac8(param_1,0,0,0);\n  }\n  auStackX_20[0] = 0;'),
        # #5401 (KH-160): FUN_180fe5f00 (MXCSR へ ecx を書く・1 引数 undefined4) の引数なし呼出し 1 件 (FUN_180fd622c 内 5723 行)。
        #   機械語: 180fd626e `call 180fe5f00` の直前で ecx = uVar2 のまま (180fd6256〜25a で計算・260〜26c の分岐で ecx は書き換わらない)。
        #   callee 180fe5f00 は入口 `mov [rsp+8],ecx; ldmxcsr` で ecx を読む。よって引数は uVar2。
        ('delay 5723 FUN_180fe5f00 ecx=uVar2 (180fd626e・FUN_180fd622c の else)', r'(\n  else \{\n    )(?:func_0x000|FUN_)180fe5f00\(\);(\n  \}\n  return uVar1;)', r'\1func_0x000180fe5f00(uVar2);\2'),
        # #5384 (KH-158): stereo ABI 族の前半 3 callee の呼出し 6 件。callee は入力を xmm0 のビット列で読む (入口 movd/movq・movaps xmm1,xmm0)。
        #   FUN_180fdc6ec・FUN_180fdc844 は引数 1 件宣言 (uint)。呼出し直前の xmm0 は入口 float (fVar) のまま = f2u(fVar)。
        #   FUN_180fdc858 は引数 1 件宣言 (ulonglong)。4042 (180fccf08) は入口 param_1 の bit を保持した経路 (movq rdx,xmm0・movaps xmm6,xmm0) で xmm0 = 入口 param_1 = d2u(param_1)。
        #   4136 (180fcd3da) は flag≠0 側。180fcd1a7 の jae は vmovq xmm0,r9 (180fcd1b3) より前に分岐するため、xmm0 は入口のまま = 入口 param_1 = d2u(param_1)。
        #   呼出し 6 件の機械語 (capstone): 180fc6b39・180fc6d65 (= 180fc6870 の 3595・3653 の順)・180fc7100・180fc745c (= 180fc6d70 の 3785・3909 の順)・180fccf08・180fcd3da (= 180fcce40 の 4042・4136 の順)。
        # #6210 (KH-184): FUN_180fc6870 の入力は xmm0 の下位 4 バイトだけ (入口で movd edx,xmm0 と vmovd eax,xmm0 の 2 箇所で読む。
        #   rcx・rdx・r8・r9・r11 は入口で読まず書いてから使う。機械語 0x180fc6870〜0x180fc6d6f 315 行で確認)。宣言を float 1 引数にし、本体の in_ZMM0 読みを引数へ置換する。
        #   本体の param_1〜4 は従来どおり未定義の値のまま残す (142 行目の FUN_180fdc320 の第 1 引数だけが param_1 を読む)。件数 1 を assert する。
        ('delay FUN_180fc6870 decl float fParam (xmm0 入力・4 引数 → 1 引数)', r'ulonglong FUN_180fc6870\(undefined8 param_1,undefined8 param_2,undefined8 param_3,undefined8 param_4\)\n\n\{\n', 'ulonglong FUN_180fc6870(float fParam)\n\n{\n  undefined8 param_1;\n  undefined8 param_2;\n  undefined8 param_3;\n  undefined8 param_4;\n'),
        ('delay FUN_180fc6870 body fVar3 = fParam (was in_ZMM0._0_4_)', r'fVar3 = in_ZMM0\._0_4_;', 'fVar3 = fParam;'),
        ('delay 3595 FUN_180fc6870 uVar1 = FUN_180fdc6ec (xmm0 = float 入力)', r'(if \(\(f2u\(fVar3\) & _DAT_1822822a0\) == _DAT_1822822a0\) \{\n\s*)uVar1 = (?:func_0x000|FUN_)180fdc6ec\(\);', r'\1uVar1 = FUN_180fdc6ec(f2u(fVar3));'),
        ('delay 3653 FUN_180fc6870 uVar1 = FUN_180fdc6ec (xmm0 = float 入力)', r'(if \(\(f2u\(fVar3\) & 0x7f800000\) == 0x7f800000\) \{\n\s*)uVar1 = (?:func_0x000|FUN_)180fdc6ec\(\);', r'\1uVar1 = FUN_180fdc6ec(f2u(fVar3));'),
        # #6160 (KH-181・受入 1): FUN_1802ed7f0 の 0 引数呼出し 934 行 (機械語 1802eda1e `call 180fc6870`)。xmm0 = xmm7 (movaps・1802eda1b)。
        #   xmm7 は 1802ed936 `movss xmm7,[rcx+0xa8]` (rcx = [param_2+0x3198]) を 1802eda13 `mulss xmm7,[181563038]` した値。
        #   [181563038] = 0x3fc90fdb = 1.5707963705062866f (π/2・float)。間に xmm7 への書込み・call は無い (1802ed936〜eda1e の直線区間)。件数 1 を assert する。
        ('delay 934 FUN_1802ed7f0 FUN_180fc6870() xmm0 = [param_2+0x3198].+0xa8 * pi/2 (1802eda1e)', r'fVar23 = \(float\)(?:func_0x000|FUN_)180fc6870\(\);', 'fVar23 = (float)FUN_180fc6870(*(float *)(*(longlong *)(param_2 + 0x3198) + 0xa8) * 1.5707963705062866f);'),
        ('delay 3785 FUN_180fc6d70 uVar25 = FUN_180fdc844 (xmm0 = float 入力)', r'(if \(\(f2u\(fVar22\) & _DAT_182282360\) == _DAT_182282360\) \{\n\s*)uVar25 = (?:func_0x000|FUN_)180fdc844\(\);', r'\1uVar25 = FUN_180fdc844(f2u(fVar22));'),
        ('delay 3909 FUN_180fc6d70 uVar25 = FUN_180fdc844 (xmm0 = float 入力)', r'(if \(\(f2u\(fVar22\) & 0x7f800000\) == 0x7f800000\) \{\n\s*)uVar25 = (?:func_0x000|FUN_)180fdc844\(\);', r'\1uVar25 = FUN_180fdc844(f2u(fVar22));'),
        ('delay 4042 FUN_180fcce40 dVar2 = FUN_180fdc858 (xmm0 = param_1)', r'(if \(\(ulonglong\)_DAT_1822828a0 <= \(ulonglong\)dVar2\) \{\n\s*dVar2 = \(double\))(?:func_0x000|FUN_)180fdc858\(\);', r'\1FUN_180fdc858(d2u(param_1));'),
        ('delay 4136 FUN_180fcce40 dVar2 = FUN_180fdc858 (xmm0 = param_1)', r'\n  dVar2 = \(double\)(?:func_0x000|FUN_)180fdc858\(\);\n  return dVar2;', '\n  dVar2 = (double)FUN_180fdc858(d2u(param_1));\n  return dVar2;'),
        # KH-154 (#5362): FUN_18004cf20 (vector の再確保・memmove) の呼出し 3 箇所 (18004d008・18004d01a・18004d035) は、d・s をアドレスの整数値 (rcx・rdx) で渡す。
        # 宣言は void* のまま (Gate の閉包も同じ shim を呼ぶため、shim を変えると gate.o が変わる)。delay の呼出し側だけ (void*) で包む。
        # 1 行 1 規則にすると if/else の同一行 (uVar3 ... 2 件) が 2 規則に当たるため、ブロック単位の規則 1 件 (件数 1 を assert) にする。
        ('delay 18004cf20 FUN_181384040 d/s as (void*) (18004d008・18004d01a・18004d035)',
         r'if \(param_2 == param_1\[1\]\) \{\n      FUN_181384040\(uVar3,\*param_1,param_2 - \*param_1\);\n      uVar1 = \*param_1;\n    \}\n    else \{\n      FUN_181384040\(uVar3,\*param_1,param_2 - \*param_1\);\n      FUN_181384040\(lVar4 \+ 4,param_2,param_1\[1\] - param_2\);',
         'if (param_2 == param_1[1]) {\n      FUN_181384040((void *)uVar3,(void *)*param_1,param_2 - *param_1);\n      uVar1 = *param_1;\n    }\n    else {\n      FUN_181384040((void *)uVar3,(void *)*param_1,param_2 - *param_1);\n      FUN_181384040((void *)(lVar4 + 4),(void *)param_2,param_1[1] - param_2);'),
        # #4889 (KH-128): FUN_180fbc1f4 の入力は xmm0 (float)、戻り値も xmm0 (float)。呼出元 FUN_1802ed7f0 の 2 件 (1082・1088) は
        #   1802ede08〜ede29: xmm6 = fVar26*48*[p+0x3188+0x24] の後、1802ede18 `jae` (X>=0) で 1802eded3 (×-0.16609640419483185) → 1802edede call (C 1082)、
        #   X<0 は 1802ede21 (×+0.16609640419483185) → 1802ede2c call (C 1088)。movaps xmm0,xmm6 の後に call。rcx は設定しない。
        #   未確定 (#5402): 符号分岐の比較対象 xmm0 = 0.0 を示す命令と VA は未確認 (plugins-kilohearts 無しで逆アセンブル不可)。±0.166 の符号はこの前提の読みで入れている。
        #   callee 本体は xmm0 を movss [rsp+8] で読む (180fbc1f4)。よって宣言は float (float)、本体は bits 変換なしで fVar4 = param_1、戻り値は fVar4。
        # #5385 (KH-159): stereo ABI 族の後半 callee (FUN_180fdc700・FUN_180fdc6d8) の呼出し 4 件。callee 宣言は ulonglong (入力 double の bit 列 = d2u)。
        #   FUN_180fdc700 2 件 ← FUN_180fcd690: 4232 は 180fcd9e5 (`movq xmm0,rdx`・rdx = 入口 param_1 の bit)、4295 は 180fcdbf0 (分岐 180fcdab7 は vmovq xmm0,r9 より前・xmm0 は入口のまま)。
        #   FUN_180fdc6d8 2 件 ← FUN_180fce0d0: 4512 は 180fce455 (`movq xmm0,rdx`・rdx = 入口 param_1)、4545 は 180fce640 (flag≠0 の 180fce460 系で xmm0 は入口のまま)。
        #   未規則化 1 件 (FUN_180fcd400 ← FUN_180fcce40 の 4060): 4060 (180fcd074) は xmm0 が reduction 後の値 (subsd の結果) で、C 側の対応式が未確定。
        ('delay 4232 FUN_180fdc700 xmm0 = param_1 (180fcd9e5)', r'(if \(\(ulonglong\)_DAT_1822829d0 <= \(ulonglong\)dVar2\) \{\n\s*)dVar2 = \(double\)(?:func_0x000|FUN_)180fdc700\(\);', r'\1dVar2 = (double)FUN_180fdc700(d2u(param_1));'),
        ('delay 4295 FUN_180fdc700 xmm0 = param_1 (180fcdbf0)', r'(\n    \}\n)    dVar2 = \(double\)(?:func_0x000|FUN_)180fdc700\(\);', r'\1    dVar2 = (double)FUN_180fdc700(d2u(param_1));'),
        ('delay 4512 FUN_180fdc6d8 xmm0 = param_1 (180fce455)', r'(return \(double\)\(\(ulonglong\)dVar4 \^ uVar1\);\n      \}\n      )dVar2 = \(double\)(?:func_0x000|FUN_)180fdc6d8\(\);', r'\1dVar2 = (double)FUN_180fdc6d8(d2u(param_1));'),
        # #5385 (KH-159 残件): FUN_180fcd400 (double, double, int) ← FUN_180fcce40 の 4048 (180fccee6)。
        #   呼出し直前: xmm0 = 入口 param_1 (180fcce60 の movq rdx,xmm0 以降 xmm0 は書かれない)、xmm1 = +0.0 (180fccee0 xorps)、r8d = 0 (180fccee3 xor)。
        ('delay 4048 FUN_180fcd400 xmm0 = param_1, xmm1 = 0.0, r8 = 0 (180fccee6)', r'(uVar3 = \(uint\)\(dVar2 != param_1\);\n\s*)dVar2 = \(double\)(?:func_0x000|FUN_)180fcd400\(\);', r'\1dVar2 = (double)FUN_180fcd400(param_1,0.0,0);'),
        ('delay 4545 FUN_180fdc6d8 xmm0 = param_1 (180fce640)', r'(    else \{\n      if \(\(ulonglong\)_DAT_182282b18 <= \(ulonglong\)dVar2\) \{\n        )dVar2 = \(double\)(?:func_0x000|FUN_)180fdc6d8\(\);', r'\1dVar2 = (double)FUN_180fdc6d8(d2u(param_1));'),
        ('delay 1082 FUN_180fbc1f4 arg xmm0 = X*(-0.166) (1802ede18 jae -> 1802eded3)', r'(0\.0 <= fVar26 \* _DAT_1814dd30c \* \*\(float \*\)\(\*\(longlong \*\)\(param_2 \+ 0x3188\) \+ 0x24\)\) \{\n\s*)fVar33 = \(float\)FUN_180fbc1f4\(\);', r'\1fVar33 = (float)FUN_180fbc1f4(fVar26 * _DAT_1814dd30c * *(float *)(*(longlong *)(param_2 + 0x3188) + 0x24) * -0.16609640419483185f);'),
        ('delay 1088 FUN_180fbc1f4 arg xmm0 = X*(+0.166) (1802ede21, X<0)', r'(dVar32 = _DAT_18147d368;\n  \}\n  else \{\n\s*)fVar33 = \(float\)FUN_180fbc1f4\(\);', r'\1fVar33 = (float)FUN_180fbc1f4(fVar26 * _DAT_1814dd30c * *(float *)(*(longlong *)(param_2 + 0x3188) + 0x24) * 0.16609640419483185f);'),
        ('delay FUN_180fbc1f4 decl float(float)', r'undefined8 FUN_180fbc1f4\(undefined8 param_1\)', 'float FUN_180fbc1f4(float param_1)'),
        ('delay FUN_180fbc1f4 input = xmm0 float bits (fVar4 = param_1)', r'uVar3 = \(undefined4\)\(\(ulonglong\)param_1 >> 0x20\);\n  fVar4 = \(float\)param_1;', 'fVar4 = param_1;'),
        ('delay FUN_180fbc1f4 return = xmm0 float (fVar4)', r'(FUN_180fbbfb8\(afStackX_8,_DAT_1813a9da0,iVar2\);\n    uVar3 = 0;\n    fVar4 = afStackX_8\[0\];\n  \}\n  )return CONCAT44\(uVar3,f2u\(fVar4\)\);', r'\1return fVar4;'),
        # #5310 (KH-149): FUN_180fdc880 (C 宣言 void) の戻り値は xmm0 (double)。機械語 180fdc9e9〜180fdc9f6 は `movq xmm0,r10; mulsd xmm0,[..]; movsd [rsi],xmm0` で、
        #   ret (180fdca0b) までの出口は 1 つ。呼出元 180fc7004 は call 直後に `movsd xmm2,xmm0` で読む。宣言は double、本体の出力先 *param_2 への書込みは残す。
        ('delay FUN_180fdc880 decl double', r'void FUN_180fdc880\(ulonglong param_1,double \*param_2,uint \*param_3\)', 'double FUN_180fdc880(ulonglong param_1,double *param_2,uint *param_3)'),
        ('delay FUN_180fdc880 return = xmm0 (*param_2 と同じ値)', r'(\n  \*param_2 = \(double\)\(uVar13 & 0xffefffffffffffff \| uVar16 \| lVar14 \+ lVar17 \+ 0x3ff << 0x34\) \*\n\s*_DAT_18228a9c0;\n)  return;\n\}', r'\1  return *param_2;\n}'),
    ],
}
# stereo 閉包 (#4871 KH-124) も、同じ 3 呼出元 (FUN_180fe3690・FUN_180fe3310・FUN_180fe3cd0。VA と機械語が delay と同一) を含む。
# FUN_180fd4f30() の引数なし呼出 22 件を delay の規則 22 本で書き換える (各規則の件数 1 は ABI の assert で確認)。
ABI['stereo'] = ABI['stereo'] + [r for r in ABI['delay'] if 'FUN_180fd4f30(' in r[2]]
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
