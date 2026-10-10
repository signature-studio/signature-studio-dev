#!/usr/bin/env python3
"""kh_lower.py — RetDec *stage-0 IR* (LLVM IR decoding 直後) を wasm 化可能な形へ lowering する (Path B)。

背景 (最重要): RetDec 最終 IR を後から機械語照合で直す方式 (kh_passes.py, Path A) は、
  ucomis*/comis* が @cf/@zf/@pf を更新しない frontend 欠陥 → jcc が *古い定数フラグ* (例: `xor ecx,ecx` 由来 cf=0,zf=1) を読む
  → LLVM が分岐を定数畳み込み → skip 側コードが **dead code として IR から消える** (Clipper の soft-knee 計算が丸ごと消滅)
  という silent miscompile に対して *復元不能* になる。そこで RetDec の decode 直後 (最適化前) の stage-0 IR
  (`--print-after-all` の最初のダンプ: レジスタ = グローバル, 1 機械語命令 = 1 ブロック, フラグ明示) を採り、
  frontend 欠陥だけを局所修復して自前で最適化・wasm 化する。

修復 (すべて stage-0 上で機械的に実施):
  [flags]   (u)comis{s,d} → @cf/@zf/@pf を fcmp で更新 (CF=lt|uno, ZF=eq|uno, PF=uno, OF=SF=AF=0)
  [mov128]  movaps/movups の 128bit store が `call i64 @__asm_movaps` + `sext i64→i128` で上位 64bit 符号拡張になる欠陥
  [store]   movups/movlps/movhps/movsd/movq/movss/movd の *メモリ store 形* が `call void @__asm_X(old_load, val)` で store 消失
  [merge]   cvtsi2ss/sd, cvtss2sd, cvtsd2ss の dest 上位 lane 保持 (helper シグネチャが dest を落とす)
  [callret] call 時の戻り番地 push/pop 省略 (stage-0) による callee スタック引数 8B ずれの補正
  [rdata]   `inttoptr (i64 <PE VA> ...)` / `i64 <PE VA>` リテラルを DLL 実データ窓 (global_var_<VA>) へ
  [abi]     入口 wrapper: rcx/rdx/r8/r9 + xmm0-3 引数 → レジスタグローバル, 戻り値 rax / xmm0 (F2 相当を ABI 仕様で解決)
usage: kh_lower.py stage0.ll OUT.ll --core HeartCore.core_64 --lift va,va,... [--abi json] [--skip a,b]
"""
import argparse
import json
import re
import sys

IMG_LO, IMG_HI = 0x180000000, 0x180000000 + 0x625c000   # SizeOfImage
WASM_DL = ('target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128-f128:64-n32:64-S128-ni:1:10:20"')
STACK = 65536
CALLEE_I = ['rbx', 'rbp', 'rsi', 'rdi', 'r12', 'r13', 'r14', 'r15']        # MS x64 ABI の callee-saved (GPR)
CALLEE_X = ['xmm%d' % k for k in range(6, 16)]                            # 同 (xmm6-15)
REGS_I64 = ['rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15']
FLAGS = ['cf', 'pf', 'az', 'zf', 'sf', 'of', 'df']

MOV128 = re.compile(r'^(\s*)(%[\w.\-]+) = call i64 @__asm_(?:movaps|movups|movdqa|movdqu|movapd|movupd)(?:\.\d+)?\(i128 ([^)]+)\)\s*$')
SEXT = re.compile(r'^(\s*)(%[\w.\-]+) = sext i64 (%[\w.\-]+) to i128\s*$')
STORE128 = re.compile(r'^(\s*)call void @__asm_(?:movaps|movups|movdqa|movdqu|movapd|movupd|movntps|movntdq)(?:\.\d+)?\(i128 (%[\w.\-]+), i128 ([^)]+)\)\s*$')
STORELOW = re.compile(r'^(\s*)call void @__asm_(movlps|movlpd|movhps|movhpd|movsd|movq|movss|movd)(?:\.\d+)?\((i64|i32) (%[\w.\-]+), i128 ([^)]+)\)\s*$')
COMIS = re.compile(r'^(\s*)call void @__asm_(?:v)?u?comis(s|d)(?:\.\d+)?\(i128 (%[\w.\-]+), (i128|i64|i32) ([^)]+)\)\s*$')
MERGE = re.compile(r'^(\s*)(%[\w.\-]+) = call i128 @__asm_(cvtsi2ss|cvtsi2sd|cvtss2sd|cvtsd2ss|sqrtsd|sqrtss)(?:\.\d+)?\(([^)]*)\)\s*$')
FN_DEF = re.compile(r'^define \S+ @function_([0-9a-f]+)\(\) \{$')
LIT = re.compile(r'(?<![\w%.@])(\d{10,11})(?![\w.])')


def vshift_pass(lines, uid, rep):
    """[vshift] 可変 shift のカウントを x86 語義 (64bit op は count & 63, 32bit op は & 31) に精密化する (D14/KH-2b)。

    x86 は CL 由来の shift count を 6bit (64bit op) / 5bit (32bit op) にマスクする (mask 後 0 なら値・フラグ不変)。
    一方 LLVM IR は count ≥ bitwidth を poison と定義するため、stage-0 IR の `shl/lshr/ashr iN %v, %c`
    (%c がレジスタ) をそのままにすると count ≥ 64 の入力で未定義動作になり得る (k_dfdb0 の
    `shl r9, cl` (cl = 64 - bsr) 等が該当位置)。`and` で事前マスクすれば LLVM == x86 に一致する。
    フラグ計算側は RetDec が既にマスク済みカウントで分岐ガードする (`and 63` + `icmp eq 0`) ので
    本 pass は値 shift のみの書換で整合する。
    """
    SH = re.compile(r'^(\s*)(%[\w.\-]+) = (shl|lshr|ashr) (i32|i64) ([^,]+), (%[\w.\-]+)\s*$')
    MASK = {'i64': 63, 'i32': 31}
    out = []
    for l in lines:
        m = SH.match(l)
        if m:
            ind, dst, op, ty, val, cnt = m.groups()
            t = uid('v')
            out.append(f'{ind}%{t}.c = and {ty} {cnt}, {MASK[ty]}')
            out.append(f'{ind}{dst} = {op} {ty} {val}, %{t}.c')
            rep['vshift'] = rep.get('vshift', 0) + 1
            continue
        out.append(l)
    return out


def gs_pass(lines, uid, rep):
    """[gs] セグメント相対アクセス (addrspace(256)) をエミュレート用グローバル @kh_gs への普通のアクセスに置換する。

    RetDec は `mov r11, gs:[0x10]` (TIB StackLimit) 等を
    `%X = load i64, i64 addrspace(256)* inttoptr (i64 N to i64 addrspace(256)*)` に出す。
    wasm32 に addrspace(256) は載らないため、@kh_gs (ゼロ初期化 4KB) へのオフセット参照に置き換える。
    値は 0 (PEB無し / StackLimit=0)。_chkstk (0x180f87cd0) の probe 経路は小さな frame では不発なので
    実機 (深い stack, probe 不発) と分岐結果が一致する。gs:[0x60] (PEB) は CRT 初期化 check 経路のみ。
    """
    out = []
    n = 0
    for l in lines:
        m = re.match(r'^(\s*)(%[\w.\-]+) = load (i\d+), \3 addrspace\(256\)\* inttoptr \(i64 (\d+) to \3 addrspace\(256\)\*\)\s*$', l)
        if m:
            ind, dst, ty, off = m.groups()
            t = uid('g')
            out += [f'{ind}%{t}.b = ptrtoint i8* @kh_gs to i32',
                    f'{ind}%{t}.o = add i32 %{t}.b, {off}',
                    f'{ind}%{t}.p = inttoptr i32 %{t}.o to {ty}*',
                    f'{ind}{dst} = load {ty}, {ty}* %{t}.p']
            rep['gs'] = rep.get('gs', 0) + 1
            continue
        out.append(l)
    return out


def lower_body(lines, cfg, skip, uid, rep, icalls=None):
    icalls = icalls or {}
    out = []
    i = 0
    pend_sext = {}
    cur_addr = None
    jt = cfg or {}
    n = len(lines)
    while i < n:
        l = lines[i]
        mc = re.match(r'^; 0x([0-9a-f]+)\s*$', l)
        if mc:
            cur_addr = mc.group(1)
        if 'store volatile i64' in l and '@_asm_program_counter' in l:
            i += 1
            continue
        # ---- 間接 call (D15): stage-0 は `call qword [reg+N]` (vtable dispatch) を *空ブロック* にする
        #      (vtable load と `mov rcx,` は残るが call が消える)。機械語側から (reg, disp) を復元し
        #      kh_icall(slot) への間接呼出に置換する (slot = vtable base + disp。wasm 側はアリーナ内
        #      vtable の実値を読んで既知 callee へ dispatch、未知は fail-fast)。
        # ---- 間接 call (D15): stage-0 は `call qword [reg+N]` (vtable dispatch) を *空ブロック* にする
        #      (vtable load と `mov rcx,` は残るが call が消える)。機械語側から (reg, disp) を復元し
        #      kh_icall(slot) への間接呼出に置換する (slot = vtable base + disp。wasm 側はアリーナ内
        #      vtable の実値を読んで既知 callee へ dispatch、未知は fail-fast)。
        if cur_addr in icalls and 'icall' not in skip:
            reg, disp = icalls.pop(cur_addr)
            t = uid('i')
            if reg == '__rip__':
                if disp >= 0:
                    # 解決済みの静的 target (lift 済保証: 検出側で vas 判定済み)
                    out += [f'  %{t}.sp = load i64, i64* @rsp', f'  %{t}.sp8 = sub i64 %{t}.sp, 8',
                            f'  store i64 %{t}.sp8, i64* @rsp', f'  %{t}.pp = inttoptr i64 %{t}.sp8 to i64*',
                            f'  store i64 0, i64* %{t}.pp', f'  %{t}.c = call i64 @kh_%x()' % disp,
                            f'  store i64 %{t}.c, i64* @rax', f'  store i64 %{t}.sp, i64* @rsp']
                else:
                    out += [f'  %{t}.c = call i64 @kh_icfail()', f'  store i64 %{t}.c, i64* @rax']
                rep['icall'] = rep.get('icall', 0) + 1
                i += 1
                continue
            out += [f'  %{t}.b = load i64, i64* @{reg}', f'  %{t}.a = add i64 %{t}.b, {disp}',
                    f'  %{t}.sp = load i64, i64* @rsp', f'  %{t}.sp8 = sub i64 %{t}.sp, 8',
                    f'  store i64 %{t}.sp8, i64* @rsp', f'  %{t}.pp = inttoptr i64 %{t}.sp8 to i64*',
                    f'  store i64 0, i64* %{t}.pp', f'  %{t}.c = call i64 @kh_icall(i64 %{t}.a)',
                    f'  store i64 %{t}.c, i64* @rax', f'  store i64 %{t}.sp, i64* @rsp']
            rep['icall'] = rep.get('icall', 0) + 1
            i += 1
            continue
        # ---- 間接 jmp (switch jump table): stage-0 は `jmp rax` を `ret i64 undef` にしてしまう → switch へ復元
        if l.strip() == 'ret i64 undef' and cur_addr in jt and 'jumptable' not in skip:
            import struct
            tb, nent = jt[cur_addr]['table'], jt[cur_addr]['n']
            tgts = [tb + struct.unpack('<i', jt['_rd'](tb + 4 * k, 4))[0] for k in range(nent)]
            t = uid('j')
            # 窓置換後の rcx(=table base の窓アドレス) との差 = テーブル要素 (target - table_base) で switch する (VA 定数に依存しない)
            out.append(f'  %{t}.a = load i64, i64* @rax')
            out.append(f'  %{t}.b = load i64, i64* @rcx')
            out.append(f'  %{t}.t = sub i64 %{t}.a, %{t}.b')
            out.append(f'  switch i64 %{t}.t, label %{t}.def [')
            for k, tg in enumerate(tgts):
                out.append(f'    i64 {tg - tb}, label %dec_label_pc_{tg:x}')
            out.append('  ]')
            out.append(f'{t}.def:')
            out.append('  unreachable')
            rep['jumptable'] = rep.get('jumptable', 0) + 1
            i += 1
            continue
        # ---- flags
        m = COMIS.match(l)
        if m and 'flags' not in skip:
            ind, kind, a, bty, b = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
            t = uid('c')
            ty, ity = ('double', 'i64') if kind == 'd' else ('float', 'i32')
            ln = [f'{ind}%{t}.a0 = trunc i128 {a} to {ity}', f'{ind}%{t}.a = bitcast {ity} %{t}.a0 to {ty}']
            if bty == 'i128':
                ln += [f'{ind}%{t}.b0 = trunc i128 {b} to {ity}', f'{ind}%{t}.b = bitcast {ity} %{t}.b0 to {ty}']
            else:
                ln += [f'{ind}%{t}.b = bitcast {bty} {b} to {ty}']
            ln += [f'{ind}%{t}.lt = fcmp olt {ty} %{t}.a, %{t}.b', f'{ind}%{t}.eq = fcmp oeq {ty} %{t}.a, %{t}.b',
                   f'{ind}%{t}.un = fcmp uno {ty} %{t}.a, %{t}.b', f'{ind}%{t}.cf = or i1 %{t}.lt, %{t}.un', f'{ind}%{t}.zf = or i1 %{t}.eq, %{t}.un',
                   f'{ind}store i1 %{t}.cf, i1* @cf', f'{ind}store i1 %{t}.zf, i1* @zf', f'{ind}store i1 %{t}.un, i1* @pf',
                   f'{ind}store i1 false, i1* @of', f'{ind}store i1 false, i1* @sf', f'{ind}store i1 false, i1* @az']
            out += ln
            rep['flags'] = rep.get('flags', 0) + 1
            i += 1
            if i < n and 'store i64 undef, i64* @rflags' in lines[i]:
                i += 1
            continue
        # ---- mov128 (store 経路の sext)
        m = MOV128.match(l)
        if m and 'mov128' not in skip:
            ind, r, x = m.group(1), m.group(2), m.group(3)
            out.append(f'{ind}{r} = trunc i128 {x} to i64')
            pend_sext[r] = x
            i += 1
            continue
        m = SEXT.match(l)
        if m and m.group(3) in pend_sext and 'mov128' not in skip:
            out.append(f'{m.group(1)}{m.group(2)} = or i128 {pend_sext[m.group(3)]}, 0')
            rep['mov128'] = rep.get('mov128', 0) + 1
            i += 1
            continue
        # ---- store 形
        m = STORE128.match(l)
        if m and 'store' not in skip:
            ind, old, val = m.group(1), m.group(2), m.group(3)
            ptr = find_load_ptr(out, old, 'i128')
            if ptr:
                out.append(f'{ind}store i128 {val}, i128* {ptr}, align 1')
                rep['store128'] = rep.get('store128', 0) + 1
                i += 1
                continue
        m = STORELOW.match(l)
        if m and 'store' not in skip:
            ind, mn, ty, old, val = m.groups()
            ptr = find_load_ptr(out, old, ty)
            if ptr:
                t = uid('s')
                v = val
                if mn in ('movhps', 'movhpd'):
                    out.append(f'{ind}%{t}.s = lshr i128 {val}, 64')
                    v = f'%{t}.s'
                out.append(f'{ind}%{t}.v = trunc i128 {v} to {ty}')
                out.append(f'{ind}store {ty} %{t}.v, {ty}* {ptr}, align 1')
                rep['storelow'] = rep.get('storelow', 0) + 1
                i += 1
                continue
        # ---- merge
        m = MERGE.match(l)
        if m and 'merge' not in skip:
            ind, r, mn, args = m.groups()
            j = i + 1
            sm = None
            while j < min(n, i + 6):
                sm = re.match(r'^(\s*)store i128 ' + re.escape(r) + r', i128\* (@xmm\d+)\s*$', lines[j])
                if sm:
                    break
                j += 1
            if sm:
                t = uid('m')
                low = (1 << 64) - 1 if mn in ('cvtsi2sd', 'cvtss2sd', 'sqrtsd') else (1 << 32) - 1
                keep = ((1 << 128) - 1) ^ low
                out.append(f'{ind}%{t}.o = load i128, i128* {sm.group(2)}')
                out.append(l)
                out += [lines[k] for k in range(i + 1, j)]
                out.append(f'{ind}%{t}.k = and i128 %{t}.o, {keep}')
                out.append(f'{ind}%{t}.l = and i128 {r}, {low}')
                out.append(f'{ind}%{t}.m = or i128 %{t}.k, %{t}.l')
                out.append(f'{ind}store i128 %{t}.m, i128* {sm.group(2)}')
                rep['merge'] = rep.get('merge', 0) + 1
                i = j + 1
                continue
        # ---- call: stage-0 は戻り番地の push/pop を省くため callee 側の [rsp+8+..] (スタック引数/shadow) が 8B ずれる → 補う
        m = re.match(r'^(\s*)(?:%[\w.\-]+ = )?call i64 @function_[0-9a-f]+\(\)\s*$', l)
        if m and 'callret' not in skip:
            ind, t = m.group(1), uid('r')
            out += [f'{ind}%{t}.s = load i64, i64* @rsp', f'{ind}%{t}.s8 = sub i64 %{t}.s, 8', f'{ind}store i64 %{t}.s8, i64* @rsp',
                    f'{ind}%{t}.p = inttoptr i64 %{t}.s8 to i64*', f'{ind}store i64 0, i64* %{t}.p', l, f'{ind}store i64 %{t}.s, i64* @rsp']
            rep['callret'] = rep.get('callret', 0) + 1
            i += 1
            continue
        if l.strip() == 'ret i64 undef':
            # stage-0 の call は `store i64 <callee 戻り値>, @rax` を後置する → callee は実 rax を返す必要がある (0 を返すと戻り値を潰す)
            t = uid('q')
            out += [f'  %{t} = load i64, i64* @rax', f'  ret i64 %{t}']
            i += 1
            continue
        out.append(l)
        i += 1
    return out


def find_load_ptr(out, old, ty):
    pat = re.compile(r'^\s*' + re.escape(old) + r' = load ' + ty + r', ' + ty + r'\* (%[\w.\-]+)')
    for k in range(len(out) - 1, max(-1, len(out) - 40), -1):
        m = pat.match(out[k])
        if m:
            return m.group(1)
    return None


def rdata_estimate(vas, bodies, rd):
    """[rdataest] rdata_window 自動推定 (KH-4 REPORT §4 設計案の実装, 半自動: 候補列挙+上限推定)。

    機械語から (1) `lea reg,[rip+X]` の表 base 候補を収集し、(2) reg を base に使うメモリ命令の
    到達幅 (disp + index*scale + opsize) を推定する。index の上限は直近の `and idx, imm` /
    `mov reg,imm` + `and` から取れる場合は正確に (例: expf の `and eax,0x3f` ×8 = 512B)。
    命令位置は stage-0 の `; 0xADDR` コメント (実命令境界) を使う (線形 sweep の desync 回避)。
    さらに **call 辺を跨ぐ base 伝播** (UCRT 数学 helper は `lea rcx,[rip+表]` → callee が
    `[rcx+idx*8]` で読む形が多い) を 2 パスで行う: 各関数の call 直前の arg reg (rcx/rdx/r8/r9)
    への base 束縛を記録し、callee の arg-base 読出しに呼び出し元の base VA を種として与える
    (複数呼び出し元は union, 最大 4 ラウンドの不動点)。
    戻り値: ({va: est_bytes}, {va: 'mask'|'static'|'gap'|'arg'|'none'}) — 精密推定が取れない
    base は次参照 VA までの gap (build 側で 8KB 打切り + 64B 余白) に倒す。fuzz 検証が最終担保。
    """
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    X86_LEA, X86_AND, X86_MOV, X86_CALL = capstone.x86.X86_INS_LEA, capstone.x86.X86_INS_AND, capstone.x86.X86_INS_MOV, capstone.x86.X86_INS_CALL
    X86_MOVABS = capstone.x86.X86_INS_MOVABS

    def RG(k):
        return getattr(capstone.x86, 'X86_REG_%s' % k.upper())

    CANON = {'eax': 'rax', 'ebx': 'rbx', 'ecx': 'rcx', 'edx': 'rdx', 'esi': 'rsi', 'edi': 'rdi', 'ebp': 'rbp', 'esp': 'rsp',
             'r8d': 'r8', 'r9d': 'r9', 'r10d': 'r10', 'r11d': 'r11', 'r12d': 'r12', 'r13d': 'r13', 'r14d': 'r14', 'r15d': 'r15'}
    reg_canon = {}
    for n64 in ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15'):
        reg_canon[RG(n64)] = RG(n64)
    for n32, n64 in CANON.items():
        reg_canon[RG(n32)] = RG(n64)

    def canon(reg_id):
        return reg_canon.get(reg_id, reg_id)
    ARG_REGS = (RG('rcx'), RG('rdx'), RG('r8'), RG('r9'))
    vaset = set(vas)

    def scan(v, seed):
        """1 関数走査。戻り値 (reach{va:max}, how{va:kind}, callsites[(addr,target,{reg:baseVA})], arguse{reg:max})"""
        body = '\n'.join(bodies[v])
        addrs = [int(x, 16) for x in re.findall(r'; 0x([0-9a-f]+)', body)]
        reach, how, callsites, arguse = {}, {}, [], {}
        if not addrs:
            return reach, how, callsites, arguse
        base = dict(seed)      # reg id -> set(table VA)
        andmask, movimm = {}, {}
        for a in addrs:
            ins = next(md.disasm(rd(a, 16), a, 1), None)
            if ins is None or ins.address != a:
                continue
            if ins.id == X86_LEA and len(ins.operands) == 2:
                d, s = ins.operands
                if d.type == capstone.x86.X86_OP_REG and s.type == capstone.x86.X86_OP_MEM and s.mem.base == RG('rip'):
                    base[canon(d.reg)] = {ins.address + ins.size + s.mem.disp}
                    andmask.pop(canon(d.reg), None)
                continue
            if ins.id in (X86_MOV, X86_MOVABS) and len(ins.operands) == 2 and ins.operands[0].type == capstone.x86.X86_OP_REG \
                    and ins.operands[1].type == capstone.x86.X86_OP_IMM and 0 < ins.operands[1].imm < (1 << 32):
                movimm[canon(ins.operands[0].reg)] = ins.operands[1].imm
                continue
            if ins.id == X86_AND and len(ins.operands) == 2 and ins.operands[0].type == capstone.x86.X86_OP_REG:
                b, s2 = ins.operands
                cand = [x for x in (andmask.get(canon(b.reg)), movimm.get(canon(b.reg)),
                                    movimm.get(canon(s2.reg)) if s2.type == capstone.x86.X86_OP_REG else None,
                                    s2.imm if s2.type == capstone.x86.X86_OP_IMM else None) if x is not None]
                if cand:
                    andmask[canon(b.reg)] = min(cand)
                continue
            if ins.id == X86_CALL and len(ins.operands) == 1 and ins.operands[0].type == capstone.x86.X86_OP_IMM:
                tgt = ins.operands[0].imm
                bind = {r: frozenset(base[r]) for r in ARG_REGS if base.get(r)}
                callsites.append((a, tgt, bind))
                for r in ARG_REGS:
                    base.pop(r, None)       # callee-saved ではない引数レジスタは call で上書きされる
                    andmask.pop(r, None)
                continue
            if ins.id in (X86_MOV, X86_MOVABS) and len(ins.operands) == 2 and \
                    ins.operands[0].type == capstone.x86.X86_OP_REG and ins.operands[1].type == capstone.x86.X86_OP_REG:
                dreg, sreg = canon(ins.operands[0].reg), canon(ins.operands[1].reg)
                if sreg in base:
                    base[dreg] = base[sreg]
                else:
                    base.pop(dreg, None)
                continue
            for op in ins.operands:
                if op.type != capstone.x86.X86_OP_MEM:
                    continue
                m = op.mem
                if not m.base:
                    continue
                bset = base.get(canon(m.base))
                opsz = max(1, op.size)
                mk = andmask.get(canon(m.index)) if m.index else None
                if bset is None:
                    if canon(m.base) in ARG_REGS and m.index:
                        arguse[canon(m.base)] = max(arguse.get(canon(m.base), 0),
                                                    max(1, m.disp) + (mk if mk is not None else 0) * m.scale + opsz)
                    continue
                kind = ('mask' if (m.index and mk is not None) else ('arg' if canon(m.base) in ARG_REGS else 'static'))
                for va in bset:
                    if m.index and mk is not None:
                        r = max(1, m.disp) + mk * m.scale + opsz
                    else:
                        r = max(1, m.disp) + opsz
                    if r > reach.get(va, 0):
                        reach[va] = r
                    prev = how.get('%x' % va)
                    if prev != 'mask':
                        how['%x' % va] = kind
        return reach, how, callsites, arguse

    # pass 1: 種なし走査 + call 辺収集
    allreach, allhow = {}, {}
    edges = []          # (tgt, bind)
    for v in vas:
        r1, h1, cs, _ = scan(v, {})
        for va, r in r1.items():
            if r > allreach.get(va, 0):
                allreach[va] = r
            allhow.setdefault('%x' % va, h1.get('%x' % va, 'none'))
        for (_, tgt, bind) in cs:
            if tgt in vaset and bind:
                edges.append((tgt, bind))
    # pass 2: arg base 伝播 (不動点, 最大 4 ラウンド)
    seeds = {}
    for tgt, bind in edges:
        s = seeds.setdefault(tgt, {})
        for reg, vs in bind.items():
            s.setdefault(reg, set()).update(vs)
    for _ in range(4):
        changed = False
        for v in vas:
            sd = seeds.get(v) or {}
            if not sd:
                continue
            sd2 = {r: set(x) for r, x in sd.items()}
            r2, h2, _, _ = scan(v, sd2)
            for va, r in r2.items():
                if r > allreach.get(va, 0):
                    allreach[va] = r
                    changed = True
                allhow.setdefault('%x' % va, h2.get('%x' % va, 'none'))
        if not changed:
            break
    return allreach, allhow


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage0')
    ap.add_argument('out')
    ap.add_argument('--core', required=True)
    ap.add_argument('--lift', required=True)
    ap.add_argument('--abi', default='{}')
    ap.add_argument('--skip', default='')
    ap.add_argument('--jt', default='{}', help='{"<jmp insn va hex>": {"table": va, "n": N}}  switch jump table (32bit signed offsets from table base)')
    a = ap.parse_args()
    skip = set(filter(None, a.skip.split(',')))
    abi = json.loads(a.abi)  # {"<va hex>": {"params": ["i64","float",...], "ret": "i64|float|double|void"}}
    vas = [int(x, 16) for x in a.lift.split(',')]
    text = open(a.stage0).read().split('\n')
    # 関数本体抽出
    bodies, cur, name = {}, None, None
    declares = {}
    for l in text:
        m = FN_DEF.match(l)
        if m:
            cur, name = [], int(m.group(1), 16)
            continue
        if cur is not None:
            if l == '}':
                bodies[name] = cur
                cur = None
            else:
                cur.append(l)
            continue
        m = re.match(r'^declare (\S+) @([\w.\-]+)\(([^)]*)\)', l)
        if m:
            declares[m.group(2)] = l
    missing = [hex(v) for v in vas if v not in bodies]
    if missing:
        sys.exit('stage0 に関数が無い: %s' % missing)
    cnt = [0]

    def uid(p):
        cnt[0] += 1
        return 'k%s%d' % (p, cnt[0])
    rep = {}
    jt = {k: {'table': int(v['table'], 16), 'n': v['n']} for k, v in json.loads(a.jt).items()}
    sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), '..', 'scripts'))
    from pe_dis import rd as _rd
    if jt:
        jt['_rd'] = _rd
    # ---- D15 [icall]: stage-0 の空ブロック (call qword [reg+disp] の欠落) を機械語から検出
    icalls = {}
    n_icall = 0
    if 'icall' not in skip:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        for v in vas:
            body = '\n'.join(bodies[v])
            addrs = [int(x, 16) for x in re.findall(r'; 0x([0-9a-f]+)', body)]
            if not addrs:
                continue
            end = max(addrs) + 16
            for ins in md.disasm(_rd(v, end - v), v):
                if ins.address >= end:
                    break
                if ins.mnemonic == 'call' and ins.op_str.startswith('qword ptr ['):
                    o = ins.op_str[len('qword ptr ['):-1]
                    m2 = re.match(r'^(r[a-z0-9]+) \+ (0x[0-9a-f]+|\d+)$', o)
                    if m2:
                        disp = int(m2.group(2), 0)
                        # stage-0 ブロックが空 (pc store のみ) か確認
                        blk = re.search(r'; 0x%x\n(.*?)(?=; 0x|\n\}|$)' % ins.address, body, re.S)
                        seg = [x for x in (blk.group(1) if blk else '').split('\n') if x.strip() and 'store volatile' not in x]
                        if not seg:
                            icalls['%x' % ins.address] = (m2.group(1), disp)
                    else:
                        # rip 相対 form (`call qword [rip+X]`): slot 実値を辿り (jmp [rip] 1 hop まで)、
                        # lift 済関数なら直接 call へ、非対応 (遅延バインド trampoline 等) は fail-fast へ
                        m3 = re.match(r'^rip \+ (0x[0-9a-f]+|\d+)$|^rip \- (0x[0-9a-f]+|\d+)$', o)
                        if m3:
                            d = int(m3.group(1), 0) if m3.group(1) else -int(m3.group(2), 0)
                            slot = ins.address + ins.size + d
                            tgt = int.from_bytes(_rd(slot, 8), 'little')
                            hops = 0
                            while hops < 2 and IMG_LO <= tgt < IMG_HI:
                                ins2 = next(md.disasm(_rd(tgt, 8), tgt), None)
                                if ins2 is not None and ins2.mnemonic == 'jmp' and ins2.op_str.startswith('qword ptr [rip'):
                                    m4 = re.search(r'rip \+ (0x[0-9a-f]+|\d+)', ins2.op_str)
                                    if m4:
                                        s2 = tgt + ins2.size + int(m4.group(1), 0)
                                        tgt = int.from_bytes(_rd(s2, 8), 'little')
                                        hops += 1
                                        continue
                                break
                            blk = re.search(r'; 0x%x\n(.*?)(?=; 0x|\n\}|$)' % ins.address, body, re.S)
                            seg = [x for x in (blk.group(1) if blk else '').split('\n') if x.strip() and 'store volatile' not in x]
                            if not seg:
                                ok = tgt in set(vas)
                                icalls['%x' % ins.address] = ('__rip__', tgt if (ok and IMG_LO <= tgt < IMG_HI) else -slot)
    n_icall = len(icalls)
    # ---- [rdataest]: 表 base + 可変 index の最大読出幅を機械語から推定 (gen_globals への窓幅候補)
    est = {}
    est_how = {}
    if 'rdataest' not in skip:
        from pe_dis import rd as _rd2
        est, est_how = rdata_estimate(vas, bodies, _rd2)
    texts = {v: '\n'.join(vshift_pass(gs_pass(lower_body(bodies[v], jt, skip, uid, rep, icalls), uid, rep), uid, rep)
                          if 'vshift' not in skip else
                          gs_pass(lower_body(bodies[v], jt, skip, uid, rep, icalls), uid, rep)) for v in vas}
    allt = '\n'.join(texts.values())
    # ---- rdata windows
    CAST = re.compile(r'inttoptr \(i64 (\d+) to ([\w*\[\] ]+)\)')
    vaset = set()
    for m in CAST.finditer(allt):
        v = int(m.group(1))
        if IMG_LO <= v < IMG_HI:
            vaset.add(v)
    for m in LIT.finditer(CAST.sub('', allt)):
        v = int(m.group(1))
        if IMG_LO <= v < IMG_HI:
            vaset.add(v)

    def window(txt):
        if 'rdata' in skip:
            return txt
        txt = CAST.sub(lambda m: (f'bitcast (i8* @global_var_{int(m.group(1)):x} to {m.group(2)})' if int(m.group(1)) in vaset else m.group(0)), txt)
        return LIT.sub(lambda m: (f'ptrtoint (i8* @global_var_{int(m.group(1)):x} to i64)' if int(m.group(1)) in vaset else m.group(1)), txt)

    def rename(txt):
        txt = re.sub(r'(@__asm_[A-Za-z0-9_]+)\.(\d+)', r'\1__\2', txt)       # .N overload 名 → C 識別子可能な __N
        for v in vas:
            txt = re.sub(r'@function_%x\(' % v, '@kh_%x(' % v, txt)
        return txt
    texts = {v: rename(window(t)) for v, t in texts.items()}
    allt = '\n'.join(texts.values())
    called = set(int(x, 16) for x in re.findall(r'@function_([0-9a-f]+)\(', allt))
    used = set(re.findall(r'@([a-z0-9_]+)\b', allt))
    regs = []
    for r in REGS_I64:
        if r in used or r in ('rax', 'rcx', 'rdx', 'r8', 'r9', 'rsp') or r in CALLEE_I:
            regs.append(f'@{r} = global i64 0')
    for k in range(32):
        if f'xmm{k}' in used:
            regs.append(f'@xmm{k} = global i128 0')
    for k in list(range(4)) + list(range(6, 16)):
        if f'xmm{k}' not in used:
            regs.append(f'@xmm{k} = global i128 0')
    for f in FLAGS:
        regs.append(f'@{f} = global i1 false')
    regs.append('@rflags = global i64 0')
    final = ['source_filename = "kh_lower"', 'target datalayout = "e-m:e-p:64:64-i64:64-f80:128-n8:16:32:64-S128"', '']
    final += regs
    final.append('@kh_stack = external global i8')
    if rep.get('gs'):
        final.append('@kh_gs = global [4096 x i8] zeroinitializer, align 16')
    for v in sorted(vaset):
        final.append(f'@global_var_{v:x} = external global i8')
    final.append('declare void @llvm.trap()')
    if n_icall:
        final.append('declare i64 @kh_icall(i64)')
        final.append('declare i64 @kh_icfail()')
    final.append('')
    hused = set(re.findall(r'@(__asm_[\w.]+)\(', allt)) | set(re.findall(r'@(llvm\.[\w.]+)\(', allt))
    # named import (Win32/CRT, 引数なし宣言 = レジスタグローバル ABI): body 内で使う関数の declare を出す (function_/kh_ は除く)
    body_names = set(re.findall(r'@([A-Za-z][\w]*)\(', allt)) - {x for x in re.findall(r'@function_([0-9a-f]+)\(', allt)} - set()
    for n in sorted(body_names):
        if re.match(r'(llvm|kh|global_var)', n) or n.startswith('function_'):
            continue
        hused.add(n)
    dec2 = {re.sub(r'(__asm_[A-Za-z0-9_]+)\.(\d+)', r'\1__\2', k): re.sub(r'(@__asm_[A-Za-z0-9_]+)\.(\d+)', r'\1__\2', v) for k, v in declares.items()}
    for h in sorted(hused):
        final.append(dec2.get(h, f'declare i64 @{h}()'))
    for c in sorted(called - set(vas)):
        final.append(f'declare i64 @function_{c:x}()')
    final.append('')
    for v in vas:
        final.append(f'define i64 @kh_{v:x}() {{')
        final.append(texts[v])
        final.append('}')
        final.append('')
    # ---- wrapper
    for v in vas:
        sg = abi.get('%x' % v, {'params': ['i64', 'i64', 'i64', 'i64'], 'ret': 'i64'})
        ps = ', '.join('%s %%p%d' % (t, k) for k, t in enumerate(sg['params']))
        w = [f'define {("i64" if sg["ret"] == "i64" else sg["ret"])} @function_{v:x}({ps}) {{', 'entry:']
        iregs = ['rcx', 'rdx', 'r8', 'r9']
        for k, t in enumerate(sg['params']):
            if t == 'i64':
                w.append(f'  store i64 %p{k}, i64* @{iregs[k]}')
            elif t == 'i32':
                w.append(f'  %p{k}.z = zext i32 %p{k} to i64\n  store i64 %p{k}.z, i64* @{iregs[k]}')
            elif t == 'float':
                w += [f'  %p{k}.b = bitcast float %p{k} to i32', f'  %p{k}.z = zext i32 %p{k}.b to i128', f'  store i128 %p{k}.z, i128* @xmm{k}']
            elif t == 'double':
                w += [f'  %p{k}.b = bitcast double %p{k} to i64', f'  %p{k}.z = zext i64 %p{k}.b to i128', f'  store i128 %p{k}.z, i128* @xmm{k}']
        w += ['  %sp = ptrtoint i8* @kh_stack to i64', f'  %sp1 = add i64 %sp, {STACK - 0x48}', '  store i64 %sp1, i64* @rsp']
        if 'abicheck' not in skip:
            for k, r in enumerate(CALLEE_I):                   # 毒入れ: 上位ビット非自明な定数で callee-saved を汚してから呼ぶ
                w.append(f'  store i64 {(0x8123456789abcdef + k * 0x11111) - (1 << 64)}, i64* @{r}')
                w.append(f'  %pre.{r} = load i64, i64* @{r}')
            for k, r in enumerate(CALLEE_X):
                w.append(f'  store i128 {(0x0fedcba987654321 << 64 | 0x8123456789abcdef) + k * 0x1011}, i128* @{r}')
                w.append(f'  %pre.{r} = load i128, i128* @{r}')
        w.append(f'  %r = call i64 @kh_{v:x}()')
        if 'abicheck' not in skip:
            # callee-saved レジスタ (rbx rbp rsi rdi r12-15 xmm6-15) が関数前後で不変であること = ABI 契約の検査。
            # xmm6-15 の spill/restore が壊れる欠陥 (mov128) は出力バッファに現れないため、この検査でのみ検出できる。
            bad = []
            for r in CALLEE_I:
                w += [f'  %post.{r} = load i64, i64* @{r}', f'  %ne.{r} = icmp ne i64 %pre.{r}, %post.{r}']
                bad.append(f'%ne.{r}')
            for r in CALLEE_X:
                w += [f'  %post.{r} = load i128, i128* @{r}', f'  %ne.{r} = icmp ne i128 %pre.{r}, %post.{r}']
                bad.append(f'%ne.{r}')
            acc = bad[0]
            for k, b in enumerate(bad[1:]):
                w.append(f'  %or{k} = or i1 {acc}, {b}')
                acc = f'%or{k}'
            w += [f'  br i1 {acc}, label %abi_bad, label %abi_ok', 'abi_bad:', '  call void @llvm.trap()', '  unreachable', 'abi_ok:']
        if sg['ret'] == 'i64':
            w += ['  %ax = load i64, i64* @rax', '  ret i64 %ax']
        elif sg['ret'] == 'i32':
            w += ['  %ax = load i64, i64* @rax', '  %ax32 = trunc i64 %ax to i32', '  ret i32 %ax32']
        elif sg['ret'] == 'float':
            w += ['  %x0 = load i128, i128* @xmm0', '  %t = trunc i128 %x0 to i32', '  %f = bitcast i32 %t to float', '  ret float %f']
        elif sg['ret'] == 'double':
            w += ['  %x0 = load i128, i128* @xmm0', '  %t = trunc i128 %x0 to i64', '  %f = bitcast i64 %t to double', '  ret double %f']
        else:
            w += ['  ret void']
        w += ['}', '']
        final += w
    open(a.out, 'w').write('\n'.join(final) + '\n')
    # 窓幅 = max(精密推定 (static disp / and mask), gap 下限 = 次参照 VA までの距離 + 64B 余白を 8KB で打切り)。
    # gap 下限の根拠: UCRT の定数プールは同一テーブル群を連続配置し、D11 (64B→不足) / D14 (164B) /
    # powf (8192B) の 3 実例がいずれも「base から 8KB 以内」に収まる (KH-4 REPORT §4)。
    # +64B は「次参照 VA が同一テーブル領域内の別 base」のケース (0x18228ac50 の 2/π 表 = 実測 +164B) を
    # 読出幅込みで被覆するための余白。過大側のコストは wasm サイズのみ、過小は O(1) 差分 (silent) という
    # 非対称性より過大側に倒す。
    vs = sorted(vaset)
    est2 = {}
    for v, r in est.items():
        nxt = next((x for x in vs if x > v), 0)
        gap = min(nxt - v + 64, 8192) if nxt else 0
        # 上限 8192: ImageBase 相対の D10 型 (lea base, [base+idx*2+0x227ffc0]) で reach が 68MB 級に
        # 爆発する実測がある (limiter/KH-6)。8192 は powf 実績窓 = 検証済み最大 (それ超は dint/fint shim 経路)。
        est2['%x' % v] = min(max(r, gap), 8192)
    json.dump({'lowered': rep, 'rdata_windows': ['%x' % v for v in sorted(vaset)], 'rdata_window_map': est2,
               'unlifted_callees': ['%x' % c for c in sorted(called - set(vas))],
               'icall_sites': sorted(icalls)},
              open(a.out + '.json', 'w'), indent=1)
    # ---- kh_icall (D15 [icall]): アリーナ内 vtable の実値 → 既知 callee へ dispatch。
    #      PE .rdata の vtable slot (slot addr → 中身が lift 対訳関数) も build 時に静的解決する。
    icall_c = None
    if n_icall:
        import numpy as np
        import pefile
        pe = pefile.PE(a.core, fast_load=True)
        data = open(a.core, 'rb').read()
        base = pe.OPTIONAL_HEADER.ImageBase
        rsect = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.rdata'][0]
        rva0, rsz = rsect.VirtualAddress, rsect.Misc_VirtualSize
        nbytes = min(rsz, rsect.SizeOfRawData) - (min(rsz, rsect.SizeOfRawData) % 8)
        arr = np.frombuffer(data[rsect.PointerToRawData:rsect.PointerToRawData + nbytes], dtype='<u8')
        vs = np.array(sorted(vas), dtype='<u8')
        idx = np.searchsorted(vs, arr)
        idx[idx >= len(vs)] = 0
        hit = (arr == vs[idx])
        slots = {}
        for k in np.nonzero(hit)[0]:
            slots[base + rva0 + int(k) * 8] = int(vs[idx[k]])
        icall_c = ['#include <emscripten.h>', '#include <stdint.h>', '#include <stdlib.h>', 'typedef uint64_t u64;']
        icall_c += ['u64 kh_%x(void);' % v for v in sorted(vas)]
        icall_c.append('EMSCRIPTEN_KEEPALIVE unsigned long long kh_icall(unsigned long long slot) {')
        icall_c.append('  if (slot < 0x10000000ULL) { unsigned long long t = *(unsigned long long*)(unsigned int)slot; switch (t) {')
        for v in sorted(vas):
            icall_c.append('    case 0x%xULL: return kh_%x();' % (v, v))
        icall_c.append('    default: __builtin_trap(); return 0; } }')
        icall_c.append('  switch (slot) {')
        for s, t in sorted(slots.items()):
            icall_c.append('    case 0x%xULL: return kh_%x();   /* .rdata vtable slot */' % (s, t))
        icall_c.append('    default: __builtin_trap(); return 0; }')
        icall_c.append('}')
        icall_c.append('EMSCRIPTEN_KEEPALIVE unsigned long long kh_icfail(void) { abort(); return 0; }')
        open(a.out + '.icall.c', 'w').write('\n'.join(icall_c) + '\n')
    print('[kh_lower]', json.dumps(rep), 'rdata windows', len(vaset), 'est', json.dumps(est2), 'unlifted callees', ['%x' % c for c in sorted(called - set(vas))],
          'icall sites', n_icall, ('icall slot map %d' % len(slots)) if icall_c else '')


if __name__ == '__main__':
    main()
