#!/usr/bin/env python3
"""k80_argfix.py — kernel lift IR の ARG (引数接続) 修復 pass (P0c-2「ARG pass 再適用」)。

  python3 k80_argfix.py IN.ll OUT.ll --abi k80abi.json [--report r.json]

RetDec が落とす引数を機械語 ABI 走査 (k80abi.py: win64 slot の read-before-write) と
突き合わせて再接続する。対象 pattern (m7 ir7/ir8 の F2 系欠陥修復の kernel 版):

  [A] movd-from-zero: `%Z = xor i128 0, 0` が `call iN @__asm_movX*(i128 %Z)` にのみ
      使われる (xmm 読込疑似 call に入力が繋がっていない; 0x5de620/0x5de660/
      0x5dffc0/0x5dfff0/0x5dfa40)。
      → 機械語の xmm slot (読み出し順) を新引数 (i64 = f32 bits) として追加し
        %Z = zext (trunc param) to i128 へ置換 (helper 構造は保持)。

  [B] spill 初期化落ち:
      B1: `alloca T` が load されるが、**どの store もその load を支配しない**
          (0x5de3e0 の xmm0 spill)
      B2: reg2mem (%rcx.0.reg2mem 等) に entry block の store が無い
          (loop 退避の初期値 = 引数が落ちた; 0x5e03f0 / 0x5e0350)
      → alloca 名がレジスタ名を含む場合はその slot、float/double は機械語の
        未割当 xmm slot に対応する引数を追加し entry block 先頭で store する。
      **CAB-253 修正**: 条件は「entry block に store が無い」ではなく「どの store も
      その load を支配しない」(CFG dom 判定)。0x5de710/0x5df610 は
      %rdx.0.reg2mem を loop preheader (5de73e) で初期化していたため、旧条件では
      false positive → `%in.rdx` 重複追加 → k80_diff の irmap がずれ
      arg2 (dst ポインタ) に r8 の値が入り SIGSEGV していた。

  [C] helper 被演算子の xmm slot 接続 (CAB-253・機械語主導の 2 段対話):
      `%Z = xor i128 0, 0` (RetDec が落とした xmm レジスタ値の placeholder) が
      `@__asm_mulss(i128 a, i128 %Z)` 等の**被演算子**に使われる場合。[A] は
      `__asm_movX*` 専用だったため、mulss/addss 等の第 2 オペランドに落ちる
      placeholder は未接続のままだった (0x5e05b0: `mulss xmm0, xmm3` の xmm3 引数)。
      → k80abi.json の `xmm_insns` (機械語の operand 位置 → レジスタ名) と IR の
        helper call を出現順で突合し、そのレジスタが機械語の read-before-write xmm
        slot (= 引数) なら `%in.xmmN.bits` を追加して zext で接続する。placeholder が
        複数 use を持つ場合は全 use が同一 slot を指すときだけ接続する。

  [D] ucomiss/comiss の flags (0x5e12b0): `or i1 %CF, %ZF` の placeholder を、被演算子の比較
      `fcmp ult` (CF) / `fcmp ueq` (ZF) に接続する (被演算子が接続済みの場合のみ)。
      [C] は戻り値の無い `call void @__asm_ucomiss` も被演算子の接続先にする。

  引数は既存 RetDec 引数の **末尾に追記** (既存参照を壊さない; m7 ir7 と同じ規約)。
  適用後は llvm-as 通過を推奨 (idempotent: 追加済みの store/引数は再適用しない)。
"""
import argparse
import json
import os
import re

SLOT_GPR = ['rcx', 'rdx', 'r8', 'r9']
SLOT_XMM = ['xmm0', 'xmm1', 'xmm2', 'xmm3']
SKIP_SPILLFIX = os.environ.get('K80_NO_SPILLFIX') == '1'
SKIP_VOIDHELPER = os.environ.get('K80_NO_VOIDHELPER') == '1'
SKIP_UCOMI_FLAGS = os.environ.get('K80_NO_UCOMI_FLAGS') == '1'


def func_name(header):
    m = re.search(r'@([\w.$-]+)\(', header)
    return m.group(1) if m else None


def append_param(header, decl):
    """define の引数リスト末尾へ decl (例: 'i64 %in.rcx') を追記。"""
    if decl in header:
        return header
    m = re.search(r'\(([^)]*)\)(\s*(?:local_unnamed_addr|#\d+)?\s*\{)\s*$', header)
    if not m:
        return header
    args = m.group(1).strip()
    newargs = (args + ', ' if args else '') + decl
    return header[:m.start()] + '(' + newargs + ')' + m.group(2) + '\n'


def entry_insert(body, stmts):
    """entry block に stmts を挿入 (既存なら何もしない)。
    alloca はブロック先頭に集める規約に従い, entry 内の最後の alloca 行の後に挿入する。"""
    for s in stmts:
        if s.strip() in body:
            return body
    lines = body.split('\n')
    idx = 0
    for i, ln in enumerate(lines):
        if re.match(r'^[\w.$-]+:\s*(;.*)?$', ln):
            idx = i + 1
            break
    # entry 内の最後の alloca の直後に置く (use-before-def 防止)
    j = idx
    for k in range(idx, len(lines)):
        if re.match(r'\s*[\w.$-]+:\s*(;.*)?$', lines[k]) or re.match(r'\s*(br|switch|ret|call)\b', lines[k]):
            break
        if re.match(r'\s*%[\w.$-]+ = alloca\b', lines[k]):
            j = k + 1
    lines[j:j] = stmts
    return '\n'.join(lines)


def entry_block_lines(lines):
    """最初の br/switch まで (entry block) の行。"""
    out = []
    for ln in lines:
        out.append(ln)
        if re.match(r'\s*br\s', ln) or re.match(r'\s*switch\s', ln):
            break
    return out


# ---------------------------------------------------------------------------
# CFG ユーティリティ (CAB-253: B2 の dom 判定用)
# ---------------------------------------------------------------------------
def parse_blocks(body):
    """body を basic block に分割 → [(label, [lines])] (entry が先頭)。"""
    lines = body.split('\n')
    starts = [i for i, ln in enumerate(lines) if re.match(r'^[\w.$-]+:\s*(;.*)?$', ln)]
    blocks = []
    for k, i in enumerate(starts):
        j = starts[k + 1] if k + 1 < len(starts) else len(lines)
        label = lines[i].split(':')[0].strip()
        blocks.append((label, lines[i:j]))
    return blocks


def block_succs(blines):
    """terminator (br/switch) から後続 block label を抽出 ('%' は除く)。"""
    succs = []
    for ln in blines:
        s = ln.strip()
        if s.startswith('br ') or s.startswith('switch'):
            for m in re.finditer(r'label (%?[\w.$-]+)', s):
                succs.append(m.group(1).lstrip('%'))
            break
    return succs


def compute_idom(blocks):
    """Cooper-Harvey-Kennedy の immediate dominator 計算。→ {label: idom or None}"""
    order = [b[0] for b in blocks]
    succs = {b[0]: [s for s in block_succs(b[1]) if s in set(order)] for b in blocks}
    entry = order[0]
    preds = {l: [] for l in order}
    for l in order:
        for s in succs.get(l, []):
            preds[s].append(l)
    idom = {l: None for l in order}
    idom[entry] = entry
    changed = True
    while changed:
        changed = False
        for l in order:
            if l == entry:
                continue
            newid = None
            for p in preds[l]:
                if idom[p] is None:
                    continue
                if newid is None:
                    newid = p
                else:
                    a, b = p, newid
                    guard = 0
                    while a != b and guard < 10000:
                        guard += 1
                        while a != b and order.index(a) > order.index(b):
                            a = idom[a] if idom[a] is not None else a
                            if guard > 5000:
                                break
                        while a != b and order.index(b) > order.index(a):
                            b = idom[b] if idom[b] is not None else b
                            if guard > 5000:
                                break
                    newid = a
            if idom[l] != newid:
                idom[l] = newid
                changed = True
    return idom


def dominates(idom, a, b):
    """a が b を支配するか (b が未 reach なら False)。"""
    while b is not None:
        if b == a:
            return True
        b = idom.get(b)
    return False


def store_dominates_loads(body, aname):
    """alloca の全 load が「必ず初期化済み」か (definitely-assigned 解析)。

    False = どこかの load は未初期化 (ARG pass の B1/B2 修復対象)。
    単純な dom 判定では loop 先头の load (最初の iteration) を見落とすため、
    forward must 解析 (IN/OUT の積集合) で「entry から全パスで store を通過したか」を見る。
    """
    blocks = parse_blocks(body)
    if not blocks:
        return False
    order = [b[0] for b in blocks]
    succs = {b[0]: [s for s in block_succs(b[1]) if s in set(order)] for b in blocks}
    entry = order[0]
    preds = {l: [] for l in order}
    for l in order:
        for s in succs.get(l, []):
            preds[s].append(l)
    esc = re.escape(aname)
    store_re = re.compile(r'\bstore\b[^,]+,\s*(?:ptr|[\w]+\*)\s*' + esc + r'\s*(?:,|$)')
    load_re = re.compile(r'=\s*load\s+[\w]+,\s*(?:ptr|[\w]+\*)\s*' + esc + r'\s*(?:,|$)')
    # 各 block 内で store より前に出る load があるか (未初期化アクセス)
    uncovered_early = {}
    has_store = {}
    for lab, ls in blocks:
        hs = False
        early = False
        for l in ls:
            if store_re.search(l):
                hs = True
            elif load_re.search(l) and not hs:
                early = True
        has_store[lab] = hs
        uncovered_early[lab] = early
    # IN[B] = AND of OUT[pred]; OUT[B] = IN[B] or has_store[B]
    IN = {l: False for l in order}                     # entry には外部 store は無い
    changed = True
    while changed:
        changed = False
        for l in order:
            if l == entry:
                out = has_store[entry]
                continue
            ps = [p for p in preds[l]]
            if ps:
                inn = all((has_store[p] or IN[p]) for p in ps)
            else:
                inn = False                              # 未 reach block
            out = inn or has_store[l]
            if inn != IN[l]:
                IN[l] = inn
                changed = True
    # 判定: どの load も「IN 又は同 block 内の先行 store」でカバーされるか
    for lab, ls in blocks:
        if uncovered_early[lab] and not IN[lab]:
            return False
    if not any(load_re.search(l) for _, ls in blocks for l in ls):
        return True                                     # load がなければ初期化不要
    return True


def fix_movd_from_zero(header, body, habi, rep, fname):
    """[A] xor i128 0,0 → __asm_movX のみ使用 → xmm slot 引数を追加。"""
    changed = False
    for _round in range(8):
        lines = body.split('\n')
        defs = []
        for ln in lines:
            m = re.match(r'^(\s*)(%[\w.$-]+) = xor i128 0, 0\s*$', ln)
            if m:
                defs.append((m.group(1), m.group(2), ln))
        if not defs:
            break
        fixed_any = False
        for ind, z, dline in defs:
            esc = re.escape(z)
            uses = [l for l in lines if re.search(r'(?<![\w.%-])' + esc + r'(?![\w.-])', l) and l != dline]
            if not uses:
                continue
            calls = [l for l in uses if re.search(r'call (?:i32|i64) @__asm_mov\w*\(i128 ' + esc + r'\)', l)
                     or (not SKIP_SPILLFIX
                         and re.search(r'call i128 @__asm_movaps\(i128 ' + esc + r'\)', l))]
            if len(calls) != len(uses):
                continue
            # movdqa [rsp/rbp+N], xmmK は非 volatile xmm6-15 の callee-save spill で引数ではない
            # (0x5df610: spill の placeholder に xmm3 を割り当て、実際に xmm3 を読む
            # `movss xmm7, xmm3` の placeholder が未接続のままだった)。
            if not SKIP_SPILLFIX and all('@__asm_movdqa(' in l for l in calls):
                continue
            site = rep['movd_sites'].get(fname, 0)
            xs = [x for x in habi.get('xmm_slots', []) if int(x[3:]) < 4]
            xmm = xs[site] if site < len(xs) else SLOT_XMM[min(site, 3)]
            rep['movd_sites'][fname] = site + 1
            pname = '%%in.%s.bits' % xmm
            helper = re.search(r'@(__asm_mov\w*)', calls[0]).group(1)
            if 'movd' in helper or (helper == '__asm_movaps' and habi.get('xmm_width', {}).get(xmm, 32) == 32):
                stmts = ['  %%trunc.%s = trunc i64 %s to i32' % (pname[1:], pname),
                         '  %s = zext i32 %%trunc.%s to i128' % (z, pname[1:])]
            else:                                          # movq 等は 64bit
                stmts = ['  %s = zext i64 %s to i128' % (z, pname)]
            body = body.replace(dline, '\n'.join(stmts))
            header = append_param(header, 'i64 %s' % pname)
            rep['movd_fixed'] += 1
            changed = True
            fixed_any = True
        if not fixed_any:
            break
    return header, body, changed


def helper_xmm_sites(habi):
    """k80abi.json の xmm_insns → {(mnemonic, #xmm reg operand): [regmap, ...]}。

    regmap = {operand position in the machine insn: xmmN}。IR の helper call は
    (mnemonic, 非即値オペランド数) でこの表を引き, 出現順で 1 つずつ突合する
    (CAB-253 の 2 段対話)。即値 (i8 0 等) はオペランド数に数えない。
    """
    out = {}
    for m, regops in habi.get('xmm_insns', []):
        d = {}
        for oi, reg in regops:
            if reg and reg.startswith('xmm'):
                d[oi] = reg
        if not d:
            continue
        out.setdefault((m, len(d)), []).append(d)
    return out


def fix_helper_operand_xmm(header, body, habi, rep, fname):
    """[C] helper 被演算子の placeholder (xor i128 0,0) を機械語の xmm 引数 slot に接続。"""
    sites = helper_xmm_sites(habi)
    if not sites:
        return header, body, False
    argslots = set(x for x in habi.get('xmm_slots', []) if int(x[3:]) < 4)
    if not argslots:
        return header, body, False
    xw = habi.get('xmm_width', {})
    changed = False
    for _round in range(8):
        lines = body.split('\n')
        defs = []
        for ln in lines:
            m = re.match(r'^(\s*)(%[\w.$-]+) = xor i128 0, 0\s*$', ln)
            if m:
                defs.append((m.group(1), m.group(2), ln))
        if not defs:
            break
        fixed_any = False
        for ind, z, dline in defs:
            esc = re.escape(z)
            uses = [l for l in lines if re.search(r'(?<![\w.%-])' + esc + r'(?![\w.-])', l) and l != dline]
            if not uses:
                continue
            helper_uses = []
            for l in uses:
                # 戻り値の無い helper (`call void @__asm_ucomiss(...)`) も被演算子の接続先 (0x5e12b0)
                hm = re.search(r'(?:=\s*)?call\s+\w+\s+@(__asm_\w+)\(', l)
                if not hm or (SKIP_VOIDHELPER and '= call' not in l and 'call void' in l):
                    helper_uses = None
                    break
                helper_uses.append((l, hm.group(1)))
            if not helper_uses:
                continue
            # 全 use が単一オペランドの __asm_mov* なら [A] の対象 (ここでは触らない)
            if helper_uses and all(h.startswith('__asm_mov')
                                   and len(l.split('(', 1)[1].split(',')) == 1
                                   for l, h in helper_uses):
                continue
            slots = set()
            ptr = {}
            ok = True
            for l, hname in helper_uses:
                # helper 名の __N サフィックスは「同名の別 signature」なのでニーモニックには
                # 残さない (movss__2 → movss)。突合キーは (mnemonic, 非即値オペランド数)。
                mn = hname[len('__asm_'):].split('__')[0]
                am = re.search(r'@' + re.escape(hname) + r'\(([^)]*)\)', l)
                if not am:
                    ok = False
                    break
                ops = [x.strip() for x in am.group(1).split(',') if x.strip()]
                nimm = sum(1 for x in ops if re.match(r'^i\d+ -?\d+$', x))
                key = (mn, len(ops) - nimm)
                k = ptr.get(key, 0)
                cand = sites.get(key, [])
                if k >= len(cand):
                    cand = []
                    regmap = {}
                else:
                    regmap = cand[k]
                ptr[key] = k + 1
                # IR の i128 オペランド (順) ↔ 機械語の xmm reg オペランド (順)
                i128pos = [i for i, x in enumerate(ops) if x.startswith('i128 %')]
                site_ok = True
                for oi, op in enumerate(ops):
                    if op.split()[-1] != z:
                        continue
                    j = i128pos.index(oi) if oi in i128pos else None
                    reg = regmap.get(j) if j is not None else None
                    if reg is None or reg not in argslots:
                        site_ok = False
                        break
                    slots.add(reg)
                if not site_ok and os.environ.get('K80_NO_REGSRC') != '1':
                    # reg-reg 形の単項変換 (cvtss2sd xmm0, xmm3 → __asm_cvtss2sd(i128 xmm3)):
                    # RetDec は dest を被演算子に含めないので、機械語の xmm 数が 1 多い (#277)。
                    # 手前の突合で mem 形 (cvtss2sd xmm1, [m]) を誤って引いた分を戻し、
                    # xmm reg が 2 個の site の source (位置 1) を探す
                    ptr[key] = k
                    alt = sites.get((mn, len(ops) - nimm + 1), [])
                    kk = ptr.get((mn, 'rr'), 0)
                    alt = [d for d in alt if 1 in d]
                    site_ok = False
                    if kk < len(alt) and len(i128pos) == 1 and ops[i128pos[0]].split()[-1] == z:
                        reg = alt[kk].get(1)
                        if reg in argslots:
                            slots.add(reg)
                            ptr[(mn, 'rr')] = kk + 1
                            site_ok = True
                if not site_ok:
                    ok = False
                    break
            if (not ok or len(slots) != 1) and os.environ.get('K80_NO_INTERSECT') != '1':
                # fallback (#277): 出現順の突合が破綻する placeholder (0x5e1210: xmm3 が movss と
                # cvtss2sd の両方に使われ、順序対応が合わない)。各 use が取り得る xmm 引数 slot の
                # 集合 (同ニーモニックの全 site の reg) の積が 1 つに決まるときだけ接続する
                inter = None
                for l, hname in helper_uses:
                    mn = hname[len('__asm_'):].split('__')[0]
                    am = re.search(r'@' + re.escape(hname) + r'\(([^)]*)\)', l)
                    ops = [x.strip() for x in am.group(1).split(',') if x.strip()] if am else []
                    n = len(ops) - sum(1 for x in ops if re.match(r'^i\d+ -?\d+$', x))
                    regs = set()
                    for nn in (n, n + 1):
                        for d in sites.get((mn, nn), []):
                            regs.update(d.values())
                    regs &= argslots
                    inter = regs if inter is None else (inter & regs)
                if inter is not None and len(inter) == 1:
                    slots, ok = set(inter), True
            if not ok or len(slots) != 1:
                continue
            xmm = slots.pop()
            pname = '%%in.%s.bits' % xmm
            if ('i64 %s' % pname) in header:
                continue                                # 接続済み (idempotent)
            w = xw.get(xmm, 32)
            if w == 64:
                stmts = ['  %s = zext i64 %s to i128' % (z, pname)]
            else:
                stmts = ['  %%trunc.%s = trunc i64 %s to i32' % (pname[1:], pname),
                         '  %s = zext i32 %%trunc.%s to i128' % (z, pname[1:])]
            body = body.replace(dline, '\n'.join(stmts))
            header = append_param(header, 'i64 %s' % pname)
            rep['helper_xmm_fixed'] += 1
            changed = True
            fixed_any = True
        if not fixed_any:
            break
    return header, body, changed


RE_UCOMI = re.compile(r'^(\s*)call void @__asm_(u?comis[sd])(?:__\d+)?\(i128 (%[\w.$-]+), i128 (%[\w.$-]+)\)\s*$')
RE_FLAG_OR = re.compile(r'^(\s*)(%[\w.$-]+) = or i1 (%[\w.$-]+), (%[\w.$-]+)\s*$')
RE_LABEL = re.compile(r'^[\w.$-]+:')


def _ucomi_one(lines):
    zdef = {}
    for k, ln in enumerate(lines):
        m = re.match(r'^\s*(%[\w.$-]+) = xor i(?:128|1) 0, 0\s*$', ln)
        if m:
            zdef[m.group(1)] = (k, 'xor i1' in ln)
    for k, ln in enumerate(lines):
        m = RE_UCOMI.match(ln)
        if not m:
            continue
        ind, mn, A, B = m.group(1), m.group(2), m.group(3), m.group(4)
        if A in zdef or B in zdef:
            continue
        j = None
        for t in range(k + 1, len(lines)):
            if RE_LABEL.match(lines[t]):
                break
            if RE_FLAG_OR.match(lines[t]):
                j = t
                break
        if j is None:
            continue
        fm = RE_FLAG_OR.match(lines[j])
        f1, f2 = fm.group(3), fm.group(4)
        if f1 not in zdef or f2 not in zdef or not (zdef[f1][1] and zdef[f2][1]):
            continue
        ok = True
        for f in (f1, f2):
            uses = [l for l in lines if re.search(r'(?<![\w.%-])' + re.escape(f) + r'(?![\w.-])', l)
                    and not re.match(r'^\s*' + re.escape(f) + r' = ', l)]
            if uses != [lines[j]]:
                ok = False
        if not ok:
            continue
        ity, fty = ('i32', 'float') if mn.endswith('ss') else ('i64', 'double')
        tag = 'ucf.%d' % k
        new = ['%s%%%s.a = trunc i128 %s to %s' % (ind, tag, A, ity),
               '%s%%%s.af = bitcast %s %%%s.a to %s' % (ind, tag, ity, tag, fty),
               '%s%%%s.b = trunc i128 %s to %s' % (ind, tag, B, ity),
               '%s%%%s.bf = bitcast %s %%%s.b to %s' % (ind, tag, ity, tag, fty),
               '%s%%%s.cf = fcmp ult %s %%%s.af, %%%s.bf' % (ind, tag, fty, tag, tag),
               '%s%%%s.zf = fcmp ueq %s %%%s.af, %%%s.bf' % (ind, tag, fty, tag, tag)]
        lines[j] = '%s%s = or i1 %%%s.cf, %%%s.zf' % (fm.group(1), fm.group(2), tag, tag)
        lines[k + 1:k + 1] = new
        return lines, f1, f2
    return None


def fix_ucomi_flags(header, body, rep, fname):
    """[D] ucomiss/comiss の flags 接続 (0x5e12b0)。RetDec は flags を `xor i1 0,0` に落とす。

    jbe/ja の判定は CF|ZF。ucomiss a,b の flags は CF = (a<b または非順序)、ZF = (a==b または非順序)
    なので、`or i1 %CF, %ZF` の 2 placeholder を `fcmp ult` / `fcmp ueq` に接続する。
    被演算子が未接続 (xor i128 0,0) のときと、placeholder が or 以外で使われるときは触らない (fail-closed)。
    """
    if SKIP_UCOMI_FLAGS:
        return header, body, False
    lines = body.split('\n')
    changed = False
    for _ in range(16):
        res = _ucomi_one(lines)
        if res is None:
            break
        lines = res[0]
        rep['ucomi_flags_fixed'] = rep.get('ucomi_flags_fixed', 0) + 1
        changed = True
    return header, '\n'.join(lines), changed


RE_STRUCT_COPY = re.compile(
    r'^  %(?P<i1>\w+) = xor i1 0, 0\n'
    r'  %(?P<ph>\w+) = xor i64 0, 0\n'
    r'  (?P<sv>%stack_var_[\w.-]+) = alloca i64, align 8\n'
    r'  %(?P<pti>\w+) = ptrtoint ptr (?P=sv) to i64\n'
    r'  store i64 (?P<sarg>%\w+), ptr (?P=sv), align 8\n'
    r'  %(?P<sel>\w+) = select i1 %(?P=i1), i64 -8, i64 8\n'
    r'  %(?P<fa>\w+) = add i64 %(?P=sel), %(?P=pti)\n'
    r'  %(?P<sa>\w+) = add i64 %(?P=sel), (?P=sarg)\n'
    r'  %(?P<sp>\w+) = inttoptr i64 %(?P=sa) to ptr\n'
    r'  %(?P<ld>\w+) = load i64, ptr %(?P=sp), align 8\n'
    r'  %(?P<fp>\w+) = inttoptr i64 %(?P=fa) to ptr\n'
    r'  store i64 %(?P=ld), ptr %(?P=fp), align 8\n', re.M)


SKIP_STRUCT_D = os.environ.get('K80_NO_STRUCTD') == '1'


def fix_struct_copy(header, body, habi, rep, fname):
    """[D] movsq ×2 の 16B record コピー (二重 deref の input) の修復。

    RetDec は `mov rsi, rdx; movsq; movsq` (ポインタ 2 個の record を frame にコピー)
    を「frame 先頭にポインタ値自体を store + select で 8/-8 の片方だけ load/store」
    という形に落とす。この結果 frame の第 1 qword はレコードの第 1 ポインタではなく
    ポインタ値自体になり、第 2 ポインタは placeholder (xor i64 0,0) のまま残る
    (0x5e05b0: `mov r9,[rbp]` / `mov r9,[rbp+8]` の双方が壊れる → NULL 書込で SIGSEGV)。
    → レコードの 2 qword を正しく load して frame に copy し、placeholder を
      第 2 qword の load で置き換える。
    """
    if SKIP_STRUCT_D:
        return header, body, False                  # 負論対照: [D] を外す
    m = RE_STRUCT_COPY.search(body)
    if not m:
        return header, body, False
    if not habi.get('ptr_struct'):
        return header, body, False
    g = m.groupdict()
    pfx = '@STRUCT%s' % (fname[-4:] if fname else 'x')
    rep_txt = (
        '  SV = alloca i64, align 8\n'
        '  PFX.p0 = inttoptr i64 SARG to ptr\n'
        '  PFX.q0 = load i64, ptr PFX.p0, align 8\n'
        '  store i64 PFX.q0, ptr SV, align 8\n'
        '  PFX.a1 = add i64 SARG, 8\n'
        '  PFX.p1 = inttoptr i64 PFX.a1 to ptr\n'
        '  PFX.q1 = load i64, ptr PFX.p1, align 8\n'
        '  PFX.f1i = ptrtoint ptr SV to i64\n'
        '  PFX.f1a = add i64 PFX.f1i, 8\n'
        '  PFX.f1 = inttoptr i64 PFX.f1a to ptr\n'
        '  store i64 PFX.q1, ptr PFX.f1, align 8\n'
        '  PH = load i64, ptr PFX.f1, align 8\n'
    )
    rep_txt = (rep_txt.replace('PFX', pfx.replace('@', '%'))
                      .replace('SV', g['sv'])
                      .replace('SARG', g['sarg'])
                      .replace('PH', '%' + g['ph']))
    body = body[:m.start()] + rep_txt + body[m.end():]
    rep['struct_copy_fixed'] += 1
    return header, body, True


def fix_orphan_alloca(header, body, habi, rep, fname):
    """[B] spill 初期化落ち (B1: store 全無し / B2: どの store も load を支配しない)。"""
    lines = body.split('\n')
    changed = False
    used_xmm = [x for x in habi.get('xmm_slots', []) if int(x[3:]) < 4]
    entry = entry_block_lines(lines)
    for ln in list(lines):
        m = re.match(r'^\s*(%[\w.$-]+) = alloca (float|double|i64)\s*$', ln)
        if not m:
            continue
        aname, ty = m.group(1), m.group(2)
        esc = re.escape(aname)
        stores = [l for l in lines if re.search(r'store [^,]+, (?:ptr|' + ty + r'\*) ' + esc + r'\s*(,|$)', l)]
        loads = [l for l in lines if re.search(r'= load [\w]+, [\w\*]+ ' + esc + r'\s*(,|$)', l)]
        if not loads:
            continue
        # CAB-253: 初期化の判定は「entry に store が無い」ではなく dom 判定
        if store_dominates_loads(body, aname):
            continue
        if stores:
            # store はあるが load を支配しない → レジスタ名で slot を決められる GPR のみ
            reg = None
            for g in SLOT_GPR:
                if re.match(r'%' + g + r'\.0\.', aname):
                    reg = g
                    break
            if reg is None or ty in ('float', 'double'):
                continue                               # 名前で slot を決められない場合は触らない
            pname = '%%in.%s' % reg
            if ('i64 %s' % pname) not in header:
                body = entry_insert(body, ['  store i64 %s, ptr %s' % (pname, aname)])
                header = append_param(header, 'i64 %s' % pname)
                rep['orphan_gpr_fixed'] += 1
                changed = True
            continue
        # B1: store 全無し (orphan spill)
        reg = None
        for x in SLOT_XMM:
            if re.match(r'%' + x + r'(\.|$)', aname[1:]):
                reg = x
                break
        for x in SLOT_GPR:
            if reg is None and re.match(r'%' + x + r'\.0\.', aname):
                reg = x
        if reg is None:
            if ty in ('float', 'double'):
                reg = used_xmm[0] if used_xmm else 'xmm0'
            else:
                reg = habi.get('gpr_slots', ['rcx'])[0] if habi.get('gpr_slots') else 'rcx'
        if reg in SLOT_XMM and ty in ('float', 'double'):
            pname = '%%in.%s' % reg
            if ('%s %s' % (ty, pname)) not in header:
                body = entry_insert(body, ['  store %s %s, ptr %s' % (ty, pname, aname)])
                header = append_param(header, '%s %s' % (ty, pname))
                rep['orphan_float_fixed'] += 1
                changed = True
        elif reg in SLOT_GPR and ty == 'i64':
            pname = '%%in.%s' % reg
            if ('i64 %s' % pname) not in header:
                body = entry_insert(body, ['  store i64 %s, ptr %s' % (pname, aname)])
                header = append_param(header, 'i64 %s' % pname)
                rep['orphan_gpr_fixed'] += 1
                changed = True
        else:
            continue                                       # i128 等は非対応 (REPORT 限界)
    return header, body, changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--abi')
    ap.add_argument('--report')
    a = ap.parse_args()
    abi = json.load(open(a.abi)) if a.abi else {}
    rep = {'movd_sites': {}, 'movd_fixed': 0, 'orphan_float_fixed': 0, 'orphan_gpr_fixed': 0,
           'helper_xmm_fixed': 0, 'ucomi_flags_fixed': 0, 'struct_copy_fixed': 0, 'funcs': {}}

    text = open(a.src, errors='replace').read()
    starts = [m.start() for m in re.finditer(r'(?m)^define [^\n]*\{', text)]
    head = text[:starts[0]] if starts else text
    chunks = []
    for k, s in enumerate(starts):
        e_next = starts[k + 1] if k + 1 < len(starts) else len(text)
        seg = text[s:e_next]
        nl = seg.index('\n') + 1
        header = seg[:nl]
        rest = seg[nl:]
        mclose = rest.rindex('\n}\n')
        chunks.append([header, rest[:mclose], rest[mclose + 3:]])

    out = [head]
    for header, body, inter in chunks:
        fname = func_name(header)
        va = '0x' + fname.split('_')[1] if fname and fname.startswith('function_') else None
        habi = abi.get(va, {}) if va else {}
        h2, b2, c1 = fix_movd_from_zero(header, body, habi, rep, fname or '')
        h3, b3, c2 = fix_helper_operand_xmm(h2, b2, habi, rep, fname or '')
        h3, b3, c25 = fix_ucomi_flags(h3, b3, rep, fname or '')
        h4, b4, c3 = fix_struct_copy(h3, b3, habi, rep, fname or '')
        h5, b5, c4 = fix_orphan_alloca(h4, b4, habi, rep, fname or '')
        if c1 or c2 or c25 or c3 or c4:
            rep['funcs'][fname] = {'movd': c1, 'helper': c2, 'ucomi': c25, 'struct': c3, 'orphan': c4}
        out.append(h5 + b5 + '\n}\n' + inter)

    result = ''.join(out)
    open(a.dst, 'w').write(result)
    if a.report:
        r2 = dict(rep)
        r2['movd_sites'] = dict(rep['movd_sites'])
        json.dump(r2, open(a.report, 'w'), indent=1)
    print('[k80_argfix]', json.dumps({k: v for k, v in rep.items() if k != 'movd_sites'}))


if __name__ == '__main__':
    main()
