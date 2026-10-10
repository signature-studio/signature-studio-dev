#!/usr/bin/env python3
"""x87fix.py — RetDec lift IR の x87 スタック模型欠陥の機械的修復 pass (P0c-3 / CAB-251).

  python3 x87fix.py IN.ll OUT.ll [--report r.json] [--funcs fn1,fn2,...]

## 背景 (tools/plugins/p0c/REPORT.md §8.0-4, §9)

RetDec は x87 スタックを fpr[] 配列 + fpu_stat_TOP 変数で模型化するが, straight-line
翻訳中の内部 TOP 追跡が破綻し, 特に loop 内で次の欠陥を生成する:

  (D1) fst/fstp/fist 系の読出 slot が 1 つずれる (st(0) 読出が st(1) 化)
  (D2) 2 回目以降の fld の書込先が 1 つずれる (既存 st(1) を破壊)
  (D3) 演算命令の st(i) オペランド絶対 slot ずれ (内部 frame ドリフト)
  (D4) loop 末尾の fpu_stat_TOP 更新が過大 (平衡 loop で +1/+2)
  (D5) fist直後の fisub が `fsub %X, %X` (=0) に落下 (frac 消失)
  (D6) fxch の対象 slot ずれ (loop 不変値を破壊)
  (D7) fpu_stat_TOP 初期化 store 欠落 (loop 1 回目の reload が undef)

## 修復規則 (機械検出 + 機械的書替え)

 pass は IR のみから, RetDec の emission パターン (機械語 1 命令 → 固定 IR 系列) を復号して
 x87 命令列を再現し, 真 の TOP を各命令位置で追跡する。全 fpr アクセスの絶対 slot を
 st(i) = fpr[(TOP+i) & 7] で再計算し, 既存の index 式を
 「add i32 <block先頭TOP値>, <true_slot - block先頭TOP>」の正準形へ書替える。
 既に正しい関数は正準形が既存式と一致するため 1 行も変わらない (不動点 = 冪等)。

  [R1] fpr index 再導出 (D1/D2/D3): pattern 復元結果の真 slot への統一書替え
  [R2] TOP 変数更新修正 (D4): latch の fpu_stat_TOP store を真 delta へ
       (平衡 loop: back-edge で TOP が一致しなければ関数全体をスキップ = 安全側)
  [R3] fisub 零化修復 (D5): fptosi 済の値を sitofp して減算へ
       - fpr model 内: load → fptosi → load(同slot) → fsub X, Y (X,Y 同値) → store
       - devirtualized: fsub double %A, %A かつ %A からの fptosi が先行
  [R4] 初期 TOP store 補完 (D7)
  [R5] fst/fist/fstp st(0) の pop 有無 (D1 の一部) は 2^k 全組合せを試し,
       「loop back-edge で TOP が平衡」する組合せが一意のときのみ採用 (機械決定)

## 検出対象パターン (RetDec emission → 機械語命令)

  push_mem : store.fpr(i, fpext|sitofp(mem/arg))            → fld/fild [mem] (push)
  dup      : load.fpr(a) → store.fpr(a-1, loadresult)       → fld st(0) (push)
  binop    : load, load, fop, store(W≡A: dest st0 / W≡B: dest st(1)+pop)
  memarith : load, fop(1 fpr operand + mem), store          → fadd/fmul/fsub [mem]
  fstp_mem : load → fptrunc → store float/double [mem]      → fstp [mem] (pop bit)
  fist     : load → [rint] → fptosi                          → fist/fistp [mem] (pop bit)
  fstpst0  : load → store(同slot, loadresult)                → fstp st(0) (pop bit)
  fxch     : load, load, store(交叉), store(交叉)            → fxch st(1)
  fisub    : load → fptosi → load(同slot) → fsub → store     → fist + fisub [mem]
  dead     : 未使用 load                                     → fcom/fcompp 等の死否定義 (触らない)

  上記以外の構造を検出したら関数全体を未変更のままスキップする (安全側)。
"""
import argparse
import itertools
import json
import re

RE_FUNC = re.compile(r'(?m)^define [^\n]*\{')
RE_LABEL = re.compile(r'^([A-Za-z_][\w.$]*):')
RE_LOAD = re.compile(r'^(\s*)(%[\w.$-]+) = call double @__frontend_reg_load\.fpr\(i32 ([\w.%$-]+)\)\s*$')
RE_STORE = re.compile(r'^(\s*)call void @__frontend_reg_store\.fpr\(i32 ([\w.%$-]+), double ([\w.%$-]+)\)\s*$')
RE_TOPSTORE = re.compile(r'^(\s*)store i32 ([\w.%$-]+), ptr (%[\w.$-]+)\s*$')
RE_MEMSTORE = re.compile(r'^\s*store (?:float|double) [%\w.$-]+, (?:ptr |(?:float|double)\*)')
RE_DEF = re.compile(r'^\s*(%[\w.$-]+) = (.+?)\s*(?:;.*)?$')

OP_RE = [
    ('fpext', re.compile(r'^fpext (?:float|double) (%[\w.$-]+) to double$')),
    ('sitofp', re.compile(r'^sitofp i(?:16|32|64) (%[\w.$-]+) to double$')),
    ('fptrunc', re.compile(r'^fptrunc double (%[\w.$-]+) to float$')),
    ('fptosi', re.compile(r'^fptosi double (%[\w.$-]+) to i(?:16|32|64)$')),
    ('rint', re.compile(r'^call double @llvm\.rint\.f64\(double (%[\w.$-]+)\)$')),
    ('fop', re.compile(r'^(fadd|fsub|fmul|fdiv) double (%[\w.$-]+), (%[\w.$-]+)$')),
    ('iadd', re.compile(r'^(add|sub) i32 (%[\w.$-]+|[-\d]+), (%[\w.$-]+|[-\d]+)$')),
    ('ixor', re.compile(r'^xor i32 (%[\w.$-]+|[-\d]+), (%[\w.$-]+|[-\d]+)$')),
    ('icmp', re.compile(r'^(?:icmp|sext|zext|trunc|inttoptr|select|call|getelementptr|sitofp i64|sitofp i32|sitofp i16|fptrunc double|fpext float|load|store|or|and|mul|shl|ashr|lshr|sub nsw|add nsw|xor i64|and i64|mul i64|add i64|sub i64|or i64|phi)')),
    ('memload', re.compile(r'^load (?:float|double|i16|i32|i64|i8), ')),
    ('const', re.compile(r'^(?:0x[0-9A-Fa-f]+|[-\d.]+(?:[eE][-\d]+)?)$')),
]

I32CONST = re.compile(r'^(-?\d+)$')


def parse_defs(lines):
    """name → {'kind','line',...}"""
    defs = {}
    for li, ln in enumerate(lines):
        m = RE_DEF.match(ln)
        if not m:
            continue
        name, rhs = m.group(1), m.group(2)
        d = {'kind': 'other', 'line': li, 'rhs': rhs}
        if '@__frontend_reg_load.fpr' in rhs:
            d['kind'] = 'fprload'
        elif '@llvm.rint.f64' in rhs:
            d['kind'] = 'rint'
            g = re.match(r'^call double @llvm\.rint\.f64\(double (%[\w.$-]+)\)$', rhs)
            d['g'] = g.groups() if g else ()
        else:
            for kind, rx in OP_RE:
                mm = rx.match(rhs)
                if mm:
                    d['kind'] = kind
                    d['g'] = mm.groups()
                    break
        defs[name] = d
    return defs


def resolve_i32(name, defs, depth=0):
    """fpu_stat_TOP 相対の定数オフセット解決 (block base = 0)。失敗は None。"""
    if depth > 12:
        return None
    m = I32CONST.match(name)
    if m:
        return int(m.group(1))
    if '.reload' in name and 'fpu_stat_TOP' in name:
        return 0                                     # block base (reload 値 = block 先頭 TOP)
    d = defs.get(name)
    if d is None:
        return None
    k = d['kind']
    if k == 'iadd':
        op, a, b = d['g']
        va, vb = resolve_i32(a, defs, depth + 1), resolve_i32(b, defs, depth + 1)
        if va is None or vb is None:
            return None
        return va + vb if op == 'add' else va - vb
    if k == 'ixor':
        va = resolve_i32(d['g'][0], defs, depth + 1)
        vb = resolve_i32(d['g'][1], defs, depth + 1)
        if va is None or vb is None:
            return None
        return va ^ vb
    return None


def find_top_var(header, body):
    m = re.search(r'%([\w.$-]*fpu_stat_TOP[\w.$-]*)\.reg2mem = alloca i32', body)
    return ('%' + m.group(1) + '.reg2mem') if m else None


def uses_of(defs_by_use, target, lines, lo, hi):
    """[lo,hi) の行で target 値を直接参照する行番号集合 (定義行除く)。"""
    pat = re.compile(r'(?<![\w.%-])' + re.escape(target) + r'(?![\w.-])')
    out = set()
    for li in range(lo, hi):
        ln = lines[li]
        if RE_DEF.match(ln) and RE_DEF.match(ln).group(1) == target:
            continue
        if pat.search(ln):
            out.add(li)
    return out


class Skip(Exception):
    pass


def decode_function(body, topvar):
    """Phase A: 構造復号 → pattern list (pop bit は site として列挙のみ)。

    patterns: dict(type=..., lines=[(idx, kind)], ...)
    line kinds: 'load' / 'store' / 'fop' / 'fptosi' / 'fsub' / 'topstore' / 'other'
    """
    lines = body.split('\n')
    defs = parse_defs(lines)
    # block 分割
    blocks = []
    cur = None
    for li, ln in enumerate(lines):
        m = RE_LABEL.match(ln)
        if m:
            cur = {'label': m.group(1), 'start': li, 'lines': []}
            blocks.append(cur)
        if cur is not None:
            cur['lines'].append(li)
    if not blocks:
        raise Skip('no blocks')

    # reload 定義名 (block base): rhs が `load i32, ptr <topvar>` の定義
    reload_name = None
    for name, d in defs.items():
        if d['rhs'] == 'load i32, ptr ' + topvar:
            reload_name = name
            break

    # zero def (entry base 候補): `= xor i32 0, 0` (i32 のみ — index 演算は i32)
    zero_name = None
    for name, d in defs.items():
        if d['rhs'] == 'xor i32 0, 0':
            zero_name = name
            break

    pats = []
    ambiguous = []
    for blk in blocks:
        idxs = blk['lines']
        i = 0
        while i < len(idxs):
            li = idxs[i]
            ln = lines[li]
            ml = RE_LOAD.match(ln)
            ms = RE_STORE.match(ln)
            if ml:
                # 連続 load 集め
                loads = []
                j = i
                while j < len(idxs):
                    mj = RE_LOAD.match(lines[idxs[j]])
                    if not mj:
                        break
                    loads.append({'li': idxs[j], 'dst': mj.group(2), 'idx': mj.group(3)})
                    j += 1
                # consumer 探索 (loads の後方, rint 1 段チェーン許容)
                consumer = None
                k = j
                scan_limit = min(len(idxs), j + 24)
                chain_vals = set(x['dst'] for x in loads)
                expanded = set(chain_vals)
                while k < scan_limit and consumer is None:
                    lk = idxs[k]
                    dk = defs.get(RE_DEF.match(lines[lk]).group(1)) if RE_DEF.match(lines[lk]) else None
                    dline = lines[lk]
                    touched = any(re.search(r'(?<![\w.%-])' + re.escape(v) + r'(?![\w.-])', dline) for v in chain_vals)
                    if touched and dk:
                        if dk['kind'] == 'rint':
                            expanded.add(RE_DEF.match(dline).group(1))
                            chain_vals.add(RE_DEF.match(dline).group(1))
                            k += 1
                            continue
                        if dk['kind'] == 'fop':
                            # fpr operand 数
                            nfp = sum(1 for g in dk['g'][1:] if defs.get(g, {}).get('kind') == 'fprload')
                            consumer = ('fop', lk, dk)
                        elif dk['kind'] == 'fptrunc':
                            consumer = ('fptrunc', lk, dk)
                        elif dk['kind'] == 'fptosi':
                            consumer = ('fptosi', lk, dk)
                        elif RE_STORE.match(dline):
                            consumer = ('store', lk, None)
                        else:
                            consumer = ('other', lk, dk)
                    elif touched and dk is None and RE_STORE.match(dline):
                        consumer = ('store', lk, None)
                    k += 1
                if consumer is None:
                    pats.append({'type': 'dead', 'block': blk['label'], 'lines': [x['li'] for x in loads]})
                    i = j
                    continue
                ctype, cli, dk = consumer
                if ctype == 'fop':
                    # store.fpr(fop結果) が後続にあるはず
                    fop_dst = RE_DEF.match(lines[cli]).group(1)
                    st = None
                    for kk in range(k, min(len(idxs), k + 24)):
                        ms2 = RE_STORE.match(lines[idxs[kk]])
                        if ms2 and ms2.group(3) == fop_dst:
                            st = idxs[kk]
                            break
                    if st is None:
                        raise Skip('binop store not found @%s' % blk['label'])
                    nfp = sum(1 for g in dk['g'][1:]
                              if defs.get(g, {}).get('kind') == 'fprload')
                    if nfp == 2:
                        la = loads[0]['idx']
                        lb = loads[1]['idx']
                        w = RE_STORE.match(lines[st]).group(2)
                        pats.append({'type': 'binop', 'block': blk['label'], 'loads': [x['li'] for x in loads],
                                     'fop': cli, 'store': st, 'w': w, 'a': la, 'b': lb,
                                     'fopkind': dk['g'][0]})
                    elif nfp == 1:
                        pats.append({'type': 'memarith', 'block': blk['label'], 'loads': [x['li'] for x in loads],
                                     'fop': cli, 'store': st})
                    else:
                        raise Skip('fop fpr operands=%d' % nfp)
                    i = idxs.index(st) + 1 if st in idxs else j
                    # 次の走査位置: store の次
                    i = idxs.index(st) + 1
                    continue
                if ctype == 'fptrunc':
                    # fptrunc → store float/double [mem]
                    ftr_dst = RE_DEF.match(lines[cli]).group(1)
                    has_mem = False
                    for kk in range(k, min(len(idxs), k + 12)):
                        if RE_MEMSTORE.match(lines[idxs[kk]]):
                            has_mem = True
                            break
                    if not has_mem:
                        raise Skip('fptrunc without mem store')
                    pats.append({'type': 'fstp_mem', 'block': blk['label'], 'loads': [x['li'] for x in loads],
                                 'fptrunc': cli, 'pop': len(ambiguous)})
                    ambiguous.append({'block': blk['label'], 'kind': 'fstp_mem'})
                    i = j
                    continue
                if ctype == 'fptosi':
                    # fist / fisub 複合判定
                    load_dst = loads[0]['dst']
                    # load の fsub 使用があるか
                    fsub_line = None
                    for kk in range(k, min(len(idxs), k + 24)):
                        dk2 = defs.get(RE_DEF.match(lines[idxs[kk]]).group(1)) if RE_DEF.match(lines[idxs[kk]]) else None
                        if dk2 and dk2['kind'] == 'fop' and dk2['g'][0] == 'fsub':
                            g1, g2 = dk2['g'][1], dk2['g'][2]
                            if g1 == load_dst or g2 == load_dst:
                                fsub_line = idxs[kk]
                                break
                    if fsub_line is not None:
                        # fisub 複合: load, [rint], fptosi, load(同idx), fsub, store
                        st = None
                        fsub_dst = RE_DEF.match(lines[fsub_line]).group(1)
                        for kk in range(idxs.index(fsub_line) + 1, min(len(idxs), idxs.index(fsub_line) + 12)):
                            ms2 = RE_STORE.match(lines[idxs[kk]])
                            if ms2 and ms2.group(3) == fsub_dst:
                                st = idxs[kk]
                                break
                        # 2 個目の load (同 idx) を特定
                        second_load = None
                        for x in loads[1:] if len(loads) > 1 else []:
                            second_load = x
                        if second_load is None:
                            for kk in range(idxs.index(fsub_line) - 1, i, -1):
                                m2 = RE_LOAD.match(lines[idxs[kk]])
                                if m2 and m2.group(2) not in [x['dst'] for x in loads]:
                                    second_load = {'li': idxs[kk], 'dst': m2.group(2), 'idx': m2.group(3)}
                                    break
                        if second_load is None or second_load['idx'] != loads[0]['idx']:
                            raise Skip('fisub second load mismatch')
                        if st is None:
                            raise Skip('fisub store not found')
                        pats.append({'type': 'fisub', 'block': blk['label'],
                                     'lines': [loads[0]['li'], second_load['li']], 'fptosi': cli,
                                     'fsub': fsub_line, 'store': st})
                        i = idxs.index(st) + 1
                        continue
                    pats.append({'type': 'fist', 'block': blk['label'], 'loads': [x['li'] for x in loads],
                                 'fptosi': cli, 'pop': len(ambiguous)})
                    ambiguous.append({'block': blk['label'], 'kind': 'fist'})
                    i = j
                    continue
                if ctype == 'store':
                    if len(loads) == 1:
                        stli = cli
                        ms2 = RE_STORE.match(lines[stli])
                        ld = loads[0]
                        if ms2.group(2) == ld['idx']:
                            pats.append({'type': 'fstpst0', 'block': blk['label'], 'loads': [ld['li']],
                                         'store': stli, 'pop': len(ambiguous)})
                            ambiguous.append({'block': blk['label'], 'kind': 'fstpst0'})
                        else:
                            # dup 判定: off(store) - off(load) == -1
                            oa = resolve_i32(ld['idx'], defs)
                            ob = resolve_i32(ms2.group(2), defs)
                            if oa is None or ob is None or ob - oa != -1:
                                raise Skip('dup delta %s' % ((oa, ob),))
                            pats.append({'type': 'dup', 'block': blk['label'], 'loads': [ld['li']], 'store': stli})
                        i = idxs.index(stli) + 1
                        continue
                    if len(loads) == 2:
                        # fxch: store(交叉) × 2
                        s1 = cli
                        ms1 = RE_STORE.match(lines[s1])
                        # s1 の値 = どちらかの load、格納先 = もう一方の idx
                        val1 = ms1.group(3)
                        src1 = next((x for x in loads if x['dst'] == val1), None)
                        dst1 = ms1.group(2)
                        oth = next((x for x in loads if x['dst'] != val1), None)
                        if src1 is None or oth is None or dst1 != oth['idx']:
                            raise Skip('fxch shape')
                        s2 = None
                        for kk in range(idxs.index(s1) + 1, min(len(idxs), idxs.index(s1) + 8)):
                            ms2 = RE_STORE.match(lines[idxs[kk]])
                            if ms2 and ms2.group(3) == oth['dst'] and ms2.group(2) == src1['idx']:
                                s2 = idxs[kk]
                                break
                        if s2 is None:
                            raise Skip('fxch second store')
                        pats.append({'type': 'fxch', 'block': blk['label'],
                                     'loads': [x['li'] for x in loads], 'stores': [s1, s2]})
                        i = idxs.index(s2) + 1
                        continue
                    raise Skip('store consumer with %d loads' % len(loads))
                raise Skip('consumer %s' % (ctype,))
            if ms:
                # store.fpr: 値の定義で分類
                val = ms.group(3)
                dv = defs.get(val)
                if dv is None:
                    raise Skip('store val no def')
                if dv['kind'] in ('fpext', 'sitofp'):
                    pats.append({'type': 'push', 'block': blk['label'], 'store': li})
                    i += 1
                    continue
                if dv['kind'] == 'const':
                    pats.append({'type': 'push', 'block': blk['label'], 'store': li})
                    i += 1
                    continue
                if dv['kind'] == 'fop':
                    nfp = sum(1 for g in dv['g'][1:]
                              if defs.get(g, {}).get('kind') == 'fprload')
                    if nfp == 0:
                        # mem 同士の演算結果を push (fld ではない) — 未対応
                        raise Skip('push of pure fop')
                    raise Skip('orphan fop store')
                raise Skip('store val kind %s' % dv['kind'])
            # TOP store
            mt = RE_TOPSTORE.match(ln)
            if mt and mt.group(3) == topvar:
                pats.append({'type': 'topstore', 'block': blk['label'], 'line': li, 'val': mt.group(2)})
            i += 1
    return pats, ambiguous, lines, defs, blocks, reload_name, zero_name


def simulate(pats, ambiguous, bits, lines, defs, blocks, reload_name, zero_name):
    """Phase B: 真 TOP シミュレーション → 書替え計画。失敗 (非平衡等) は None。"""
    top = 0
    entry_top = {}
    plan = []                                   # (line_idx, action, data)
    base_for = {}
    for blk in blocks:
        label = blk['label']
        # block base 名 (entry block は定数 0, 他は reload 値)
        if label == blocks[0]['label']:
            base = zero_name if zero_name else '0'
        else:
            if reload_name is None:
                return None
            base = reload_name
        base_for[label] = base
    # pattern 適用
    byblock = {}
    for p in pats:
        byblock.setdefault(p['block'], []).append(p)
    amb_iter = {}
    for a in ambiguous:
        amb_iter.setdefault(a['block'], []).append(a)
    for blk in blocks:
        label = blk['label']
        if label not in entry_top:
            if blk is blocks[0]:
                entry_top[label] = 0                  # 関数入口 TOP = 0
            else:
                return None                           # layout 順で未到達 (保守的にスキップ)
        top = entry_top[label]
        base = base_for[label]
        pats_b = byblock.get(label, [])
        ambs_b = {id(a): n for n, a in enumerate([x for x in ambiguous if x['block'] == label])}
        bitn = 0
        for p in pats_b:
            t = p['type']
            if t == 'push':
                plan.append((p['store'], 'idx', top - 1 - entry_top[label], base))
                top -= 1
            elif t == 'dup':
                plan.append((p['loads'][0], 'idx', top - entry_top[label], base))
                plan.append((p['store'], 'idx', top - 1 - entry_top[label], base))
                top -= 1
            elif t == 'binop':
                w, a, b = p['w'], p['a'], p['b']
                wa = resolve_i32(a, defs)
                wb = resolve_i32(b, defs)
                ww = resolve_i32(w, defs)
                if wa is None or wb is None or ww is None:
                    return None
                if ww == wa:
                    plan.append((p['loads'][0], 'idx', top - entry_top[label], base))
                    plan.append((p['loads'][1], 'idx', top + (wb - wa) - entry_top[label], base))
                    plan.append((p['store'], 'idx', top - entry_top[label], base))
                elif ww == wb:
                    plan.append((p['loads'][1], 'idx', top + 1 - entry_top[label], base))
                    plan.append((p['loads'][0], 'idx', top - entry_top[label], base))
                    plan.append((p['store'], 'idx', top + 1 - entry_top[label], base))
                    top += 1
                else:
                    return None
            elif t == 'memarith':
                plan.append((p['loads'][0], 'idx', top - entry_top[label], base))
                plan.append((p['store'], 'idx', top - entry_top[label], base))
            elif t == 'fstp_mem':
                plan.append((p['loads'][0], 'idx', top - entry_top[label], base))
                top += 1 if bits[p['pop']] else 0
            elif t == 'fist':
                plan.append((p['loads'][0], 'idx', top - entry_top[label], base))
                top += 1 if bits[p['pop']] else 0
            elif t == 'fstpst0':
                plan.append((p['loads'][0], 'idx', top - entry_top[label], base))
                plan.append((p['store'], 'idx', top - entry_top[label], base))
                top += 1 if bits[p['pop']] else 0
            elif t == 'fxch':
                plan.append((p['loads'][0], 'idx', top - entry_top[label], base))
                plan.append((p['loads'][1], 'idx', top + 1 - entry_top[label], base))
                plan.append((p['stores'][0], 'idx', top - entry_top[label], base))
                plan.append((p['stores'][1], 'idx', top + 1 - entry_top[label], base))
            elif t == 'fisub':
                plan.append((p['lines'][0], 'idx', top - entry_top[label], base))
                plan.append((p['lines'][1], 'idx', top - entry_top[label], base))
                plan.append((p['store'], 'idx', top - entry_top[label], base))
                plan.append((p['fsub'], 'fsubfix', p['fptosi'], base))
            elif t == 'topstore':
                plan.append((p['line'], 'topstore', top - entry_top[label], base))
            elif t == 'dead':
                pass
            else:
                return None
            if t in ('fstp_mem', 'fist', 'fstpst0'):
                bitn += 1
        # block 末尾の br 先に対する平衡検査 (back-edge 含む)
        for li in blk['lines']:
            ln = lines[li]
            if not re.match(r'^\s*br ', ln):
                continue
            for succ in re.findall(r'label %([\w.$]+)', ln):
                if succ in entry_top:
                    if entry_top[succ] != top:
                        return None
                else:
                    entry_top[succ] = top
        # block 末尾で br 先の entry_top を予約: ここでは layout 順の次 block への
        # フォールスルーと back-edge を区別しない。代わりに「全 block 走査後に
        # 先頭に戻る block (loop) の整合」を最終検査する。
    # 平衡検査: 各 block の entry_top が「全 pred の終了 top」と一致することを
    # 簡易検査: 同一 label への分岐を含む場合、その label の entry_top == 分岐時 top
    # (Phase A で br 先は topstore と dead を除き解析しない簡略化のため、ここでは
    #  entry_top の二重定義チェックのみ = simulate 内で実施済み)
    # 追加検査: entry block 以外で entry_top が未定義の block があれば NG
    for blk in blocks:
        if blk['label'] not in entry_top:
            return None
    return plan


def apply_plan(body, pats, plan, topvar, fname, blocks=None):
    """Phase C: 計画適用 → 新 body。"""
    lines = body.split('\n')
    defs = parse_defs(lines)

    def block_of(li):
        if blocks:
            for b in blocks:
                if li in b['lines']:
                    return b
        return None

    # line_idx → 新 idx 式
    newidx = {}
    fsubfix = {}
    topstore = {}
    for item in plan:
        if item is None:
            continue
        li, act, val, base = item
        if act == 'idx':
            newidx[li] = (base, val)
        elif act == 'fsubfix':
            fsubfix[li] = val
        elif act == 'topstore':
            topstore[li] = (base, val)
    # 必要な add def を集める
    need = {}
    for li, (base, k) in list(newidx.items()) + list(topstore.items()):
        if k == 0:
            continue
        need.setdefault((base, k), None)
    # 既存 def 探索 (同一 block 内で使用行より前, 同一テキスト)
    for (base, k) in list(need.keys()):
        want = 'add i32 %s, %d' % (base, k)
        for name, d in defs.items():
            if d['rhs'] != want:
                continue
            bu = block_of(d['line'])
            okdom = True
            for li2, (b2, k2) in list(newidx.items()) + list(topstore.items()):
                if (b2, k2) != (base, k):
                    continue
                bb = block_of(li2)
                if bb is None or bu is None or bb['label'] != bu['label'] or d['line'] >= li2:
                    okdom = False
                    break
            if okdom:
                need[(base, k)] = name
                break
    counters = {'n': 0}

    def mint():
        counters['n'] += 1
        return '%%x87s%d' % counters['n']

    for (base, k) in need:
        if need[(base, k)] is None:
            need[(base, k)] = mint()
    out = []
    # 挿入位置: base 定義行の直後 (load 間挟まない → 冪等パース安定)
    #   - base が reload / zero-def の block 内でその定義の直後に置く
    #   - base がリテラル '0' の場合は block 先頭 label 行の直後
    insert_at = {}
    if blocks:
        def base_def_line(block):
            for li2 in block['lines']:
                d2 = defs.get(RE_DEF.match(lines[li2]).group(1)) if RE_DEF.match(lines[li2]) else None
                if d2 and (d2['rhs'] == 'load i32, ptr ' + topvar or d2['rhs'] == 'xor i32 0, 0'):
                    return li2
            return block['lines'][0]
        for (base, k), nm in need.items():
            if k == 0 or not nm.startswith('%x87s'):
                continue
            # この (base,K) を使う site の block
            for li2, (b2, k2) in list(newidx.items()) + list(topstore.items()):
                if (b2, k2) == (base, k):
                    blk = None
                    for bb in blocks:
                        if li2 in bb['lines']:
                            blk = bb
                            break
                    if blk is None:
                        continue
                    pos = base_def_line(blk) + 1
                    insert_at.setdefault(pos, [])
                    if nm not in insert_at[pos]:
                        insert_at[pos].append(nm)
                    break
    # fisub 用 sitofp 挿入
    sitofp_at = {}
    for li, fptosi_line in fsubfix.items():
        sitofp_at.setdefault(fptosi_line, []).append(li)

    sitofp_name = {}
    for li in sitofp_at:
        counters['n'] += 1
        sitofp_name[li] = '%%x87f%d' % counters['n']
    fptosi_dst = {}
    for li in sitofp_at:
        fptosi_dst[li] = RE_DEF.match(lines[li]).group(1)

    rev_need = {v: kk for kk, v in need.items()}
    for li, ln in enumerate(lines):
        for nm in insert_at.get(li, []):
            kk = rev_need[nm]
            out.append('  %s = add i32 %s, %d' % (nm, kk[0], kk[1]))
        if li in newidx:
            base, k = newidx[li]
            if k == 0:
                idxs = base
            else:
                idxs = need[(base, k)]
            ln = re.sub(r'^(call void @__frontend_reg_store\.fpr\(i32 )([\w.%$-]+)(,)$',
                        r'\g<1>%s\g<3>' % idxs, ln) if ln.lstrip().startswith('call void @__frontend_reg_store') else \
                re.sub(r'^(= call double @__frontend_reg_load\.fpr\(i32 )([\w.%$-]+)(\))$',
                       lambda m: '%s%s%s' % (m.group(1), idxs, m.group(3)), ln)
            # 上の正規化が失敗した場合のフォールバック (置換されなければ元のまま → 後で検査)
            m2 = RE_STORE.match(ln)
            m3 = RE_LOAD.match(ln)
            if m2:
                ln = '%scall void @__frontend_reg_store.fpr(i32 %s, double %s)' % (m2.group(1), idxs, m2.group(3))
            elif m3:
                ln = '%s%s = call double @__frontend_reg_load.fpr(i32 %s)' % (m3.group(1), m3.group(2), idxs)
        if li in fsubfix:
            m4 = RE_DEF.match(ln)
            if m4 and m4.group(2).startswith('fsub double'):
                g = re.match(r'^fsub double (%[\w.$-]+), (%[\w.$-]+)$', m4.group(2))
                if g:
                    ln = '  %s = fsub double %s, %s' % (m4.group(1), g.group(1), sitofp_name[fsubfix[li]])
        if li in topstore:
            base, k = topstore[li]
            val = base if k == 0 else need[(base, k)]
            m5 = RE_TOPSTORE.match(ln)
            ln = '%sstore i32 %s, ptr %s' % (m5.group(1), val, topvar)
        out.append(ln)
        if li in sitofp_at:
            out.append('  %s = sitofp i32 %s to double' % (sitofp_name[li], fptosi_dst[li]))
    return '\n'.join(out)


def fix_fsub_zero_global(text):
    """[R3] devirtualized fisub 零化修復: `fsub double %A, %A` かつ %A からの fptosi が同 block 先行。

    戻り値: (新text, 修復件数)
    """
    n = 0
    out_lines = []
    for ln in text.split('\n'):
        out_lines.append(ln)
    # block 単位で処理
    lines = out_lines
    i = 0
    # fsub %A, %A を探す
    fsub_re = re.compile(r'^(\s*)(%[\w.$-]+) = fsub double (%[\w.$-]+), \3\s*$')
    def_re = re.compile(r'^\s*(%[\w.$-]+) = (.*?)\s*(?:;.*)?$')
    while i < len(lines):
        m = fsub_re.match(lines[i])
        if not m:
            i += 1
            continue
        a = m.group(3)
        # 先行する fptosi double %A to i32 を探す (同一 block 内, A の定義以降)
        j = i - 1
        fptosi_line = None
        fptosi_dst = None
        a_def_line = None
        for k in range(i - 1, -1, -1):
            md = def_re.match(lines[k])
            if md and md.group(1) == a:
                a_def_line = k
                break
        if a_def_line is None:
            i += 1
            continue
        for k in range(a_def_line + 1, i):
            md = def_re.match(lines[k])
            if md and re.match(r'^fptosi double ' + re.escape(a) + r' to i(?:16|32|64)$', md.group(2)):
                fptosi_line = k
                fptosi_dst = md.group(1)
                break
        if fptosi_line is None:
            i += 1
            continue
        # 書替え: fptosi 直後に sitofp を挿入し, fsub の第2 operand を置換
        counters = [0]
        # 既存の sitofp が無いか確認 (冪等)
        exists = any(re.match(r'^\s*%[\w.$-]+ = sitofp i32 ' + re.escape(fptosi_dst) + r' to double$', lines[k])
                     for k in range(fptosi_line + 1, i))
        if not exists:
            counters[0] += 1
            n += 1
            newname = '%%x87g%d' % i
            lines.insert(fptosi_line + 1, '  %s = sitofp i32 %s to double' % (newname, fptosi_dst))
            i += 1
            lines[i] = re.sub(r'(= fsub double ' + re.escape(a) + r', )' + re.escape(a) + r'(\s*)$',
                              r'\g<1>' + newname + r'\g<2>', lines[i])
        i += 1
    return '\n'.join(lines), n


def process_function(header, body, fname, rep):
    topvar = find_top_var(header, body)
    if topvar is None:
        rep.append({'name': fname, 'status': 'skip:no-top-var'})
        return body, False
    try:
        pats, ambiguous, lines, defs, blocks, reload_name, zero_name = decode_function(body, topvar)
    except Skip as e:
        rep.append({'name': fname, 'status': 'skip:%s' % e})
        return body, False
    # 初期 TOP store 欠落補完判定
    has_init = any(p['type'] == 'topstore' and p['block'] == blocks[0]['label'] for p in pats)
    need_init = (not has_init) and reload_name is not None
    # bits 全組合せ
    k = len(ambiguous)
    plans = []
    for combo in itertools.product([1, 0], repeat=k):
        plan = simulate(pats, ambiguous, list(combo), lines, defs, blocks, reload_name, zero_name)
        if plan is not None:
            plans.append((combo, plan))
    if not plans:
        rep.append({'name': fname, 'status': 'skip:unbalanced',
                    'patterns': len(pats), 'ambiguous': k})
        return body, False
    if len(plans) > 1:
        rep.append({'name': fname, 'status': 'skip:ambiguous-balance',
                    'combos': [c for c, _ in plans]})
        return body, False
    combo, plan = plans[0]
    # 変更要否: 既存 index 式が正準形と一致するか
    changed = need_init or len(plan) > 0
    # 詳細: plan 中の idx が既存と同値かは簡易に「canonical 文字列一致」で判定
    def canon_of(arg):
        return resolve_i32(arg, defs)
    diff = 0
    for li, act, val, base in plan:
        if act == 'idx':
            cur = None
            m3 = RE_LOAD.match(lines[li])
            m2 = RE_STORE.match(lines[li])
            cur = m2.group(2) if m2 else (m3.group(3) if m3 else None)
            if cur is None:
                diff += 1
                continue
            want = val
            have = canon_of(cur)
            # cur が base そのものの場合 have=0
            if have != want:
                diff += 1
        elif act == 'topstore':
            mt = RE_TOPSTORE.match(lines[li])
            have = resolve_i32(mt.group(2), defs) if mt else None
            if have != val:
                diff += 1
        elif act == 'fsubfix':
            diff += 1
    if diff == 0 and not need_init:
        rep.append({'name': fname, 'status': 'already-correct', 'patterns': len(pats), 'popbits': list(combo)})
        return body, False
    newbody = apply_plan(body, pats, plan, topvar, fname, blocks)
    if need_init:
        # entry block 末尾 (最初の br 手前) に store i32 <top> を挿入
        ebase = zero_name if zero_name else '0'
        e_top = _entry_exit_top(pats, combo, lines, defs, blocks)
        initval = ebase if e_top == 0 else 'add i32 %s, %d' % (ebase, e_top)
        if initval == 'add i32 0, 0':
            initval = '0'
        epos = _entry_block_end(blocks, newbody.split('\n'))
        blines = newbody.split('\n')
        blines.insert(epos, '  store i32 %s, ptr %s' % (initval, topvar))
        newbody = '\n'.join(blines)
    rep.append({'name': fname, 'status': 'fixed', 'patterns': len(pats),
                'sites': diff, 'popbits': list(combo), 'init_top_store': bool(need_init)})
    return newbody, True


def _entry_exit_top(pats, combo, lines, defs, blocks):
    """entry block 走査終了時の top (init store 用)。"""
    top = 0
    first = blocks[0]['label']
    for p in pats:
        if p['block'] != first:
            continue
        t = p['type']
        if t == 'push':
            top -= 1
        elif t == 'dup':
            top -= 1
        elif t == 'binop':
            w, a, b = p['w'], p['a'], p['b']
            wa = resolve_i32(a, defs)
            wb = resolve_i32(b, defs)
            ww = resolve_i32(w, defs)
            if ww == wb and ww != wa:
                top += 1
        elif t in ('fstp_mem', 'fist', 'fstpst0'):
            top += 1 if combo[p['pop']] else 0
    return top


def _entry_block_end(blocks, lines):
    """entry block 内の最初の `br ` 行の行番号 (その手前に init store を挿入)。"""
    first = blocks[0]
    for li in first['lines']:
        if re.match(r'^\s*br ', lines[li]):
            return li
    return first['lines'][-1] + 1


# ============================================================
# [R6] fstp f32 の chop 丸め (RC=toward-zero) — fldcw chop 区間の f32 store
# ============================================================
RE_FPTRUNC = re.compile(r'^(\s*)(%[\w.$-]+) = fptrunc double (%[\w.$-]+) to float\s*$')
RE_F32STORE = re.compile(r'^(\s*)store float (%[\w.$-]+), (.+)$')
NEXTAFTER_DECL = 'declare float @nextafterf(float, float)'


def fix_chop_f32(body, fname, rep):
    """[R6] fptrunc+store float (fstp dword 模型) を chop (toward zero) 丸めへ。

    機械語: fstp dword は fldcw 区間内では RC=chop で f32 丸めする。RetDec/f80_lower の
    fptrunc は nearest のため ±1 f32 ulp 差分になる (~50% of cells)。
    修復: nearest 結果が真値を跨いだ場合のみ nextafter で 1 つ戻す (toward-zero 化)。
      r  = fptrunc x            (nearest)
      chop(x>0): r > x なら nextafter(r, -inf) / r ≤ x なら r
      chop(x<0): r < x なら nextafter(r, +inf) / r ≥ x なら r
    冪等: 適用後は fptrunc の直接 store user が消えるため 2 回目は不発。
    """
    lines = body.split('\n')
    ins_after = {}                                # line idx → 挿入行リスト
    store_val = {}                                # line idx → 新 store 値
    cnt = [0]

    def mint():
        cnt[0] += 1
        return '%%x87c%d' % cnt[0]

    for li, ln in enumerate(lines):
        m = RE_FPTRUNC.match(ln)
        if not m:
            continue
        dst = m.group(2)
        srcval = m.group(3)
        n0, n1, n2, n3, n4, n5, n6, n7, n8, n9, n10 = (mint() for _ in range(11))
        for lj in range(li + 1, min(li + 40, len(lines))):
            l2 = lines[lj]
            if RE_LABEL.match(l2) or re.match(r'^\s*br ', l2):
                break
            ms = RE_F32STORE.match(l2)
            if ms and ms.group(2) == dst:
                ins_after[li] = [
                    '  %s = fpext float %s to double' % (n0, dst),
                    '  %s = fcmp ogt double %s, %s' % (n1, n0, srcval),
                    '  %s = fcmp olt double %s, %s' % (n2, n0, srcval),
                    '  %s = fcmp ogt double %s, 0.0' % (n7, srcval),
                    '  %s = fcmp olt double %s, 0.0' % (n8, srcval),
                    '  %s = and i1 %s, %s' % (n9, n7, n1),
                    '  %s = and i1 %s, %s' % (n10, n8, n2),
                    '  %s = call float @nextafterf(float %s, float 0x7FF0000000000000)' % (n3, dst),
                    '  %s = call float @nextafterf(float %s, float 0xFFF0000000000000)' % (n4, dst),
                    '  %s = select i1 %s, float %s, float %s' % (n5, n10, n3, dst),
                    '  %s = select i1 %s, float %s, float %s' % (n6, n9, n4, n5),
                ]
                store_val[lj] = n6
                break
    if not ins_after:
        return body, 0, False
    out = []
    for li, ln in enumerate(lines):
        if li in store_val:
            ms = RE_F32STORE.match(ln)
            out.append('%sstore float %s, %s' % (ms.group(1), store_val[li], ms.group(3)))
            continue
        out.append(ln)
        for part in ins_after.get(li, []):
            out.append(part)
    newbody = '\n'.join(out)
    need_decl = NEXTAFTER_DECL not in newbody and NEXTAFTER_DECL not in body
    return newbody, len(ins_after), need_decl



# ============================================================
# [R10] fist/fistp の overflow → 0x80000000 (indefinite) emulation
# ============================================================
RE_FPTOSI_LD = re.compile(r'^(\s*)(%[\w.$-]+) = fptosi double (%[\w.$-]+) to i32\s*$')
RE_LDDEF = re.compile(r'^\s*(%[\w.$-]+) = call double @__frontend_reg_load\.fpr\(i32 ([\w.%$-]+)\)\s*$')


def fix_fist_overflow(body, rep):
    """[R10] fptosi の入力が i32 範囲外のとき LLVM は poison (= 未定義)。機械語の fist は
    0x80000000 (indefinite) を返す。fptosi 直前で |v| ≥ 2^31 を 0xC1E0000000000000 (-2^31)
    へ clamp して等価化する。対象: fptosi の直接入力が frontend_reg_load の場合 (fist 模型)。
    冪等: 適用後は fptosi の入力が select になり再不発。
    """
    lines = body.split('\n')
    defs = {}
    for li, ln in enumerate(lines):
        m = RE_DEF.match(ln)
        if m:
            defs[m.group(1)] = (li, m.group(2))
    ins = {}            # fptosi line idx → (newv_name, v)
    for li, ln in enumerate(lines):
        m = RE_FPTOSI_LD.match(ln)
        if not m:
            continue
        v = m.group(3)
        # 入力チェーンを 3 段まで遡り, fist 由来 (load.fpr / fmul / fadd / rint) か判定
        ok = False
        cur = v
        for _ in range(3):
            d = defs.get(cur)
            if not d:
                ok = True                     # 定義不明 (引数等) でも対象内 fptosi は fist 模型
                break
            rhs = d[1]
            if '@__frontend_reg_load.fpr' in rhs:
                ok = True
                break
            mr = re.match(r'^call double @llvm\.rint\.f64\(double ([\w.%$-]+)\)$', rhs)
            mf = re.match(r'^(?:fmul|fadd|fsub) double ([\w.%$-]+), ([\w.%$-]+)$', rhs)
            if mr:
                cur = mr.group(1)
                continue
            if mf:
                cur = mf.group(1)
                ok = True                     # 積/和から直接 fptosi = fist 模型
                break
            break
        if not ok:
            continue
        nm = '%%x87v%d' % li
        ins[li] = (nm, v)
    if not ins:
        return body, 0, False
    out = []
    for li, ln in enumerate(lines):
        if li in ins:
            nm, v = ins[li]
            out.append('  %s = fcmp oge double %s, 0x41E0000000000000' % (nm + 'a', v))
            out.append('  %s = fcmp ole double %s, 0xC1E0000000000000' % (nm + 'b', v))
            out.append('  %s = or i1 %s, %s' % (nm + 'c', nm + 'a', nm + 'b'))
            out.append('  %s = select i1 %s, double 0xC1E0000000000000, double %s' % (nm, nm + 'c', v))
            ln = RE_FPTOSI_LD.match(ln).group(1) + RE_FPTOSI_LD.match(ln).group(2) + ' = fptosi double %s to i32' % nm
        out.append(ln)
    return '\n'.join(out), len(ins), True




def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--report')
    ap.add_argument('--funcs', default='', help='対象関数名カンマ区切り (空 = 自動検出全対象)')
    ap.add_argument('--chop-f32-fns', default='', help='[R6] fstp f32 chop 丸めを適用する関数名カンマ区切り')
    a = ap.parse_args()
    want = set(x for x in a.funcs.replace(',', ' ').split() if x)
    chop32 = set(x for x in a.chop_f32_fns.replace(',', ' ').split() if x)
    text = open(a.src, errors='replace').read()
    # [R3] グローバル fisub 零化修復 (devirtualized)
    text, nzero = fix_fsub_zero_global(text)
    starts = [m.start() for m in RE_FUNC.finditer(text)]
    head = text[:starts[0]] if starts else text
    chunks = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(text)
        seg = text[s:e]
        nl = seg.index('\n') + 1
        header = seg[:nl]
        rest = seg[nl:]
        mclose = rest.rindex('\n}\n')
        if mclose < 0:
            chunks.append([header, rest, ''])
        else:
            chunks.append([header, rest[:mclose], '\n}\n' + rest[mclose + 3:]])
    rep = {'ruleB_fsubzero_fixed': nzero, 'functions': []}
    nchop = 0
    need_nextafter = False
    need_fma = False
    for ci, (header, body, inter) in enumerate(chunks):
        m = re.search(r'@([\w.$-]+)\(', header)
        fname = m.group(1) if m else '?'
        if want and fname not in want:
            continue
        newbody, changed = process_function(header, body, fname, rep['functions'])
        if changed:
            body = newbody
        ovr_body, novr, ovr_chg = fix_fist_overflow(body, rep)
        if novr:
            body = ovr_body
            rep['functions'].append({'name': fname, 'status': 'fixed:fist-overflow', 'sites': novr})
        if fname in chop32:
            cbody, n, need_decl = fix_chop_f32(body, fname, rep)
            if n:
                body = cbody
                nchop += n
                need_nextafter = True
                rep['functions'].append({'name': fname, 'status': 'fixed:chop-f32', 'sites': n})
        chunks[ci][1] = body
    rep['ruleB_chop_f32'] = nchop
    result = head
    for header, body, inter in chunks:
        result += header + body + inter
    if need_nextafter and NEXTAFTER_DECL not in result:
        result = result.rstrip('\n') + '\n\n' + NEXTAFTER_DECL + '\n'
    if need_fma and FMA_DECL not in result:
        result = result.rstrip('\n') + '\n\n' + FMA_DECL + '\n'
    open(a.dst, 'w').write(result)
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1, ensure_ascii=False)
    fixed = sum(1 for r in rep['functions'] if r['status'] == 'fixed')
    skipped = sum(1 for r in rep['functions'] if r['status'].startswith('skip'))
    ok = sum(1 for r in rep['functions'] if r['status'] == 'already-correct')
    print('[x87fix] fixed=%d already-correct=%d skipped=%d fsubzero=%d chop_f32=%d' % (fixed, ok, skipped, nzero, nchop))


if __name__ == '__main__':
    main()
