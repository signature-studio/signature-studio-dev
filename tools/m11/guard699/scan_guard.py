#!/usr/bin/env python3
"""#699: 全 IR 関数の「ループ先頭ガード脱落」を機械語との分岐突合で走査する (検出器の実測版).

突合規則 (docs/DEFECTS.md 検出器設計 §1 の実装):
  0. IR ブロックは名前 (dec_label_pc_<VA>[.<suffix>]) で区別する。接尾辞付きブロック
     (.preheader / .crit_edge / .lr.ph 等) を直前ブロックに混ぜない (#1190)。
  1. 機械語 (.pdata 区間の線型 disasm; ldfix/ldmach.py) の各 jcc (命令 VA A, 絶対 target T) を取る。
  2. A を含む機械語ブロック B (A 以下で最大の VA) の帰属先は、同 VA の接尾辞無しブロック
     (無ければ接尾辞付きブロック) とする。B の後続集合 succ(B) (終端 br/switch のラベル VA) を取る。
  3. T ∉ succ(B) なら「jcc 脱落」候補 (dropped)。
  4. strict (= ループ先頭ガード型): dropped かつ A の直前 2 命令に cmp/test があり、T > A (前方の脱出先)、
     B の終端が無条件 br で後続 L が B より後方にあり、L の頭ブロックよりテキスト順で後ろのブロック C から back-edge を持つ (ループ先頭)。接尾辞付きの preheader (L と同 VA だがループ外) は前方にあるため候補から外れる (#1190 指摘 1)。
出力: 関数数 / jcc 数 / dropped 数 / strict 数 と strict 一覧 (JSON)。
使い方: python3 guard699/scan_guard.py <IR.ll> --pe <PE.bin> --report <out.json>
判定 (positive control): 8c5eb0 の (A=8c5f18, T=8c6066, L=8c5f23) が guard 脱落 IR で strict に出ること。
"""
import argparse
import bisect
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'ldfix'))
from ldmach import Machine, FnMach  # noqa: E402

DEF_RE = re.compile(r'^define [^@\n]*@(function_[0-9a-f]+)\(', re.M)
BLK_RE = re.compile(r'^dec_label_pc_([0-9a-f]+)((?:\.[A-Za-z0-9_.]+)?):', re.M)
LABEL_RE = re.compile(r'label %dec_label_pc_([0-9a-f]+)(?:\.[A-Za-z0-9_.]+)?')
HEX_OP = re.compile(r'0x[0-9a-f]+')


def parse_blocks(body):
    """名前 (VA + 接尾辞) -> {va, succ, uncond, term}。挿入順 = IR のテキスト順。"""
    blocks = {}
    cur = None
    for line in body.split('\n'):
        m = BLK_RE.match(line)
        if m:
            cur = m.group(1) + m.group(2)
            blocks[cur] = {'va': int(m.group(1), 16), 'lines': []}
        elif cur is not None and line.strip():
            blocks[cur]['lines'].append(line)
    out = {}
    for name, b in blocks.items():
        term = ''
        for line in b['lines']:
            if re.match(r'^\s+(br|ret|switch|unreachable|indirectbr)\b', line):
                term = line
        succ = set(int(x, 16) for x in LABEL_RE.findall(term))
        out[name] = {'va': b['va'], 'succ': succ, 'uncond': term.lstrip().startswith('br label'), 'term': term}
    return out


def owners(blocks):
    """VA -> 機械語を持つブロック名。接尾辞無しを優先し、無ければテキスト順の先頭。"""
    by_va = {}
    for name, b in blocks.items():
        by_va.setdefault(b['va'], []).append(name)
    own = {}
    ambiguous = 0
    for va, names in by_va.items():
        plain = [n for n in names if '.' not in n]
        if not plain and len(names) > 1:
            ambiguous += 1
        own[va] = plain[0] if plain else names[0]
    return own, ambiguous


def after_head(blocks, own, L):
    """ループ先頭 L の頭ブロックより IR テキスト順で後ろにあるブロック名 (back-edge の候補 C)。
    接尾辞付きの preheader (L と同 VA だがループの外側) は前方にあるため除外される (#1190 指摘 1)。"""
    head = own.get(L)
    if head is None:
        return []
    names = list(blocks)
    return names[names.index(head) + 1:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--report')
    a = ap.parse_args()

    text = open(a.ir, errors='replace').read()
    mach = Machine(a.pe)
    st = Counter()
    strict = []
    for m in DEF_RE.finditer(text):
        name = m.group(1)
        va = int(name[len('function_'):], 16)
        end = text.index('\n}', m.end()) + 2
        blocks = parse_blocks(text[m.start():end])
        if not blocks:
            st['fn_noblock'] += 1
            continue
        own, ambiguous = owners(blocks)
        st['owner_va_suffix_only_multi'] += ambiguous
        st['blk_suffixed'] += sum(1 for n in blocks if '.' in n)
        fv = FnMach(mach, va, list(own.keys()))
        if not fv.ins:
            st['fn_nomach'] += 1
            continue
        st['fn'] += 1
        bvs = sorted(own.keys())
        ins = fv.ins
        for idx, i in enumerate(ins):
            mn = i.mnemonic
            if not (mn.startswith('j') and mn != 'jmp' and HEX_OP.fullmatch(i.op_str or '')):
                continue
            st['jcc'] += 1
            A = i.address
            T = int(i.op_str, 16)
            k = bisect.bisect_right(bvs, A) - 1
            if k < 0:
                st['jcc_noblock'] += 1
                continue
            B = bvs[k]
            info = blocks[own[B]]
            if T in info['succ']:
                continue
            if T not in own:
                st['dropped_target_not_label'] += 1
                continue
            st['dropped'] += 1
            cmp_before = any(j.mnemonic in ('cmp', 'test') for j in ins[max(0, idx - 2):idx])
            L = next(iter(info['succ'])) if (info['uncond'] and len(info['succ']) == 1) else None
            if not (cmp_before and T > A and L is not None and L > B and L != T):
                continue
            back = any(L in blocks[n]['succ'] for n in after_head(blocks, own, L))
            if back:
                st['strict'] += 1
                strict.append({'fn': name, 'jcc': '%x' % A, 'target': '%x' % T, 'loop_head': '%x' % L,
                               'block': '%x' % B, 'mnemonic': mn})
    rep = {'ir': a.ir, 'counts': dict(st), 'strict': strict}
    print('[scan_guard] ' + json.dumps({k: st[k] for k in sorted(st)}, ensure_ascii=False))
    for s in strict[:50]:
        print('[scan_guard] strict %(fn)s jcc=%(jcc)s %(mnemonic)s -> %(target)s loop_head=%(loop_head)s' % s)
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
