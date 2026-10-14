#!/usr/bin/env python3
"""#1492: 退避経由 gradeChar 追跡の基本ブロック版 (分岐合流 + 直接 call の callee 越し)。読取専用。

probe_1220.py (線形走査) との違い:
  - 関数を基本ブロックに分け、分岐の合流では状態 (レジスタ・スタックスロットのタグ集合) の和集合を取る不動点計算。
  - 直接 call (`call 0x...`) は引数レジスタ (rcx/rdx/r8/r9) のタグを callee の入口状態に渡し、callee を解析する。
    callee の戻り値 (rax のタグ) は呼出し元へ返す。
限界 (未網羅・件数を結果 JSON の untraced に出す): 間接 call・間接 jmp (jump table)・.pdata 外への jmp・
スタック渡し引数 (push したタグ)・深さ上限 (DEPTH_MAX)・callee 再帰。
usage: python3 probe_1492.py [--write] [--no-slot] [--no-callee] [--no-rec-summary]  (環境変数 PROBE_DEPTH で callee 深さ上限)
  --no-slot: スタック退避の伝播を止める (ネガティブコントロール。退避経由は 0 件になるはず)
  --no-callee: callee 越しを止める (callee 越しの寄与を見る比較用)
  --no-rec-summary: 再帰打切り (approx) の要約を空にする (アブレーション。再帰要約の寄与を見る比較用)
"""
import json, os, re, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from peidx import Image, rip_target  # noqa: E402
from scan_consumers import GSLOT, GOFF, VOLATILE  # noqa: E402
from probe_1220 import parse_mem, canon, is_r64, rip_target_of, ARGREGS, run_func  # noqa: E402

DEPTH_MAX = int(os.environ.get('PROBE_DEPTH', '30'))
INDIRECT_RIP = re.compile(r'^qword ptr \[rip ([+-]) 0x[0-9a-f]+\]$')
HEXIMM = re.compile(r'^0x[0-9a-f]+$')
EMPTY = frozenset()
NO_REC = '--no-rec-summary' in sys.argv


def direct_imm(x):
    s = x.op_str.strip()
    return int(s, 16) if HEXIMM.match(s) else None


def setr(regs, op, new):
    c = canon(op)
    if not c:
        return
    if is_r64(op) and new:
        regs[c] = new
    else:
        regs.pop(c, None)


def copy_state(st):
    return (dict(st[0]), dict(st[1]))


def join(a, b):
    if a is None:
        return copy_state(b)
    r = dict(a[0])
    for k, v in b[0].items():
        r[k] = r.get(k, EMPTY) | v
    s = dict(a[1])
    for k, v in b[1].items():
        s[k] = s.get(k, EMPTY) | v
    return (r, s)


def transfer(st, x, out, az):
    regs, slots = st
    mn, va, op = x.mnemonic, x.address, x.op_str
    if mn == 'call':
        evs, rax = az.on_call(x, regs)
        if out is not None:
            out.extend(evs)
        for r in list(regs):
            if r in VOLATILE:
                del regs[r]
        setr(regs, 'rax', rax)
        return
    if mn.startswith('j') or mn in ('ret', 'nop', 'int3') or not op:
        return
    ops = [o.strip() for o in op.split(',')]
    text = f'{mn} {op}'

    def emit(d):
        if out is not None:
            out.append(d)

    if mn == 'push' and canon(ops[0]) and regs.get(canon(ops[0])):
        emit({'ev': 'untraced', 'why': 'push-tag', 'va': va})
    for i, o in enumerate(ops):
        if '[' not in o:
            continue
        pm = parse_mem(o)
        if pm is None:
            if any(regs.get(canon(w)) for w in re.findall(r'\b[a-z][a-z0-9]*\b', o) if canon(w)):
                emit({'ev': 'complex', 'va': va, 'text': text})
            continue
        b, d = pm
        if b == 'rip':
            continue
        if b in ('rbp', 'rsp'):
            key = f'{b}{d:+d}'
            if az.use_slot and mn == 'mov' and i == 0 and len(ops) == 2:
                if canon(ops[1]):
                    new = regs.get(canon(ops[1]), EMPTY)
                    if new:
                        slots[key] = new
                    else:
                        slots.pop(key, None)
                else:
                    slots.pop(key, None)
            elif i == 0 and mn not in ('cmp', 'test', 'push'):
                slots.pop(key, None)
            continue
        bt = regs.get(canon(b), EMPTY)
        if not bt:
            continue
        is_write = i == 0 and mn not in ('cmp', 'test', 'push')
        rw = 'write' if is_write else 'read'
        origins = sorted(t for t in bt if t.startswith('GCP@'))
        if origins and d == 0:
            kind = 'gcp_byte' if 'byte ptr' in o else 'gcp_other'
            for t in origins:
                emit({'ev': kind, 'va': va, 'rw': rw, 'origin': t[4:], 'text': text})
        flds = sorted(t for t in bt if t.startswith('FLD@'))
        if d == 0 and flds:
            emit({'ev': 'fld_write' if is_write else 'fld_read', 'va': va, 'rw': rw,
                  'origin': flds[0][4:], 'text': text})
    # 値の伝播 (probe_1220.run_func と同じ規則。分岐合流は呼出し側の join が担う)
    if mn == 'lea' and len(ops) == 2 and canon(ops[0]):
        new = EMPTY
        pm = parse_mem(ops[1])
        if pm and pm[0] not in ('rbp', 'rsp', 'rip'):
            b, d = pm
            bt = regs.get(canon(b), EMPTY)
            if 'OBJ' in bt and d == GOFF:
                new = frozenset({f'FLD@{va:x}'})
            elif d == 0:
                new = frozenset(t for t in bt if t.startswith(('FLD@', 'GCP@', 'OBJ')))
        setr(regs, ops[0], new)
    elif mn in ('mov', 'movzx', 'movsx', 'movsxd', 'movabs') and len(ops) == 2 and canon(ops[0]):
        new = EMPTY
        s = ops[1]
        if canon(s):
            new = regs.get(canon(s), EMPTY)
        elif 'rip' in s and rip_target_of(s, x) == GSLOT:
            new = frozenset({'GS'})
        else:
            pm = parse_mem(s)
            if pm and pm[0] in ('rbp', 'rsp'):
                new = slots.get(f'{pm[0]}{pm[1]:+d}', EMPTY) if az.use_slot else EMPTY
            elif pm and pm[0] != 'rip':
                b, d = pm
                bt = regs.get(canon(b), EMPTY)
                if 'OBJ' in bt and d == GOFF and is_r64(ops[0]):
                    new = frozenset({'GCP@d'})
                elif 'GS' in bt and d == 0:
                    new = frozenset({'OBJ'})
                elif d == 0 and is_r64(ops[0]):
                    new = frozenset(f'GCP@{t[4:]}' for t in bt if t.startswith('FLD@'))
        setr(regs, ops[0], new)
    elif mn not in ('cmp', 'test', 'push') and canon(ops[0]) and mn != 'mov':
        regs.pop(canon(ops[0]), None)


class Az:
    def __init__(self, im, use_slot=True, use_callee=True):
        self.im = im
        self.use_slot = use_slot
        self.use_callee = use_callee
        self.hi = {lo: hi for lo, hi in im.funcs if im.text_lo <= lo < im.text_hi}
        self.dis = {}
        self.memo = {}
        self.approx = {}
        self.inprog = set()
        self.depth = 0
        self.lims = set()
        self.unreach = {}
        self.stat = {'join_edges': 0, 'join_disagree': 0, 'join_new': 0}
        self.written = self._refs()

    def _refs(self):
        refs = set()
        for lo in self.hi:
            for x in self.fn(lo):
                if x.mnemonic == 'call':
                    continue
                t = rip_target(x)
                if t is not None:
                    refs.add(t)
                refs.update(int(h, 16) for h in re.findall(r'0x[0-9a-f]+', x.op_str))
        return refs

    def static_slot_target(self, x):
        if x.mnemonic != 'call' or not INDIRECT_RIP.match(x.op_str):
            return None
        slot = rip_target(x)
        if slot in self.written:
            return None
        val = struct.unpack('<Q', self.im.read(slot, 8))[0]
        return val if val in self.hi else None

    def fn(self, lo):
        if lo not in self.dis:
            self.dis[lo] = self.im.disasm_func(lo, self.hi[lo])
        return self.dis[lo]

    def has_gs(self, lo):
        return any(rip_target(i) == GSLOT and i.mnemonic == 'mov' and i.op_str.startswith('r') for i in self.fn(lo))

    def lim(self, why, va):
        self.lims.add((why, va))

    def blocks(self, lo, ins):
        idx = {x.address: i for i, x in enumerate(ins)}
        lead = {0}
        for i, x in enumerate(ins):
            mn = x.mnemonic
            if mn.startswith('j') or mn in ('ret', 'ud2', 'int3', 'hlt'):
                if i + 1 < len(ins):
                    lead.add(i + 1)
                t = direct_imm(x) if mn.startswith('j') else None
                if t is not None and t in idx:
                    lead.add(idx[t])
        starts = sorted(lead)
        bl = [(s, starts[k + 1] if k + 1 < len(starts) else len(ins)) for k, s in enumerate(starts)]
        bidx = {s: k for k, (s, _) in enumerate(bl)}
        succ = []
        for k, (s, e) in enumerate(bl):
            last = ins[e - 1]
            mn = last.mnemonic
            ss = []
            if mn in ('ret', 'ud2', 'int3', 'hlt'):
                pass
            elif mn.startswith('j'):
                t = direct_imm(last)
                if t is not None and t in idx:
                    ss.append(bidx[idx[t]])
                elif t is None:
                    self.lim('indirect-jmp', last.address)
                else:
                    self.lim('jmp-out', last.address)
                if mn != 'jmp' and e < len(ins):
                    ss.append(k + 1)
            elif e < len(ins):
                ss.append(k + 1)
            succ.append(ss)
        return bl, succ

    def fixpoint(self, lo, entry):
        ins = self.fn(lo)
        bl, succ = self.blocks(lo, ins)
        st_in = {0: entry}
        work = [0]
        while work:
            b = work.pop()
            st = copy_state(st_in[b])
            s, e = bl[b]
            for x in ins[s:e]:
                transfer(st, x, None, self)
            for t in succ[b]:
                pre = st_in.get(t)
                new = join(pre, st)
                if pre is not None:
                    self.stat['join_edges'] += 1
                    if st != pre:
                        self.stat['join_disagree'] += 1
                    if new != pre and new != st:
                        self.stat['join_new'] += 1
                if new != pre:
                    st_in[t] = new
                    work.append(t)
        return ins, bl, st_in

    def final(self, lo, entry):
        ins, bl, st_in = self.fixpoint(lo, entry)
        evs = []
        rax = EMPTY
        for b, (s, e) in enumerate(bl):
            if b not in st_in:
                self.unreach[(lo, s)] = e - s
                continue
            st = copy_state(st_in[b])
            loc = []
            for x in ins[s:e]:
                transfer(st, x, loc, self)
            if ins[e - 1].mnemonic == 'ret':
                rax = rax | st[0].get('rax', EMPTY)
            for d in loc:
                d.setdefault('fn', lo)
            evs.extend(loc)
        return evs, rax

    def analyze(self, lo, entry_regs):
        key = (lo, frozenset(entry_regs.items()))
        if key in self.memo:
            return self.memo[key]
        self.inprog.add(key)
        self.depth += 1
        try:
            res = self.final(lo, (dict(entry_regs), {}))
        finally:
            self.depth -= 1
            self.inprog.discard(key)
        self.memo[key] = res
        return res

    def on_call(self, x, regs):
        va = x.address
        sig = {r: regs[r] for r in ARGREGS if regs.get(r)}
        evs = []
        rax = EMPTY
        for r, t in sorted(sig.items()):
            evs.append({'ev': 'passed', 'va': va, 'why': r, 'origins': sorted(t)})
        tgt = direct_imm(x)
        if tgt is None:
            tgt = self.static_slot_target(x)
            if tgt is not None and sig:
                evs.append({'ev': 'static-indirect', 'why': 'slot', 'va': va, 'target': tgt})
        if tgt is None:
            if sig:
                evs.append({'ev': 'untraced', 'why': 'indirect-call-with-tag', 'va': va})
            self.lim('indirect-call', va)
        elif tgt not in self.hi:
            if sig:
                evs.append({'ev': 'untraced', 'why': 'callee-not-in-pdata', 'va': va})
        elif not self.use_callee:
            if sig:
                evs.append({'ev': 'untraced', 'why': 'callee-disabled', 'va': va})
        elif not sig and not self.has_gs(tgt):
            pass
        elif self.depth >= DEPTH_MAX:
            evs.append({'ev': 'untraced', 'why': 'depth', 'va': va})
        else:
            key = (tgt, frozenset(sig.items()))
            if key in self.inprog:
                evs.append({'ev': 'approx', 'why': 'recursive', 'va': va})
                cev, rax = ([], EMPTY) if NO_REC else self.approx.get(key, ([], EMPTY))
            else:
                cev, rax = self.analyze(tgt, sig)
            for e in cev:
                ne = dict(e)
                ne['via'] = (va,) + tuple(e.get('via', ()))
                evs.append(ne)
        return evs, rax


def keyof(e):
    return (e['va'], e['rw'], e['origin'])


def is_escaped_byte(e):
    return e.get('ev') in ('gcp_byte', 'gcp_other') and e.get('origin') != 'd'


def one_pass(az, roots):
    az.memo = {}
    az.unreach = {}
    az.lims = set()
    az.stat = {'join_edges': 0, 'join_disagree': 0, 'join_new': 0}
    new_keys, new_direct, new_via = {}, set(), set()
    untr = {}
    rec_roots = 0
    for lo in roots:
        evs, _ = az.analyze(lo, {})
        if any(e['ev'] == 'approx' and e['why'] == 'recursive' for e in evs):
            rec_roots += 1
        for e in evs:
            if e['ev'] == 'untraced':
                untr[e['why']] = untr.get(e['why'], 0) + 1
            if not is_escaped_byte(e):
                continue
            k = keyof(e)
            new_keys.setdefault(k, set()).add(e['fn'])
            if e.get('via'):
                new_via.add(k)
            else:
                new_direct.add(k)
    sig = frozenset((k, rax, frozenset(keyof(e) for e in evs if is_escaped_byte(e)))
                    for k, (evs, rax) in az.memo.items())
    return new_keys, new_direct, new_via, untr, rec_roots, sig


def main(use_slot, use_callee):
    t0 = time.time()
    im = Image()
    az = Az(im, use_slot, use_callee)
    roots = [lo for lo in az.hi if az.has_gs(lo)]
    prev = None
    az.converged = False
    for it in range(1, 33):
        new_keys, new_direct, new_via, untr, rec_roots, sig = one_pass(az, roots)
        if sig == prev:
            az.converged = True
            break
        prev = sig
        az.approx = dict(az.memo)
    az.iters = it
    t_new = time.time() - t0
    lin_keys, lin_fn = set(), set()
    for lo in roots:
        ins = az.fn(lo)
        for e in run_func(ins, use_slot):
            if is_escaped_byte(e):
                lin_keys.add(keyof(e))
                lin_fn.add(lo)
    rd = lambda ks: sum(1 for k in ks if k[1] == 'read')
    wr = lambda ks: sum(1 for k in ks if k[1] == 'write')
    only_lin = sorted(lin_keys - set(new_keys))
    only_new = sorted(set(new_keys) - lin_keys)
    summary = {
        'roots': len(roots),
        'linear': {'read': rd(lin_keys), 'write': wr(lin_keys), 'funcs': len(lin_fn)},
        'cfg': {'read': rd(new_keys), 'write': wr(new_keys), 'funcs': len({f for v in new_keys.values() for f in v})},
        'cfg_only_via_callee': {'read': rd(new_via - new_direct), 'write': wr(new_via - new_direct)},
        'lin_not_in_cfg': len(only_lin),
        'cfg_not_in_lin': len(only_new),
        'unreachable_blocks': len(az.unreach),
        'unreachable_insns': sum(az.unreach.values()),
        'join': dict(az.stat),
        'callee_tagged_pairs': sum(1 for (_, ent) in az.memo if ent),
        'roots_reaching_recursive': rec_roots,
        'fixpoint': {'iters': az.iters, 'converged': az.converged},
        'static_slot_calls': sum(1 for lo in az.hi for x in az.fn(lo) if az.static_slot_target(x)),
        'limits': {w: sum(1 for why, _ in az.lims if why == w) for w in sorted({w for w, _ in az.lims})},
        'untraced_events': untr,
        'elapsed_s': round(t_new, 2),
    }
    return summary, lin_keys, new_keys, only_lin, only_new, new_via - new_direct, az, time.time() - t0


if __name__ == '__main__':
    use_slot = '--no-slot' not in sys.argv
    use_callee = '--no-callee' not in sys.argv
    summary, lin_keys, new_keys, only_lin, only_new, via_only, az, dt = main(use_slot, use_callee)
    summary['elapsed_total_s'] = round(dt, 2)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if use_slot and use_callee:
        ok = (summary['linear']['read'], summary['linear']['write'], summary['linear']['funcs']) == (207, 69, 20)
        print(('PASS ' if ok else 'FAIL ') + '線形基準 (probe_1220 と同じ 207/69/20) の再現')
        if not ok:
            sys.exit(1)
    if '--no-slot' in sys.argv:
        ok = summary['cfg']['read'] == 0 and summary['cfg']['write'] == 0
        print(('PASS ' if ok else 'FAIL ') + 'ネガティブコントロール (--no-slot で退避経由 0 件)')
        if not ok:
            sys.exit(1)
    if '--write' in sys.argv:
        out = os.path.join(HERE, 'results')
        os.makedirs(out, exist_ok=True)
        dump = {
            'summary': summary,
            'only_linear': [list(k) for k in only_lin],
            'only_cfg': [list(k) for k in only_new],
            'cfg_only_via_callee': [list(k) for k in sorted(via_only)],
            'limits': sorted([list(x) for x in az.lims], key=lambda t: (t[0], t[1])),
            'untraced_tagged_indirect_call': sorted({(f'0x{e["fn"]:x}', f'0x{e["va"]:x}') for lo in az.hi if az.has_gs(lo)
                                                     for e in az.analyze(lo, {})[0]
                                                     if e['ev'] == 'untraced' and e['why'] == 'indirect-call-with-tag'}),
            'approx_recursive_call': sorted({(f'0x{e["fn"]:x}', f'0x{e["va"]:x}') for lo in az.hi if az.has_gs(lo)
                                             for e in az.analyze(lo, {})[0]
                                             if e['ev'] == 'approx' and e['why'] == 'recursive'}),
        }
        with open(os.path.join(out, 'escaped_1492.json'), 'w') as f:
            json.dump(dump, f, indent=1, ensure_ascii=False)
