#!/usr/bin/env python3
"""LD-198 (#4173): 多重候補 (fvm 前に候補 2 件以上) の関数を fault_arg で分類し直す。
使い方: FL_WIN64_DIR=... python3 tools/liftdiff/ld198_recount.py <base の batch jsonl>
入力: fvm 以外の case で判定した base の jsonl (例 tools/liftdiff/work/m11/batch_sample_800.jsonl)。
出力: 多重候補の件数と、fault_arg の分類 (排他・合計は多重候補の件数)。
分類: ret_fragment / resolved (arg が候補内) / arg_not_candidate / unresolved_* (None の理由別)。
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldlib import cases  # noqa: E402
from ldlib.pe import PE, Analyzer, REG_FULL  # noqa: E402
import capstone  # noqa: E402


def main(jsonl):
    pe_path = os.path.join(os.environ['FL_WIN64_DIR'], 'extracted', 'block00031_PE.bin')
    pe = PE(pe_path)
    an = Analyzer(pe)
    multi = []
    for line in open(jsonl):
        r = json.loads(line)
        cs = [c for c in r['cases'] if c.get('pattern') != 'fvm']
        if any(c['outcome'] in ('equal', 'diff', 'wasm_trap') for c in cs):
            continue
        fault = next((c['fault'] for c in cs if c.get('pattern') == 's' and c.get('fault')), None)
        if fault is None:
            continue
        cand = cases.fvm_candidates(fault, cases.kinds_of(r['function']['sig']['params']))
        if len(cand) >= 2:
            multi.append((r['function']['va'], cand, fault))
    cls = collections.Counter()
    for va_s, cand, fault in multi:
        va = int(va_s, 16)
        rip = int(fault['rip'], 16)
        if an.is_ret_fragment(va):
            cls['ret_fragment'] += 1
            continue
        a = an.fault_arg(va, rip)
        if a is not None:
            cls['resolved' if a in cand else 'arg_not_candidate'] += 1
            continue
        cls['unresolved_' + unresolved_reason(an, va, rip)] += 1
    print('多重候補 (fvm 前に候補 2 件以上):', len(multi))
    for k in sorted(cls):
        print('  %-24s %d' % (k, cls[k]))
    print('合計:', sum(cls.values()))
    by = collections.defaultdict(list)
    for va_s, cand, fault in multi:
        by[classify(an, va_s, cand, fault)].append(va_s)
    for k in sorted(by):
        print('VA %s: %s' % (k, ' '.join(sorted(by[k]))))


def classify(an, va_s, cand, fault):
    va = int(va_s, 16)
    if an.is_ret_fragment(va):
        return 'ret_fragment'
    a = an.fault_arg(va, int(fault['rip'], 16))
    if a is not None:
        return 'resolved' if a in cand else 'arg_not_candidate'
    return 'unresolved_' + unresolved_reason(an, va, int(fault['rip'], 16))


def unresolved_reason(an, va, rip):
    """fault_arg が None を返した理由 (fault_arg と同じ線形追跡を再現する)。"""
    ins = an._dis(rip - an.pe.base)
    mem = [o for o in ins.operands if o.type == capstone.CS_OP_MEM and o.mem.base] if ins else []
    if not mem or an.cs.reg_name(mem[0].mem.base) not in REG_FULL:
        return 'base_not_gpr64'
    prov = {'rcx', 'rdx', 'r8', 'r9'}
    r, end, n = va - an.pe.base, rip - an.pe.base, 0
    while r < end:
        if n >= 3000:
            return 'limit3000'
        i = an._dis(r)
        if i is None:
            return 'undecodable'
        if i.group(capstone.CS_GRP_RET):
            return 'ret_before_rip'
        if i.group(capstone.CS_GRP_JUMP):
            return 'jump_before_rip'
        r += i.size
        n += 1
    return 'base_not_arg'


if __name__ == '__main__':
    main(sys.argv[1])
