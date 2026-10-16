#!/usr/bin/env python3
"""LD-291 (#5973): 13 件の戻り経路で止まる間接 call の解決方式を、同じ判定器に適用して比べる。

  python3 tools/liftdiff/tests/ld291_schemes.py <PE> --scheme S0|S1|S2|S3 [--reasons]

  S0: 現行 (ld215_retprop.py --callee-arg と同じ。間接 call は未確定)。
  S1: IAT 参照の call [rip+disp] だけを外部 API とみなす。戻りは rax 上書き、rdx / xmm0 は引数読みとみなす。
  S2: 上限見積もり (非健全)。呼出し元の継続にある間接 call だけを素通し (何も読まず書かない) とみなす。
      呼出し先の中の間接 call は対象外。候補が増えても採用の根拠にはしない。基準線としてだけ使う。
  S3: 上限見積もり (非健全)。呼出し先の中の間接 call も素通しとみなす。解決方式が完全に効いたときの上限。

--reasons を付けると、未確定を生んだ理由 (間接 call の形・深さ超過など) を形別に数える。
"""
import argparse
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import ld215_retprop as R  # noqa: E402
from ldlib import pe as P  # noqa: E402

T13 = '7ce2e0 12657b0 442670 5b0970 442890 6a3a90 1311f70 13114b0 40c650 4421d0 45e3c0 45ee00 8e6660'.split()
BUDGET = 400


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pe')
    ap.add_argument('--scheme', default='S0', choices=['S0', 'S1', 'S2', 'S3'])
    ap.add_argument('--reasons', action='store_true')
    ap.add_argument('--maxdepth', type=int, default=4, help='直接 call の再帰の深さ上限 (既定 4 = ld215 と同じ)')
    a = ap.parse_args()
    t = R.Text(a.pe)
    p = P.PE(a.pe)
    hits = R.call_sites(t, {int(x, 16): x for x in T13})
    rcache = {}
    reason = collections.Counter()

    def form(ins):
        return 'rip-mem' if 'rip' in ins.op_str else 'mem'

    def is_iat_call(ins):
        if '[' not in ins.op_str or 'rip' not in ins.op_str:
            return False
        disp = ins.operands[-1].mem.disp
        return p.in_iat(ins.address + ins.size + disp - p.base)

    def callee_why(entry, depth=0):
        """callee_reads が None を返す理由 (呼出し先の中で最初に詰まった形)。解析できれば None。"""
        stack = [(entry, frozenset())]
        seen = set()
        steps = 0
        while stack:
            va, w = stack.pop()
            if (va, w) in seen:
                continue
            seen.add((va, w))
            steps += 1
            if steps > BUDGET * 4:
                return 'callee-budget'
            ins = t.at(va)
            if ins is None:
                return 'callee-nodecode'
            _rd, wr = t.acc(ins)
            m = ins.mnemonic
            if m in ('ret', 'retq') or m in R.NORET:
                continue
            if m == 'call':
                if not ins.op_str.startswith('0x'):
                    if a.scheme == 'S3':
                        stack.append((va + ins.size, w))
                        continue
                    return 'callee-indcall:' + form(ins)
                if depth >= a.maxdepth:
                    return 'callee-depth'
                sub = callee_why(int(ins.op_str, 16), depth + 1)
                if sub is not None:
                    return sub
                stack.append((va + ins.size, w))
                continue
            w2 = w | frozenset(wr)
            if m == 'jmp':
                if not ins.op_str.startswith('0x'):
                    return 'callee-indjmp'
                stack.append((int(ins.op_str, 16), w2))
            elif m.startswith('j'):
                if not ins.op_str.startswith('0x'):
                    return 'callee-indjcc'
                stack.append((va + ins.size, w2))
                stack.append((int(ins.op_str, 16), w2))
            else:
                stack.append((va + ins.size, w2))
        return None

    def callee_reads_s3(entry, depth=0):
        """S3 (上限見積もり・非健全): callee_reads と同じだが、呼出し先の間接 call を素通し (読まず書かない) とみなす。"""
        rd_any = set()
        must = None
        seen = set()
        stack = [(entry, frozenset())]
        steps = 0
        while stack:
            va, w = stack.pop()
            if (va, w) in seen:
                continue
            seen.add((va, w))
            steps += 1
            if steps > BUDGET * 4:
                return None
            ins = t.at(va)
            if ins is None:
                return None
            rd, wr = t.acc(ins)
            rd_any |= {k for k in rd if k not in w}
            m = ins.mnemonic
            if m in ('ret', 'retq'):
                must = set(w) if must is None else (must & w)
                continue
            if m in R.NORET:
                continue
            if m == 'call':
                if not ins.op_str.startswith('0x'):
                    stack.append((va + ins.size, w))
                    continue
                if depth >= a.maxdepth:
                    return None
                sub = callee_reads_s3(int(ins.op_str, 16), depth + 1)
                if sub is None:
                    return None
                sub_rd, sub_must = sub
                rd_any |= {k for k in sub_rd if k not in w}
                stack.append((va + ins.size, w | frozenset(sub_must)))
                continue
            w2 = w | frozenset(wr)
            if m == 'jmp':
                if not ins.op_str.startswith('0x'):
                    return None
                stack.append((int(ins.op_str, 16), w2))
            elif m.startswith('j'):
                if not ins.op_str.startswith('0x'):
                    return None
                stack.append((va + ins.size, w2))
                stack.append((int(ins.op_str, 16), w2))
            else:
                stack.append((va + ins.size, w2))
        return rd_any, set(must or set())

    def reads_of(va):
        if va not in rcache:
            rcache[va] = callee_reads_s3(va) if a.scheme == 'S3' else R.callee_reads(t, va, BUDGET * 4)
        return rcache[va]

    def caller(ret_va):
        # res[k] が None のままのレジスタを『未確定』とする (ld215_retprop.caller_use と同じ規則)
        res = {k: None for k in R.REGS}
        stack = [(ret_va, frozenset(R.REGS))]
        seen = set()
        steps = 0
        while stack:
            va, pend = stack.pop()
            if not pend or (va, pend) in seen:
                continue
            seen.add((va, pend))
            steps += 1
            if steps > BUDGET:
                reason['caller-budget'] += len(pend)
                break
            ins = t.at(va)
            if ins is None:
                reason['caller-nodecode'] += len(pend)
                continue
            rd, wr = t.acc(ins)
            left = set(pend)
            for k in list(left):
                if k in rd:
                    left.discard(k)
                    res[k] = res[k] or 'read'
            for k in list(left):
                if k in wr:
                    left.discard(k)
                    res[k] = res[k] or 'dead'
            if not left:
                continue
            m = ins.mnemonic
            if m in ('ret', 'retq'):
                for k in left:
                    res[k] = res[k] or 'pass'
                continue
            if m == 'call' and ins.op_str.startswith('0x'):
                sm = reads_of(int(ins.op_str, 16))
                if sm is None:
                    why = callee_why(int(ins.op_str, 16)) or 'callee-unknown'
                    reason['caller-direct-call:' + why] += len(left)
                    continue
                sub_rd, sub_must = sm
                for k in list(left):
                    if k in sub_rd:
                        left.discard(k)
                        res[k] = res[k] or 'read'
                    elif k in sub_must:
                        left.discard(k)
                        res[k] = res[k] or 'dead'
                if left:
                    stack.append((va + ins.size, frozenset(left)))
                continue
            if m == 'call':
                if a.scheme == 'S2':
                    stack.append((va + ins.size, frozenset(left)))
                elif a.scheme == 'S1' and is_iat_call(ins):
                    for k in list(left):
                        if k == 'rax':
                            left.discard(k)
                            res[k] = res[k] or 'dead'
                        elif k in ('rdx', 'xmm0'):
                            left.discard(k)
                            res[k] = res[k] or 'read'
                    if left:
                        stack.append((va + ins.size, frozenset(left)))
                else:
                    reason['caller-indcall:' + form(ins)] += len(left)
                continue
            if m == 'jmp':
                if ins.op_str.startswith('0x'):
                    stack.append((int(ins.op_str, 16), frozenset(left)))
                else:
                    reason['caller-indjmp'] += len(left)
                continue
            if m.startswith('j'):
                stack.append((va + ins.size, frozenset(left)))
                if ins.op_str.startswith('0x'):
                    stack.append((int(ins.op_str, 16), frozenset(left)))
                else:
                    reason['caller-indjcc'] += len(left)
                continue
            stack.append((va + ins.size, frozenset(left)))
        return res

    for name in T13:
        va = int(name, 16)
        if a.scheme == 'S3':
            sm = callee_reads_s3(va)
            ok, must = sm is not None, (sm[1] if sm else set())
        else:
            must, _may, ok = R.callee_defs(t, va, BUDGET * 4)
        rd_n = collections.Counter()
        dead_n = collections.Counter()
        unk_n = 0
        for c in hits[va]:
            r = caller(c + 5)
            for k in R.REGS:
                if r[k] == 'read':
                    rd_n[k] += 1
                elif r[k] == 'dead':
                    dead_n[k] += 1
                elif r[k] is None:
                    unk_n += 1
        cand = sorted(k for k in R.REGS if ok and must and k in must and rd_n[k] > 0) if unk_n == 0 else []
        print('%s calls=%d must=%s read=%s dead=%s unknown=%d cand=%s' % (
            name, len(hits[va]), sorted(must) if ok else '-', dict(rd_n), dict(dead_n), unk_n, ','.join(cand) or '-'))
    if a.reasons:
        print('== 未確定の理由 (13 件の合計・レジスタ単位)')
        for k, v in reason.most_common():
            print('  %-44s %d' % (k, v))


if __name__ == '__main__':
    sys.exit(main())
