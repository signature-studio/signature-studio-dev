#!/usr/bin/env python3
"""MX-39 (#3776) U4d: MSVC funclet の深い closure 到達と E8/E9 一致候補の由来 (命令境界で判定)。

入力は mx_closure.py の出力 (<prefix>_sets.pkl・linear と flow の 2 本)。closure の round k は
「seeds から callee 辺を k 本以内で辿れる入口」= BFS 深さ ≤ k と一致する (mx_closure の round 規則と同じ)。
- 各 funclet の BFS 深さ (何 round で入口集合に入るか) と、funclet への直接辺 (call/jmp) の元の最小深さ
- funclet を指す E8/E9 一致候補 (.text 生バイト走査) の由来: 候補バイトが命令境界か、どの関数 (pdata) の
  どの命令か、その関数の closure 深さ、関数の FH3 上の位置 (funclet 自身か親か)

funclet の定義は mx6_pdata_eh.py と同じ (FH3 FuncInfo の unwind action と catch handler 配列)。
usage: mx39_funclet_reach.py <pe> <linear_sets.pkl> <flow_sets.pkl> <out.json>
"""
import bisect
import json
import os
import pickle
import sys
import collections

import capstone
import pefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mx6_pdata_eh as P  # noqa: E402

CHAIN, EHANDLER, UHANDLER = P.CHAIN, P.EHANDLER, P.UHANDLER
FH3 = 'VCRUNTIME140.dll!__CxxFrameHandler3'
TERM = ('ret', 'int3', 'ud2', 'hlt')


def fh3_funclets_capped(rd, fi, max_state_cap=0x1000, n_try_cap=0x1000, n_catch_cap=0x100):
    """P.funclets_fh3 と同じ解析。PE 全体の FH3 を走査するため、件数の上限で不正な FuncInfo を捨てる
    (上限超過は None。上限内の正常な FuncInfo の結果は P.funclets_fh3 と同一)。"""
    b = rd(fi, 36)
    if b is None or int.from_bytes(b[:4], 'little') not in (0x19930520, 0x19930521, 0x19930522):
        return None
    max_state, disp_unwind, n_try, disp_try = (int.from_bytes(b[4 + 4 * i:8 + 4 * i], 'little') for i in range(4))
    if max_state > max_state_cap or n_try > n_try_cap:
        return None
    out = set()
    for i in range(max_state):
        e = rd(disp_unwind + 8 * i, 8) or b'\0' * 8
        act = int.from_bytes(e[4:8], 'little')
        if act:
            out.add(act)
    for t in range(n_try):
        tb = rd(disp_try + 20 * t, 20) or b'\0' * 20
        n_catch = int.from_bytes(tb[12:16], 'little')
        if n_catch > n_catch_cap:
            return None
        disp_ha = int.from_bytes(tb[16:20], 'little')
        for h in range(n_catch):
            hb = rd(disp_ha + 16 * h, 16) or b'\0' * 16
            out.add(int.from_bytes(hb[12:16], 'little'))
    return out


def bfs_depth(callees, seeds):
    dist = {s: 0 for s in seeds}
    frontier, d = list(seeds), 0
    while frontier:
        d += 1
        nxt = []
        for f in frontier:
            for t in callees.get(f, ()):
                if t not in dist:
                    dist[t] = d
                    nxt.append(t)
        frontier = nxt
    return dist


def direct_preds(callees, depth):
    """funclet 候補への直接辺の元 (entry -> 0 以上の深さ) を {target: min(depth(pred))}。"""
    best = {}
    for p, ts in callees.items():
        if p not in depth:
            continue
        for t in ts:
            if t not in best or depth[p] < best[t][0]:
                best[t] = (depth[p], p)
    return best


def reach_insns(md, data, off, base, e, end):
    """e から制御フローで到達する命令 (fall-through・直接 jcc/jmp・call は後続へ進む) を {rva: (size, mn, ops)}。
    間接 jmp (テーブル) は追わない。"""
    work, seen = [e], {}
    while work:
        a = work.pop()
        if not (e <= a < end):
            continue
        for ea, iz, mn, ops in md.disasm_lite(data[off(a):off(a) + min(4096, end - a)], base + a):
            r = ea - base
            if r in seen or not (e <= r < end):
                break
            seen[r] = (iz, mn, ops)
            if mn in TERM:
                break
            if mn.startswith('j') and ops.startswith('0x'):
                work.append(int(ops, 16) - base)
            if mn == 'jmp':
                break
    return seen


def main(pe_path, lin_p, flow_p, out_p):
    pe = pefile.PE(pe_path, fast_load=False)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    rd = P.make_rva_reader(pe, data)
    iat = P.walk_imports(rd, pe.OPTIONAL_HEADER.DATA_DIRECTORY[1].VirtualAddress)
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    praw = pdata.get_data()
    entries = {}
    for i in range(0, len(praw) - 11, 12):
        st, e, ui = (int.from_bytes(praw[i + j:i + j + 4], 'little') for j in (0, 4, 8))
        if st and e > st:
            entries[st] = (e, ui)

    tx = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    t_lo, t_raw = tx.VirtualAddress, tx.PointerToRawData
    tb = data[t_raw:t_raw + tx.SizeOfRawData]

    def off(r):
        return t_raw + (r - t_lo)

    def handler_is_fh3(h):
        code = rd(h, 6) or b''
        if code[:2] == b'\xff\x25':
            slot = h + 6 + int.from_bytes(code[2:6], 'little', signed=True)
            return iat.get(slot) == FH3
        return False

    # FH3 の funclet universe: 関数 begin -> (funclet 集合)
    fl_of = {}
    n_rej = 0
    for st, (e, ui) in entries.items():
        b = rd(ui, 4)
        if b is None or b == b'\0\0\0\0':
            continue
        if not (b[0] >> 3) & (EHANDLER | UHANDLER):
            continue
        hdr = 4 + 2 * ((b[2] + 1) & ~1)
        hb = rd(ui + hdr, 8)
        if hb is None or not handler_is_fh3(int.from_bytes(hb[:4], 'little')):
            continue
        got = fh3_funclets_capped(rd, int.from_bytes(hb[4:8], 'little'))
        if got:
            fl_of[st] = got
        elif got is None:
            n_rej += 1
    parents = collections.defaultdict(set)
    for st, fs in fl_of.items():
        for f in fs:
            parents[f].add(st)
    fl_all = set(parents)

    lin = pickle.load(open(lin_p, 'rb'))
    flo = pickle.load(open(flow_p, 'rb'))
    seeds = set(lin['seeds'])
    fsz = lin['fsz']
    begins = sorted(fsz)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    res = {'funclet_universe_fh3_all': len(fl_all), 'fh3_functions_all': len(fl_of),
           'fh3_funcinfo_rejected_by_cap': n_rej, 'modes': {}}
    dl = bfs_depth(lin['callees'], seeds)
    df = bfs_depth(flo['callees'], seeds)
    # 旧 e2e の母数 (seeds + 1-round 入口) の FH3 funclet (REPORT の 537 に対応)
    one_fl = set()
    for st in fl_of:
        if dl.get(st, 99) <= 1:
            one_fl |= fl_of[st]
    res['funclet_one_round_set_linear'] = len(one_fl)

    for label, dep, cal in (('linear', dl, lin['callees']), ('flow', df, flo['callees'])):
        hist = collections.Counter()
        for f in fl_all:
            hist[dep.get(f, 'unreached')] += 1
        preds = direct_preds(cal, dep)
        pred_hist = collections.Counter()
        for f in fl_all:
            if f in preds:
                pred_hist[preds[f][0]] += 1
            else:
                pred_hist['no_direct_pred'] += 1
        reached = []
        for f in sorted(fl_all):
            if f in dep and f not in seeds:
                p = preds.get(f)
                reached.append({'funclet': hex(f), 'depth': dep[f],
                                'pred': hex(p[1]) if p else None, 'pred_depth': p[0] if p else None,
                                'pred_is_fh3_parent': (p[1] in fl_of) if p else None,
                                'pred_is_funclet': (p[1] in fl_all) if p else None,
                                'parents': sorted(hex(x) for x in parents[f])})
        res['modes'][label] = {
            'reached_funclets': reached,
            'closure_entries_by_round': {k: sum(1 for v in dep.values() if v <= k) for k in range(0, 6)},
            'funclet_entry_depth_hist': {str(k): v for k, v in sorted(hist.items(), key=lambda kv: str(kv[0]))},
            'funclet_direct_pred_min_depth_hist': {str(k): v for k, v in sorted(pred_hist.items(), key=lambda kv: str(kv[0]))},
            'funclets_entry_in_round_le_2': sum(1 for f in fl_all if dep.get(f, 99) <= 2),
            'funclets_entry_in_round_le_3': sum(1 for f in fl_all if dep.get(f, 99) <= 3),
        }

    # E8/E9 一致候補 (.text 生バイト走査・命令境界を見ない) の由来
    def containing(s):
        j = bisect.bisect_right(begins, s) - 1
        if j >= 0 and s < begins[j] + fsz[begins[j]]:
            return begins[j]
        return None

    cands = []
    for op in (b'\xe8', b'\xe9'):
        i = tb.find(op)
        while i >= 0 and i + 5 <= len(tb):
            s = t_lo + i
            tgt = s + 5 + int.from_bytes(tb[i + 1:i + 5], 'little', signed=True)
            if tgt in fl_all:
                cands.append((s, op.hex(), tgt))
            i = tb.find(op, i + 1)
    res['candidates_total_fl_all'] = len(cands)
    rows = []
    for s, opx, tgt in cands:
        F = containing(s)
        row = {'site_rva': hex(s), 'op': opx, 'target_funclet': hex(tgt),
               'target_parents': sorted(hex(p) for p in parents[tgt]),
               'target_parent_in_round1': tgt in one_fl}
        if F is None:
            row['container'] = None
            row['note'] = 'pdata 関数範囲外 (data・thunk・padding のいずれか)'
            rows.append(row)
            continue
        e_end = F + fsz[F]
        lin_ins = {}
        for ea, iz, mn, ops in md.disasm_lite(data[off(F):off(F) + fsz[F]], base + F):
            lin_ins[ea - base] = (iz, mn, ops)
        starts = set(lin_ins)
        flow_ins = reach_insns(md, data, off, base, F, e_end)
        ins = lin_ins.get(s)
        row.update({
            'container': hex(F),
            'container_is_funclet': F in fl_all,
            'container_is_fh3_parent': F in fl_of,
            'container_depth_linear': dl.get(F),
            'container_depth_flow': df.get(F),
            'site_is_insn_boundary_linear': s in starts,
            'site_reached_by_flow_in_container': s in flow_ins,
            'site_insn': None if ins is None else {'len': ins[0], 'mn': ins[1], 'ops': ins[2]},
        })
        before = [lin_ins[k][1] + ' ' + lin_ins[k][2] for k in sorted(starts) if k < s][-2:]
        row['before_context'] = before
        rows.append(row)
    res['candidates'] = rows
    res['candidates_boundary_and_flow_reached'] = sum(
        1 for r in rows if r.get('site_is_insn_boundary_linear') and r.get('site_reached_by_flow_in_container'))
    res['candidates_container_depth_flow'] = collections.Counter(
        str(r.get('container_depth_flow')) for r in rows)
    with open(out_p, 'w') as f:
        json.dump(res, f, indent=1, ensure_ascii=False, default=str)
    print(json.dumps({k: v for k, v in res.items() if k != 'candidates'}, indent=1, ensure_ascii=False, default=str))
    for r in rows:
        print(json.dumps(r, ensure_ascii=False, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:5]))
