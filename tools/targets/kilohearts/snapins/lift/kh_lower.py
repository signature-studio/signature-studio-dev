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


def lower_body(lines, cfg, skip, uid, rep):
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
    if jt:
        sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), '..', 'scripts'))
        from pe_dis import rd as _rd
        jt['_rd'] = _rd
    texts = {v: '\n'.join(lower_body(bodies[v], jt, skip, uid, rep)) for v in vas}
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
    for v in sorted(vaset):
        final.append(f'@global_var_{v:x} = external global i8')
    final.append('declare void @llvm.trap()')
    final.append('')
    hused = set(re.findall(r'@(__asm_[\w.]+)\(', allt)) | set(re.findall(r'@(llvm\.[\w.]+)\(', allt))
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
        elif sg['ret'] == 'float':
            w += ['  %x0 = load i128, i128* @xmm0', '  %t = trunc i128 %x0 to i32', '  %f = bitcast i32 %t to float', '  ret float %f']
        elif sg['ret'] == 'double':
            w += ['  %x0 = load i128, i128* @xmm0', '  %t = trunc i128 %x0 to i64', '  %f = bitcast i64 %t to double', '  ret double %f']
        else:
            w += ['  ret void']
        w += ['}', '']
        final += w
    open(a.out, 'w').write('\n'.join(final) + '\n')
    json.dump({'lowered': rep, 'rdata_windows': ['%x' % v for v in sorted(vaset)], 'unlifted_callees': ['%x' % c for c in sorted(called - set(vas))]},
              open(a.out + '.json', 'w'), indent=1)
    print('[kh_lower]', json.dumps(rep), 'rdata windows', len(vaset), 'unlifted callees', ['%x' % c for c in sorted(called - set(vas))])


if __name__ == '__main__':
    main()
