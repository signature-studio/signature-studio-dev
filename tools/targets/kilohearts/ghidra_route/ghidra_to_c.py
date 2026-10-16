#!/usr/bin/env python3
"""ghidra_to_c.py — Ghidra decompile 出力 (DecompEach.java の <va>.c 群) を emcc でビルド可能な 1 本の C に組む (KH-5)。

  ghidra_to_c.py <name> <outdir> <decomp_dir> <core.pe> [--fix F1,F2,..]

機械的書換えだけを行う (手書きの意味補正は --fix で個別に ON/OFF = 「修復の要否」を測るため):
  常時:   Ghidra 型名 shim (ghidra_shim.h)、FUN_<va> の前方宣言、_DAT_/_UNK_ グローバルを PE 実データで定義、
          `undefined1 auVarN[16]` + `<< 0x20` の 128bit 書込を V128 へ、callee stub (memmove/memset/abort)、
          harness 用 function_<va> wrapper (sigs.json 付き)
  --fix 対象 (既定 なし):
    bitcast    Ghidra は float のビット操作 (abs マスク `(float)((uint)(x) & MASK)`) を C キャストで表示するが、C では数値変換になる。
               f2u()/u2f() のビット再解釈に書換える (`(float)(*(uint*)p & uVarN)` も同様)
    concat     `CONCAT44(hi, fVarN)` は float をビット列として連結する意味だが、C の関数引数では float→uint の数値変換になる。f2u() で包む
    intload    Ghidra が float フィールドを int 型 (`(int **)p)[1]`) で読み `(float)` 数値変換で包む型混同。ビット再解釈 (`((float*)*(int**)p)[1]`) に直す
    assoc      Ghidra は浮動小数の積/和の結合括弧を表示で落とす (`a*(b*c)` を `a * b * c` と印字 → C は左結合 `(a*b)*c` で 1 ulp ずれる)。
               実機 x86 の演算順 (逆アセンブルで確認) に合わせ手で括弧を戻す = patches.py の (name, regex, repl) 表。**手作業 1 件 = 1 行**
    stackpair  lStack_e8/lStack_e0 のように「隣接を仮定して &lStack_e8 を配列として渡される」2 変数を long long[2] にする
    gtype      `_DAT_<va>` の C 型を patches.py の GTYPE (実機の命令の幅で確認した整数マスク) で上書きする
    lanes      Delay の 128bit ローカル auStack_118/128/138 を、参照されるレーンの型 (_0_8_・_8_8_ は double、_8_4_・_12_4_ は uint32) を持つ V128L にする (#3094)。
               同じ関数の aauStack_f8[11][16] (混在型) を整数レーンの V128A にし、float 読みは u2f・12 バイト代入は memcpy にする (#3809)
"""
import json
import re
import sys
import os

import pefile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SNAPINS = {
    'gain': {'proc': 0x1804b0380, 'exports': [0x1804b0380], 'stubs': {}},
    'haas': {'proc': 0x1804d0280, 'exports': [0x1804d0280, 0x1804d0180, 0x1804cff00, 0x1804cff90, 0x1804d0720], 'stubs': {}},
    'gate': {'proc': 0x1804c2f50, 'exports': [0x1804c2f50], 'stubs': {}, 'also': [0x180295f20, 0x180020e70]},
    'resonator': {'proc': 0x180743390, 'exports': [0x180743390], 'stubs': {}, 'also': [0x180fbc1f4, 0x180fbbfb8, 0x180fbdfcc, 0x180fbe018, 0x180fcf904, 0x180fd54cc, 0x180fd62dc, 0x180fd6320, 0x180fb6ce0, 0x180fd648c, 0x180fbdef4, 0x180fe5dfc, 0x180fd6498, 0x180fd662c, 0x180fe5f40, 0x180fd3144]},
    'stereo': {'proc': 0x18080d4d0, 'exports': [0x18080d4d0], 'stubs': {
        # 未関数化 callee (#3108 KH-45・2 件)。FP 例外の報告経路で、Inf 入力 (180fdc6d8 の指数全 1・仮数 0) でのみ到達する。
        # also へ足すと閉包が広がる (§10-7j・§10-7l の前例) ため stub にする。到達時は abort (突合で検出)。
        0x180fd8aac: 'void FUN_180fd8aac() { abort(); }',
    }, 'also': [0x180fcd690, 0x180fce0d0, 0x180fdc470, 0x180fdc660, 0x180fdc700, 0x180fdfdb0, 0x180fdc6d8, 0x180fb6c0c, 0x180fb6ce0, 0x180fcd690, 0x180fce0d0, 0x180fd1ac4, 0x180fd1b00, 0x180fd1f30, 0x180fd1f84, 0x180fd2c10, 0x180fd2c90, 0x180fd2d38, 0x180fd2f20, 0x180fd3144, 0x180fd4f30, 0x180fd51cc, 0x180fd5bcc, 0x180fd5bf4, 0x180fd5f30, 0x180fd620c, 0x180fd622c, 0x180fd62a8, 0x180fd62c8, 0x180fd8988, 0x180fd89f0, 0x180fd8aac, 0x180fdc470, 0x180fdc660, 0x180fdc6d8, 0x180fdc700, 0x180fdfdb0, 0x180fe2788, 0x180fe27b0, 0x180fe3284, 0x180fe3310, 0x180fe34b0, 0x180fe34e8, 0x180fe3510, 0x180fe3690, 0x180fe3cd0, 0x180fe4020, 0x180fe4394, 0x180fe5c6c, 0x180fe5ef0, 0x180fe5f00, 0x180fe5f0a, 0x181327120, 0x181327314, 0x18132753c]},
    'delay': {'proc': 0x1802ed7f0, 'exports': [0x1802ed7f0], 'stubs': {}, 'also': [0x180005c50, 0x18004cf20, 0x180289ea0, 0x1802ecfc0, 0x1802ed3b0, 0x1802ed490, 0x1802ed550, 0x1802ed640, 0x1802ed790, 0x180f878e0, 0x180f8791c, 0x180f87cac, 0x180f87d40, 0x180f87f24, 0x180f88084, 0x180f880a4, 0x180f880e4, 0x180f88104, 0x180fa8534, 0x180fb5b4c, 0x180fb5bb4, 0x180fb5c20, 0x180fb5c6c, 0x180fb5dd0, 0x180fb5e6c, 0x180fb5f3c, 0x180fb5f5c, 0x180fb5f8c, 0x180fb6bf8, 0x180fb6c0c, 0x180fb6ce0, 0x180fbbfb8, 0x180fbc1f4, 0x180fbde90, 0x180fbdfcc, 0x180fbe018, 0x180fc1920, 0x180fc4590, 0x180fc61dc, 0x180fc61e4, 0x180fc6870, 0x180fc6d70, 0x180fc7468, 0x180fcce40, 0x180fcd400, 0x180fcd690, 0x180fcdbfc, 0x180fcde58, 0x180fce0d0, 0x180fcf904, 0x180fd0898, 0x180fd08d0, 0x180fd099c, 0x180fd0a64, 0x180fd0a98, 0x180fd0ac8, 0x180fd0b50, 0x180fd1540, 0x180fd172c, 0x180fd185c, 0x180fd1ac4, 0x180fd1b00, 0x180fd1b34, 0x180fd1f30, 0x180fd1f84, 0x180fd27a8, 0x180fd2a60, 0x180fd2ba0, 0x180fd2c10, 0x180fd2c90, 0x180fd2d38, 0x180fd2f20, 0x180fd2fcc, 0x180fd3144, 0x180fd320c, 0x180fd4f30, 0x180fd51cc, 0x180fd5250, 0x180fd54cc, 0x180fd5bcc, 0x180fd5bf4, 0x180fd5f04, 0x180fd5f30, 0x180fd620c, 0x180fd622c, 0x180fd62a8, 0x180fd62c8, 0x180fd62dc, 0x180fd6320, 0x180fd648c, 0x180fd6498, 0x180fd662c, 0x180fd66a0, 0x180fd7d94, 0x180fd7f54, 0x180fd8988, 0x180fd89f0, 0x180fd8aac, 0x180fd8bd4, 0x180fd8d08, 0x180fdb6e0, 0x180fdc320, 0x180fdc470, 0x180fdc660, 0x180fdc6d8, 0x180fdc6ec, 0x180fdc700, 0x180fdc714, 0x180fdc7b8, 0x180fdc844, 0x180fdc858, 0x180fdc880, 0x180fdfdb0, 0x180fe027c, 0x180fe2470, 0x180fe24b8, 0x180fe2788, 0x180fe27b0, 0x180fe3284, 0x180fe3310, 0x180fe3488, 0x180fe34b0, 0x180fe34e8, 0x180fe3510, 0x180fe3690, 0x180fe3cd0, 0x180fe4020, 0x180fe4394, 0x180fe5c6c, 0x180fe5dfc, 0x180fe5ef0, 0x180fe5f00, 0x180fe5f0a, 0x180fe5f40, 0x181327120, 0x181327314, 0x181327348, 0x18132753c]},
}
STUB = {  # 未 decompile の callee → C 実装 (RetDec stage-0 + kh_lower ルート (snapins/lift/kh_lower.py) の shims/fail-fast stub と同じ扱い)
    0x181384040: 'void* FUN_181384040(void* d, const void* s, ulonglong n) { return memmove(d, s, (size_t)n); }',
    0x1813846e0: 'void* FUN_1813846e0(void* d, int c, ulonglong n) { return memset(d, c, (size_t)n); }',
    0x18004cf20: 'longlong FUN_18004cf20(void* a, void* b, void* c) { abort(); return 0; }',
    # 未関数化 callee (delay 閉包の外・decompile していない)。`()` 定義で呼出の arity を問わない。到達時に abort する。
    0x180fe5c74: 'longlong FUN_180fe5c74() { abort(); return 0; }',
    0x180fe2508: 'longlong FUN_180fe2508() { abort(); return 0; }',
}
# THUNK: Ghidra が `func_0x000<va>(...)` と呼ぶ callee → fail-fast stub。引数無しの定義 (`()`) は呼出の arity を問わない。
# 到達時に abort し、突合で検出する。2 種類ある: (a) IAT thunk (jmp [rip+disp] → KERNEL32 の import)・(b) 未関数化 callee (本体を decompile していない VA)。
THUNK = {
    # (a) IAT thunk。Win API の意味は実装しない
    0x180fd81e4: 'longlong func_0x000180fd81e4() { abort(); return 0; } /* KERNEL32!FlsGetValue */',
    0x180fd81ec: 'longlong func_0x000180fd81ec() { abort(); return 0; } /* KERNEL32!FlsSetValue */',
    # (b) 未関数化 callee (delay 閉包の外)。decompile せず fail-fast stub にする
    0x180fbdef4: 'longlong func_0x000180fbdef4() { abort(); return 0; } /* 未関数化 callee (stub) */',
    0x180fbdd78: 'longlong func_0x000180fbdd78() { abort(); return 0; } /* 未関数化 callee (stub) */',
}
# Ghidra の下線なし名 (`DAT_<va>`・`uRam<16桁 va>`) の C 型。Ghidra は型を出さないため使用箇所から確定し、表に無い名前は停止する。
# 根拠 (delay.c の使用行): DAT_182280d00・DAT_182280d70 = `(ulonglong)DAT_x` の bit マスク (uint64)。
#   DAT_184161fb0 = `!= '\0'` と `= '\x01'` の once フラグ (byte)。DAT_1829899e0 = `== '\0'` (byte)。
#   DAT_182989850 = `(DAT_x & 2) != 0` の読み出しのみ (byte 読みでも bit 1 は同じ)。
#   DAT_182989680・DAT_184162358 = `&DAT_x` のアドレスだけ (`undefined *` 型の比較・代入先と一致)。
#   uRam1829899cc/d0/d4 = `undefined4` 変数への読み出し (uint)。uRam18436cc00 = FUN_181327120 (GS 失敗報告経路・swi(0x29) で fail-fast) の書込み (8 byte の ExceptionInformation 相当)。
EXT_CTYPE = {
    'DAT_182280d00': 'ulonglong', 'DAT_182280d70': 'ulonglong', 'DAT_184161fb0': 'unsigned char',
    'DAT_1829899e0': 'unsigned char', 'DAT_182989850': 'unsigned char', 'DAT_182989680': 'undefined',
    'DAT_184162358': 'undefined',
    'uRam00000001829899cc': 'uint', 'uRam00000001829899d0': 'uint', 'uRam00000001829899d4': 'uint',
    'uRam000000018436cc00': 'ulonglong',
}


RCPPS_HELPER = r'''/* rcpps 2 引数形 rcpps(dest, src): 実機 (AMD Ryzen 9 9950X) の近似表 (snapins/lift/gen_simd.py と同一表・同一指数則)。 */
static const uint32_t kh_at_rcp[4096] = %s;
static inline uint32_t kh_rcp_exact(uint32_t x) {
    uint32_t s = x & 0x80000000u, e = (x >> 23) & 0xff, man = x & 0x7fffffu;
    if (e == 0) return s | 0x7f800000u;
    if (e == 0xff) return man ? (s | 0x7f800000u | (man | 0x400000u)) : s;
    int t = 253 - (int)e;
    return t <= 0 ? s : (s | ((uint32_t)t << 23) | kh_at_rcp[(x >> 11) & 0xfffu]);
}
#define rcpps(dst, src) kh_rcpps(src)  /* dst は未使用 (Ghidra の 1 引数目)。値を捨てる */
static inline V128 kh_rcpps(V128 src) {
    V128 r;
    for (int i = 0; i < 4; i++) {
        uint32_t x, w;
        memcpy(&x, src.b + 4 * i, 4);
        w = kh_rcp_exact(x);
        memcpy(r.b + 4 * i, &w, 4);
    }
    return r;
}
'''


RSQRTPS_HELPER = r'''/* rsqrtps 2 引数形 rsqrtps(dest, src): 実機の近似表 (snapins/lift/gen_simd.py の kh_rsqrt_exact と同一表・同一指数則)。 */
static const uint32_t kh_at_rsq_odd[4096] = %s;
static const uint32_t kh_at_rsq_even[4096] = %s;
static inline uint32_t kh_rsqrt_exact(uint32_t x) {
    uint32_t s = x & 0x80000000u, e = (x >> 23) & 0xff, man = x & 0x7fffffu;
    if (e == 0) return s | 0x7f800000u;
    if (e == 0xff) return man ? (s | 0x7f800000u | (man | 0x400000u)) : (s ? 0xffc00000u : 0u);
    if (s) return 0xffc00000u;
    return (((uint32_t)(190 - (int)((e + 1) >> 1)) << 23) | ((e & 1) ? kh_at_rsq_odd[(x >> 11) & 0xfffu]
                                                                    : kh_at_rsq_even[(x >> 11) & 0xfffu]));
}
#define rsqrtps(dst, src) kh_rsqrtps(src)  /* dst は未使用 (Ghidra の 1 引数目)。値を捨てる */
static inline V128 kh_rsqrtps(V128 src) {
    V128 r;
    for (int i = 0; i < 4; i++) {
        uint32_t x, w;
        memcpy(&x, src.b + 4 * i, 4);
        w = kh_rsqrt_exact(x);
        memcpy(r.b + 4 * i, &w, 4);
    }
    return r;
}
'''


LANE_HELPER = r'''/* 128bit ローカルの型付きレーン (Delay auStack_118/128/138)。Ghidra の参照文脈で型を決めた: _0_8_・_8_8_ は double (dVar の代入と (double) 参照)、
   _8_4_・_12_4_ は uint32 (SUB84 と (int)(x >> 0x20) の書込み)。float 型の V128 に載せると整数→浮動小数の数値変換になるため別型にする。 */
typedef union {
    uint8_t b[16];
    struct { double _0_8_; };
    struct { uint8_t _p8a[8]; double _8_8_; };
    struct { uint8_t _p8b[8]; uint32_t _8_4_; };
    struct { uint8_t _p12[12]; uint32_t _12_4_; };
} V128L;
'''


LANE_F8_HELPER = r'''/* Delay の aauStack_f8[11][16] (128bit 一時領域の 2 次元配列)。参照文脈で型を決めた (#3809): _0_4_・_4_4_・_8_4_・_12_4_ は整数レーン
   (書込みは int・uint の値、float 読みは u2f でビット再解釈)、_4_12_ は 12 バイトのバイト列 (undefined1[12] の代入は memcpy)、_8_8_ は uint64。 */
typedef union {
    uint8_t b[16];
    struct { uint32_t _0_4_, _4_4_, _8_4_, _12_4_; };
    struct { uint8_t _p4[4]; uint8_t _4_12_[12]; };
    struct { uint8_t _p8[8]; uint64_t _8_8_; };
} V128A;
'''


# delay の 2 件 (機械語で確定・REPORT_APPENDIX_3835.md)。件数は各 1 件に固定し、外れたら停止する (DELAY_RULES)
#   LAB_180fd2aab: FUN_180fd2a60 の `call FUN_180fb5c6c` の戻り番地 (機械語の fall-through 先と同じ番地)。
#                  C の継続は制御の流れで表すので、戻り番地の 8 byte 書込みは同関数の既存行 (0x180fd2ab5) と同形に書く。
#   PTR__guard_dispatch_icall_1813a1d38: FUN_180fa8534 の CFG 間接呼出し (機械語 0x180fa856a)。
#                  this = rcx = *param_1 - 8、vtable = *this、呼出先 = vtable[0x40] (rax)、rdx = 呼出し時点の元の param_2。
#                  param_2 は vtable[0x30] に置き換える (機械語の rbx)。戻り値は使わない (直後で eax=0)。
DELAY_RULES = [
    ('LAB_180fd2aab: 戻り番地の書込み', r'\*\(undefined1 \*\*\)\(puVar4 \+ -8\) = &LAB_180fd2aab;',
     '*(undefined8 *)(puVar4 + -8) = 0x180fd2aab;', 1),
    ('PTR__guard_dispatch_icall: CFG 間接呼出し',
     r'param_2 = \*\(byte \*\*\)\(\*\(longlong \*\)\(\*param_1 \+ -8\) \+ 0x30\);\n    \(\*\(code \*\)PTR__guard_dispatch_icall_1813a1d38\)\(\);',
     '{ longlong kh_this = *param_1 - 8; longlong kh_vt = *(longlong *)kh_this; byte *kh_p2 = param_2; param_2 = *(byte **)(kh_vt + 0x30);\n'
     '      ((void (*)(longlong, byte *))*(code **)(kh_vt + 0x40))(kh_this, kh_p2); }', 1),
    # #4685 (KH-108): 型不一致の残り 3 行。機械語で確定 (REPORT_APPENDIX_4685.md)。
    #   _DAT_18436cd18: FUN_181327120・FUN_181327348 の 8 byte 整数書込み (mov qword [..],rax)。GTYPE で longlong。ポインタ値を整数として書く。
    #   _UNK_182280e04: FUN_180fc4590 の auVar2 の 12 byte (バイト 4〜15) の定数 (e04 から 12 byte)。memcpy で同じバイト列を写す。
    ('_DAT_18436cd18 = puVar3 + 0x40: ポインタ値の整数書込み (#4685)', r'_DAT_18436cd18 = puVar3 \+ 0x40;',
     '_DAT_18436cd18 = (longlong)(puVar3 + 0x40);', 2),
    ('_UNK_182280e04: 12 byte 代入 (#4685)', r'auVar2\._4_12_ = _UNK_182280e04;',
     'memcpy(&auVar2._4_12_, gd_182280e04, 12);', 1),
    # #4900 (KH-132): vcvtpd2dq の結果 (32bit 整数) の下位 lane を int で読む 2 行。機械語で確定 (REPORT_APPENDIX_4900.md)。
    #   FUN_180fc4590 0x180fc48bc〜48db: movd ecx,xmm4 → and eax,ecx → sub ecx,eax → sar ecx,6 (整数演算)。
    #   auVar20 は V128 (_0_4_ が float) なので、ビット列を f2u() で読み直す (値変換の (int) にしない。V128 の型は変えない)。
    ('auVar20._0_4_ & 0x3f: vcvtpd2dq の下位 lane をビット列で読む (#4900)', r'uVar19 = auVar20\._0_4_ & 0x3f;',
     'uVar19 = f2u(auVar20._0_4_) & 0x3f;', 1),
    ('auVar20._0_4_ - uVar19: vcvtpd2dq の下位 lane をビット列で読む (#4900)', r'uVar3 = \(int\)\(auVar20\._0_4_ - uVar19\) >> 6;',
     'uVar3 = (int)(f2u(auVar20._0_4_) - uVar19) >> 6;', 1),
    # #5664 (KH-174): float のグローバルの符号反転 (`xorps` 0x1813d1a80) を、値変換 (float)(uint) ではなくビット列で行う 2 行。
    #   FUN_180fbbfb8 0x180fbc06f〜0a7: movss xmm2,[182286970] (float) → movaps → xorps [1813d1a80] → comiss。
    #   2684 は `(float)((uint)_DAT_182286970 ^ M)` (値変換で 2^-25 が 0 になる)。機械語の値は bit 列の XOR なので u2f(f2u(X) ^ M)。
    #   2707 は FUN_180fbc14f の `movss xmm1,[182286958]` → `xorps [1813d1a80]` (同形)。
    ('2684 _DAT_182286970 ^ sign: float の符号反転をビット列で (#5664)', r'\(float\)\(\(uint\)_DAT_182286970 \^ _DAT_1813d1a80\)',
     'u2f(f2u(_DAT_182286970) ^ _DAT_1813d1a80)', 1),
    ('2707 _DAT_182286958 ^ sign: float の符号反転をビット列で (#5664)', r'\(float\)\(\(uint\)_DAT_182286958 \^ _DAT_1813d1a80\)',
     'u2f(f2u(_DAT_182286958) ^ _DAT_1813d1a80)', 1),
    # #5664 (KH-174): FUN_1802ed7f0 の 1249・1254 行 (1250・1255 の同形を含む)。機械語 1802ee03d: movaps xmm2,xmm0 → xorps [1813d1a80] → andps xmm2,xmm0。
    #   float レジスタへの符号マスク XOR と AND なので、(uint)fVar は数値変換ではなくビット列 f2u() で読む。
    # #5664 (KH-174): FUN_180fbc1f4 の符号判定。機械語 180fbc2c1: test WORD PTR [rsp+0x42],0x8000 (float の上位 16bit の符号)。
    #   (uint)float は値変換 (負の float で未定義) なので、ビット列 f2u() で符号ビットを読む。
    ('2766 FUN_180fbc1f4 sign bit of afStackX_8[0] (ビット列)', r'if \(\(\(uint\)afStackX_8\[0\] & 0x80000000\) != 0\) \{',
     'if (((f2u(afStackX_8[0])) & 0x80000000) != 0) {', 1),
    # #5664 (KH-174): FUN_180fc61e4 (float 1 引数) の同形の符号判定。機械語 180fc6223: test WORD PTR [rsp+0x32],ax (0x8000)。
    ('3549 FUN_180fc61e4 sign bit of afStackX_8[0] (ビット列)', r'if \(\(\(uint\)afStackX_8\[0\] & 0x80000000\) == 0\) \{',
     'if (((f2u(afStackX_8[0])) & 0x80000000) == 0) {', 1),
    ('1249 FUN_1802ed7f0 uVar21 = fVar26 sign bits', r'uVar21 = \(uint\)fVar26 \^ _DAT_1813d1a80;', 'uVar21 = f2u(fVar26) ^ _DAT_1813d1a80;', 1),
    ('1250 FUN_1802ed7f0 uVar19 = fVar31 sign bits', r'uVar19 = \(uint\)fVar31 \^ _UNK_1813d1a84;', 'uVar19 = f2u(fVar31) ^ _UNK_1813d1a84;', 1),
    ('1254 FUN_1802ed7f0 auVar6 hi = fVar31 bits', r'auVar6\._4_4_ = uVar19 & \(uint\)fVar31;', 'auVar6._4_4_ = uVar19 & f2u(fVar31);', 1),
    ('1255 FUN_1802ed7f0 auVar6 lo = fVar26 bits', r'auVar6\._0_4_ = uVar21 & \(uint\)fVar26;', 'auVar6._0_4_ = uVar21 & f2u(fVar26);', 1),
    # #4838 (KH-119): 代入の pointer⇔整数 5 行。機械語で確定 (REPORT_APPENDIX_3801.md の P6 の現 HEAD 残件)。
    #   FUN_180f88084・FUN_180f880a4・FUN_180fd2d38: 初期化の 8 byte スロットへ leaq で得た番地を movq で書く。
    #   値はそのアドレス (&UNK_<va>) のビット列。整数型スロットへ同ビットを明示キャストで書く (数値変換にしない)。
    #   `&UNK_` 形は tbase 置換 (gt_<base> + off) より前に当てる。
    ('param_1[1] = &UNK_18227b1f8 (#4838)', r'param_1\[1\] = &UNK_18227b1f8;',
     'param_1[1] = (longlong)&UNK_18227b1f8;', 1),
    ('param_1[1] = &UNK_18227b208 (#4838)', r'param_1\[1\] = &UNK_18227b208;',
     'param_1[1] = (longlong)&UNK_18227b208;', 1),
    ('*param_1 = &UNK_1813a3e58 (#4838)', r'\*param_1 = &UNK_1813a3e58;',
     '*param_1 = (longlong)&UNK_1813a3e58;', 1),
    ('*param_1 = &UNK_1813a4968 (#4838)', r'\*param_1 = &UNK_1813a4968;',
     '*param_1 = (longlong)&UNK_1813a4968;', 1),
    ('*param_1 = &UNK_1822849e0 (#4838)', r'\*param_1 = &UNK_1822849e0;',
     '*param_1 = (longlong)&UNK_1822849e0;', 1),
    # KH-136 (#4955): FUN_1802ecfc0 (tap_add) の宣言と本体。機械語 0x1802ecfc0〜ecfe6 で確定:
    #   r8・r9 (param_3・param_4) は addps の 16 byte メモリオペランド。結果は movlps で下位 8 byte (2 lane) だけを書く。
    #   よって param_3・param_4 は V128 * (float * は誤り)。lane は (float) の数値変換ではなくビット列 (u2f) で読む。
    ('FUN_1802ecfc0 宣言: 16 byte の V128 * (KH-136)', r'void FUN_1802ecfc0\(longlong param_1,int param_2,float \*param_3,float \*param_4\)',
     'void FUN_1802ecfc0(longlong param_1,int param_2,V128 *param_3,V128 *param_4)', 1),
    ('FUN_1802ecfc0 本体 lane 0・1 (param_3): addps の 2 lane (KH-136)',
     r'CONCAT44\(\(float\)\(\(ulonglong\)uVar1 >> 0x20\) \+ param_3\[1\],\(float\)uVar1 \+ \*param_3\);',
     'CONCAT44(f2u(u2f((uint)(uVar1 >> 0x20)) + param_3->_4_4_),f2u(u2f((uint)uVar1) + param_3->_0_4_));', 1),
    ('FUN_1802ecfc0 本体 lane 0・1 (param_4): addps の 2 lane (KH-136)',
     r'CONCAT44\(\(float\)\(\(ulonglong\)uVar2 >> 0x20\) \+ param_4\[1\],\(float\)uVar2 \+ \*param_4\);',
     'CONCAT44(f2u(u2f((uint)(uVar2 >> 0x20)) + param_4->_4_4_),f2u(u2f((uint)uVar2) + param_4->_0_4_));', 1),
    # 呼出元 (delay 1271): uStack_108 (8 byte) と uStack_100 (0 を書いた上位 8 byte) を 1 つの 16 byte 引数にまとめる。
    #   aauStack_f8 は呼出先が 16 byte (aauStack_f8[0]) を読むので V128 * へ cast する (値は変えない)。
    ('caller FUN_1802ecfc0: uStack_108/100 を 16 byte 引数に (KH-136)',
     r'FUN_1802ecfc0\(\*\(undefined8 \*\)\(param_1 \+ 0x198\),uVar22 & 0xffffffff,&uStack_108,\s*aauStack_f8\);',
     '{ V128 kh_p108; kh_p108._0_8_ = uStack_108; kh_p108._8_8_ = uStack_100; FUN_1802ecfc0(*(undefined8 *)(param_1 + 0x198),uVar22 & 0xffffffff,&kh_p108,(V128 *)aauStack_f8); }', 1),
]


def approx_rcp_table():
    """snapins/scripts/approx_tables.b64 の rcp 表 (4096 entry) を C 配列リテラルで返す。"""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'snapins', 'lift'))
    import gen_simd
    return gen_simd.load_approx_tables()['rcp']


def approx_rsq_tables():
    """同 approx_tables.b64 の rsq_odd / rsq_even 表 (各 4096 entry) を (odd, even) の C 配列リテラルで返す。"""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'snapins', 'lift'))
    import gen_simd
    t = gen_simd.load_approx_tables()
    return t['rsq_odd'], t['rsq_even']


def pe_bytes(pe, va, n):
    rva = va - pe.OPTIONAL_HEADER.ImageBase
    return pe.get_data(rva, n)


THUNK_HDR = re.compile(r'^([\w \*]+?\s*\n?\s*)thunk_FUN_([0-9a-f]+)(\([^;{}]*\)\s*\n\s*\{)', re.S | re.M)


def rewrite_thunks(t, va):
    """関数 va の本文 (コメント除去済み): 定義ヘッダの thunk_FUN_<X> は FUN_<va>、本体の呼出 thunk_FUN_<X> は飛び先の FUN_<X> (jmp thunk なので同じ動作)。"""
    t = THUNK_HDR.sub(lambda m: m.group(1) + 'FUN_%x' % va + m.group(3), t, count=1)
    return re.sub(r'\bthunk_FUN_([0-9a-f]+)\b', r'FUN_\1', t)


def _close(t, o):
    """t[o] == '(' の対応する ')' の位置。"""
    depth = 0
    for k in range(o, len(t)):
        if t[k] == '(':
            depth += 1
        elif t[k] == ')':
            depth -= 1
            if depth == 0:
                return k
    raise SystemExit('括弧が閉じない (dbitcast・停止)')


def dbitcast(t):
    """double のビット再解釈を d2u/u2d に書換える。対象は double 変数 (dVarN と double 引数 param_N)。
    (double)( … (ulonglong)X … ) はビット演算の結果を double に読む形なので u2d( … ) にする。
    (double)(int)・(double)(uint) で始まる式は数値変換なので残す。残りの (ulonglong)X は d2u(X)。"""
    dnames = set(re.findall(r'\bdouble (\w+)\b', t)) | set(re.findall(r'\bdVar\d+\b', t))
    alt = '|'.join(sorted(map(re.escape, dnames), key=len, reverse=True)) or r'(?!)'
    cast = re.compile(r'\(ulonglong\)(' + alt + r')\b')

    def rec(s):
        out, i = [], 0
        while True:
            j = s.find('(double)(', i)
            if j < 0:
                out.append(s[i:])
                break
            o = j + len('(double)')
            k = _close(s, o)
            inner = s[o + 1:k]
            is_bits = bool(cast.search(inner)) and not re.match(r'\s*\((int|uint)\)', inner)
            if is_bits:
                out.append(s[i:j] + 'u2d(' + rec(inner) + ')')
            else:
                out.append(s[i:j] + '(double)(' + rec(inner) + ')')
            i = k + 1
        return ''.join(out)

    t = rec(t)
    return cast.sub(r'd2u(\1)', t)


def infer_type(lines, sym):
    """グローバル sym ごとの C 型推定。(double) キャスト直前の比較 → double / `& sym`・`uVarN = sym`・`sym = uVarN` → uint / 他 float。
    Ghidra は同一グローバルを float と uint の両方で使うことがある (abs マスク 0x1813d6fc0)。uint が 1 行でもあれば uint。"""
    t = set()
    for l in lines:
        if re.search(r'\(double\)\w+\)?\s*$|<= \(double\)|\(double\)[^;]*[<>]=? ' + re.escape(sym) + r'|' + re.escape(sym) + r' [<>]=? \(double\)', l):
            t.add('double')
        elif re.search(r'& ' + re.escape(sym) + r'\b|\buVar\d+ = ' + re.escape(sym) + r'\b|\b' + re.escape(sym) + r' = uVar\d+', l):
            t.add('uint')
        else:
            t.add('float')
    return t


def main():
    a = sys.argv[1:]
    name, outdir, ddir, core = a[:4]
    fixes = set((a[a.index('--fix') + 1] if '--fix' in a else '').split(','))
    cfg = SNAPINS[name]
    os.makedirs(outdir, exist_ok=True)
    pe = pefile.PE(core, fast_load=True)
    vas = list(dict.fromkeys(cfg['exports'] + cfg.get('also', [])))
    src = {va: open(os.path.join(ddir, '%x.c' % va)).read() for va in vas}
    alltxt = '\n'.join(src.values())
    # rcpps は代入形 `X = rcpps(D, S);` だけを許す (戻り値を捨てる形は数値が silent に誤るため停止)
    rc_bad = [l for l in alltxt.split('\n') if 'rcpps(' in l and not re.match(r'^\s*\w+ = rcpps\(\w+,\s*\w+\);\s*$', l)]
    if rc_bad:
        raise SystemExit('rcpps の非代入形を検出 (停止): ' + ' | '.join(rc_bad[:3]))
    # rsqrtps も同じく代入形だけを許す (rsqrtps(D, S) の戻り値を捨てる形は停止)
    rs_bad = [l for l in alltxt.split('\n') if 'rsqrtps(' in l and not re.match(r'^\s*\w+ = rsqrtps\(\w+,\s*\w+\);\s*$', l)]
    if rs_bad:
        raise SystemExit('rsqrtps の非代入形を検出 (停止): ' + ' | '.join(rs_bad[:3]))
    # --- グローバル
    gl = {}
    for m in re.finditer(r'\b(_DAT|_UNK)_([0-9a-f]{8,9})\b', alltxt):
        gl.setdefault(int(m.group(2), 16), m.group(1))
    gtypes = {}
    for va, kind in gl.items():
        ls = [l for l in alltxt.split('\n') if ('%s_%x' % (kind, va)) in l]
        ts = infer_type(ls, '%s_%x' % (kind, va))
        gtypes[va] = ('uint' if kind == '_UNK' or 'uint' in ts else ('double' if 'double' in ts else 'float'), kind, sorted(ts))
    if 'gtype' in fixes:
        from patches import GTYPE
        for k, ty in GTYPE.get(name, {}).items():
            va = int(k, 16)
            assert va in gtypes, 'gtype rule not used (global not in %s): %s' % (name, k)
            gtypes[va] = (ty, gtypes[va][1], gtypes[va][2])
    out = ['#include "ghidra_shim.h"', '/* 自動生成: ghidra_to_c.py %s (fix=%s) */' % (name, ','.join(sorted(f for f in fixes if f)) or 'none')]
    if 'rcpps(' in alltxt:
        out.append(RCPPS_HELPER % approx_rcp_table())
    if 'rsqrtps(' in alltxt:
        out.append(RSQRTPS_HELPER % approx_rsq_tables())
    if name == 'stereo':  # callee の戻り xmm0 (縮約値) の helper (KH-74)。式と突合は kh_xmm0.h / xmm0_check.c
        out.append(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kh_xmm0.h')).read())
    if 'lanes' in fixes and re.search(r'undefined1 auStack_(118|128|138) \[16\];', alltxt):
        out.append(LANE_HELPER)
    if 'lanes' in fixes and re.search(r'undefined1 aauStack_f8 \[11\] \[16\];', alltxt):
        out.append(LANE_F8_HELPER)
    for va, (ty, kind, _) in sorted(gtypes.items()):
        if ty == 'FNPTR':  # 関数ポインタ slot (#4671): PE の thunk を値として再現せず、到達時 abort の関数を指す
            out.append('static void FNPTR_%x() { abort(); }' % va)
            out.append('static void (*fp_%x)() = FNPTR_%x;' % (va, va))
            out.append('#define %s_%x fp_%x' % (kind, va, va))
            continue
        d = pe_bytes(pe, va, 16)
        out.append('static unsigned char gd_%x[16] __attribute__((aligned(16))) = {%s};' % (va, ','.join(str(x) for x in d)))
        out.append('#define %s_%x (*(%s*)gd_%x)' % (kind, va, ty, va))
    # --- 下線なしの名前 (DAT_<va>・uRam<16桁>): 同じ PE 実データを指す。型は EXT_CTYPE (使用箇所で確定)。表に無い名前は停止する
    ext = {}
    for n in sorted(set(re.findall(r'\b(DAT_[0-9a-f]{8,9}|uRam[0-9a-f]{16})\b', alltxt))):
        if n not in EXT_CTYPE:
            raise SystemExit('未定義 identifier の型が未確定 (停止): ' + n)
        ext[n] = int(n[4:], 16)
    gd_done = set(gtypes)  # 同じ VA を指す名前 (例 DAT_x と uRam0000000x) があっても gd 配列は 1 回だけ定義する
    for n, va in sorted(ext.items(), key=lambda kv: kv[1]):
        if va not in gd_done:
            gd_done.add(va)
            d = pe_bytes(pe, va, 16)
            out.append('static unsigned char gd_%x[16] __attribute__((aligned(16))) = {%s};' % (va, ','.join(str(x) for x in d)))
        out.append('#define %s (*(%s*)gd_%x)' % (n, EXT_CTYPE[n], va))
    # --- 配列参照 (&UNK_x + 添字 = テーブル先頭からのバイト位置): 参照された範囲を 1 本の byte 配列にする
    tabs = sorted(set(int(x, 16) for x in re.findall(r'&UNK_([0-9a-f]{8,9})\b', alltxt)))
    tbase = tend = None
    if tabs:
        tbase = tabs[0] & ~0xf
        tend = max(tabs) + 0x40
        tb = pe_bytes(pe, tbase, tend - tbase)
        out.append('static unsigned char gt_%x[%d] __attribute__((aligned(16))) = {%s};' % (
            tbase, tend - tbase, ','.join(str(x) for x in tb)))
    # --- 前方宣言 (Ghidra の定義シグネチャから)
    protos = []
    bodies = []
    abi_hits = {}
    from patches import V128OPS
    v128_hits = {}
    delay_hits = {}
    stubs = dict(STUB)
    stubs.update(cfg['stubs'])
    for va in vas:
        t = src[va]
        t = re.sub(r'/\*.*?\*/', '', t, flags=re.S)
        t = rewrite_thunks(t, va)
        t = re.sub(r'undefined1 (auVar\d+) \[16\];', r'V128 \1;', t)
        t = re.sub(r'undefined1 (in_XMM\d+) \[16\];', r'V128 \1;', t)
        if 'lanes' in fixes:
            t = re.sub(r'undefined1 (auStack_(?:118|128|138)) \[16\];', r'V128L \1;', t)
            t = re.sub(r'undefined1 aauStack_f8 \[11\] \[16\];', r'V128A aauStack_f8 [11];', t)
            t = re.sub(r'\b(aauStack_f8\[\d+\]\._4_12_) = (auStack_\w+);', r'memcpy(\1, \2, 12);', t)
            t = re.sub(r'= (aauStack_f8\[\d+\]\._(?:0|4)_4_);', r'= u2f(\1);', t)
            t = re.sub(r'(auVar\d+\._(?:8|12)_4_) = (uVar\d+ & aauStack_f8\[\d+\]\._(?:8|12)_4_);', r'\1 = u2f(\2);', t)
        if name == 'delay':
            t = t.replace('func_0x0001802ecfc0(', 'FUN_1802ecfc0(')
            for nm, rx, rp, _ in DELAY_RULES:
                t, k = re.subn(rx, rp, t)
                delay_hits[nm] = delay_hits.get(nm, 0) + k
        t = re.sub(r'\b(in_XMM\d+)\._0_8_\b', r'\1._0_8_d', t)
        t = re.sub(r'\b(maxps|minps|vpand_avx|vpor_avx|vpsubq_avx|vpsubd_avx)\((\w+),_DAT_([0-9a-f]+)\)', r'\1(\2,(*(V128 *)gd_\3))', t)
        if tbase is not None:
            t = re.sub(r'&UNK_([0-9a-f]{8,9})\b', lambda m: '((unsigned char*)gt_%x + 0x%x)' % (tbase, int(m.group(1), 16) - tbase), t)
        t = re.sub(r'\*\(undefined1 \(\*\) \[16\]\)\((.*?)\) = (auVar\d+) << 0x20;', r'v128_store_shl32((void*)(\1), \2);', t)
        t = re.sub(r'\*\(undefined1 \(\*\) ?\[16\]\)', r'*(V128 *)', t)
        if 'bitcast' in fixes:
            t = re.sub(r'\(float\)\(\(uint\)(\(.*?\)) & (_DAT_[0-9a-f]+|uVar\d+)\)', r'u2f(f2u\1 & \2)', t)
            t = re.sub(r'\(float\)\((\*\(uint \*\)\(.*?\)) & (uVar\d+)\)', r'u2f(\1 & \2)', t)
        if 'dbitcast' in fixes:
            t = dbitcast(t)
        if 'concat' in fixes:
            t = re.sub(r'CONCAT44\((\w+),(fVar\d+)\)', r'CONCAT44(\1,f2u(\2))', t)
        if 'intload' in fixes:
            t = re.sub(r'\(float\)(\(\*\(int \*\*\)\(.*?\)\))\[(\d+)\]', r'((float *)\1)[\2]', t)
        if 'assoc' in fixes:
            from patches import ASSOC
            for nm, rx, rp in ASSOC.get(name, []):
                t, k = re.subn(rx, rp, t)
                if k == 0 and ('FUN_%x' % va) in nm:
                    pass
        if 'stackpair' in fixes:
            t = re.sub(r'\blonglong lStack_e8;\n\s*longlong lStack_e0;', 'longlong lStk[2];', t)
            t = t.replace('&lStack_e8', 'lStk').replace('lStack_e8', 'lStk[0]').replace('lStack_e0', 'lStk[1]')
        from patches import ABI
        for nm, rx, rp in ABI.get(name, []):
            t, k = re.subn(rx, rp, t)
            abi_hits[nm] = abi_hits.get(nm, 0) + k
        for nm, rx, rp, _ in V128OPS.get(name, []):
            t, k = re.subn(rx, rp, t)
            v128_hits[nm] = v128_hits.get(nm, 0) + k
        m = re.search(r'^([\w \*]+?)\s*\n?\s*FUN_%x\((.*?)\)\s*\n\s*\{' % va, t, re.S | re.M)
        if not m:
            m = re.search(r'^([\w \*]+?)\s+FUN_%x\((.*?)\)\s*\{?' % va, t, re.S | re.M)
        assert m, 'signature not found %x' % va
        protos.append('%s FUN_%x(%s);' % (m.group(1).strip(), va, ' '.join(m.group(2).split())))
        bodies.append(t)
    for nm, _, _ in ABI.get(name, []):
        assert abi_hits.get(nm) == 1, 'ABI rule hit %s: %s' % (abi_hits.get(nm), nm)
    for nm, _, _, n in V128OPS.get(name, []):
        assert v128_hits.get(nm) == n, 'V128 rule hit %s (want %d): %s' % (v128_hits.get(nm), n, nm)
    for nm, _, _, n in (DELAY_RULES if name == 'delay' else []):
        assert delay_hits.get(nm) == n, 'delay rule hit %s (want %d): %s' % (delay_hits.get(nm), n, nm)
    # スタブは本体を decompile していない callee にだけ出す (本体がある VA に出すと宣言が衝突する: FUN_18004cf20・delay)
    for va, s in stubs.items():
        if ('FUN_%x' % va) in alltxt and va not in vas:
            protos.append(s.split('{')[0].strip() + ';')
    out += protos
    out += [stubs[v] for v in stubs if ('FUN_%x' % v) in alltxt and v not in vas]
    out += [THUNK[v] for v in THUNK if ('func_0x000%x' % v) in alltxt and v not in vas]
    # --- 呼出名の統一: Ghidra は未命名 callee を func_0x<va> で呼ぶが、定義側は同一 va を FUN_<va> で出す (also 追加分)
    defined = set(vas)
    bodies = [re.sub(r'\bfunc_0x000(180f[0-9a-f]{5})\b', lambda m: 'FUN_' + m.group(1)
                     if int(m.group(1), 16) in defined else m.group(0), b) for b in bodies]
    out += bodies
    # --- export wrapper (harness は i64×4 + 戻り値 kind で呼ぶ)
    sigs = {}
    for va in cfg['exports']:
        sg = [p for p in protos if ' FUN_%x(' % va in p or p.split('(')[0].endswith('FUN_%x' % va)][0]
        params = [p.strip() for p in re.search(r'\((.*)\)', sg).group(1).split(',')]
        ret = sg.split('FUN_')[0].strip()
        args = []
        for k, p in enumerate(params):
            ty = re.sub(r'\s*\b\w+$', '', p).strip()
            args.append('(%s)a%d' % (ty, k))
        call = 'FUN_%x(%s)' % (va, ','.join(args))
        out.append('EMSCRIPTEN_KEEPALIVE longlong function_%x(longlong a0, longlong a1, longlong a2, longlong a3) { %s; }' % (
            va, ('return (longlong)%s' % call) if ret != 'void' else '%s; return 0' % call))
        sigs['%x' % va] = {'params': ['i64'] * 4, 'ret': 'i64'}
    open(os.path.join(outdir, name + '.c'), 'w').write('\n'.join(out) + '\n')
    json.dump(sigs, open(os.path.join(outdir, 'sigs.json'), 'w'))
    json.dump({'%x' % k: {'type': v[0], 'kind': v[1], 'candidates': v[2]} for k, v in gtypes.items()}, open(os.path.join(outdir, 'globals.json'), 'w'), indent=1)
    print(json.dumps({'name': name, 'functions': [hex(v) for v in vas], 'globals': {('%x' % k): v[0] for k, v in gtypes.items()}, 'fix': sorted(f for f in fixes if f)}))


if __name__ == '__main__':
    main()
