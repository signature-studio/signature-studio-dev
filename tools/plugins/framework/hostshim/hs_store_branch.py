#!/usr/bin/env python3
"""hs_store_branch.py — 応答スロット [rbp+0x11a0] への格納 (27 行) の分岐条件を機械語から出す (#4075 / PLG-P0b-42)。

入力: REPORT_DISPATCHER_APPENDIX_3735.md §5 の格納 VA (既定 27 件)。
出力: 格納ごとに、
  * 格納を支配する最後の条件分岐 (jcc)。格納は分岐の成立側 (taken) か不成立側 (fall) か。
  * その jcc のフラグを決める直前の cmp/test と、そのオペランドの供給元 (直前の書込み)。
  * 支配関係: 関数内の CFG で、格納への全経路が jcc の該当側を通るか (支配判定)。

方式: 関数 [FN_LO, FN_HI) を逆アセンブルし、基本ブロックと後続関係を作る。
格納 S を含むブロックを起点に、後戻りを除く逆向き探索で「S へ至る経路」を列挙し、
どの jcc の枝を必ず通るかを求める (支配 = その枝を外すと S に届かない)。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_store_branch.py [VA...]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pefile
import hs_resp_src as S
import hs_disp_emu as E

STORES27 = [
    0x1319f13, 0x1319f1f, 0x1320fc4, 0x1320ff9, 0x13218c1, 0x1321966, 0x13219b0, 0x1321b6c,
    0x1321bb0, 0x1321f0e, 0x1321f34, 0x1321f6c, 0x1321fc2, 0x132206e, 0x13220b2, 0x13220be,
    0x13220ef, 0x132210a, 0x13221be, 0x132257d, 0x132268e, 0x132415e, 0x132567c, 0x1326b9a,
    0x1320fda, 0x13210e8, 0x1321225,
]

JCC = {'je', 'jne', 'jz', 'jnz', 'ja', 'jae', 'jb', 'jbe', 'jg', 'jge', 'jl', 'jle', 'js', 'jns', 'jp', 'jnp', 'jo', 'jno'}
JMP = {'jmp'}
RET = {'ret'}


def decode(read_va):
    code = read_va(E.FN_LO, E.FN_HI - E.FN_LO)
    insns = list(S.md.disasm(code, E.FN_LO))
    return insns, {i.address: i for i in insns}


def successors(ins, idx):
    """命令 ins の後続 VA。jcc は (taken, fall)、jmp は (target,)、ret は ()。"""
    nxt = ins.address + ins.size
    if ins.mnemonic in JCC:
        tgt = int(ins.op_str, 16) if ins.op_str.startswith('0x') else None
        return (tgt, nxt) if tgt is not None else (nxt,)
    if ins.mnemonic in JMP:
        tgt = int(ins.op_str, 16) if ins.op_str.startswith('0x') else None
        return (tgt,) if tgt is not None else ()
    if ins.mnemonic in RET:
        return ()
    return (nxt,)


def build_graph(insns, idx):
    """入口から到達する命令の後続・先行の表と、逆後順 (RPO) の番号を作る。"""
    entry = E.FN_LO
    succ = {}
    stack = [entry]
    while stack:
        a = stack.pop()
        if a in succ or a not in idx:
            continue
        ss = [s for s in successors(idx[a], idx) if s is not None and s in idx]
        succ[a] = ss
        stack.extend(ss)
    pred = {a: [] for a in succ}
    for a, ss in succ.items():
        for s in ss:
            if s in pred:
                pred[s].append(a)
    order, seen = [], set()

    def dfs(n):
        stk = [(n, iter(succ.get(n, [])))]
        seen.add(n)
        while stk:
            node, it = stk[-1]
            for nx in it:
                if nx not in seen and nx in succ:
                    seen.add(nx)
                    stk.append((nx, iter(succ.get(nx, []))))
                    break
            else:
                order.append(node)
                stk.pop()

    dfs(entry)
    rpo = list(reversed(order))
    num = {n: i for i, n in enumerate(rpo)}
    return succ, pred, rpo, num


def idoms(pred, rpo, num):
    """Cooper-Harvey-Kennedy の支配木 (idom)。"""
    entry = rpo[0]
    idom = {entry: entry}

    def intersect(a, b):
        while a != b:
            while num[a] > num[b]:
                a = idom[a]
            while num[b] > num[a]:
                b = idom[b]
        return a

    changed = True
    while changed:
        changed = False
        for n in rpo[1:]:
            ps = [p for p in pred.get(n, []) if p in idom]
            if not ps:
                continue
            new = ps[0]
            for p in ps[1:]:
                new = intersect(p, new)
            if idom.get(n) != new:
                idom[n] = new
                changed = True
    return idom


def dominating_branches(insns, idx, store, g):
    """store への全経路が必ず通る jcc の枝 (jcc VA, 側) を列挙する。
    支配木で store の支配者を辿り、枝の先 t が store を支配し、かつ t の先行が jcc だけなら、その枝は必須。"""
    succ, pred, rpo, num = g
    if store not in num:
        return None
    dom = idoms(pred, rpo, num)
    out = []
    n = store
    while True:
        n = dom[n]
        if n == E.FN_LO or n not in idx:
            break
        if idx[n].mnemonic in JCC:
            taken, fall = successors(idx[n], idx)
            for side, dst in (('taken', taken), ('fall', fall)):
                if dst is None or dst not in dom:
                    continue
                if dst == store or dominates(dom, dst, store):
                    if set(pred.get(dst, [])) == {n} or dst == store:
                        out.append((n, side))
        if n == dom[n]:
            break
    return out


def dominates(dom, a, b):
    """a が b を支配するか (dom は idom の表)。"""
    while True:
        if a == b:
            return True
        nb = dom.get(b)
        if nb is None or nb == b:
            return False
        b = nb


def flag_setter(insns, pos, jcc_addr):
    """jcc の直前で最後にフラグを立てた命令 (cmp/test/sub/and/add/or/xor 等) を探す。"""
    flagops = {'cmp', 'test', 'sub', 'and', 'add', 'or', 'xor', 'inc', 'dec'}
    for k in range(pos - 1, max(-1, pos - 40), -1):
        i = insns[k]
        if i.mnemonic in flagops:
            return i
    return None


REG_ALIAS = {'eax': 'rax', 'rax': 'rax', 'al': 'rax', 'ax': 'rax',
             'ecx': 'rcx', 'rcx': 'rcx', 'cl': 'rcx', 'edx': 'rdx', 'rdx': 'rdx', 'dl': 'rdx',
             'r8': 'r8', 'r9': 'r9', 'rbx': 'rbx', 'ebx': 'rbx', 'rsi': 'rsi', 'rdi': 'rdi'}


def operands(ins):
    s = ins.op_str
    depth, cur, parts = 0, '', []
    for ch in s:
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def writes_reg(ins, reg):
    """命令が reg (正規化名) を書くか。先頭オペランドが宛先の命令だけを見る (cmp/test は書かない)。"""
    if ins.mnemonic in ('cmp', 'test', 'push', 'jmp') or ins.mnemonic in JCC:
        return False
    if ins.mnemonic == 'call':
        return reg == 'rax'
    ops = operands(ins)
    if not ops:
        return False
    return REG_ALIAS.get(ops[0]) == reg


def writes_mem(ins, mem):
    if ins.mnemonic in ('cmp', 'test', 'push') or ins.mnemonic in JCC:
        return False
    ops = operands(ins)
    return bool(ops) and ops[0].endswith(mem)


def supplier(insns, pos, opnd):
    """フラグ供給命令のオペランド opnd の供給元を、直前へ線形に逆向きに辿る (候補であり、分岐をまたぐため確定ではない)。"""
    parts = operands_of_flagsetter(opnd)
    if parts is None:
        return None
    kind, key = parts
    if kind == 'reg':
        for k in range(pos - 1, max(-1, pos - 300), -1):
            i = insns[k]
            if writes_reg(i, key):
                return '0x%x %s %s' % (i.address, i.mnemonic, i.op_str)
        return '(窓内に書込みなし)'
    for k in range(pos - 1, max(-1, pos - 300), -1):
        i = insns[k]
        if writes_mem(i, key):
            return '0x%x %s %s' % (i.address, i.mnemonic, i.op_str)
    return '(窓内に書込みなし)'


def operands_of_flagsetter(opnd):
    o = opnd.strip()
    if o.startswith('qword ptr ') or o.startswith('byte ptr ') or o.startswith('dword ptr ') or '[' in o:
        m = o[o.index('['):]
        return ('mem', m)
    key = REG_ALIAS.get(o)
    if key is None:
        return None
    return ('reg', key)


def main():
    vas = [int(a, 0) for a in sys.argv[1:]] or STORES27
    pe = pefile.PE(E.PE_PATH, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    rd = S.make_reader(pe, base)
    insns, idx = decode(rd)
    g = build_graph(insns, idx)
    pos_of = {i.address: k for k, i in enumerate(insns)}
    for st in vas:
        print('==== 0x%x' % st)
        if st not in idx:
            print('  (命令境界に揃わない)')
            continue
        sI = idx[st]
        print('  store: 0x%x %s %s' % (sI.address, sI.mnemonic, sI.op_str))
        doms = dominating_branches(insns, idx, st, g)
        if doms is None:
            print('  (関数入口から到達しない)')
            continue
        if not doms:
            print('  dominating jcc: なし (全 ID 共通経路)')
            continue
        for ja, side in doms:
            j = idx[ja]
            k = pos_of[ja]
            fs = flag_setter(insns, k, ja)
            print('  jcc: 0x%x %s %s  -> %s 側必須' % (j.address, j.mnemonic, j.op_str, side))
            if fs:
                print('    flags: 0x%x %s %s' % (fs.address, fs.mnemonic, fs.op_str))
                fk = pos_of[fs.address]
                print('    supplier(線形の直前書込み・候補): %s' % supplier(insns, fk, operands(fs)[0]))


if __name__ == '__main__':
    main()
