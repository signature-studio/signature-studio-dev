#!/usr/bin/env python3
# M11 #4: IR パス鎖 (m5 ir5_patch / m6 ir6 書戻し実績の copy+拡張, tools/m11 配下のみ)
#   [M1] @global_var_X の全使用を inttoptr i64 <LVA>(VA-0x400000) に置換し,
#        定義 (constant/global) を廃棄する (memory-image 一極化: m5 C13/m6 ir6_gdata 後継)
#   [M2] 定数 inttoptr (i64 VA to ptr) → linear へ -0x400000 remap (m6 ir6_shift 後継)
#   [M2b] store/add/sub の i64 即値 VA remap
#   [M2c] sext/zext/trunc operand 型suffix補完 (LLVM typed operand; parser workaround)
#   [M2n] call site / callee signature 整合 (LLVM wasm FixFunctionBitcasts の invalid
#         thunk [body=unreachable] 発生防止を IR 前処理で潰す)
#   [M5] init 関数 prologue に m11 counter store を挿入 (boot 検証用)
#
# 使い方: python3 m11_passes.py IN.ll OUT.ll [--report OUT.json] [--init-list F] [--no-m2b]
import sys, re, json, argparse, os, itertools
from collections import Counter

from lb_base import LB as LB_BASE   # M11_LB_BASE (既定 0): LVA = VA - 0x400000 + LB_BASE

BASE_VA = 0x400000 - LB_BASE
IMG_LO = 0x400000
IMG_HI = 0x1abf400   # 全 image 末尾 (.rsrc 終端 VA)

def stage(tag, msg):
    print('[ir11][%s] %s' % (tag, msg), file=sys.stderr)


def shiftva(v):
    if not (IMG_LO <= v < IMG_HI):
        return None
    return v - BASE_VA


# ---------------------------------------------------------------
# [M2h] select constexpr の命令化 (LLVM 15 以降は const select 禁止).
# ---------------------------------------------------------------

def pass_m2h_select(text, report):
    """`store i32 select (i1 %c, i32 %a, i32 %b), ptr ...` を store 前の変数化に落とす."""
    lines = text.split('\n')
    out = []
    nfix = 0
    pat = re.compile(r'^(\s*store\s+\S+\s+)select\s*\((.*)\)(,\s*ptr.*|\s+.+)$')
    for l in lines:
        m = pat.match(l)
        if m:
            head, inner, tail = m.group(1), m.group(2), m.group(3)
            parts = []
            depth = 0
            cur = ''
            for ch in inner:
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                if depth == 0 and ch == ',':
                    parts.append(cur.strip())
                    cur = ''
                    continue
                cur += ch
            parts.append(cur.strip())
            if len(parts) == 3:
                nfix += 1
                selname = '_m11sel_%d' % nfix
                out.append('  %%%s = select %s' % (selname, ', '.join(parts)))
                out.append('%s%%%s%s' % (head, selname, tail))
                continue
        out.append(l)
    text = '\n'.join(out)
    if nfix:
        stage('M2h', 'const-select  lift: %d sites' % nfix)
    report['m2h_fix'] = nfix
    return text


def pass_m2i_fnname(text, report):
    """[M2i] function-local name inside constexpr (add (i64 %reg, i64 1) to ptr) 命令化."""
    lines = text.split('\n')
    out = []
    nfix = 0
    pat = re.compile(r'inttoptr \(i64 (add|sub|mul|and|or|xor|shl|ashr|lshr) \((.*)\) to ptr\)')
    for l in lines:
        m = pat.search(l)
        if m:
            op, inner = m.group(1), m.group(2)
            nfix += 1
            j = m.start()
            pre = l[:j]
            post = l[m.end():]
            # 使用側の置換行より *前* に定義命令を置く (LLVM SSA は use の前向き参照を許さない;
            # 後置きだと `invalid use of function-local name` で clang パースに失敗する)
            inner2 = inner
            if inner2.startswith('i64 '):
                inner2 = inner2[4:]
            # retdec 形: `i64 <imm>` の第 2 operand は LLVM では imm で記述
            inner2 = re.sub(r',\s*(?:i\d+|f\d+)\s+', ',', inner2)
            inner2 = re.sub(r'^\s*([-%][\w.$]+|\-?\d+)\b', r'\1', inner2)
            out.append('  %' + 'm11op_%d' % nfix + ' = ' + op + ' i64 ' + inner2)
            out.append('  %' + 'm11INTP_%d' % nfix + ' = inttoptr i64 %' + 'm11op_%d' % nfix + ' to ptr')
            out.append(pre + '%' + 'm11INTP_%d' % nfix + post)
            continue
        out.append(l)
    text = '\n'.join(out)
    if nfix:
        stage('M2i', 'constexpr function-name inttoptr lift: %d sites' % nfix)
    report['m2i_fix'] = nfix
    return text


def pass_m2j_imm(text, report):
    """[M2j] `add i1 0, i1 %reg` 指令 LLVM 記法修復: imm を第 2 operand *に* 変換:
    RetDec が第一 operand に imm がある field (LLVM では invalid) を,
    `op ty %reg, <imm>` に reorder する."""
    lines = text.split('\n')
    out = []
    nfix = 0
    pat = re.compile(r'^(\s*%([\w.$-]+)\s*=\s*)(add|sub|mul|and|or|xor|lshr|ashr|shl|sdiv|udiv|srem|urem)\s+([iw]\d+)\s+(-?[\w.$%]+)\s*,\s*(i\d+)\s+([-%]?[\w.$]+)\s*(;.*)?$')
    for l in lines:
        m = pat.match(l)
        if m:
            head, name, op, ty, op1, ty2, op2, tail = m.groups()
            nfix += 1
            regname = op2[1:] if op2.startswith('%') else op2
            regname = (('_' if regname[0].isdigit() else '') + regname)
            out.append('%s%s %s %s, %s%s' % (head, op, ty, '%' + regname, op1, (tail or '')))
            continue
        out.append(l)
    text = '\n'.join(out)
    if nfix:
        stage('M2j', 'add-imm normalize: %d sites' % nfix)
    report['m2j_fix'] = nfix
    return text


def pass_m2k_dedupdecls(text, report):
    """[M2k] declare 行の重複除去 + declared-function の define との衝突解消."""
    defines = set(re.findall(r'^define \S+ @([\w.$-]+)', text, re.M))
    declares = re.findall(r'^declare .+@([\w.$-]+)\(.+\)', text, re.M)
    cnt = Counter(declares)
    lines = text.split('\n')
    out = []
    drop = set()
    for i, l in enumerate(lines):
        m = re.match(r'^declare .+@([\w.$-]+)\(', l)
        if m and (m.group(1) in defines or cnt[m.group(1)] > 1):
            cnt[m.group(1)] -= 1
            if m.group(1) in defines or cnt[m.group(1)] > 0:
                drop.add(id(l))
                continue
        out.append(l)
    text = '\n'.join(out)
    if drop:
        stage('M2k', 'decl dedup: %d lines dropped' % len(drop))
    report['m2k_fix'] = len(drop)
    return text


def pass_m2l_numballs(text, report):
    """[M2l] @m11num_<N> defs は, 残っている *uses* があるなら *定義を維持* する."""
    uses = re.findall(r'@m11num_(\d+)\b(?!\s*=)', text)
    used = set(uses)          # 文字列 set ('%d' 呼出は int になり型比較を壊す — 文字列のまま比較)
    defs = re.findall(r'^@m11num_(\d+)\s*=', text, re.M)
    keep = set(defs) & used
    lines = text.split('\n')
    out = []
    ndrop = 0
    for l in lines:
        m = re.match(r'^@m11num_(\d+)\s*=', l)
        if m:
            if m.group(1) not in used:
                ndrop += 1
                continue
        out.append(l)
    text = '\n'.join(out)
    stage('M2l', 'num-global defs kept: %d (dropped: %d)' % (len(keep), ndrop))
    report['m2l_keep'] = len(keep)
    return text


def pass_m2g_irfix(text, report):
    """[M2g] specific broken-lift fixes (broken `ptrtoint ptr <X> to i64` 在 *call arg* ptr position)."""
    lines = text.split('\n')
    out = []
    nfix = 0
    pairs = {}
    for l in lines:
        m = re.match(r'^\s*%([\w.$-]+)x\s*=\s*ptrtoint ptr\s*%([\w.$-]+)\s*to i64\s*$', l)
        if m:
            pairs[m.group(1) + 'x'] = m.group(2)
    for l in lines:
        for xname, orig in pairs.items():
            for pat in (r'\bptr nonnull %' + re.escape(xname), r'\bptr %' + re.escape(xname)):
                if re.search(pat, l):
                    l = re.sub(pat, 'ptr nonnull %' + orig, l)
                    nfix += 1
        out.append(l)
    text = '\n'.join(out)
    if nfix:
        stage('M2g', 'specific ptrtoint→ptr fix: %d sites' % nfix)
    report['m2g_fix'] = nfix
    return text


def pass_m1(text, report):
    names = sorted(set(re.findall(r'@global_var_([0-9a-f]+)\b', text)))
    out_n = 0

    def rep(m):
        nonlocal out_n
        h = m.group(1)
        v = int(h, 16)
        if not (IMG_LO <= v < IMG_HI):
            return m.group(0)
        out_n += 1
        return 'inttoptr (i64 %d to ptr)' % (v - BASE_VA)

    text = re.sub(r'@global_var_([0-9a-f]+)\b(?!\s*=)', rep, text)
    stagen = re.compile(r'^(@global_var_[0-9a-f]+)(\s*=\s)', re.M)
    def rep2(m):
        return '@m11_g_def_%s%s' % (m.group(1)[len('@global_var_'):], m.group(2))
    text = stagen.sub(rep2, text)
    lines = text.split('\n')
    out = []
    dropped = 0
    for l in lines:
        p = re.match(r'^@m11_g_def_[0-9a-f]+ = ', l)
        if p:
            dropped += 1
            continue
        if re.search(r'@m11_g_def_[0-9a-f]+', l):
            l = re.sub(r'@m11_g_def_([0-9a-f]+)', r'@global_var_\1', l)
        out.append(l)
    text = '\n'.join(out)
    # numeric globals (RetDec @0..@99) の定義も memory-image 一極化で廃棄
    text2 = []
    for l in text.split('\n'):
        if re.match(r'^@(m11num_[0-9]+|[0-9]+) = ', l) and False:
            dropped += 1
            continue
        text2.append(l)
    text = '\n'.join(text2)
    stage('M1', 'global_var uses→inttoptr %d, drop defs %d (incl. numeric-globals)' % (out_n, dropped))
    report['m1_uses'] = out_n
    report['m1_dropped'] = dropped
    return text


def pass_m2(text, report):
    n = [0]

    def rep(m):
        pre, val, post = m.group(1), m.group(2), m.group(3)
        v = int(val, 16)
        nv = shiftva(v)
        if nv is None:
            return m.group(0)
        n[0] += 1
        return pre + hex(nv) + post

    text = re.sub(r'(inttoptr i64 )(0x[0-9a-f]+)( to ptr\b)', rep, text)
    stage('M2', 'inttoptr constant VA remap: %d' % n[0])
    report['m2_inttoptr_remap'] = n[0]
    return text


def pass_m2p_dec_inttoptr(text, report):
    """[M2p] 命令形式の 10 進 `%x = inttoptr i64 <VA> to ptr` の VA→LVA remap (#417).
    RetDec は絶対アドレスを 10 進で出すが pass_m2 は 16 進しか見ない。pass_m1 が作る定数式形式
    `inttoptr (i64 N to ptr)` は既に LVA なので触らず、行頭が `%name = inttoptr i64 N to ptr` の形だけを対象にする。"""
    n = [0]

    def rep(m):
        nv = shiftva(int(m.group(2)))
        if nv is None:
            return m.group(0)
        n[0] += 1
        return m.group(1) + str(nv) + m.group(3)

    text = re.sub(r'(?m)^(\s*%[\w.$-]+\s*=\s*inttoptr i64 )(\d+)( to ptr\b)', rep, text)
    stage('M2p', 'decimal inttoptr instr VA remap: %d' % n[0])
    report['m2p_dec_inttoptr_remap'] = n[0]
    return text


def pass_m2q_fn980ed0(text, report):
    """[M2q] function_980ed0 の定数 VA 0x15e4080 (10 進 22954112) を LVA に remap (#861 → #1043).
    RetDec が 10 進で出したこの 1 件だけが VA→LVA 漏れ。残ると n が linear 0 の残骸を読み、unit 368 で 832MB の VirtualAlloc
    (2 GiB 上限超過で halt0) になる。全件 remap (M2P) は unit 503 でハングするため、この 1 件に限定する。"""
    old = '%ce0n11_function_980ed0 = inttoptr i64 22954112 to ptr'
    n = text.count(old)
    new = '%ce0n11_function_980ed0 = inttoptr i64 ' + str(shiftva(22954112)) + ' to ptr'
    text = text.replace(old, new)
    stage('M2q', 'function_980ed0 VA->LVA remap: %d sites' % n)
    report['m2q_fn980ed0_remap'] = n
    return text


# #4498 (LD-221): 段数が IR と機械語で一致する 25 件 (ldfix/results/depth_1046a30_4498.tsv の match=yes・0x15e 系)。
# 既定は 22946304 の 1 件 (#2958) だけ。残り 24 件は M11_M2R=1 の時だけ直す (未検証の runtime 確認まで既定 OFF)。
M2R_FN1046A30_VAS = frozenset([
    22937624, 22942488, 22950312, 22948232, 22946280, 22937720, 22940032, 22947960,
    22947080, 22953672, 22949400, 22951184, 22940536, 22943760, 22957000,
    22956552, 22951640, 22957928, 22951168, 22948096, 22949192, 22953072, 22947608,
    22952864,
])


def pass_m2r_fn1046a30(text, report):
    """[M2r] function_1046a30 の cell 参照 `%ceNn11_function_1046a30` の定数 VA を LVA に remap (#2958 / LD-142 → #4498 / LD-221).
    機械語の rip 先が cell (VA 0x15e0000〜0x15e4fff・LVA 0x11e0000〜0x11e4fff) を指す件を直す。
    22946304 (0x15e2200) の 1 件は #2958 から既定 ON。残り 24 件は段数一致を確認済みだが、起動結果 (本番 IR) の検証は未実施のため M11_M2R=1 で有効化する。
    RetDec が 10 進 VA で出したこの定数は、残すと linear の画像外 (22515781 B 超) や別の cell を読む (M2q と同型)。
    0x104cxxx 系 (コード範囲) は含めない (#4498 受入 3)。全件 remap (M2P) は使わない (#417)。"""
    n = 0
    extra = os.environ.get('M11_M2R') == '1'
    if extra:
        pat = r'(%ce\d+n11_function_1046a30) = inttoptr i64 (\d+) to ptr'
    else:
        pat = r'(%ce12n11_function_1046a30) = inttoptr i64 (22946304) to ptr'

    def fix(m):
        nonlocal n
        v = int(m.group(2))
        if v != 22946304 and not (extra and v in M2R_FN1046A30_VAS):
            return m.group(0)
        n += 1
        return '%s = inttoptr i64 %d to ptr' % (m.group(1), shiftva(v))

    text = re.sub(pat, fix, text)
    stage('M2r', 'function_1046a30 VA->LVA remap: %d sites (M11_M2R=%s)' % (n, '1' if extra else '0'))
    report['m2r_fn1046a30_remap'] = n
    return text


def pass_m2s_fn40fd90_iid(text, report):
    """[M2s] function_40fd90 (GetInterfaceEntry) の IID 先頭 8 バイト比較を復元 (#4012 / WIN-43).
    機械語 40fdd4 `cmp r11,[r9]` (r9 = arg2 = IID ポインタ) は IID の先頭 8 バイトを読むが、RetDec の IR は
    `icmp eq i64 %11, %arg2` でポインタ値そのものと比べていた。後半 8 バイト (`[arg2+8]`) は正しく読まれているため、同じ形で先頭も読む。
    この関数の 1 箇所だけを対象にする (他関数の同形比較は対象外)。"""
    head = 'define i64 @function_40fd90('
    i = text.find(head)
    if i < 0:
        head = 'define weak i64 @function_40fd90('
        i = text.find(head)
    if i < 0:
        stage('M2s', 'function_40fd90 IID compare restore: 0 sites (function absent)')
        report['m2s_fn40fd90_iid'] = 0
        return text
    j = text.find('\n}\n', i)
    if j < 0:
        stage('M2s', 'function_40fd90 IID compare restore: 0 sites (no closing brace)')
        report['m2s_fn40fd90_iid'] = 0
        return text
    body = text[i:j]
    old = '  %12 = icmp eq i64 %11, %arg2\n'
    new = ('  %iid0p = inttoptr i64 %arg2 to ptr\n'
           '  %iid0 = load i64, ptr %iid0p, align 8\n'
           '  %12 = icmp eq i64 %11, %iid0\n')
    n = body.count(old)
    if n == 1:
        text = text[:i] + body.replace(old, new) + text[j:]
    stage('M2s', 'function_40fd90 IID compare restore: %d sites' % n)
    report['m2s_fn40fd90_iid'] = n
    return text


def pass_m2s_fn41a800_vtable0(text, report):
    """[M2v] function_41a800 (Delphi interface cast) の vtable[0] 呼出しを復元 (#4011 / WIN-42).
    機械語 41a83d-41a842: `mov rax,[rsi]; call [rax]; test eax,eax` (rcx=Source, rdx=IID, r8=&out)。
    RetDec の IR は戻り値の代わりに IID ポインタの下位 32 bit (`trunc arg3`) で判定していたため、非 0 で必ず Halt0 した。
    この関数の 1 箇所だけを対象にする。既定 OFF (M11_M2V=1 で有効)。"""
    head = 'define i64 @function_41a800('
    i = text.find(head)
    j = text.find('\n}\n', i) if i >= 0 else -1
    if i < 0 or j < 0:
        stage('M2v', 'function_41a800 vtable0 restore: 0 sites (function absent)')
        report['m2v_fn41a800_vtable0'] = 0
        return text
    body = text[i:j]
    old = ('  %4 = ptrtoint ptr %arg3 to i64\n'
           '  store i64 0, ptr %stack_var_-48, align 8\n'
           '  %5 = ptrtoint ptr %stack_var_-48 to i64\n'
           '  %6 = call i64 @function_41a770(i64 %5)\n'
           '  %7 = trunc i64 %4 to i32\n'
           '  %8 = icmp eq i32 %7, 0\n')
    new = ('  %4 = ptrtoint ptr %arg3 to i64\n'
           '  store i64 0, ptr %stack_var_-48, align 8\n'
           '  %5 = ptrtoint ptr %stack_var_-48 to i64\n'
           '  %6 = call i64 @function_41a770(i64 %5)\n'
           '  %vt0p = inttoptr i64 %arg2 to ptr\n'
           '  %vt0 = load ptr, ptr %vt0p, align 8\n'
           '  %vtva = load i64, ptr %vt0, align 8\n'
           '  %vtret = call i64 @m11_icall(i64 %vtva, i64 %arg2, i64 %4, i64 %6, i64 0, i64 0, i64 0, i64 0, i64 0)\n'
           '  %7 = trunc i64 %vtret to i32\n'
           '  %8 = icmp eq i32 %7, 0\n')
    n = body.count(old)
    if n == 1:
        text = text[:i] + body.replace(old, new) + text[j:]
        if 'declare i64 @m11_icall(' not in text:
            text = text.replace(head, 'declare i64 @m11_icall(i64, i64, i64, i64, i64, i64, i64, i64, i64)\n' + head, 1)
    stage('M2v', 'function_41a800 vtable0 restore: %d sites' % n)
    report['m2v_fn41a800_vtable0'] = n
    return text


def pass_m2v_fn40fcf0_arg1(text, report):
    """[M2v] function_40fcf0 の function_40fd90 呼出しの第 1 引数を [arg1] (VMT) にする (#4011 段 2).
    機械語 40fd0b: `mov rcx,[rbx]` (rbx=self) で [self] を渡す。RetDec の IR は self をそのまま渡していたため、
    function_40fd90 が [rcx-0xc0] を self-0xc0 から読み範囲外へ出た (trap wasm 0x14e5b0)。
    この呼出し 1 箇所だけを対象にする。既定 OFF (M11_M2V=1 で有効)。"""
    head = 'define i64 @function_40fcf0('
    i = text.find(head)
    j = text.find('\n}\n', i) if i >= 0 else -1
    if i < 0 or j < 0:
        stage('M2v', 'function_40fcf0 arg1 VMT: 0 sites (function absent)')
        report['m2v_fn40fcf0_arg1'] = 0
        return text
    body = text[i:j]
    old = '  %1 = call i64 @function_40fd90(i64 %arg1, i64 %arg2)\n'
    new = ('  %vmt0p = inttoptr i64 %arg1 to ptr\n'
           '  %vmt0 = load i64, ptr %vmt0p, align 8\n'
           '  %1 = call i64 @function_40fd90(i64 %vmt0, i64 %arg2)\n')
    n = body.count(old)
    if n == 1:
        text = text[:i] + body.replace(old, new) + text[j:]
    stage('M2v', 'function_40fcf0 arg1 VMT: %d sites' % n)
    report['m2v_fn40fcf0_arg1'] = n
    return text


def pass_m2v_fn40fcf0_addref(text, report):
    """[M2v] function_40fcf0 の AddRef 呼出し `call [rax+8]` (機械語 40fd31-40fd3a) を復元 (#5359 / #4011 段 3).
    40fd31: `mov rax,[rdi]; mov rcx,rax; mov rax,[rax]; call [rax+8]` (rdi = 出力ポインタ, 非 0 のときだけ)。
    RetDec の IR はこの呼出しを落としていた (戻り値は [rdi] の非 0 判定で決まるため影響は無い)。
    この関数の 1 箇所だけを対象にする。既定 OFF (M11_M2V=1 で有効)。"""
    head = 'define i64 @function_40fcf0('
    i = text.find(head)
    j = text.find('\n}\n', i) if i >= 0 else -1
    if i < 0 or j < 0:
        stage('M2v', 'function_40fcf0 AddRef restore: 0 sites (function absent)')
        report['m2v_fn40fcf0_addref'] = 0
        return text
    body = text[i:j]
    old = ('  %9 = icmp eq i64 %8, 0\n'
           '  %spec.select = select i1 %9, i64 0, i64 %arg3\n'
           '  store i64 %spec.select, ptr %rax.0.reg2mem\n'
           '  br label %dec_label_pc_40fd7c\n')
    new = ('  %9 = icmp eq i64 %8, 0\n'
           '  br i1 %9, label %dec_label_pc_40fd22z, label %dec_label_pc_40fd22a\n'
           '\n'
           'dec_label_pc_40fd22z:\n'
           '  store i64 0, ptr %rax.0.reg2mem\n'
           '  br label %dec_label_pc_40fd7c\n'
           '\n'
           'dec_label_pc_40fd22a:\n'
           '  %arvtp = inttoptr i64 %8 to ptr\n'
           '  %arvt = load i64, ptr %arvtp, align 8\n'
           '  %arslot = add i64 %arvt, 8\n'
           '  %arslotp = inttoptr i64 %arslot to ptr\n'
           '  %arfn = load i64, ptr %arslotp, align 8\n'
           '  %arret = call i64 @m11_icall(i64 %arfn, i64 %8, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0)\n'
           '  store i64 %arg3, ptr %rax.0.reg2mem\n'
           '  br label %dec_label_pc_40fd7c\n')
    n = body.count(old)
    if n == 1:
        text = text[:i] + body.replace(old, new) + text[j:]
        if 'declare i64 @m11_icall(' not in text:
            text = text.replace(head, 'declare i64 @m11_icall(i64, i64, i64, i64, i64, i64, i64, i64, i64)\n' + head, 1)
    stage('M2v', 'function_40fcf0 AddRef restore: %d sites' % n)
    report['m2v_fn40fcf0_addref'] = n
    return text


def pass_m2b(text, report):
    n = [0]

    def rep_store(m):
        v = int(m.group(1), 16)
        nv = shiftva(v)
        if nv is None:
            return m.group(0)
        n[0] += 1
        return 'store i64 %d, ptr' % nv

    text = re.sub(r'store i64 (0x4[0-9a-f]{5}|0x1[0-3a][0-9a-f]{6}), ptr', rep_store, text)

    def rep_addsub(m):
        v = int(m.group(2), 16)
        nv = shiftva(v)
        if nv is None:
            return m.group(0)
        n[0] += 1
        return m.group(1) + str(nv)

    text = re.sub(r'(add i64 %[\w.-]+, )(0x4[0-9a-f]{5}|0x1[0-3a][0-9a-f]{6})\b', rep_addsub, text)
    text = re.sub(r'(sub i64 %[\w.-]+, )(0x4[0-9a-f]{5}|0x1[0-3a][0-9a-f]{6})\b', rep_addsub, text)
    stage('M2b', 'store/add/sub VA remap: %d' % n[0])
    report['m2b_remap'] = n[0]
    return text


# ---------------------------------------------------------------
# [M2c] sext/zext/trunc operand の型 suffix 補完 (LLVM typed-operand)
# ---------------------------------------------------------------
def pass_m2c(text, report):
    lines = text.split('\n')
    out = []
    fixed = 0
    i = 0
    n = len(lines)
    while i < n:
        l = lines[i]
        m = re.match(r'^define \S+ @', l)
        if not m:
            out.append(l)
            i += 1
            continue
        body = [l]
        i += 1
        while i < n and not lines[i].startswith('}'):
            body.append(lines[i])
            i += 1
        if i < n:
            body.append(lines[i])
            i += 1
        # reg → type 推定
        tm = {}
        for l2 in body:
            m2 = re.match(r'^\s*%([\w.$-]+)\s*=\s*(\w+)\b\s*(.*)$', l2)
            if not m2:
                continue
            nm, op, rest = m2.group(1), m2.group(2), m2.group(3)
            mt = None
            tos = re.findall(r'\bto\s+([if]\d+|ptr)\b', rest)
            if tos:
                mt = tos[-1]
            ty = mt if mt else None
            if ty is None and op in ('or', 'and', 'add', 'sub', 'mul', 'lshr', 'ashr', 'shl', 'div', 'sdiv', 'udiv', 'srem', 'urem', 'xor', 'fadd', 'fsub', 'fmul', 'fdiv', 'fneg'):
                mb = re.match(r'([if]\d+)\s', rest)
                if mb:
                    ty = mb.group(1)
            if op in ('load', 'store'):
                mt2 = re.match(r'(i\d+|f\d+)\s*,', rest)
                if mt2:
                    ty = mt2.group(1)
            elif op in ('icmp', 'fcmp', 'select'):
                ty = 'i1' if op in ('icmp', 'fcmp') else None
            elif op == 'alloca':
                ty = 'ptr'
            elif op in ('getelementptr', 'inttoptr', 'bitcast'):
                ty = 'ptr'
            if ty and re.match(r'^([if]\d+|ptr)$', ty):
                tm[nm] = ty

        def rep(m2):
            nonlocal fixed
            op = m2.group(1)
            v = m2.group(2)
            to = m2.group(3)
            tname = tm.get(v.lstrip('%'))
            if tname and re.match(r'^[if]\d+$', tname):
                fixed += 1
                return '%s %s %s to %s' % (op, tname, v, to)
            return m2.group(0)

        for j, l2 in enumerate(body):
            l3 = re.sub(r'\b(sext|zext|trunc) ([-%][\w.$]+\b) to (i\d+|f\d+|ptr)\b', rep, l2)
            body[j] = l3
        # [M2d] inttoptr i64 %reg で %reg が i32 型のとき sext を一体を挿入
        body = pass_m2d(body, tm)
        body = pass_m2e(body, tm)
        body = pass_m2f(body, tm)
        out.extend(body)
    text = '\n'.join(out)
    stage('M2c', 'typed-operand sext/zext/trunc: %d sites' % fixed)
    report['m2c_fixed'] = fixed
    return text


def pass_m2d(body, tm):
    """[M2d] inttoptr i64 <reg(i32 型)> to ptr — i32/i64 幅混合の broken-lift 注入."""
    out = []
    fixed = 0
    for l in body:
        m = re.match(r'^\s*%([\w.$-]+)\s*=\s*inttoptr i64 ([-%][\w.$]+) to ptr\s*$', l)
        if m:
            v = m.group(2)
            tname = tm.get(v.lstrip('%'))
            if tname in ('i8', 'i16', 'i32'):
                fixed += 1
                newname = '%s_m11z64' % m.group(1)
                out.append('  %%%s = sext %s %s to i64' % (newname, tname, v))
                out.append('  %%%s = inttoptr i64 %%%s to ptr' % (m.group(1), newname))
                continue
        out.append(l)
    if fixed:
        stage('M2d', 'inttoptr i32→i64 fix: %d sites' % fixed)
    return out


def pass_m2e(body, tm):
    """行: `op i32 %a, %b` で %b が i64 型 (または逆) の場, cast を前段に挿入する."""
    out = []
    fixed = 0
    for l in body:
        m = re.match(r'^(\s*%([\w.$-]+)\s*=\s*([\w ]+?)\s+)(i\d+)(\s.+)$', l)
        if not m:
            out.append(l)
            continue
        head, name, op, ty, rest = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        parts = re.split(r'\s*,\s*', rest.strip())
        newparts = []
        changed = False
        for p in parts:
            mm = re.match(r'^([-%][\w.$]+)$', p)
            if mm:
                v = mm.group(1)
                t = tm.get(v.lstrip('%'))
                if t and t != ty and re.match(r'^i\d+$', t) and re.match(r'^i\d+$', ty):
                    fixed += 1
                    changed = True
                    newname = ('_' if name[0].isdigit() else '') + '%s_cast%d' % (name, fixed)
                    fnm = newname.lstrip('%')
                    if int(t[1:]) >= int(ty[1:]):
                        out.append('  %' + fnm + ' = trunc ' + t + ' ' + v + ' to ' + ty)
                    else:
                        out.append('  %' + fnm + ' = sext ' + t + ' ' + v + ' to ' + ty)
                    newparts.append('%' + newname.lstrip('%'))
                    continue
            newparts.append(p)
        if changed:
            out.append('%s%s %s' % (head, ty, ', '.join(newparts)))
            continue
        out.append(l)
    if fixed:
        stage('M2e', 'binary-op operand cast: %d sites' % fixed)
    return out


def pass_m2f(body, tm):
    """call 行の引数で 'ptr <v>' が i64/i32 の場 → 'ptr inttoptr (i64 v) to ptr' 等."""
    out = []
    fixed = 0
    for l in body:
        m = re.match(r'^\s*(%[\w.$-]+\s*=\s*)?call\b\s*([^\s]+)\s*(@?[\w.$-]+)\((.*)\)(.*)$', l)
        if not m:
            out.append(l)
            continue
        lhs, rty, callee, args, tail = m.groups()
        parts = re.split(r',\s*', args.strip())
        newparts = []
        changed = False
        for p in parts:
            pm = re.match(r'^\s*([\w.]+\s+)?([-%][\w.$]+)\s*$', p)
            if not pm:
                newparts.append(p.strip())
                continue
            typ, v = pm.group(1), pm.group(2)
            t = tm.get(v.lstrip('%'))
            if typ and (typ.startswith('ptr') or typ.endswith('ptr')) and t and re.match(r'^i\d+$', t) and t != 'i64':
                fixed += 1
                changed = True
                cname = '_m11arg_%d' % fixed
                seg = ''
                if int(t[1:]) >= 32:
                    out.append('  %' + cname.lstrip('_') + '_m11p = inttoptr i64 %' + v.lstrip('%') + ' to ptr')
                else:
                    out.append('  %' + cname.lstrip('_') + '_m11p = inttoptr i64 zext(' + t + ' %' + v.lstrip('%') + ' to i64) to ptr')
                newparts.append('ptr %' + cname.lstrip('_') + '_m11p')
                continue
            newparts.append(p.strip())
        if changed:
            out.append('  %scall %s %s(%s)%s' % ((lhs if lhs else ''), rty, callee, ', '.join(newparts), tail))
            continue
        out.append(l)
    if fixed:
        stage('M2f', 'call-site arg cast: %d sites' % fixed)
    return out


# ---------------------------------------------------------------
# [M2n] call site / callee signature 整合.
#   LLVM wasm backend (WebAssemblyFixFunctionBitcasts) は call operand 型 ≠ callee 型の
#   場所に thunk を生成するが, no-op cast でない組 (i32↔i64 等) は
#   .L<fn>_bitcast_invalid (body=unreachable) になり実行時 abort になる。
#   ここで define/declare の実 signature に合わせて IR 上で正当化する:
#     引数:   ptr→iN は ptrtoint (= wasm では zext), iN→ptr は inttoptr,
#             int 幅違いは zext/trunc
#     戻り値: 実戻値を %r_raw で受け, 元 SSA 名を変換命令で再定義 (後続 use 型不変)
# ---------------------------------------------------------------
_INT_TY = re.compile(r'^i\d+$')


def _topsplit(s):
    """トップレベル ', ' 分割 (括弧ネスト対応)."""
    parts, depth, cur = [], 0, ''
    for ch in s:
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(cur.strip())
            cur = ''
            continue
        cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _cast_reg(out, vname, aty, pty, ctr):
    """%reg operand の変換命令 1..2 行を emit; 変換後名 (先頭 % 付き) を返す (変換不能は None)."""
    if aty == pty:
        return vname
    base = vname.lstrip('%')
    n = '__m11c_%d' % next(ctr)
    if aty == 'ptr' and _INT_TY.match(pty):
        out.append('  %%%s = ptrtoint ptr %%%s to %s' % (n, base, pty))
        return '%' + n
    if _INT_TY.match(aty) and pty == 'ptr':
        out.append('  %%%s = inttoptr %s %%%s to ptr' % (n, aty, base))
        return '%' + n
    if _INT_TY.match(aty) and _INT_TY.match(pty):
        a, b = int(aty[1:]), int(pty[1:])
        op = 'trunc' if a > b else 'zext'
        out.append('  %%%s = %s %s %%%s to %s' % (n, op, aty, base, pty))
        return '%' + n
    return None  # float/struct 等は対応しない (site skip)


def _cast_const(val, aty, pty):
    """定数 operand の型 token 置換 (変換不能は None)."""
    if aty == pty:
        return None
    if aty == 'ptr':
        if _INT_TY.match(pty):
            if val == 'null' or val == 'poison':
                return '%s 0' % pty
            return '%s ptrtoint (ptr %s to %s)' % (pty, val, pty)
        return None
    if _INT_TY.match(aty) and pty == 'ptr':
        return 'ptr inttoptr (%s %s to ptr)' % (aty, val)
    if _INT_TY.match(aty) and _INT_TY.match(pty):
        return '%s %s' % (pty, val)
    return None


def _retconv_line(rty, rreal, raw):
    """call 実戻値 %raw (型 rreal) → 元期待型 rty の変換命令行 (対応不能は None).
    rty=='void' 相当 (discard) は 'D' を返す."""
    if rty == rreal:
        return None
    if rreal == 'void':
        if rty == 'ptr':
            return '%s = inttoptr i64 0 to ptr' % ('%' + raw)
        if _INT_TY.match(rty):
            return '%s = add %s 0, 0' % ('%' + raw, rty)
        return None
    if rty == 'void':
        return 'D'  # 戻り値を捨てる (lhs は呼ばない)
    if rty == 'ptr' and _INT_TY.match(rreal):
        return '%%%s = inttoptr %s %%%s to ptr' % (raw, rreal, raw)
    if _INT_TY.match(rty) and rreal == 'ptr':
        return '%%%s = ptrtoint ptr %%%s to %s' % (raw, raw, rty)
    if _INT_TY.match(rty) and _INT_TY.match(rreal):
        a, b = int(rreal[1:]), int(rty[1:])
        op = 'trunc' if a > b else 'zext'
        return '%s = %s %s %%%s to %s' % ('%' + raw, op, rreal, raw, rty)
    return None


def pass_m2n_callsig(text, report):
    # --- signature 収集 ---
    sig = {}
    for m in re.finditer(r'^define (\S+) @([\w.$-]+)\((.*)\)', text, re.M):
        nm, ps = m.group(2), m.group(3)
        params = _topsplit(ps)
        sig[nm] = None if '...' in params else (m.group(1), [p.split()[0] for p in params])
    for m in re.finditer(r'^declare (\S+) @([\w.$-]+)\((.*?)\)', text, re.M):
        nm = m.group(2)
        if nm in sig:
            continue
        ps = m.group(3)
        sig[nm] = 'vararg' if '...' in ps else (m.group(1), [p.split()[0] for p in _topsplit(ps)])
    lines = text.split('\n')
    out = []
    ctr = itertools.count(1)
    nfix = 0
    nskip = 0
    pat = re.compile(r'^([ \t]*)(%([\w.$-]+)[ \t]*=[ \t]*)?((?:tail[ \t])?(?:fastcc[ \t])?call(?:[ \t]+\w+cc)?[ \t]+)(\S+)[ \t]+@([\w.$-]+)\((.*)\)(.*)$')
    for l in lines:
        m = pat.match(l)
        if not m:
            out.append(l)
            continue
        head0, lhs, lhsname, head, rty, callee, argstr, tailafter = m.groups()
        s = sig.get(callee)
        if s is None or s == 'vararg':
            nskip += 1
            out.append(l)
            continue
        rreal, params = s
        args = _topsplit(argstr)
        if len(args) != len(params):
            nskip += 1
            out.append(l)
            continue
        have_lhs = lhsname is not None
        # --- 戻り値整合判定 ---
        retmode = None   # None=単純一致, 'POISON', 'DISCARD', 'CAST'
        if have_lhs and rty != rreal:
            retconv = _retconv_line(rty, rreal, 'RAWNAME')
            if retconv is None:
                nskip += 1
                out.append(l)
                continue
            retmode = 'D' if retconv == 'D' else 'CAST'
        elif not have_lhs and rty != rreal:
            retmode = 'DISCARD'
        # --- 引数変換 ---
        conv_lines = []
        newargs = []
        ok = True
        changed = False
        for a, p in zip(args, params):
            tk = a.split()
            pty = p
            aty = tk[0]
            rest = tk[1:]
            if aty == pty:
                newargs.append(a)
                continue
            if not (aty == 'ptr' or _INT_TY.match(aty)) or not rest:
                ok = False
                break
            # operand 抽出: attr token (nonnull/dereferenceable 等) を除いた最初の
            # %reg / 定数式を取る (定数式は getelementptr inbounds (...) 等空間含む)
            ATTRS = {'nonnull', 'null', 'nocapture', 'readonly', 'readnone',
                     'dereferenceable', 'dereferenceable_or_null', 'align', 'byval',
                     'swiftself', 'swifterror', 'inalloca', 'noalias', 'returned'}
            ws = list(rest)
            while ws and ws[0] in ATTRS:
                ws.pop(0)
                if ws and ws[0] == 'align':
                    ws.pop(0)  # 'align 8' 2-token
                    continue
                if ws and ws[0].startswith('dereferenceable'):
                    continue
            if not ws:
                ok = False
                break
            val = ws[0]
            if val.startswith('%'):
                nv = _cast_reg(conv_lines, val, aty, pty, ctr)
                if nv is None:
                    ok = False
                    break
                newargs.append('%s %s' % (pty, nv))
            else:
                # 定数式 (要素が空間含むことがある → 残トークンを結合)
                valc = ' '.join(ws)
                nv = _cast_const(valc, aty, pty)
                if nv is None:
                    ok = False
                    break
                newargs.append(nv)
            changed = True
        if not ok:
            nskip += 1
            out.append(l)
            continue
        if not changed and retmode is None:
            out.append(l)   # 変更不要
            continue
        for cl in conv_lines:
            out.append(cl)
        emit_ret = rty if retmode is None else rreal
        if retmode == 'DISCARD' or not have_lhs:
            out.append('%s%scall %s @%s(%s)%s' % (head0, lhs or '', emit_ret, callee, ', '.join(newargs), tailafter))
        else:
            if retmode is None:
                # 戻り値一致: 元 lhs 名のまま (引数だけ置換)
                out.append('%s%%%s = call %s @%s(%s)%s' % (head0, lhsname, emit_ret, callee, ', '.join(newargs), tailafter))
            else:
                rawn = '__m11r_%d' % next(ctr)
                if emit_ret == 'void':
                    out.append('%scall void @%s(%s)%s' % (head0, callee, ', '.join(newargs), tailafter))
                else:
                    out.append('%s%%%s = call %s @%s(%s)%s' % (head0, rawn, emit_ret, callee, ', '.join(newargs), tailafter))
            if retmode == 'CAST':
                cl = _retconv_line(rty, rreal, rawn)
                headc, tailc = cl.split(' = ', 1)
                out.append('  %%%s = %s' % (lhsname, tailc))
            elif retmode == 'POISON':
                pc = _retconv_line(rty, 'void', rawn)
                out.append('  %%%s = %s' % (lhsname, pc.split(' = ', 1)[1]))
        nfix += 1
    text = '\n'.join(out)
    stage('M2n', 'call signature sites rewritten: %d (skipped: %d)' % (nfix, nskip))
    report['m2n_fix'] = nfix
    report['m2n_skip'] = nskip
    return text


def pass_m5(text, init_fns, report):
    if not init_fns:
        return text
    lines = text.split('\n')
    out = []
    n_ins = 0
    st = ['  %m11cntp = call ptr @m11_counter_ptr()',
          '  %m11c_load = load i32, ptr %m11cntp',
          '  %m11c_add = add i32 %m11c_load, 1',
          '  store i32 %m11c_add, ptr %m11cntp']
    infl = set(init_fns)
    i = 0
    N = len(lines)
    text_decl = '\ndeclare ptr @m11_counter_ptr()' if '@m11_counter_ptr' not in text else ''
    while i < N:
        l = lines[i]
        m = re.match(r'^define \S+ @([\w.$_-]+)\(', l)
        if m and m.group(1) in infl:
            out.append(l)
            i += 1
            seen_label = False
            while i < N and not lines[i].startswith('}'):
                if re.match(r'^dec_label_[\w.]+:' + r'|^[\w.$_-]+:', lines[i]):
                    seen_label = True
                    out.append(lines[i])
                    i += 1
                    continue
                is_alloca = bool(re.match(r'^\s*%[\w.$-]+ = alloca\b', lines[i]))
                if seen_label and not is_alloca:
                    out.extend(st)
                    out.append('')
                    n_ins += 1
                    break
                out.append(lines[i])
                i += 1
            continue
        out.append(l)
        i += 1
    text = '\n'.join(out)
    if text_decl:
        text += text_decl
    stage('M5', 'init prologue counter-insert: %d fn' % n_ins)
    report['m5_probe'] = n_ins
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('infile')
    ap.add_argument('outfile')
    ap.add_argument('--report', default='')
    ap.add_argument('--init-list', default='')
    ap.add_argument('--no-m2b', action='store_true')
    args = ap.parse_args()
    text = open(args.infile).read()
    report = {}
    init_fns = []
    if args.init_list:
        x = args.init_list
        if x.startswith('@'):
            x = open(x[1:]).read()
        elif os.path.isfile(x):
            x = open(x).read()
        init_fns = [s for s in x.replace(',', ' ').split() if s.strip()]
    text = pass_m2l_numballs(text, report)
    text = pass_m1(text, report)
    text = pass_m2(text, report)
    text = pass_m2q_fn980ed0(text, report)
    text = pass_m2r_fn1046a30(text, report)
    if os.environ.get('M11_M2S') == '1':   # #4012: 既定 OFF (未検証の runtime 確認まで有効化しない)
        text = pass_m2s_fn40fd90_iid(text, report)
    if os.environ.get('M11_M2V') == '1':   # #4011: 既定 OFF (runtime 確認まで有効化しない)
        text = pass_m2s_fn41a800_vtable0(text, report)
        text = pass_m2v_fn40fcf0_arg1(text, report)
        text = pass_m2v_fn40fcf0_addref(text, report)
    if os.environ.get('M11_M2P') == '1':   # #417: 既定 OFF (有効化すると unit 503 で survey がハング, REPORT 参照)
        text = pass_m2p_dec_inttoptr(text, report)
    text = pass_m2c(text, report)
    text = pass_m2g_irfix(text, report)
    text = pass_m2h_select(text, report)
    text = pass_m2i_fnname(text, report)
    text = pass_m2j_imm(text, report)
    text = pass_m2k_dedupdecls(text, report)
    text = pass_m2n_callsig(text, report)
    if not args.no_m2b:
        text = pass_m2b(text, report)
    text = pass_m5(text, init_fns, report)
    open(args.outfile, 'w').write(text)
    if args.report:
        json.dump(report, open(args.report, 'w'), indent=1)
    stage('M11', 'ir passes done: out=%s (%d lines)' % (args.outfile, text.count('\n')))


if __name__ == '__main__':
    main()


# --- hotfix: M2n emit 分岐の整合 (v2 再実装済み: 上記 pass_m2n_callsig が正規版) ---
