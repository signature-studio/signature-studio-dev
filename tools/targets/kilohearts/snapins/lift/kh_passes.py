#!/usr/bin/env python3
"""kh_passes.py — RetDec 生 .ll (LLVM12 typed pointer, !insn.addr 付き) に対する「機械語ガイド付き」修復 pass 群。

RetDec が静かに落とす/誤結線する意味を、PE の機械語 (capstone) と照合して復元する。
!insn.addr メタデータを使うため、ir5_patch (A7 でメタデータ除去) より *前* に実行すること。

  [flags]  ucomis*/comis* → jcc の分岐条件が無関係な直前 cmp に誤結線される (P1)。jcc 種別と ucomis オペランドから fcmp で再構成。
  [branches] ucomis* 直後の jcc が IR から丸ごと消え skip 領域が無条件実行になる (silent miscompile)。領域を新 BB に切り出し fcmp 条件 br で括り直す。
  [f7]     `mov r64,[rB]` (disp=0, rB=引数 reg) の deref 脱落 (rD := rB 扱い)。消費命令の IR 行に load を挿入して復元。
  [f2]     関数入口で live-in の xmm0-3 (float/double 引数) が引数として宣言されない (F2)。シグネチャへ追加し bogus 定義を置換。
  [mov128] 128bit store (movaps/movups) が `call i64 @__asm_movaps` + `sext i64→i128` に化けて上位 64bit が符号拡張になる。
  [storelow] movlps/movhps/movsd/movq/movss/movd の *メモリ store 形* が `call void @__asm_movlps(old_load, val)` に化けて store 消失 (64/32bit 形; 128bit 形は ir5_patch[S1a])。
  [trace]  (報告のみ) メモリオペランドを持つのに IR 痕跡 (insn.addr) が無い機械語命令 = 脱落候補を列挙 (silent miscompile 検出器の入力)

usage: kh_passes.py IN.ll OUT.ll --core HeartCore.core_64 [--skip a,b] [--only a,b] [--report r.json]
"""
import argparse
import json
import re
from collections import defaultdict
from khmach import Mach, GPR64

ARGREG = {'rcx': 1, 'rdx': 2, 'r8': 3, 'r9': 4}
DEF_RE = re.compile(r'^define\s+(?P<ret>\S+)\s+@function_(?P<va>[0-9a-f]+)\((?P<params>[^)]*)\)(?P<rest>.*)\{$')
ADDR_RE = re.compile(r'!insn\.addr !(\d+)')
META_RE = re.compile(r'^!(\d+) = !\{i64 (\d+)\}$')
COMIS_RE = re.compile(r'^\s*call void @__asm_(v)?(u)?comis(s|d)(?:__\d+|\.\d+)?\((?P<args>.*?)\)(?P<tail>, !insn\.addr !\d+)?\s*$')
BR_RE = re.compile(r'^(\s*)br i1 (%[\w.\-]+), label %([\w.\-]+), label %([\w.\-]+)(, !insn\.addr !\d+)?\s*$')

PRED = {'jb': 'ult', 'jc': 'ult', 'jnae': 'ult', 'jae': 'oge', 'jnb': 'oge', 'jnc': 'oge', 'jbe': 'ule', 'jna': 'ule',
        'ja': 'ogt', 'jnbe': 'ogt', 'je': 'ueq', 'jz': 'ueq', 'jne': 'one', 'jnz': 'one', 'jp': 'uno', 'jpe': 'uno',
        'jnp': 'ord', 'jpo': 'ord'}
ZERO_IDIOM = ('xorps', 'xorpd', 'pxor', 'vxorps', 'vxorpd', 'vpxor')


def split_args(s):
    out, depth, cur = [], 0, ''
    for ch in s:
        if ch in '([<':
            depth += 1
        elif ch in ')]>':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


class Fn:
    def __init__(self, va, start, end):
        self.va, self.start, self.end = va, start, end  # lines[start..end] = define .. }
        self.before = defaultdict(list)
        self.after = defaultdict(list)
        self.sub = {}


def parse(lines):
    metas, fns = {}, []
    i = 0
    while i < len(lines):
        m = META_RE.match(lines[i])
        if m:
            metas[int(m.group(1))] = int(m.group(2))
        m = DEF_RE.match(lines[i])
        if m:
            j = i
            while lines[j] != '}':
                j += 1
            fns.append(Fn(int(m.group('va'), 16), i, j))
            i = j
        i += 1
    return metas, fns


def line_addr(line, metas):
    m = ADDR_RE.search(line)
    return metas.get(int(m.group(1))) if m else None


class Ctx:
    def __init__(self, M, lines, metas):
        self.M, self.lines, self.metas = M, lines, metas
        self.report = {}
        self.n = 0

    def uid(self, tag):
        self.n += 1
        return 'kh%s%d' % (tag, self.n)

    def addr_lines(self, fn):
        d = defaultdict(list)
        for k in range(fn.start, fn.end + 1):
            a = line_addr(self.lines[k], self.metas)
            if a is not None:
                d[a].append(k)
        return d


# ---------------------------------------------------------------- flags (P1)
def find_comis(cx, fn, mf, ins):
    """jcc の直前フラグ設定命令が (u)comis なら (found_insn, crossed_join) を返す"""
    idx = mf.index(ins.addr)
    found, crossed_join, p, steps = None, False, idx - 1, 0
    while p >= 0 and steps < 12:
        q = mf.insns[p]
        if q.mn in ('call', 'ret', 'jmp'):
            break
        if q.flagw:
            found = q
            break
        if q.addr in mf.targets:
            crossed_join = True
        p -= 1
        steps += 1
    if ins.addr in mf.targets:
        crossed_join = True
    if not found or not re.match(r'^(v)?u?comis[sd]$', found.mn):
        return None, crossed_join
    return found, crossed_join


def fcmp_for(cx, fn, ck, pred, memo, st, a):
    """ucomis call 行 ck の直後に fcmp <pred> を生成 (memo 済みなら再利用)。名前 or None"""
    lines = cx.lines
    cm = COMIS_RE.match(lines[ck])
    kind = cm.group(3)
    args = split_args(cm.group('args'))
    if len(args) != 2:
        st['unfixed'].append('%x args %s' % (a, args))
        return None
    ty, ity = ('double', 'i64') if kind == 'd' else ('float', 'i32')
    if (ck, 'base') not in memo:
        t = cx.uid('fl')
        ins_l, ops = [], []
        for n_, arg in enumerate(args):
            aty, aval = arg.split(' ', 1)
            nm = '%%%s.o%d' % (t, n_)
            if aty == 'i128':
                ins_l.append('  %s.t = trunc i128 %s to %s' % (nm, aval, ity))
                ins_l.append('  %s = bitcast %s %s.t to %s' % (nm, ity, nm, ty))
            elif aty == ity:
                ins_l.append('  %s = bitcast %s %s to %s' % (nm, ity, aval, ty))
            elif aty == 'i64' and ity == 'i32':
                ins_l.append('  %s.t = trunc i64 %s to i32' % (nm, aval))
                ins_l.append('  %s = bitcast i32 %s.t to float' % (nm, nm))
            else:
                st['unfixed'].append('%x operand types %s' % (a, args))
                return None
            ops.append(nm)
        fn.after[ck].extend(ins_l)
        memo[(ck, 'base')] = (t, ops, ty)
    t, ops, ty = memo[(ck, 'base')]
    key = (ck, pred)
    if key not in memo:
        nm = '%%%s.%s' % (t, pred)
        fn.after[ck].append('  %s = fcmp %s %s %s, %s' % (nm, pred, ty, ops[0], ops[1]))
        memo[key] = nm
    return memo[key]


def pass_flags(cx, fn, mf):
    st = cx.report.setdefault('flags', {'sites': 0, 'fixed': 0, 'unfixed': []})
    lines, metas = cx.lines, cx.metas
    addr_lines = cx.addr_lines(fn)
    memo = fn.memo = getattr(fn, 'memo', {})
    for k in range(fn.start, fn.end + 1):
        m = BR_RE.match(lines[k])
        if not m:
            continue
        a = line_addr(lines[k], metas)
        ins = mf.at(a) if a else None
        if not ins or not ins.mn.startswith('j') or ins.mn == 'jmp':
            continue
        found, crossed_join = find_comis(cx, fn, mf, ins)
        if not found:
            continue
        st['sites'] += 1
        pred = PRED.get(ins.mn)
        if pred is None or crossed_join:
            st['unfixed'].append('%x %s (%s)' % (a, ins.mn, 'join' if crossed_join else 'pred'))
            continue
        cl = [x for x in addr_lines.get(found.addr, []) if COMIS_RE.match(lines[x])]
        if not cl:
            st['unfixed'].append('%x no ucomis call in IR' % found.addr)
            continue
        cond = fcmp_for(cx, fn, cl[0], pred, memo, st, a)
        if cond is None:
            continue
        tgt = '%x' % int(ins.ops, 16)
        T, F = m.group(3), m.group(4)
        newcond = cond
        if T.startswith('dec_label_pc_' + tgt):
            pass
        elif F.startswith('dec_label_pc_' + tgt):
            newcond = '%s.inv%d' % (cond, k)
            fn.before[k].append('  %s = xor i1 %s, true' % (newcond, cond))
        else:
            st['unfixed'].append('%x label orientation %s %s' % (a, T, F))
            continue
        fn.sub[k] = lines[k].replace('br i1 %s,' % m.group(2), 'br i1 %s,' % newcond, 1)
        st['fixed'] += 1


# ---------------------------------------------------------------- branches (dropped jcc)
def pass_branches(cx, fn, mf):
    """ucomis* の後ろの jcc が *IR から丸ごと消えている* (skip 領域が無条件実行になる) silent miscompile の復元。
    skip 領域 (jcc の次〜target 直前) の IR 行を新 BB に切り出し、fcmp 条件の br で括り直す。"""
    st = cx.report.setdefault('branches', {'dropped': 0, 'restored': 0, 'unfixed': []})
    lines, metas = cx.lines, cx.metas
    addr_lines = cx.addr_lines(fn)
    S = set(addr_lines)
    memo = fn.memo = getattr(fn, 'memo', {})
    for ins in mf.insns:
        if not (ins.mn.startswith('j') and ins.mn != 'jmp' and ins.ops.startswith('0x')) or ins.addr in S:
            continue
        tgt = int(ins.ops, 16)
        found, crossed_join = find_comis(cx, fn, mf, ins)
        st['dropped'] += 1
        if tgt <= ins.addr or not found or crossed_join or ins.mn not in PRED:
            st['unfixed'].append('%x %s -> %x (%s)' % (ins.addr, ins.mn, tgt, 'backward' if tgt <= ins.addr else 'non-fp/join/pred'))
            continue
        reg_lo, reg_hi = ins.addr + ins.size, tgt
        K = sorted(k for a, ks in addr_lines.items() if reg_lo <= a < reg_hi for k in ks)
        if not K:
            st['unfixed'].append('%x empty region' % ins.addr)
            continue
        i0, i1 = K[0], K[-1]
        if any(re.match(r'^[\w.\-]+:', lines[x]) for x in range(i0, i1 + 1)):
            st['unfixed'].append('%x region spans BB boundary' % ins.addr)
            continue
        term_end = bool(re.match(r'^\s*(br|ret|switch|unreachable|indirectbr)\b', fn.sub.get(i1, lines[i1])))
        tl = 'dec_label_pc_%x' % tgt
        if term_end:
            nx = i1 + 1
            while nx <= fn.end and not lines[nx].strip():
                nx += 1
            if nx > fn.end or not lines[nx].startswith(tl + ':'):
                st['unfixed'].append('%x region ends with terminator, target label %s not next' % (ins.addr, tl))
                continue
        region = set(range(i0, i1 + 1))
        # 副作用の無い純計算 (アドレス計算等) は CSE で領域外から参照されうる → 分岐の前へ hoist
        PURE = re.compile(r'^(\s*)(%[\w.\-]+) = (?:add|sub|mul|shl|lshr|and|or|xor|sext|zext|trunc|inttoptr|ptrtoint|bitcast|icmp|select)\b')
        hoisted, hdefs = [], set()
        defs = set()
        for x in sorted(region):
            md = re.match(r'^\s*(%[\w.\-]+) = ', lines[x])
            if not md:
                continue
            pm = PURE.match(lines[x])
            toks = set(re.findall(r'%[\w.\-]+', lines[x].split('=', 1)[1].split(', !insn')[0]))
            if pm and not (toks & (defs - hdefs)):
                hoisted.append(x)
                hdefs.add(md.group(1))
            defs.add(md.group(1))
        defs -= hdefs
        leak = [d for d in defs for x in range(fn.start, fn.end + 1) if x not in region and re.search(re.escape(d) + r'(?![\w.\-])', lines[x]) and not re.match(r'^\s*' + re.escape(d) + r' = ', lines[x])]
        if leak:
            st['unfixed'].append('%x region defs used after join: %s' % (ins.addr, sorted(set(leak))[:3]))
            continue
        cl = [x for x in addr_lines.get(found.addr, []) if COMIS_RE.match(lines[x])]
        if not cl or cl[0] >= i0:
            st['unfixed'].append('%x ucomis call not before region' % ins.addr)
            continue
        cond = fcmp_for(cx, fn, cl[0], PRED[ins.mn], memo, st, ins.addr)
        if cond is None:
            continue
        # 領域を含む BB ラベル (phi 後続参照の付け替え用)
        lab = None
        for x in range(i0, fn.start, -1):
            ml = re.match(r'^([\w.\-]+):', lines[x])
            if ml:
                lab = ml.group(1)
                break
        body, skip = cx.uid('bd'), cx.uid('sk')
        ren = {}
        for x in hoisted:
            d = re.match(r'^\s*(%[\w.\-]+) = ', lines[x]).group(1)
            if re.fullmatch(r'%\d+', d):                 # 無名 SSA は定義順番号の制約があるため名前付きに改名
                ren[d] = '%' + cx.uid('hz')
        def rn(txt):
            return re.sub(r'%\d+(?![\w.\-])', lambda mm: ren.get(mm.group(0), mm.group(0)), txt) if ren else txt
        for x in hoisted:
            fn.before[i0].append(lines[x])
            fn.sub[x] = ''
        if ren:
            for x in range(fn.start, fn.end + 1):
                lines[x] = rn(lines[x])
                if x in fn.sub:
                    fn.sub[x] = rn(fn.sub[x])
            for dct in (fn.before, fn.after):
                for kk in list(dct):
                    dct[kk] = [rn(t_) for t_ in dct[kk]]
        fn.before[i0].append('  br i1 %s, label %%%s, label %%%s' % (cond, skip, body))
        fn.before[i0].append('%s:' % body)
        if not term_end:
            fn.after[i1].append('  br label %%%s' % skip)
        fn.after[i1].append('%s:' % skip)
        if term_end:
            fn.after[i1].append('  br label %%%s' % tl)
        if lab:
            for x in range(i1 + 1, fn.end + 1):
                if 'phi ' in lines[x] and ('%' + lab) in lines[x]:
                    fn.sub[x] = re.sub(r'(\[ [^,\]]+, )%' + re.escape(lab) + r'( \])', r'\1%' + skip + r'\2', fn.sub.get(x, lines[x]))
        st['restored'] += 1


# ---------------------------------------------------------------- f7
def pass_f7(cx, fn, mf):
    st = cx.report.setdefault('f7', {'drops': 0, 'sites_patched': 0, 'unfixed': []})
    lines = cx.lines
    addr_lines = cx.addr_lines(fn)
    S = set(addr_lines)
    for n, ins in enumerate(mf.insns):
        mem = ins.mem
        if not (ins.mn == 'mov' and mem and mem['size'] == 8 and mem['base'] in ARGREG and not mem['index']
                and mem['disp'] == 0 and ins.addr not in S):
            continue
        rD = [r for r in ins.writes if r in GPR64]
        if len(rD) != 1:
            continue
        rD, rB = rD[0], mem['base']
        st['drops'] += 1
        # 消費範囲 (rD が再定義されるまで) を先に求め、rB の書込がその範囲より後ろにしか無いこと (+ 後方分岐で戻らない) を要求
        cons, last = [], ins.addr
        for c in mf.insns[n + 1:]:
            if rD in c.reads:
                cons.append(c)
                last = c.addr
            if (rD in c.writes and rD not in c.reads) or c.mn == 'ret':
                break
        bad = False
        for w in mf.insns:
            if rB in w.writes and w.addr != ins.addr:
                if w.addr <= last:
                    bad = True
                for j in mf.insns:
                    if j.addr >= w.addr and (j.mn == 'jmp' or j.mn.startswith('j')) and j.ops.startswith('0x') and int(j.ops, 16) <= last:
                        bad = True
        if bad:
            st['unfixed'].append('%x base %s redefined before/around consumers' % (ins.addr, rB))
            continue
        argv = '%%arg%d' % ARGREG[rB]
        pat = re.escape(argv) + r'(?![\w.])'
        for c in mf.insns[n + 1:]:
            if rD in c.reads and rB not in c.reads and c.addr in addr_lines:
                for k in addr_lines[c.addr]:
                    cur = fn.sub.get(k, lines[k])
                    if re.search(pat, cur):
                        t = cx.uid('f7')
                        fn.before[k].append('  %%%s.p = inttoptr i64 %s to i64*' % (t, argv))
                        fn.before[k].append('  %%%s = load i64, i64* %%%s.p, align 8' % (t, t))
                        fn.sub[k] = re.sub(pat, '%' + t, cur)
                        st['sites_patched'] += 1
            if (rD in c.writes and rD not in c.reads) or c.mn == 'ret':
                break


# ---------------------------------------------------------------- f2
def pass_f2(cx, fn, mf):
    st = cx.report.setdefault('f2', {'liveins': {}, 'patched': 0, 'unfixed': [], 'sigs': {}})
    lines = cx.lines
    written, live = set(), {}
    for ins in mf.insns:
        reads = set(ins.reads)
        if ins.mn in ZERO_IDIOM:
            ops = [o.strip() for o in ins.ops.split(',')]
            if len(ops) == 2 and ops[0] == ops[1]:
                reads = set()
        for r in reads:
            if r in ('xmm0', 'xmm1', 'xmm2', 'xmm3') and r not in written:
                live.setdefault(r, []).append(ins)
        written |= {w for w in ins.writes if w.startswith('xmm')}
    if not live:
        return
    d = DEF_RE.match(lines[fn.start])
    params = [p.strip() for p in d.group('params').split(',') if p.strip()]
    addr_lines = cx.addr_lines(fn)
    newp = {}
    for r, uses in sorted(live.items()):
        pos = int(r[3:])
        ty = 'double' if uses[0].mn.endswith('sd') else 'float'
        newp[pos] = ty
        st['liveins']['%x:%s' % (fn.va, r)] = ty
        for ins in uses:
            done = False
            for k in addr_lines.get(ins.addr, []):
                l = fn.sub.get(k, lines[k])
                m = re.match(r'^(\s*)(%[\w.\-]+) = sext i64 (%[\w.\-]+) to i128(, !insn\.addr !\d+)?$', l)
                m2 = re.match(r'^(\s*)(%[\w.\-]+) = load i128, i128\* (%[\w.\-]+)(, align \d+)?(, !insn\.addr !\d+)?$', l)
                mm = m or m2
                if mm:
                    bits = 'i64' if ty == 'double' else 'i32'
                    t = cx.uid('f2')
                    fn.sub[k] = '%s%%%s.b = bitcast %s %%kxmm%d to %s' % (mm.group(1), t, ty, pos, bits)
                    fn.after[k].append('%s%s = zext %s %%%s.b to i128' % (mm.group(1), mm.group(2), bits, t))
                    done = True
                    st['patched'] += 1
                    break
            if not done:
                st['unfixed'].append('%x %s read at %x not patchable' % (fn.va, r, ins.addr))
    maxpos = max(newp)
    existing = {}
    for p in params:
        mm = re.match(r'.*%arg(\d+)$', p)
        if mm:
            existing[int(mm.group(1))] = p
    out = []
    for pos in range(maxpos + 1):
        if pos in newp:
            out.append('%s %%kxmm%d' % (newp[pos], pos))
        elif (pos + 1) in existing:
            out.append(existing[pos + 1])
        else:
            out.append('i64 %%kpad%d' % pos)
    for pos, p in sorted(existing.items()):
        if pos - 1 > maxpos:
            out.append(p)
    fn.sub[fn.start] = lines[fn.start].replace('(' + d.group('params') + ')', '(' + ', '.join(out) + ')', 1)
    st['sigs']['%x' % fn.va] = out


# ---------------------------------------------------------------- mov128
def pass_mov128(cx, fn, mf):
    st = cx.report.setdefault('mov128', {'patched': 0})
    lines = cx.lines
    names = r'(?:movaps|movups|movdqa|movdqu|movapd|movupd)(?:__\d+|\.\d+)?'
    callre = re.compile(r'^(\s*)(%[\w.\-]+) = call i64 @__asm_' + names + r'\(i128 ([^)]+)\)(, !insn\.addr !\d+)?$')
    for k in range(fn.start, fn.end + 1):
        m = callre.match(lines[k])
        if not m:
            continue
        ind, r, x = m.group(1), m.group(2), m.group(3)
        fn.sub[k] = '%s%s = trunc i128 %s to i64' % (ind, r, x)
        for j in range(k + 1, fn.end + 1):
            s = re.match(r'^(\s*)(%[\w.\-]+) = sext i64 ' + re.escape(r) + r' to i128(, !insn\.addr !\d+)?$', lines[j])
            if s:
                fn.sub[j] = '%s%s = or i128 %s, 0' % (s.group(1), s.group(2), x)
                st['patched'] += 1


# ---------------------------------------------------------------- storelow
def pass_storelow(cx, fn, mf):
    """movlps/movhps/movlpd/movhpd/movsd/movq/movss/movd の *メモリ store 形* は RetDec が
    `%old = load iN, iN* %p` + `call void @__asm_movlps(iN %old, i128 %val)` に化かし store が消える (128bit 形は
    ir5_patch[S1a] が復元するが 64/32bit 形は未対応)。load の ptr を辿って store へ復元する。"""
    st = cx.report.setdefault('storelow', {'patched': 0, 'unfixed': []})
    lines = cx.lines
    callre = re.compile(r'^(\s*)call void @__asm_(movlps|movlpd|movhps|movhpd|movsd|movq|movss|movd)(?:__\d+|\.\d+)?\((i64|i32) (%[\w.\-]+), i128 ([^)]+)\)(, !insn\.addr !\d+)?$')
    for k in range(fn.start, fn.end + 1):
        m = callre.match(lines[k])
        if not m:
            continue
        ind, mn, ty, old, val = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        pat = re.compile(r'^\s*' + re.escape(old) + r' = load ' + ty + r', ' + ty + r'\* (%[\w.\-]+)')
        ptr = None
        for j in range(k - 1, fn.start, -1):
            mm = pat.match(lines[j])
            if mm:
                ptr = mm.group(1)
                break
        if ptr is None:
            st['unfixed'].append('%x line %d: no load for %s' % (fn.va, k, old))
            continue
        t = cx.uid('sl')
        pre = []
        v = val
        if mn in ('movhps', 'movhpd'):
            pre.append('%s%%%s.s = lshr i128 %s, 64' % (ind, t, val))
            v = '%%%s.s' % t
        pre.append('%s%%%s.v = trunc i128 %s to %s' % (ind, t, v, ty))
        pre.append('%sstore %s %%%s.v, %s* %s, align 1%s' % (ind, ty, t, ty, ptr, m.group(6) or ''))
        fn.sub[k] = '\n'.join(pre)
        st['patched'] += 1
    # VEX.256 vmovaps の store 形 (`vmovaps ymmword ptr [m], ymm`): gen_simd は void 2 引数を abort スタブのままにするため、
    # 呼出を 32B store へ直接復元する (#3358 / KH-54)。old は `load i256, i256* %p` の値。
    cre256 = re.compile(r'^(\s*)call void @__asm_vmovaps(?:__\d+|\.\d+)?\(i256 (%[\w.\-]+), i256 ([^)]+)\)(, !insn\.addr !\d+)?$')
    for k in range(fn.start, fn.end + 1):
        m = cre256.match(lines[k])
        if not m:
            continue
        ind, old, val = m.group(1), m.group(2), m.group(3)
        pat = re.compile(r'^\s*' + re.escape(old) + r' = load i256, i256\* (%[\w.\-]+)')
        ptr = None
        for j in range(k - 1, fn.start, -1):
            mm = pat.match(lines[j])
            if mm:
                ptr = mm.group(1)
                break
        if ptr is None:
            st.setdefault('unfixed', []).append('%x line %d: no load for %s (vmovaps256)' % (fn.va, k, old))
            continue
        fn.sub[k] = '%sstore i256 %s, i256* %s, align 1%s' % (ind, val, ptr, m.group(4) or '')
        st['patched'] += 1
        st['vmovaps256'] = st.get('vmovaps256', 0) + 1


# ---------------------------------------------------------------- trace (report only)
def pass_trace(cx, fn, mf):
    st = cx.report.setdefault('trace', {})
    S = set(cx.addr_lines(fn))
    st['%x' % fn.va] = ['%x %s %s' % (i.addr, i.mn, i.ops) for i in mf.insns
                        if i.mem and i.mn not in ('nop', 'lea', 'prefetcht0', 'prefetchnta') and i.addr not in S]


PASSES = [('flags', pass_flags), ('branches', pass_branches), ('f7', pass_f7), ('f2', pass_f2), ('mov128', pass_mov128), ('storelow', pass_storelow), ('trace', pass_trace)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inp')
    ap.add_argument('out')
    ap.add_argument('--core', required=True)
    ap.add_argument('--skip', default='')
    ap.add_argument('--only', default='')
    ap.add_argument('--report', default='')
    a = ap.parse_args()
    skip = set(filter(None, a.skip.split(',')))
    only = set(filter(None, a.only.split(',')))
    M = Mach(a.core)
    lines = open(a.inp).read().split('\n')
    metas, fns = parse(lines)
    cx = Ctx(M, lines, metas)
    for fn in fns:
        mf = M.function(fn.va)
        for name, p in PASSES:
            if name in skip or (only and name not in only):
                continue
            p(cx, fn, mf)
    allsub, allbefore, allafter = {}, defaultdict(list), defaultdict(list)
    for fn in fns:
        allsub.update(fn.sub)
        for k, v in fn.before.items():
            allbefore[k] += v
        for k, v in fn.after.items():
            allafter[k] += v
    out = []
    for k, l in enumerate(lines):
        out.extend(allbefore.get(k, []))
        out.append(allsub.get(k, l))
        out.extend(allafter.get(k, []))
    open(a.out, 'w').write('\n'.join(out))
    if a.report:
        json.dump(cx.report, open(a.report, 'w'), indent=1)
    summ = {}
    for k, v in cx.report.items():
        if k == 'trace':
            summ[k] = {f: len(m) for f, m in v.items()}
        else:
            summ[k] = {kk: (len(vv) if isinstance(vv, (list, dict)) else vv) for kk, vv in v.items()}
    print('[kh_passes]', json.dumps(summ))


if __name__ == '__main__':
    main()
