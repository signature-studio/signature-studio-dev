#!/usr/bin/env python3
"""mx_ir_zeroinit.py — MX-2 IR zero-init pass (CAB-265 / MX2-1)。

RetDec (x86-64) の raw .ll は reg2mem 化の際に「store 前に load する」alloca
(未初期化読み出し) を残す。ネイティブではこれが「スタックのゴミ」を読む動作に
なり最適化レベルで結果が変わる (C 規格的には UB)。wasm/emcc では特に深刻:

  -O0 : entry block の store が実行されないため reg2mem alloca は 0 (= スタックの
        ゼロ初期化と偶然一致) → 11/11 PASS
  -O1+: LLVM が icmp の前に load を hoist / undef 畳み込みし、未初期化
        dereference (MSVC std::string の "add -8; load" = ヒープブロック先頭の
        サイズ読出し) → "memory access out of bounds" TRAP 6/11 PASS

本 pass は **dominance 解析で「初期化前に読まれる可能性がある alloca」** を求め、
entry block 先頭に `store <zero>` を挿入して決定論的な 0 初期化にする。
対象の数え方 (規則 36): 1 モジュール内の `define` 関数ごとに、load を含む block を
`store` を含む block のいずれかが dominate していない alloca = 未初期化読み出し候補。

既知欠陥類型 (DEFECTS.md) との関係: **D11 該当**。0x180724c60 は pdata 関数
0x180724b70 の offset 208 = interior call。これを RetDec が string-builder と
推定し mock は `return 0` のみ → SSO バッファ (stack_var_-848) が未初期化で残る。
D11 が無ければ 0x180724b70 の真入口から lift され store が入るため未初期化にならない。

usage: mx_ir_zeroinit.py in.ll out.ll [--report r.json] [--check] [--dry-run]
"""
import argparse
import collections
import json
import re
import sys

LABEL_RE = re.compile(r'^([A-Za-z0-9_.]+):\s*(?:;.*)?$')
ALLOC_RE = re.compile(r'^\s*(%[\w.$-]+)\s*=\s*alloca\s+(\S+)')
LOAD_RE = re.compile(r'^\s*(%[\w.$-]+)\s*=\s*load\s+(\S+?),\s*(ptr\s+%[\w.$-]+)\s*(?:,.*)?$')
STORE_RE = re.compile(r'^\s*store\s+(.*)$')
STORE_PTR_RE = re.compile(r'^store\s+\S+.*,\s*(ptr\s+%[\w.$-]+)\s*(?:,.*)?$')
BR_RE = re.compile(r'^\s*br\s+i1\s+.*,\s*label\s+%([A-Za-z0-9_.]+),\s*label\s+%([A-Za-z0-9_.]+)')
BRL_RE = re.compile(r'^\s*br\s+label\s+%([A-Za-z0-9_.]+)')
SWITCH_RE = re.compile(r'^\s*switch\s+.*\s*\[', re.S)
UNREACH_RE = re.compile(r'^\s*ret\s')


def fn_ranges(lines):
    """(名前, 開始行, 終了行) のリスト。名前は @ を除いた LLVM シンボル
    (mkrun_merge の _pre rename 後も拾うため function_<hex> に限定しない)。"""
    out, cur = [], None
    for i, l in enumerate(lines):
        if l.startswith('define'):
            m = re.search(r'@([\w.$]+)\(', l)
            cur = (m.group(1) if m else None, i) if m else None
        elif l.startswith('}') and cur:
            out.append((cur[0], cur[1], i))
            cur = None
    return out


def split_blocks(lines, s, e):
    """→ OrderedDict[block] = (indices of instrs) と block 順序リスト"""
    blocks = collections.OrderedDict()
    cur = None
    for i in range(s + 1, e):
        l = lines[i]
        m = LABEL_RE.match(l)
        if m:
            cur = m.group(1)
            blocks[cur] = []
        elif cur is not None:
            blocks[cur].append(i)
    return blocks


def preds(blocks, order):
    """直接先行 block 集合"""
    p = collections.defaultdict(set)
    for b in order:
        for tgt in succ_of(blocks, b):
            if tgt in blocks:
                p[tgt].add(b)
    return p


def succ_of(blocks, b):
    out = []
    for i in blocks[b]:
        l = lines_g[0][i]
        m = BR_RE.match(l)
        if m:
            return [m.group(1), m.group(2)]
        m = BRL_RE.match(l)
        if m:
            return [m.group(1)]
        m = SWITCH_RE.match(l)
        if m:                     # switch: 全 label を拾う (粗い conservative)
            out = re.findall(r'label\s+%([A-Za-z0-9_.]+)', l)
            return out
    return out


lines_g = [None]


def dom_analysis(blocks, order):
    """iterative dominators: dom[b] = b を dominate する block 集合"""
    idx = {b: i for i, b in enumerate(order)}
    universe = set(order)
    dom = {b: set(universe) for b in order}
    if not order:
        return dom
    entry = order[0]
    dom[entry] = {entry}
    changed = True
    while changed:
        changed = False
        for b in order:
            if b == entry:
                continue
            pred = preds(blocks, order).get(b, set())
            new = None
            for pb in pred:
                if pb not in dom:
                    continue
                new = set(dom[pb]) if new is None else (new & dom[pb])
            if new is None:
                new = set()
            new |= {b}
            if new != dom[b]:
                dom[b] = new
                changed = True
    return dom


def zero_const(ty):
    if ty == 'i1':
        return 'i8 0'
    if ty in ('i8', 'i16', 'i32', 'i64', 'i128', 'half', 'float', 'double'):
        return '%s 0' % ty
    if ty == 'ptr' or ty.endswith('*'):
        return 'ptr null'
    if ty.startswith('['):
        return '%s zeroinitializer' % ty
    return None


def uninit_reads(lines, s, e):
    """(alloca 名, alloca 型) → 初期化前に load されたか。dominance ベース。"""
    blocks = split_blocks(lines, s, e)
    order = list(blocks.keys())
    # entry から到達不能な block (RetDec が残す死んだ block) は dom={自分のみ} になり
    # 後続の共通部分を空にして偽陽性を出すため、解析対象から外す
    seen, stack = set(), order[:1]
    while stack:
        b = stack.pop()
        if b in seen or b not in blocks:
            continue
        seen.add(b)
        stack.extend(succ_of(blocks, b))
    order = [b for b in order if b in seen]
    dom = dom_analysis(blocks, order)
    allocas = {}          # name -> (ty, entry index of alloca insn)
    for i in range(s + 1, e):
        m = ALLOC_RE.match(lines[i])
        if m and m.group(1) not in allocas:
            allocas[m.group(1)] = (m.group(2).rstrip(','), i)
    stores = collections.defaultdict(list)   # name -> [block, ...]
    for b in order:
        for i in blocks[b]:
            m = STORE_PTR_RE.match(lines[i].strip())
            if m:
                stores[m.group(1).split()[-1]].append(b)
    bad = {}
    for b in order:
        for i in blocks[b]:
            lm = LOAD_RE.match(lines[i])
            if not lm:
                continue
            var = lm.group(3).split()[-1]
            if var not in allocas:
                continue
            sb = stores.get(var, [])
            # この load に到達する全ての経路に store があるか = dom[b] ∩ store blocks
            if not any(x in dom[b] for x in sb):
                bad[var] = allocas[var]
    return bad, blocks, order


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--report', default=None)
    ap.add_argument('--check', action='store_true',
                    help='pass 適用後に未初期化読み出し候補が 0 件であることを検証')
    ap.add_argument('--dry-run', action='store_true', help='件数のみ出力')
    a = ap.parse_args()

    global lines_g
    lines = open(a.src).read().splitlines()
    lines_g[0] = lines
    report = {'fn': {}, 'skipped': []}

    # パス後の再検証用に全関数の候補を先に集計
    cand_all = {}
    for (fva, s, e) in fn_ranges(lines):
        bad, blocks, order = uninit_reads(lines, s, e)
        cand_all[fva] = bad

    out = list(lines)
    # 後ろから挿入 (index をずらさないため)
    total = 0
    for (fva, s, e) in reversed(fn_ranges(out)):
        lines_g[0] = out                 # 解析対象は挿入済み out (線番号も out 基準)
        bad, blocks, order = uninit_reads(out, s, e)
        if bad:
            report['fn']['%s' % fva] = {
                'n': len(bad),
                'vars': sorted(k.lstrip('%') for k in bad),
            }
        # 挿入位置 = entry block の最後の alloca の直後
        entry = order[0]
        last_alloc = None
        for i in blocks[entry]:
            if ALLOC_RE.match(out[i]):
                last_alloc = i
        if last_alloc is None or not bad:
            continue
        ins = []
        for var in sorted(bad):
            ty = bad[var][0].rstrip(',')
            z = zero_const(ty)
            if z is None:
                report['skipped'].append({'fn': '%s' % fva, 'var': var, 'ty': ty})
                continue
            ins.append('  store %s, ptr %s, align 1 ; MX2-1 zero-init (CAB-265)' % (z, var))
            total += 1
        out[last_alloc + 1:last_alloc + 1] = ins
        report['fn']['%s' % fva]['inserted'] = len(ins)

    report['zero_stores'] = total
    report['fn_count'] = len(fn_ranges(lines))
    report['fn_with_uninit'] = sum(1 for v in cand_all.values() if v)

    if a.check:
        lines_g[0] = out
        leftover = {}
        for (fva, s, e) in fn_ranges(out):
            bad, blocks, order = uninit_reads(out, s, e)
            if bad:
                leftover['%s' % fva] = sorted(k.lstrip('%') for k in bad)
        report['check_leftover_uninit_reads'] = leftover
        if leftover:
            raise SystemExit('check fail: 未初期化読み出し候補が残存: %s' % leftover)

    if a.dry_run:
        print('mx_ir_zeroinit(dry): %d fn 中 %d 個に候補, zero-store 予定 %d'
              % (report['fn_count'], report['fn_with_uninit'], total))
        return
    open(a.dst, 'w').write('\n'.join(out) + '\n')
    if a.report:
        json.dump(report, open(a.report, 'w'), ensure_ascii=False, indent=1)
    print('mx_ir_zeroinit: %d fn 中 %d 個に未初期化読み出し候補 → zero-store %d 本 -> %s'
          % (report['fn_count'], report['fn_with_uninit'], total, a.dst))


if __name__ == '__main__':
    main()
