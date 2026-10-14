#!/usr/bin/env python3
"""data_code_count.py — closure 関数のうち、RetDec の dsm で data 区分とされた箇所に実コードを含む関数数を数える (ICALL-82 #2696)。

入力: work/rt_freshair-core/before.0.drc.dsm (RetDec の逆アセンブル) と map.json (func_map = closure 関数の VA)。
定義 (2 系統。どちらも dsm だけから数え、IR は見ない):
  A (fall-through 系): 関数 f の dsm 区間 [S, E) の直後 (A == E) に data 区分 [E, B) がある。その先頭から
     capstone で線形に decode し、8 命令以上が連続して正常に decode でき、その先頭 16 B に 00 00 (add [..],al)
     と cc (int3) が無いものを「実コード」とみなす。E 直前の最後の命令が ret/jmp/ud2/hlt/int3 なら対象外 (脱落ではない)。
  B (区間系): 関数 f の dsm 区間の先頭 S から、次の関数ヘッダ (任意の関数) の開始 N までの data 区分 [A, B) のうち、
     capstone の線形 decode が 8 命令以上続き、その中に ret/call/j* を 1 つ以上含むものを「実コードの可能性」とする。
     境界の 00 00 / cc 条件は使わない (A より緩い。上限側の見積り)。
decode の検査: capstone は decode 不能な命令で停止し (`(bad)` は出さない)、線形 decode の出力は正常 decode の先頭連続。
dsm の dump に欠けたバイト (未ダンプの `??` 行を含む) を読んだら error で止める (黙って詰めない)。
出力: stdout に集計 (JSON 1 行) と、件ごとの一覧を work/icall_data_code/data_code_count*.json に書く。
用法: python3 tools/icall/diff/data_code_count.py
      python3 tools/icall/diff/data_code_count.py --control zero|cc|random|shuffle [--seed N]
      (--control は negative control。data 区分の bytes だけを差し替え、関数本体と区間の位置は変えない)
"""
import argparse
import json
import os
import random
import re
import sys

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
RTD = os.path.join(HERE, '..', 'work', 'rt_freshair-core')
DSM = os.path.join(RTD, 'before.0.drc.dsm')
MAP = os.path.join(RTD, 'map.json')
OUT_DIR = os.path.join(HERE, '..', 'work', 'icall_data_code')
MIN_RUN = 8

FUNC_RE = re.compile(r'^; function: (\S+) at 0x([0-9a-f]+) -- 0x([0-9a-f]+)')
DATA_RE = re.compile(r'^; data inside code section at 0x([0-9a-f]+) -- 0x([0-9a-f]+)')
# dump 行: 16 B を 8 B ずつ区切る (8 B 目の後が二重空白 `0f  10`)。列の終わり (` |` または tab) まで全バイトを取る。
DUMP_RE = re.compile(r'^0x([0-9a-f]+):((?: +[0-9a-f]{2})+) +(?:\||\t)')
TERM = ('ret', 'jmp', 'ud2', 'int3', 'hlt')
CONTROLS = ('none', 'zero', 'cc', 'random', 'shuffle')


def parse_dsm(path):
    funcs, datas, bytes_at, unparsed = [], [], {}, []
    with open(path, errors='replace') as f:
        for line in f:
            m = FUNC_RE.match(line)
            if m:
                funcs.append((int(m.group(2), 16), int(m.group(3), 16), m.group(1)))
                continue
            m = DATA_RE.match(line)
            if m:
                datas.append((int(m.group(1), 16), int(m.group(2), 16)))
                continue
            m = DUMP_RE.match(line)
            if m:
                base = int(m.group(1), 16)
                for i, h in enumerate(m.group(2).split()):
                    bytes_at[base + i] = int(h, 16)
                continue
            if line.startswith('0x'):
                unparsed.append(line[:20])
    return sorted(funcs), sorted(datas), bytes_at, unparsed


def read_bytes(bytes_at, a, b):
    missing = [x for x in range(a, b) if x not in bytes_at]
    if missing:
        sys.exit('error: dsm dump missing %d byte(s) in [0x%x, 0x%x) (first 0x%x)' % (len(missing), a, b, missing[0]))
    return bytes(bytes_at[x] for x in range(a, b))


def linear_decode(md, bytes_at, a, b):
    """A から B の手前まで線形に decode し、(addr, mnem, op, size) のリストを返す。decode 不能で止まる。"""
    code = read_bytes(bytes_at, a, b)
    return [(ins.address, ins.mnemonic, ins.op_str, ins.size) for ins in md.disasm(code, a)]


def apply_control(bytes_at, datas, control, seed):
    """negative control: data 区分の bytes だけを差し替える。関数本体・区間の位置は変えない。"""
    if control == 'none':
        return bytes_at
    rng = random.Random(seed)
    out = dict(bytes_at)
    for A, B in datas:
        cur = list(read_bytes(bytes_at, A, B))
        if control == 'zero':
            new = [0] * len(cur)
        elif control == 'cc':
            new = [0xCC] * len(cur)
        elif control == 'random':
            new = [rng.randrange(256) for _ in cur]
        elif control == 'shuffle':
            new = list(cur)
            rng.shuffle(new)
        for x, v in zip(range(A, B), new):
            out[x] = v
    return out


def ir_insn_addrs(path):
    """route の IR (after.0.restored.ll) が持つ命令アドレスの集合 (!insn.addr のメタデータ値)。別経路の検算用。"""
    md_val = {}
    used = set()
    md_re = re.compile(r'^!(\d+) = !\{i64 (\d+)\}')
    ref_re = re.compile(r'!insn\.addr !(\d+)')
    with open(path) as f:
        for line in f:
            m = md_re.match(line)
            if m:
                md_val[m.group(1)] = int(m.group(2))
                continue
            for r in ref_re.findall(line):
                used.add(r)
    return {md_val[i] for i in used if i in md_val}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--control', choices=CONTROLS, default='none')
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args()

    funcs, datas, bytes_at, unparsed = parse_dsm(DSM)
    # 関数本体の線形 decode (末尾判定) は元のバイトのまま。control は data 区分を decode する側だけに効かせる
    dat_at = apply_control(bytes_at, datas, args.control, args.seed)
    ir_addrs = ir_insn_addrs(os.path.join(RTD, 'after.0.restored.ll'))
    fmap = json.load(open(MAP))['func_map']
    closure = sorted(int(k, 16) for k in fmap)
    func_starts = [f[0] for f in funcs]
    func_end = {f[0]: f[1] for f in funcs}
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False
    rows = []
    for S in closure:
        if S not in func_end:
            rows.append({'va': '0x%x' % S, 'missing_in_dsm': True})
            continue
        E = func_end[S]
        # A: fall-through 系
        last = linear_decode(md, bytes_at, S, E)
        last_mn = last[-1][1] if last else ''
        a_hit = None
        dd = [d for d in datas if d[0] == E]
        a_cand = bool(dd) and not last_mn.startswith(TERM)
        if a_cand:
            A, B = dd[0]
            ins = linear_decode(md, dat_at, A, B)
            raw = read_bytes(dat_at, A, A + 16)
            has_pad = b'\x00\x00' in raw or 0xCC in raw
            if len(ins) >= MIN_RUN and not has_pad:
                fa, fm, fo, fs = last[-1]
                a_hit = {'data': '0x%x-0x%x' % (A, B),
                         'first': ['%x %s %s' % (i[0], i[1], i[2]) for i in ins[:4]],
                         'fn_tail': '%x %s %s' % (fa, fm, fo), 'fn_tail_ends_at_E': fa + fs == E,
                         'ir_has_start': A in ir_addrs}
        # B: 区間系
        N = next((s for s in func_starts if s > S), None)
        if N is None:
            N = max(d[1] for d in datas) if datas else E
        b_hits = []
        b_cand = False
        for A, B in datas:
            if not (S <= A < N):
                continue
            b_cand = True
            mns = [i[1] for i in linear_decode(md, dat_at, A, B)]
            if len(mns) >= MIN_RUN and any(m == 'ret' or m == 'call' or m.startswith('j') for m in mns):
                b_hits.append('0x%x-0x%x' % (A, B))
        rows.append({'va': '0x%x' % S, 'end': '0x%x' % E, 'next_func': '0x%x' % N if N else None,
                     'A_fallthrough': a_hit, 'B_span_data': b_hits, 'A_candidate': a_cand, 'B_candidate': b_cand})
    a_n = sum(1 for r in rows if r.get('A_fallthrough'))
    b_n = sum(1 for r in rows if r.get('B_span_data'))
    ab_n = sum(1 for r in rows if r.get('A_fallthrough') or r.get('B_span_data'))
    a_ir_absent = sum(1 for r in rows if r.get('A_fallthrough') and not r['A_fallthrough']['ir_has_start'])
    summary = {'control': args.control, 'seed': args.seed if args.control in ('random', 'shuffle') else None,
               'closure_funcs': len(closure), 'in_dsm': sum(1 for r in rows if not r.get('missing_in_dsm')),
               'A_candidates': sum(1 for r in rows if r.get('A_candidate')),
               'B_candidates': sum(1 for r in rows if r.get('B_candidate')),
               'A_fallthrough_with_code': a_n, 'B_span_with_code': b_n, 'A_or_B': ab_n,
               'A_start_absent_in_route_ir': a_ir_absent, 'dsm_unparsed_0x_lines': len(unparsed)}
    os.makedirs(OUT_DIR, exist_ok=True)
    name = 'data_code_count.json' if args.control == 'none' else 'data_code_count_%s_%d.json' % (args.control, args.seed)
    with open(os.path.join(OUT_DIR, name), 'w') as f:
        json.dump({'summary': summary, 'rows': rows}, f, indent=1)
    print(json.dumps(summary))
    for r in rows:
        if r.get('A_fallthrough') or r.get('B_span_data'):
            print(r['va'], 'A' if r.get('A_fallthrough') else '-', 'B%d' % len(r.get('B_span_data') or []))


if __name__ == '__main__':
    sys.exit(main())
