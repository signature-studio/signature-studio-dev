#!/usr/bin/env python3
"""unmatched / no_prologue の site を、親 IR の call と機械語の prologue で個別に判定する (#5576 / SHX-T48)。

base_check.py の判定を変えずに、次の 2 点だけを補う:
  - CALL_RE は第 1 引数が ptr のときしか拾わない。IR の多くは i64 で渡すため unmatched に落ちる。
    ここでは第 1 引数の形を問わず、callee の call を数える。
  - prologue の `add rsp, -N` (負の即値) を `sub rsp, N` と同じに扱う。base_check は落として no_prologue にする。
判定 (site 単位):
  - no_ir_call : 親 IR に callee の call が無い (call 欠落の疑い)
  - base_match : 第 1 引数が stack_var_X (X = 機械語の rbp 位置) と一致
      - ir_truncated : callee の rbp 基準の最大端 E > alloca 幅 S
      - ir_covers    : E <= S
  - base_mismatch : 第 1 引数が X と違う

使い方:
  FL_WIN64_DIR=<展開先> python3 frame_share/unmatched_check.py --ir work/boot_final3.ll --base work/base_check.json --sites work/frame_share.json --out work/unmatched_check.json
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
M11 = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(M11, 'ldfix'))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402
import classify  # noqa: E402


def rbp_entry_offset(mach, va):
    pushes = 0
    sub = 0
    for ins in mach.disasm_fn(va):
        if ins.mnemonic == 'push':
            pushes += 1
        elif ins.mnemonic in ('sub', 'add') and ins.op_str.startswith('rsp, '):
            try:
                v = int(ins.op_str.split(', ')[1], 0)
            except ValueError:
                return None
            sub += v if ins.mnemonic == 'sub' else -v
        elif ins.mnemonic == 'mov' and ins.op_str == 'rbp, rsp':
            return -(8 * pushes + sub)
        elif ins.op_str.startswith('rsp') or ins.mnemonic in ('call', 'ret'):
            return None
    return None


def resolve_ptrtoint(body, call_pos, name):
    defs = list(re.finditer(r'%' + re.escape(name) + r' = ([^\n]*)', body[:call_pos]))
    if not defs:
        return name
    m = re.match(r'ptrtoint ptr %([\w.\-]+) to i64', defs[-1].group(1))
    return m.group(1) if m else name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ir', required=True)
    ap.add_argument('--base', required=True)
    ap.add_argument('--sites', required=True)
    ap.add_argument('--pe', default=os.path.join(os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block00031_PE.bin'))
    ap.add_argument('--out')
    a = ap.parse_args()
    fns = classify.bodies(open(a.ir, errors='replace').read())
    base = json.load(open(a.base))['sites']
    sites = {(s['parent'], s['call_at']): s for s in json.load(open(a.sites))['sites']}
    mach = Machine(a.pe)
    out = []
    for r in base:
        if r['verdict'] not in ('unmatched', 'no_prologue'):
            continue
        p, callee = r['parent'], r['callee']
        body = fns.get(p)
        X = rbp_entry_offset(mach, int(p.split('_')[1], 16))
        E = max((x['off'] + x['size'] for x in sites[(p, r['call_at'])]['callee_access']), default=None)
        rec = dict(call_at=r['call_at'], parent=p, callee=callee, prev=r['verdict'], rbp_entry=X, need=E)
        args = set(resolve_ptrtoint(body or '', m.start(), m.group(1)) for m in re.finditer(r'call [^@]*@' + re.escape(callee) + r'\((?:ptr|i64|i32)[^%,]*%([\w.\-]+)', body or ''))
        raw = len(re.findall(r'^\s*(?:%[\w.\-]+ = )?call [^\n]*@' + re.escape(callee) + r'\(', body or '', re.M))
        rec['raw_calls'] = raw
        if E is None:
            rec['verdict'] = 'no_callee_access'
        elif body is None or raw == 0:
            rec['verdict'] = 'no_ir_call'
        elif not args:
            rec['verdict'] = 'arg_type_unmatched'
        elif X is None:
            rec['verdict'] = 'no_rbp_entry'
        elif args == {'stack_var_%d' % X}:
            sizes = classify.alloca_sizes(body)
            S = sizes.get('stack_var_%d' % X)
            rec.update(passed='stack_var_%d' % X, alloca_size=S)
            rec['verdict'] = 'ir_truncated' if S is not None and E > S else 'ir_covers'
        else:
            rec['verdict'] = 'base_mismatch'
            rec['passed'] = sorted(args)
        out.append(rec)
    cnt = collections.Counter(r['verdict'] for r in out)
    pairs = {}
    for r in out:
        pairs.setdefault((r['parent'], r['callee']), r['verdict'])
    summary = dict(sites=len(out), by_site=dict(cnt), pairs=len(pairs), by_pair=dict(collections.Counter(pairs.values())))
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if a.out:
        json.dump(dict(summary=summary, sites=out), open(a.out, 'w'), ensure_ascii=False, indent=1)
        open(a.out, 'a').write('\n')


if __name__ == '__main__':
    main()
