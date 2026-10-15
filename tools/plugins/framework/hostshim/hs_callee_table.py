#!/usr/bin/env python3
"""hs_callee_table.py — callee 81 件の個別影響表 (#3735 / PLG-P0b-39 受入 1)。

入力: 基準 JSON (hs_disp_emu.py HS_DISP_PATH=1 の全 256 ID) と、callee ごとの JSON
(HS_DISP_RET_SPEC=<VA>:one で、そのときの基準 callout ID だけを実行したもの)、
さらに全 callee を同時に one にした JSON。
出力: 1 callee 1 行の表 (202 集合の出入り・経路変化・rax 変化・格納 VA の増減) と、
個別の和集合と全 82 VA 同時実行の差 (組合せ効果)。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_callee_table.py base.json dir_with_c_json all82.json
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hs_store_cov as C
import hs_disp_emu as E
import hs_resp_src as S

MAIN = 0x40fe90


def load(p):
    return json.load(open(p))


def state(run, static):
    """ID ごとの (202 集合の所属, 経路 hash, rax, 格納 VA 集合)。"""
    out = {}
    s202 = C.no_case_store(run, static)
    for k, v in run.items():
        stores = frozenset(a for a in (v['path'] or []) if a in static)
        out[int(k)] = (int(k) in s202, v['path_hash'], v['rax'], stores)
    return out


def diff(b, c):
    ids = sorted(b)
    left = [i for i in ids if b[i][0] and not c[i][0]]
    enter = [i for i in ids if not b[i][0] and c[i][0]]
    path = [i for i in ids if b[i][1] != c[i][1]]
    rax = [i for i in ids if b[i][2] != c[i][2]]
    new_st = sorted(set().union(*[c[i][3] - b[i][3] for i in ids]))
    lost_st = sorted(set().union(*[b[i][3] - c[i][3] for i in ids]))
    return left, enter, path, rax, new_st, lost_st


def fmt(xs):
    return ','.join('0x%02x' % x for x in xs) or '-'


def fmtva(xs):
    return ','.join('0x%x' % x for x in xs) or '-'


def main():
    base_p, cdir, all_p = sys.argv[1], sys.argv[2], sys.argv[3]
    base = load(base_p)
    allr = load(all_p)
    pe_data = open(E.PE_PATH, 'rb').read()
    pe, _, _ = E.load_image(pe_data)
    static = C.static_stores(S.make_reader(pe, E.load_image(pe_data)[1]))
    sb = state(base, static)
    callees = json.load(open(os.path.join(cdir, 'callee_ids.json')))
    indiv = {}
    print('| callee | 202 から外れた ID | 202 に入った ID | 経路が変わった ID | rax が変わった ID | 新たに実行される格納 | 失われる格納 |')
    print('|---|---|---|---|---|---|---|')
    for va in sorted(callees, key=lambda s: int(s, 16)):
        p = os.path.join(cdir, 'c_%s.json' % va)
        run = load(p)
        # 基準側の同じ ID 集合だけを比べる (他 ID は基準と同一の経路)。
        ids = [int(k) for k in run]
        bsub = {str(i): base[str(i)] for i in ids}
        cs = state(run, static)
        bs = state(bsub, static)
        l, e, pth, rx, ns, ls = diff(bs, cs)
        indiv[va] = (set(l), set(e), set(pth), set(rx), set(ns), set(ls))
        tag = ' (基準)' if int(va, 16) == MAIN else ''
        print('| `%s`%s | %s | %s | %s | %s | %s | %s |' % (
            va, tag, fmt(l), fmt(e), fmt(pth), fmt(rx), fmtva(ns), fmtva(ls)))
    # 組合せ効果: 全 82 個別 run (MAIN を含む) の和集合と、全 82 同時 run の差
    union = [set(), set(), set(), set(), set(), set()]
    for va, parts in indiv.items():
        for j, s in enumerate(parts):
            union[j] |= s
    ab = {str(i): base[str(i)] for i in range(256)}
    l, e, pth, rx, ns, ls = diff(state(ab, static), state(allr, static))
    print()
    print('個別 82 件 (MAIN 含む) の和集合: 202 から外れた %s / 入った %s / 経路変化 %s / rax 変化 %s' % (
        fmt(sorted(union[0])), fmt(sorted(union[1])), fmt(sorted(union[2])), fmt(sorted(union[3]))))
    print('全 82 VA 同時 (one): 202 から外れた %s / 入った %s / 経路変化 %s / rax 変化 %s' % (
        fmt(l), fmt(e), fmt(pth), fmt(rx)))
    print('組合せ効果 (全同時にだけ現れる差): 外れた %s / 入った %s / 経路 %s / rax %s' % (
        fmt(sorted(set(l) - union[0])), fmt(sorted(set(e) - union[1])),
        fmt(sorted(set(pth) - union[2])), fmt(sorted(set(rx) - union[3]))))
    for n in (0x19, 0x36, 0x40, 0x58, 0x80):
        print('未収載 0x%02x: 基準 rax=%s / 全同時 rax=%s' % (
            n, hex(base[str(n)]['rax']), hex(allr[str(n)]['rax'])))


if __name__ == '__main__':
    main()
