#!/usr/bin/env python3
"""data_code_count.py — closure 関数のうち、RetDec の dsm で data 区分とされた箇所に実コードを含む関数数を数える (ICALL-82 #2696)。

入力: work/rt_freshair-core/before.0.drc.dsm (RetDec の逆アセンブル) と map.json (func_map = closure 関数の VA)。
定義 (2 系統。どちらも dsm だけから数え、IR は見ない):
  A (fall-through 系): 関数 f の dsm 区間 [S, E) の直後 (A == E) に data 区分 [E, B) がある。その先頭から
     capstone で線形に decode し、8 命令以上が連続して正常に decode でき、その先頭 8 命令に 00 00 (add [..],al)
     と cc (int3) が無いものを「実コード」とみなす。E 直前の最後の命令が ret/jmp/ud2 なら対象外 (脱落ではない)。
  B (区間系): 関数 f の dsm 区間の先頭 S から、次の関数ヘッダ (任意の関数) の開始 N までの data 区分 [A, B) のうち、
     capstone の線形 decode で「8 命令以上の連続 decode かつ ret/call/jcc/jmp を 1 つ以上含む run」があるもの。
     境界の 00 00 / cc 条件は使わない (A より緩い。上限側の見積り)。
出力: stdout に集計 (JSON 1 行) と、件ごとの一覧を work/icall_data_code/data_code_count.json に書く。
用法: python3 tools/icall/diff/data_code_count.py
"""
import json
import os
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
DUMP_RE = re.compile(r'^0x([0-9a-f]+):\s+((?:[0-9a-f]{2} ?)+)\s')
TERM = ('ret', 'jmp', 'ud2', 'int3', 'hlt')


def parse_dsm(path):
    funcs, datas, bytes_at, last_ins = [], [], {}, {}
    with open(path) as f:
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
    return sorted(funcs), sorted(datas), bytes_at


def read_bytes(bytes_at, a, b):
    return bytes(bytes_at[x] for x in range(a, b) if x in bytes_at)


def linear_decode(md, bytes_at, a, b):
    """A から B の手前まで線形に decode し、(addr, mnem, op, size) のリストを返す。"""
    code = read_bytes(bytes_at, a, b)
    out = []
    for ins in md.disasm(code, a):
        out.append((ins.address, ins.mnemonic, ins.op_str, ins.size))
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
    funcs, datas, bytes_at = parse_dsm(DSM)
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
        if dd and not last_mn.startswith(TERM):
            A, B = dd[0]
            ins = linear_decode(md, bytes_at, A, B)[:MIN_RUN]
            bad = any(i[1] in ('(bad)',) for i in ins)
            raw = read_bytes(bytes_at, A, A + 16)
            has_pad = b'\x00\x00' in raw[:16] or 0xcc in raw[:16]
            if len(ins) >= MIN_RUN and not bad and not has_pad:
                a_hit = {'data': '0x%x-0x%x' % (A, B), 'first': ['%x %s %s' % (i[0], i[1], i[2]) for i in ins[:4]],
                         'ir_has_start': A in ir_addrs}
        # B: 区間系
        N = next((s for s in func_starts if s > S), None)
        if N is None:
            N = max(d[1] for d in datas) if datas else E
        b_hits = []
        for A, B in datas:
            if not (S <= A < N):
                continue
            ins = linear_decode(md, bytes_at, A, B)
            run, best = [], []
            for i in ins:
                if i[1] == '(bad)':
                    run = []
                    continue
                run.append(i)
                if len(run) > len(best):
                    best = list(run)
            mns = [i[1] for i in best]
            if len(best) >= MIN_RUN and any(m == 'ret' or m == 'call' or m.startswith('j') for m in mns):
                b_hits.append('0x%x-0x%x' % (A, B))
        rows.append({'va': '0x%x' % S, 'end': '0x%x' % E, 'next_func': '0x%x' % N if N else None,
                     'A_fallthrough': a_hit, 'B_span_data': b_hits})
    a_n = sum(1 for r in rows if r.get('A_fallthrough'))
    b_n = sum(1 for r in rows if r.get('B_span_data'))
    ab_n = sum(1 for r in rows if r.get('A_fallthrough') or r.get('B_span_data'))
    a_ir_absent = sum(1 for r in rows if r.get('A_fallthrough') and not r['A_fallthrough']['ir_has_start'])
    summary = {'closure_funcs': len(closure), 'in_dsm': sum(1 for r in rows if not r.get('missing_in_dsm')),
               'A_fallthrough_with_code': a_n, 'B_span_with_code': b_n, 'A_or_B': ab_n,
               'A_start_absent_in_route_ir': a_ir_absent}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, 'data_code_count.json'), 'w') as f:
        json.dump({'summary': summary, 'rows': rows}, f, indent=1)
    print(json.dumps(summary))
    for r in rows:
        if r.get('A_fallthrough') or r.get('B_span_data'):
            print(r['va'], 'A' if r.get('A_fallthrough') else '-', 'B%d' % len(r.get('B_span_data') or []))


if __name__ == '__main__':
    sys.exit(main())
