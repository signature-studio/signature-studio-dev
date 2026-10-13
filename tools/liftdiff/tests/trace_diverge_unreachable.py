#!/usr/bin/env python3
"""LD-7 (#307): m11 wasm_trap/unreachable 218 件の native/wasm trace 分岐点を独立に再計算する。

各関数の最初の unreachable case について trace_head (関数入口 VA 列) を native/wasm で比較し、
先頭から最初に食い違う位置の直前の関数 L (= 最後の共通 entry) を求める。L の機械語 (PE) に
メモリ間接 call (`call qword ptr [reg+disp]`、rip 相対 = IAT 経由は除く) があるか、
lift 後 IR (boot_final3.ll) の L に対応する call 数が機械語の直接 call 数以下かを調べる。

  python3 tools/liftdiff/tests/trace_diverge_unreachable.py > tools/liftdiff/results/m11_unreachable_diverge.md

--pe 省略時は $LD_M11_PE、無ければ targets/m11.json の pe。入力既定 = tools/liftdiff/work/m11/batch_closure.jsonl・
tools/m11/work/boot_final3.ll (cwd 非依存)。引数: [--pe PE.bin] [batch.jsonl] [boot_final3.ll]

判定は「D15 型候補」: 機械語のメモリ間接 call と IR の call を call site / block 単位では対応づけていない。
trace_head が両側で同一のまま終わる関数 (食い違いが観測できない) は分岐点の集計から除き別枠で数える。
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from ldlib.pe import PE  # noqa: E402
import capstone  # noqa: E402
from capstone import x86_const as X  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('batch', nargs='?', default=os.path.join(ROOT, 'work/m11/batch_closure.jsonl'))
ap.add_argument('ir', nargs='?', default=os.path.join(ROOT, '../m11/work/boot_final3.ll'))
ap.add_argument('--pe', default=os.environ.get('LD_M11_PE') or json.load(open(os.path.join(ROOT, 'targets/m11.json')))['pe'])
A = ap.parse_args()

pe = PE(A.pe)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True


def mach(va):
    """関数 va の機械語を ret/int3 (最初の無条件終端) まで線形に読み、(直接 call 先集合, メモリ間接 call 数) を返す。
    分岐先の先読みはしない近似だが、対象は短い Delphi RTL 関数のみ。"""
    data = pe.read(va - pe.base, 0x600)
    direct, mem_ind, reg_ind = set(), 0, 0
    for i in md.disasm(data, va):
        if i.id == X.X86_INS_CALL:
            op = i.operands[0]
            if op.type == X.X86_OP_IMM:
                direct.add(op.imm)
            elif op.type == X.X86_OP_MEM:
                if op.mem.base == X.X86_REG_RIP:
                    pass
                else:
                    mem_ind += 1
            else:
                reg_ind += 1
        if i.id in (X.X86_INS_RET, X.X86_INS_INT3):
            break
    return direct, mem_ind, reg_ind


def tail_jmps(va):
    """関数 va を ret/int3 まで読み、無条件 jmp の飛び先が [va, 終端] の外にあるもの (tail jump 候補) を返す。"""
    ins = []
    for i in md.disasm(pe.read(va - pe.base, 0x600), va):
        ins.append(i)
        if i.id in (X.X86_INS_RET, X.X86_INS_INT3):
            break
    end = ins[-1].address
    return [i.operands[0].imm for i in ins
            if i.id == X.X86_INS_JMP and i.operands[0].type == X.X86_OP_IMM
            and not (va <= i.operands[0].imm <= end)]


def is_cand(d, mi, ic):
    return mi > 0 and ic is not None and ic <= len(d)


def ir_calls(ir_text_by_fn, va):
    body = ir_text_by_fn.get('function_%x' % va)
    if body is None:
        return None
    return len(re.findall(r'\bcall\b', body))


def load_ir(path, want):
    out = {}
    cur, buf = None, []
    pat = re.compile(r'^define .*@(function_[0-9a-f]+)\(')
    for line in open(path):
        if cur is None:
            m = pat.match(line)
            if m and m.group(1) in want:
                cur, buf = m.group(1), [line]
        else:
            buf.append(line)
            if line.startswith('}'):
                out[cur] = ''.join(buf)
                cur = None
    return out


def main():
    rows = [json.loads(l) for l in open(A.batch)]
    un = []
    for r in rows:
        cs = [c for c in r['cases'] if c['outcome'] == 'wasm_trap']
        if cs and (cs[0].get('wasm_detail') or '').startswith('unreachable') and cs[0].get('wasm_status') != 'badjson':
            un.append((r, cs[0]))
    div = collections.Counter()
    ex = {}
    nodiv = collections.Counter()   # trace_head が両側で同一 (食い違い未観測): (trace_len 同一で打切りか, 件数)
    for r, c in un:
        N = [int(t[0], 16) for t in c['raw']['native']['trace_head']]
        W = [int(t[0], 16) for t in c['raw']['wasm']['trace_head']]
        i = 0
        while i < len(N) and i < len(W) and N[i] == W[i]:
            i += 1
        if i == len(N) == len(W):
            nl, wl = c['raw']['native'].get('trace_len'), c['raw']['wasm'].get('trace_len')
            nodiv[(nl, wl)] += 1
            continue
        L = N[i - 1] if i else None
        nn = N[i] if i < len(N) else None
        ww = W[i] if i < len(W) else None
        div[(L, nn, ww)] += 1
        ex.setdefault((L, nn, ww), r['function']['va'])
    last = collections.Counter()
    for (L, nn, ww), n in div.items():
        last[L] += n
    irs = load_ir(A.ir, {'function_%x' % L for L in last if L})

    w = print
    w('<!-- 自動生成: python3 tools/liftdiff/tests/trace_diverge_unreachable.py > tools/liftdiff/results/m11_unreachable_diverge.md (既定入力 = tools/liftdiff/work/m11/batch_closure.jsonl, tools/m11/work/boot_final3.ll, PE = $LD_M11_PE。cwd 非依存) (LD-7, #307) -->')
    w('# m11 unreachable の native/wasm trace 分岐点 (LD-7, #307)')
    w('')
    n_div = sum(div.values())
    w('対象 = 最初の wasm_trap case が unreachable の関数 **%d** (batch jsonl %d 行)。うち trace_head 内で食い違いを観測した **%d**、'
      'trace_head が native/wasm で完全一致し食い違い未観測 **%d** (分岐点集計から除外、§4)。' % (len(un), len(rows), n_div, len(un) - n_div))
    w('trace_head (関数入口 VA 列、最大 12 件) を native/wasm で先頭から比較し、最初に食い違う直前の関数 L を求める。')
    w('')
    w('## 1. 最後の共通 entry L ごとの件数')
    w('')
    w('| L | 件数 | L の直接 call 数 | L のメモリ間接 call (非 rip) | L のレジスタ間接 call | lift 後 IR の call 数 | 判定 |')
    w('|---|---:|---:|---:|---:|---:|---|')
    drop_total = 0
    drop_L = []
    for L, n in last.most_common():
        if L is None:
            w('| (先頭から不一致) | %d | | | | | |' % n)
            continue
        d, mi, ri = mach(L)
        ic = ir_calls(irs, L)
        drop = is_cand(d, mi, ic)
        if drop:
            drop_total += n
            drop_L.append(L)
        w('| 0x%x | %d | %d | %d | %d | %s | %s |' % (L, n, len(d), mi, ri, ic if ic is not None else '-',
                                                    '**D15 型候補 (メモリ間接 call 脱落の疑い)**' if drop else ''))
    w('')
    w('候補条件 = メモリ間接 call を持ち、かつ IR の call 数 ≤ 機械語の直接 call 先 (distinct) 数。該当 L の件数: **%d / %d** (分母 = 食い違い観測 %d)。' % (drop_total, n_div, n_div))
    w('call site / block は対応づけていない (直接 call の脱落や重複 call の集約でも成立しうる) ため **D15 型の確定ではなく候補**。')
    w('')
    f = lambda v: '-' if v is None else '0x%x' % v
    w('## 2. 分岐の型 (LD-17 / #864)')
    w('')
    w('§1 の D15 型候補を先に除き、残りを排他的に分類する (上から順に判定)。L の直接 call 先 = 機械語の直接 call 先集合 d。')
    w('')
    w('| 型 | 件数 | 上位 L (件数) |')
    w('|---|---:|---|')
    kinds = collections.OrderedDict([
        ('A', 'D15 型候補 (§1)'),
        ('B', 'L が leaf (ret まで call 無し・tail jump 無し)。食い違いは L の戻り後の呼出元で起きる (推定。根拠: 下記 tail jump 検出)'),
        ('C', 'L の直接 call 先で分岐 (native/wasm の次 entry のどちらかが d に含まれる)'),
        ('D', 'L の直接 call 先に含まれない分岐 (未特定)'),
        ('E', 'trace_head 先頭から不一致 (L 無し)'),
    ])
    by_kind = collections.defaultdict(collections.Counter)
    for (L, nn, ww), n in div.items():
        if L is None:
            k = 'E'
        else:
            d, mi, ri = mach(L)
            ic = ir_calls(irs, L)
            if is_cand(d, mi, ic):
                k = 'A'
            elif not d and not mi and not ri and not tail_jmps(L):
                k = 'B'
            elif nn in d or ww in d:
                k = 'C'
            else:
                k = 'D'
        by_kind[k][L] += n
    for k, label in kinds.items():
        tot = sum(by_kind[k].values())
        top = ', '.join('%s (%d)' % (f(L), m) for L, m in by_kind[k].most_common(3))
        w('| %s: %s | %d | %s |' % (k, label, tot, top))
    w('')
    tj = sorted({L for (L, _, _) in div if L is not None and not any(mach(L)) and tail_jmps(L)})
    w('型 B の根拠: 型 B の L 以外に、call 無し leaf のうち tail jump 先を持つ L は %s (これらは型 D に入る)。' % (
        ', '.join(f(L) for L in tj) if tj else 'なし'))
    w('')
    w('内訳の合計 = 食い違い観測 %d。型 A 以外 (B+C+D) = 未特定の残り **%d**。' % (
        n_div, n_div - sum(by_kind['A'].values())))
    w('')
    w('## 3. 分岐 (L, native 次, wasm 次) 上位')
    w('')
    w('| L | native 次 | wasm 次 | 件数 | 例 |')
    w('|---|---|---|---:|---|')
    for (L, nn, ww), n in div.most_common(12):
        w('| %s | %s | %s | %d | %s |' % (f(L), f(nn), f(ww), n, ex[(L, nn, ww)]))
    w('')
    w('## 4. trace_head が完全一致で食い違い未観測の関数 (分岐点集計から除外)')
    w('')
    w('| native trace_len | wasm trace_len | 件数 | 備考 |')
    w('|---:|---:|---:|---|')
    for (nl, wl), n in sorted(nodiv.items(), key=lambda kv: -kv[1]):
        note = 'trace_head 上限 12 で打切り (以降の食い違いは不明)' if (nl or 0) > 12 or (wl or 0) > 12 else 'trace 全体が一致 (trap までの関数入口列が同一)'
        w('| %s | %s | %d | %s |' % (nl, wl, n, note))
    w('')
    w('## 5. ネガティブコントロール (候補判定の検査)')
    w('')
    w('候補 L の IR に call を 1 行足すと、判定が外れることを確認する (IR 本文を文字列で書き換えて同じ関数で再判定)。')
    w('')
    w('| L | 書換前 IR call 数 | 判定 | 書換後 IR call 数 | 判定 |')
    w('|---|---:|---|---:|---|')
    for L in drop_L:
        body = irs.get('function_%x' % L)
        d, mi, _ = mach(L)
        fake = {'function_%x' % L: body.replace('\n}', '\n  %nc = call i64 @nc_dummy()\n' * (len(d) + 1) + '}', 1)}
        a, b = ir_calls(irs, L), ir_calls(fake, L)
        w('| 0x%x | %d | %s | %d | %s |' % (L, a, '候補' if is_cand(d, mi, a) else '非候補', b, '候補' if is_cand(d, mi, b) else '非候補'))


if __name__ == '__main__':
    main()
