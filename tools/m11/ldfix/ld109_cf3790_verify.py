#!/usr/bin/env python3
"""ld109_cf3790_verify.py — #2388 (LD-109) cf3790 の残り 15 site の判定根拠を機械語・IR の実物で検証して生成する。

判定は人が突合表 (results/ld105_reg2mem_map.tsv) と IR を読んで付けたもの。本スクリプトは、その根拠に書いた
  (1) 機械語の命令列 (アドレス + 命令文字列) が image の逆アセンブルと一致すること
  (2) IR の行 (SSA 名 + 命令文) が function_cf3790 の中でちょうど 1 行に一致し、その絶対行番号
の 2 つを機械的に確かめ、candidate_verdicts_1161.jsonl と同じ形式の行を出力する。どちらかが外れたら失敗する。
入力: tools/m11/work/boot_final3.ll / m11_image.bin (M11_WORK で差し替え可)
使い方: python3 ld109_cf3790_verify.py            生成した 15 行を標準出力へ
        python3 ld109_cf3790_verify.py --check    results/candidate_verdicts_1161.jsonl の 15 行と一致するか検査 (不一致で rc=1)
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '../../..'))
sys.path.insert(0, HERE)
from ldmach_img import ImageMachine  # noqa: E402

W = os.environ.get('M11_WORK', os.path.join(REPO, 'tools/m11/work'))
FN, FN_END = 0xcf3790, 0xcf3790 + 0x1000
CAND = os.path.join(HERE, 'results/candidate_verdicts_1161.jsonl')

mach = ImageMachine(os.path.join(W, 'm11_image.bin'), os.path.join(W, 'boot*.drc.config.json'))
ins = {x.address: x for x in mach.cs.disasm(mach.read(FN - mach.base, FN_END - FN), FN, FN_END - FN)}

ir_path = os.path.join(W, 'boot_final3.ll')
ll = open(ir_path).read().splitlines()
start = next(i for i, l in enumerate(ll) if l.startswith('define weak i64 @function_cf3790('))
end = next(i for i in range(start, len(ll)) if ll[i] == '}')
body = [l.strip() for l in ll[start:end]]
FN_LINE = start + 1  # define 行 (1 始まり)


def rip_target(addr):
    x = ins[addr]
    m = re.search(r'\[rip \+ (0x[0-9a-f]+)\]', x.op_str)
    return '0x%X' % (x.address + x.size + int(m.group(1), 16))


def check_mach(chain):
    for a, text in chain:
        x = ins.get(int(a, 16))
        got = '%s %s' % (x.mnemonic, x.op_str) if x else '(no insn)'
        if got != text:
            raise SystemExit('機械語不一致 %s: 期待 %r / 実際 %r' % (a, text, got))


def find_ir(regex):
    hits = [i for i, l in enumerate(body) if re.search(regex, l)]
    if len(hits) != 1:
        raise SystemExit('IR アンカー %r が %d 行に一致 (期待 1)' % (regex, len(hits)))
    return FN_LINE + hits[0]


# --- フレーム対応 (retdec の stack_var_N = disp - 0x1d8) の独立確認 ---
check_mach([('cf379e', 'mov qword ptr [rbp + 0x48], 0'), ('cf37ce', 'mov qword ptr [rbp + 0x188], 0'),
            ('cf3790', 'push rbp'), ('cf3793', 'push rbx'), ('cf3794', 'sub rsp, 0x1b8'), ('cf379b', 'mov rbp, rsp')])
find_ir(r'^store i64 0, ptr %stack_var_-400, align 8$')
find_ir(r'^store ptr null, ptr %stack_var_-80, align 8$')
assert 0x48 - 0x1d8 == -400 and 0x188 - 0x1d8 == -80

# --- IR アンカー (名前 -> 正規表現)。function_cf3790 内でちょうど 1 行に一致すること ---
A = {
    'a36': r'^%36 = load i64, ptr inttoptr \(i64 18745080 to ptr\), align 8$',
    'a51': r'^%51 = add i64 %36, -16$',
    'a52': r'^%52 = add i64 %51, %50$',
    'a59': r'^%59 = inttoptr i64 %52 to ptr$',
    'a89': r'^%89 = load i64, ptr %59, align 8$',
    'a90': r'^%90 = icmp eq i64 %89, 0$',
    'a89s': r'^store i64 %89, ptr %\.reg2mem$',
    'a93': r'^%93 = add i64 %89, -8$',
    'a95s': r'^store i64 %95, ptr %stack_var_-200\.0\.reg2mem$',
    'a96': r'^%96 = add i64 %stack_var_-200\.0\.reload, 1$',
    'a97': r'^%97 = call i64 @function_417fc0\(ptr %59, .*, i64 %96\)$',
    'pre11': r'^%\.pre11 = load i64, ptr %59, align 8$',
    'a98': r'^%98 = icmp eq i64 %\.pre11, 0$',
    'pre11s': r'^store i64 %\.pre11, ptr %\.reg2mem$',
    'a99': r'^%99 = add i64 %\.reload, -8$',
    'a101': r'^%101 = load i64, ptr %100, align 8$',
    'a101s': r'^store i64 %101, ptr %stack_var_-216\.0\.reg2mem$',
    'a102': r'^%102 = mul i64 %stack_var_-216\.0\.reload, 8$',
    'a103': r'^%103 = add i64 %\.reload19, -8$',
    'a105': r'^%105 = inttoptr i64 %104 to ptr$',
    'a106': r'^%106 = load i64, ptr %105, align 8$',
    'a107': r'^%107 = icmp eq i64 %106, 0$',
    'a108': r'^%108 = add i64 %106, -8$',
    'a110s': r'^store i64 %110, ptr %stack_var_-232\.0\.reg2mem$',
    'a111': r'^%111 = add i64 %stack_var_-232\.0\.reload, 1$',
    'a112': r'^%112 = call i64 @function_417fc0\(ptr %105, .*, i64 %111\)$',
    'a113': r'^%113 = load i64, ptr %105, align 8$',
    'a114': r'^%114 = icmp eq i64 %113, 0$',
    'a115': r'^%115 = add i64 %113, -8$',
    'a117s': r'^store i64 %117, ptr %stack_var_-248\.0\.reg2mem$',
    'a118': r'^%118 = mul i64 %stack_var_-248\.0\.reload, 4$',
    'a119': r'^%119 = add i64 %113, -4$',
    'a121s': r'^store i32 %67, ptr %121, align 4$',
    'b145': r'^%145 = load i64, ptr inttoptr \(i64 18745080 to ptr\), align 8$',
    'b145s': r'^store i64 %145, ptr %\.reg2mem22$',
    'b159': r'^%159 = add i64 %158, %\.reload23$',
    'b167': r'^%167 = inttoptr i64 %159 to ptr$',
    'b166': r'^%166 = call i64 @function_414da0\(i64 %151, i64 5,',
    'b168': r'^%168 = load i64, ptr %167, align 8$',
    'b169': r'^%169 = icmp eq i64 %168, 0$',
    'b170': r'^%170 = add i64 %168, -8$',
    'b172s': r'^store i64 %172, ptr %stack_var_-280\.0\.reg2mem$',
    'b173': r'^%173 = call i64 @function_43a820\(ptr %152, i64 %stack_var_-280\.0\.reload, i64 0\)$',
    'b178': r'^%178 = call i64 @function_412d60\(',
    'b179': r'^%179 = load i64, ptr %167, align 8$',
    'b180': r'^%180 = icmp eq i64 %179, 0$',
    'b181': r'^%181 = add i64 %179, -8$',
    'b183': r'^%183 = load i64, ptr %182, align 8$',
    'b184': r'^%184 = add i64 %183, -1$',
    'b185': r'^%185 = icmp slt i64 %184, 0$',
    'b183s': r'^store i64 %183, ptr %rsi\.0\.in\.reg2mem$',
    'c193': r'^%193 = load i64, ptr %167, align 8$',
    'c196': r'^%196 = add i64 %193, %195$',
    'c197': r'^%197 = inttoptr i64 %196 to ptr$',
    'c198': r'^%198 = load i64, ptr %197, align 8$',
    'c199': r'^%199 = icmp eq i64 %198, 0$',
    'c200': r'^%200 = add i64 %198, -8$',
    'c202': r'^%202 = load i64, ptr %201, align 8$',
    'c203': r'^%203 = add i64 %202, -1$',
    'c198s': r'^store i64 %198, ptr %\.reg2mem24$',
    'c202s': r'^store i64 %202, ptr %rdi\.0\.in\.reg2mem$',
    'c208': r'^%208 = add i64 %207, %\.reload25$',
    'c210': r'^%210 = load i32, ptr %209, align 4$',
    'c214': r'^%214 = call i64 @function_414bb0\(i64 %__m11c_3745, i64 %213\)$',
    'c215': r'^%215 = load i64, ptr %197, align 8$',
    'c216': r'^%216 = icmp eq i64 %215, 0$',
    'c217': r'^%217 = add i64 %215, -8$',
    'c219s': r'^store i64 %219, ptr %stack_var_-328\.0\.reg2mem$',
    'c220': r'^%220 = add i64 %stack_var_-328\.0\.reload, -1$',
    'c221': r'^%221 = icmp sgt i64 %220, %206$',
}
L = {k: find_ir(v) for k, v in A.items()}

# 上流の脱落 (既判定) 機械語。配列要素アドレス [rbp+0x178] / [rbp+0x160] の基底が slot 1 段 deref であること
UP_E = [('cf3932', 'mov rax, qword ptr [rip + 0x8ecdbf]'), ('cf3939', 'mov rax, qword ptr [rax]'),
        ('cf394e', 'mov qword ptr [rbp + 0x178], rax')]
UP_E3 = [('cf3d73', 'mov rax, qword ptr [rip + 0x8ec97e]'), ('cf3d7a', 'mov rax, qword ptr [rax]'),
         ('cf3d8b', 'mov qword ptr [rbp + 0x160], rax')]
assert rip_target(0xcf3932) == '0x15E06F8' and rip_target(0xcf3d73) == '0x15E06F8'

T_E = ('基底 %59 は %52=%51+%50 (行 {a52})・%51=%36-16 (行 {a51}) で、%36 (行 {a36}) は機械語 cf3932〜cf394e の slot 0x15E06F8 の 1 段 deref '
       '(cf3939 mov rax,[rax]) が脱落した cf390f の脱落値のため、アドレスは別途汚染 (cf3af5 と同じ注記。当 site の deref 自体は存在)')
T_E3 = ('基底 %167 は %159 (行 {b159}) ← .reload23 ← %145 (行 {b145}・store 行 {b145s}) で、%145 は機械語 cf3d73〜cf3d8b の slot 0x15E06F8 の 1 段 deref '
        '(cf3d7a mov rax,[rax]) が脱落した cf3d20 の脱落値のため、アドレスは別途汚染 (当 site の deref 自体は存在)')

SITES = []


def site(s, mach_chain, ev):
    SITES.append((s, mach_chain, ev))


site('cf3b03', UP_E + [('cf3af2', 'mov rax, qword ptr [rax]'), ('cf3af5', 'mov qword ptr [rbp + 0x118], rax'),
                       ('cf3afc', 'mov rax, qword ptr [rbp + 0x118]'), ('cf3b03', 'mov qword ptr [rbp + 0x110], rax'),
                       ('cf3b0a', 'cmp qword ptr [rbp + 0x110], 0'), ('cf3b1b', 'mov rax, qword ptr [rax - 8]'),
                       ('cf3b3a', 'mov rax, qword ptr [rbp + 0x110]'), ('cf3b41', 'lea r9, [rax + 1]'), ('cf3b45', 'call 0x417fc0')],
     '機械語 cf3af2 mov rax,[rax]→cf3af5 mov [rbp+0x118],rax (既判定 OK_LOAD)、cf3afc mov rax,[rbp+0x118]→cf3b03 mov [rbp+0x110],rax は同値の複製、'
     '読み戻し cf3b0a cmp [rbp+0x110],0 / cf3b1b mov rax,[rax-8] / cf3b3a〜cf3b41 lea r9,[rax+1]→cf3b45 call 417fc0。[rbp+0x110]=stack_var_-200 (disp-0x1d8)。'
     'IR は cf3af5 と同じ値 `%89 = load i64, ptr %59` (行 {a89}) を保持し、`%90 = icmp eq %89, 0` (行 {a90}) / `%93 = add %89, -8` (行 {a93}) / '
     '`store %89, ptr %.reg2mem` (行 {a89s}) / len 側 `store %95, stack_var_-200.0.reg2mem` (行 {a95s}) → `%96 = add stack_var_-200.0.reload, 1` (行 {a96}) → '
     '`%97 = call @function_417fc0(%59, .., %96)` (行 {a97}) で使用。deref・消費者とも IR に存在。' + T_E)

site('cf3b54', [('cf3b45', 'call 0x417fc0'), ('cf3b4a', 'mov rax, qword ptr [rbp + 0x178]'), ('cf3b51', 'mov rax, qword ptr [rax]'),
                ('cf3b54', 'mov qword ptr [rbp + 0x108], rax'), ('cf3b5b', 'mov rax, qword ptr [rbp + 0x108]'),
                ('cf3b62', 'mov qword ptr [rbp + 0x100], rax')],
     '機械語 cf3b45 call 417fc0 (SetLength) の後の cf3b4a mov rax,[rbp+0x178] (要素アドレス)→cf3b51 mov rax,[rax]→cf3b54 mov [rbp+0x108],rax、'
     '読み戻し cf3b5b→cf3b62 mov [rbp+0x100],rax。[rbp+0x108]=stack_var_-208 は mem2reg で SSA 値になり alloca が無い (ld105_reg2mem_map の alloca: no は slot 名の式の誤りと、この昇格の両方による)。'
     'IR は call (行 {a97}) の後に `%.pre11 = load i64, ptr %59` (行 {pre11}) で再 load し、`%98 = icmp eq %.pre11, 0` (行 {a98}) / '
     '`store %.pre11, ptr %.reg2mem` (行 {pre11s}) で使用 (SetLength を跨ぐ再 load が保たれている)。SetLength を通らない経路 (cf3adb→cf3b73) では call が無く、'
     '同値の `%89` (行 {a89}) を `store %89, ptr %.reg2mem` (行 {a89s}) 経由で使う。' + T_E)

site('cf3b62', [('cf3b5b', 'mov rax, qword ptr [rbp + 0x108]'), ('cf3b62', 'mov qword ptr [rbp + 0x100], rax'),
                ('cf3b69', 'cmp qword ptr [rbp + 0x100], 0'), ('cf3b7a', 'mov rax, qword ptr [rax - 8]'),
                ('cf3b7e', 'mov qword ptr [rbp + 0x100], rax'), ('cf3b8f', 'mov rcx, qword ptr [rbp + 0x100]'),
                ('cf3b96', 'lea rcx, [rcx - 1]'), ('cf3b9a', 'lea rax, [rax + rcx*8]'), ('cf3b9e', 'mov qword ptr [rbp + 0x168], rax')],
     '機械語 cf3b5b mov rax,[rbp+0x108] (cf3b54 の値)→cf3b62 mov [rbp+0x100],rax は同値の複製、読み戻し cf3b69 cmp [rbp+0x100],0 / cf3b7a mov rax,[rax-8]→cf3b7e 上書き / '
     'cf3b8f〜cf3b9a lea rcx,[rcx-1]; lea rax,[rax+rcx*8]→cf3b9e mov [rbp+0x168],rax。[rbp+0x100]=stack_var_-216。'
     'IR は cf3b54 の値 `%.pre11` (行 {pre11}) を `%98 = icmp eq` (行 {a98}) / `%99 = add %.reload, -8` (行 {a99}) → `%101 = load` (行 {a101}) → '
     '`store %101, stack_var_-216.0.reg2mem` (行 {a101s}) → `%102 = mul stack_var_-216.0.reload, 8` (行 {a102}) / `%103 = add %.reload19, -8` (行 {a103}) → '
     '`%105 = inttoptr` (行 {a105}) で要素アドレスを作る形で使用。deref・消費者とも IR に存在。' + T_E)

site('cf3baf', [('cf3b9e', 'mov qword ptr [rbp + 0x168], rax'), ('cf3ba5', 'mov rax, qword ptr [rbp + 0x168]'),
                ('cf3bac', 'mov rax, qword ptr [rax]'), ('cf3baf', 'mov qword ptr [rbp + 0xf8], rax'),
                ('cf3bb6', 'mov rax, qword ptr [rbp + 0xf8]'), ('cf3bbd', 'mov qword ptr [rbp + 0xf0], rax')],
     '機械語 cf3b9e mov [rbp+0x168],rax (要素アドレス E2)→cf3ba5 mov rax,[rbp+0x168]→cf3bac mov rax,[rax]→cf3baf mov [rbp+0xf8],rax、読み戻し cf3bb6→cf3bbd mov [rbp+0xf0],rax。'
     '[rbp+0xf8]=stack_var_-224 は SSA 値 (alloca 無し)。IR は `%106 = load i64, ptr %105` (行 {a106}) で E2=%105 (行 {a105}) を deref し、'
     '`%107 = icmp eq %106, 0` (行 {a107}) / `%108 = add %106, -8` (行 {a108}) で使用。deref・消費者とも IR に存在。' + T_E)

site('cf3bbd', [('cf3bb6', 'mov rax, qword ptr [rbp + 0xf8]'), ('cf3bbd', 'mov qword ptr [rbp + 0xf0], rax'),
                ('cf3bc4', 'cmp qword ptr [rbp + 0xf0], 0'), ('cf3bd5', 'mov rax, qword ptr [rax - 8]'),
                ('cf3bd9', 'mov qword ptr [rbp + 0xf0], rax'), ('cf3bf4', 'mov rax, qword ptr [rbp + 0xf0]'),
                ('cf3bfb', 'lea r9, [rax + 1]'), ('cf3bff', 'call 0x417fc0')],
     '機械語 cf3bb6 mov rax,[rbp+0xf8] (cf3baf の値)→cf3bbd mov [rbp+0xf0],rax は同値の複製、読み戻し cf3bc4 cmp [rbp+0xf0],0 / cf3bd5 mov rax,[rax-8]→cf3bd9 上書き / '
     'cf3bf4〜cf3bfb lea r9,[rax+1]→cf3bff call 417fc0。[rbp+0xf0]=stack_var_-232。'
     'IR は cf3baf の値 %106 (行 {a106}) を `%107 = icmp eq` (行 {a107}) / `%108 = add -8` (行 {a108}) → `store %110, stack_var_-232.0.reg2mem` (行 {a110s}) → '
     '`%111 = add stack_var_-232.0.reload, 1` (行 {a111}) → `%112 = call @function_417fc0(%105, .., %111)` (行 {a112}) で使用。deref・消費者とも IR に存在。' + T_E)

site('cf3c0e', [('cf3bff', 'call 0x417fc0'), ('cf3c04', 'mov rax, qword ptr [rbp + 0x168]'), ('cf3c0b', 'mov rax, qword ptr [rax]'),
                ('cf3c0e', 'mov qword ptr [rbp + 0xe8], rax'), ('cf3c15', 'mov rax, qword ptr [rbp + 0xe8]'),
                ('cf3c1c', 'mov qword ptr [rbp + 0xe0], rax')],
     '機械語 cf3bff call 417fc0 (SetLength) の後の cf3c04 mov rax,[rbp+0x168]→cf3c0b mov rax,[rax]→cf3c0e mov [rbp+0xe8],rax、読み戻し cf3c15→cf3c1c mov [rbp+0xe0],rax。'
     '[rbp+0xe8]=stack_var_-240 は SSA 値 (alloca 無し)。IR は call (行 {a112}) の後に `%113 = load i64, ptr %105` (行 {a113}) で再 load し、'
     '`%114 = icmp eq %113, 0` (行 {a114}) / `%115 = add %113, -8` (行 {a115}) / `%119 = add %113, -4` (行 {a119}) で使用。deref・消費者とも IR に存在。' + T_E)

site('cf3c1c', [('cf3c15', 'mov rax, qword ptr [rbp + 0xe8]'), ('cf3c1c', 'mov qword ptr [rbp + 0xe0], rax'),
                ('cf3c23', 'cmp qword ptr [rbp + 0xe0], 0'), ('cf3c34', 'mov rax, qword ptr [rax - 8]'),
                ('cf3c38', 'mov qword ptr [rbp + 0xe0], rax'), ('cf3c3f', 'mov rax, qword ptr [rbp + 0x168]'),
                ('cf3c46', 'mov rax, qword ptr [rax]'), ('cf3c49', 'mov rcx, qword ptr [rbp + 0xe0]'),
                ('cf3c50', 'lea rcx, [rcx - 1]'), ('cf3c5a', 'mov dword ptr [rax + rcx*4], edx')],
     '機械語 cf3c15 mov rax,[rbp+0xe8] (cf3c0e の値)→cf3c1c mov [rbp+0xe0],rax は同値の複製、読み戻し cf3c23 cmp [rbp+0xe0],0 / cf3c34 mov rax,[rax-8]→cf3c38 上書き / '
     'cf3c49〜cf3c50 lea rcx,[rcx-1]→cf3c5a mov [rax+rcx*4],edx。[rbp+0xe0]=stack_var_-248。'
     'IR は cf3c0e の値 %113 (行 {a113}) を `%114 = icmp eq` (行 {a114}) / `%115 = add -8` (行 {a115}) → `store %117, stack_var_-248.0.reg2mem` (行 {a117s}) → '
     '`%118 = mul stack_var_-248.0.reload, 4` (行 {a118}) + `%119 = add %113, -4` (行 {a119}) → `store i32 %67, ptr %121` (行 {a121s}) で使用。deref・消費者とも IR に存在。' + T_E)

site('cf3dfa', UP_E3 + [('cf3deb', 'call 0x414da0'), ('cf3df0', 'mov rax, qword ptr [rbp + 0x160]'),
                        ('cf3df7', 'mov rax, qword ptr [rax]'), ('cf3dfa', 'mov qword ptr [rbp + 0xc8], rax'),
                        ('cf3e01', 'mov rax, qword ptr [rbp + 0xc8]'), ('cf3e08', 'mov qword ptr [rbp + 0xc0], rax')],
     '機械語 cf3d8b mov [rbp+0x160],rax (要素アドレス E3)・cf3deb call 414da0 の後の cf3df0 mov rax,[rbp+0x160]→cf3df7 mov rax,[rax]→cf3dfa mov [rbp+0xc8],rax、読み戻し cf3e01→cf3e08 mov [rbp+0xc0],rax。'
     '[rbp+0xc8]=stack_var_-272 は SSA 値 (alloca 無し)。IR は call (行 {b166}) の後に `%168 = load i64, ptr %167` (行 {b168}) で E3=%167 (行 {b167}) を deref し、'
     '`%169 = icmp eq %168, 0` (行 {b169}) / `%170 = add %168, -8` (行 {b170}) で使用。deref・消費者とも IR に存在。' + T_E3)

site('cf3e08', [('cf3e01', 'mov rax, qword ptr [rbp + 0xc8]'), ('cf3e08', 'mov qword ptr [rbp + 0xc0], rax'),
                ('cf3e0f', 'cmp qword ptr [rbp + 0xc0], 0'), ('cf3e20', 'mov rax, qword ptr [rax - 8]'),
                ('cf3e24', 'mov qword ptr [rbp + 0xc0], rax'), ('cf3e2f', 'mov rdx, qword ptr [rbp + 0xc0]'),
                ('cf3e36', 'call 0x43a820')],
     '機械語 cf3e01 mov rax,[rbp+0xc8] (cf3dfa の値)→cf3e08 mov [rbp+0xc0],rax は同値の複製、読み戻し cf3e0f cmp [rbp+0xc0],0 / cf3e20 mov rax,[rax-8]→cf3e24 上書き / '
     'cf3e2f mov rdx,[rbp+0xc0]→cf3e36 call 43a820 (Length を文字列化)。[rbp+0xc0]=stack_var_-280。'
     'IR は cf3dfa の値 %168 (行 {b168}) を `%169 = icmp eq` (行 {b169}) / `%170 = add -8` (行 {b170}) → `store %172, stack_var_-280.0.reg2mem` (行 {b172s}) → '
     '`%173 = call @function_43a820(%152, stack_var_-280.0.reload, 0)` (行 {b173}) で使用。deref・消費者とも IR に存在。' + T_E3)

site('cf3e7a', [('cf3e6b', 'call 0x412d60'), ('cf3e70', 'mov rax, qword ptr [rbp + 0x160]'), ('cf3e77', 'mov rax, qword ptr [rax]'),
                ('cf3e7a', 'mov qword ptr [rbp + 0xb8], rax'), ('cf3e81', 'mov rax, qword ptr [rbp + 0xb8]'),
                ('cf3e88', 'mov qword ptr [rbp + 0xb0], rax')],
     '機械語 cf3e6b call 412d60 の後の cf3e70 mov rax,[rbp+0x160]→cf3e77 mov rax,[rax]→cf3e7a mov [rbp+0xb8],rax、読み戻し cf3e81→cf3e88 mov [rbp+0xb0],rax。'
     '[rbp+0xb8]=stack_var_-288 は SSA 値 (alloca 無し)。IR は call (行 {b178}) の後に `%179 = load i64, ptr %167` (行 {b179}) で再 load し、'
     '`%180 = icmp eq %179, 0` (行 {b180}) / `%181 = add %179, -8` (行 {b181}) で使用。deref・消費者とも IR に存在。' + T_E3)

site('cf3e88', [('cf3e81', 'mov rax, qword ptr [rbp + 0xb8]'), ('cf3e88', 'mov qword ptr [rbp + 0xb0], rax'),
                ('cf3e8f', 'cmp qword ptr [rbp + 0xb0], 0'), ('cf3ea0', 'mov rax, qword ptr [rax - 8]'),
                ('cf3ea4', 'mov qword ptr [rbp + 0xb0], rax'), ('cf3ead', 'mov rcx, qword ptr [rbp + 0xb0]'),
                ('cf3eb4', 'lea rsi, [rcx - 1]')],
     '機械語 cf3e81 mov rax,[rbp+0xb8] (cf3e7a の値)→cf3e88 mov [rbp+0xb0],rax は同値の複製、読み戻し cf3e8f cmp [rbp+0xb0],0 / cf3ea0 mov rax,[rax-8]→cf3ea4 上書き / '
     'cf3ead mov rcx,[rbp+0xb0]→cf3eb4 lea rsi,[rcx-1] (内側ループ上限)。[rbp+0xb0]=stack_var_-296 は SSA 値 (alloca 無し)。'
     'IR は cf3e7a の値 %179 (行 {b179}) を `%180 = icmp eq` (行 {b180}) / `%181 = add -8` → `%183 = load` (行 {b183}) → `%184 = add %183, -1` (行 {b184}) → '
     '`%185 = icmp slt %184, 0` (行 {b185}) と `store %183, rsi.0.in.reg2mem` (行 {b183s}) で使用。deref・消費者とも IR に存在。' + T_E3)

site('cf3f47', [('cf3f21', 'mov rax, qword ptr [rbp + 0x160]'), ('cf3f28', 'mov rax, qword ptr [rax]'),
                ('cf3f32', 'lea rax, [rax + rcx*8]'), ('cf3f36', 'mov qword ptr [rbp + 0x150], rax'),
                ('cf3f3d', 'mov rax, qword ptr [rbp + 0x150]'), ('cf3f44', 'mov rax, qword ptr [rax]'),
                ('cf3f47', 'mov qword ptr [rbp + 0xa8], rax'), ('cf3f4e', 'mov rax, qword ptr [rbp + 0xa8]'),
                ('cf3f55', 'mov qword ptr [rbp + 0xa0], rax')],
     '機械語 cf3f21 mov rax,[rbp+0x160]→cf3f28 mov rax,[rax]→cf3f32 lea rax,[rax+rcx*8]→cf3f36 mov [rbp+0x150],rax (要素アドレス E4)、'
     'cf3f3d mov rax,[rbp+0x150]→cf3f44 mov rax,[rax]→cf3f47 mov [rbp+0xa8],rax、読み戻し cf3f4e→cf3f55 mov [rbp+0xa0],rax。[rbp+0xa8]=stack_var_-304 は SSA 値 (alloca 無し)。'
     'IR は E4 の基底 `%193 = load i64, ptr %167` (行 {c193}・cf3f28 の deref) → `%196 = add %193, %195` (行 {c196}) → `%197 = inttoptr` (行 {c197}) を作り、'
     '`%198 = load i64, ptr %197` (行 {c198}) で deref し、`%199 = icmp eq %198, 0` (行 {c199}) / `%200 = add %198, -8` (行 {c200}) / `store %198, ptr %.reg2mem24` (行 {c198s}) で使用。'
     'deref・消費者とも IR に存在。' + T_E3)

site('cf3f55', [('cf3f4e', 'mov rax, qword ptr [rbp + 0xa8]'), ('cf3f55', 'mov qword ptr [rbp + 0xa0], rax'),
                ('cf3f5c', 'cmp qword ptr [rbp + 0xa0], 0'), ('cf3f6d', 'mov rax, qword ptr [rax - 8]'),
                ('cf3f71', 'mov qword ptr [rbp + 0xa0], rax'), ('cf3f7a', 'mov rcx, qword ptr [rbp + 0xa0]'),
                ('cf3f81', 'lea rdi, [rcx - 1]')],
     '機械語 cf3f4e mov rax,[rbp+0xa8] (cf3f47 の値)→cf3f55 mov [rbp+0xa0],rax は同値の複製、読み戻し cf3f5c cmp [rbp+0xa0],0 / cf3f6d mov rax,[rax-8]→cf3f71 上書き / '
     'cf3f7a mov rcx,[rbp+0xa0]→cf3f81 lea rdi,[rcx-1] (最内ループ上限)。[rbp+0xa0]=stack_var_-312 は SSA 値 (alloca 無し)。'
     'IR は cf3f47 の値 %198 (行 {c198}) を `%199 = icmp eq` (行 {c199}) / `%200 = add -8` → `%202 = load` (行 {c202}) → `%203 = add %202, -1` (行 {c203}) と '
     '`store %202, rdi.0.in.reg2mem` (行 {c202s}) で使用。deref・消費者とも IR に存在。' + T_E3)

site('cf3fd3', [('cf3fc4', 'call 0x414bb0'), ('cf3fc9', 'mov rax, qword ptr [rbp + 0x150]'), ('cf3fd0', 'mov rax, qword ptr [rax]'),
                ('cf3fd3', 'mov qword ptr [rbp + 0x98], rax'), ('cf3fda', 'mov rax, qword ptr [rbp + 0x98]'),
                ('cf3fe1', 'mov qword ptr [rbp + 0x90], rax')],
     '機械語 (解析範囲 0x1000 の内側) cf3fc4 call 414bb0 の後の cf3fc9 mov rax,[rbp+0x150]→cf3fd0 mov rax,[rax]→cf3fd3 mov [rbp+0x98],rax、読み戻し cf3fda→cf3fe1 mov [rbp+0x90],rax。'
     '[rbp+0x98]=stack_var_-320 は SSA 値 (alloca 無し)。IR は call (行 {c214}) の後に `%215 = load i64, ptr %197` (行 {c215}) で E4=%197 (行 {c197}) を再 load し、'
     '`%216 = icmp eq %215, 0` (行 {c216}) / `%217 = add %215, -8` (行 {c217}) で使用。deref・消費者とも IR に存在。' + T_E3)

site('cf3fe1', [('cf3fda', 'mov rax, qword ptr [rbp + 0x98]'), ('cf3fe1', 'mov qword ptr [rbp + 0x90], rax'),
                ('cf3fe8', 'cmp qword ptr [rbp + 0x90], 0'), ('cf3ff9', 'mov rax, qword ptr [rax - 8]'),
                ('cf3ffd', 'mov qword ptr [rbp + 0x90], rax'), ('cf4004', 'mov rax, qword ptr [rbp + 0x90]'),
                ('cf400b', 'lea rax, [rax - 1]'), ('cf400f', 'cmp rbx, rax')],
     '機械語 cf3fda mov rax,[rbp+0x98] (cf3fd3 の値)→cf3fe1 mov [rbp+0x90],rax は同値の複製、読み戻し cf3fe8 cmp [rbp+0x90],0 / cf3ff9 mov rax,[rax-8]→cf3ffd 上書き / '
     'cf4004 mov rax,[rbp+0x90]→cf400b lea rax,[rax-1]→cf400f cmp rbx,rax。[rbp+0x90]=stack_var_-328。'
     'IR は cf3fd3 の値 %215 (行 {c215}) を `%216 = icmp eq` (行 {c216}) / `%217 = add -8` → `store %219, stack_var_-328.0.reg2mem` (行 {c219s}) → '
     '`%220 = add stack_var_-328.0.reload, -1` (行 {c220}) → `%221 = icmp sgt %220, %206` (行 {c221}) で使用。deref・消費者とも IR に存在。' + T_E3)

rows = []
for s, chain, ev in SITES:
    check_mach(chain + [(s, 'mov qword ptr [rbp + %s], rax' % re.search(r'\[rbp \+ (0x[0-9a-f]+)\]', ins[int(s, 16)].op_str).group(1))])
    rows.append({'fn': 'cf3790', 'site': s, 'verdict': 'OK_LOAD', 'evidence': ev.format(**L)})

# 順序の独立確認: SetLength / 呼び出しの後に再 load が来る (機械語の順序と同じ)
assert L['a97'] < L['pre11'] < L['a98'] and L['a112'] < L['a113'] and L['b166'] < L['b168']
assert L['b178'] < L['b179'] and L['c214'] < L['c215']

sha = hashlib.sha256(open(ir_path, 'rb').read()).hexdigest()
print('[ld109] IR sha256=%s function_cf3790 define 行=%d / 機械語 %d site の命令列と IR アンカー %d 行を検証 OK' % (
    sha, FN_LINE, len(rows), len(L)), file=sys.stderr)

if '--check' in sys.argv:
    have = {}
    for ln in open(CAND):
        r = json.loads(ln)
        if r['fn'] == 'cf3790':
            have[r['site']] = r
    bad = [r['site'] for r in rows if have.get(r['site']) != r]
    if bad:
        print('[ld109] candidate_verdicts_1161.jsonl と不一致: %s' % ' '.join(bad), file=sys.stderr)
        sys.exit(1)
    print('[ld109] candidate_verdicts_1161.jsonl の %d 行と一致' % len(rows), file=sys.stderr)
else:
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
