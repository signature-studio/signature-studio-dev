#!/usr/bin/env python3
"""#1220: gradeChar (`[[[0x15e4790]]+0xd0]`) の退避アドレス経由アクセスを関数単位で追跡する (読取専用)。

方法: GS ロード (`mov r1,[0x15e4790]`) を含む各関数を .pdata の境界どおり先頭から線形に走査し、次のタグを
レジスタと rbp/rsp 基準のスタックスロットに伝播する。
  GS      : `mov r1,[GSLOT]` の値
  OBJ     : `mov r2,[r1]` (r1 が GS) の値 = obj
  FLD@va  : `lea X,[obj+0xd0]` (va はその lea 命令) = gradeChar ポインタフィールドのアドレス
  GCP@x   : `mov Y,[obj+0xd0]` (x=d) または `mov Y,[X]` (X は FLD@va, x=va) = gradeChar バイトのポインタ
GCP を基底に持つ byte アクセスを、直接 (x=d) と退避アドレス経由 (x=lea の VA) に分けて数える。
限界: 分岐の合流を見ない線形走査 (タグは後続ブロックへ残る)。call の引数レジスタ (rcx/rdx/r8/r9) に残ったタグは
passed として列挙するが、その先 (callee) は追わない = 未網羅。`[r+r*k]` 形は complex として数える。
usage: python3 probe_1220.py [--no-slot]   (--no-slot: スタック退避の伝播を止める = ネガティブコントロール)
"""
import json, os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from peidx import Image, rip_target  # noqa: E402
from scan_consumers import _CANON, VOLATILE, GSLOT, GOFF  # noqa: E402

MEM = re.compile(r'\[(\w+)(?: ([+-]) (0x[0-9a-fA-F]+|\d+))?\]')
ARGREGS = ('rcx', 'rdx', 'r8', 'r9')


def parse_mem(s):
    m = MEM.search(s)
    if not m:
        return None
    d = 0
    if m.group(3):
        v = int(m.group(3), 0)
        d = v if m.group(2) == '+' else -v
    return m.group(1), d


def canon(name):
    return _CANON.get(name)


def is_r64(name):
    return name.startswith('r') and not re.search(r'\d[dwb]$', name) and name in _CANON


def run_func(ins, use_slot):
    regs, slots = {}, {}
    ev = []
    for x in ins:
        mn, va = x.mnemonic, x.address
        if mn == 'call':
            for r in ARGREGS:
                t = regs.get(r)
                if t:
                    ev.append({'va': va, 'ev': 'passed', 'text': f'call (arg {r}: {",".join(sorted(t))})'})
            for r in list(regs):
                if r in VOLATILE:
                    del regs[r]
            continue
        if mn.startswith('j') or mn in ('ret', 'nop', 'int3') or not x.op_str:
            continue
        ops = [o.strip() for o in x.op_str.split(',')]
        text = f'{mn} {x.op_str}'
        # 1) メモリオペランドのアクセス判定
        for i, o in enumerate(ops):
            if '[' not in o:
                continue
            pm = parse_mem(o)
            if pm is None:
                if any(regs.get(canon(w)) for w in re.findall(r'\b[a-z][a-z0-9]*\b', o) if canon(w)):
                    ev.append({'va': va, 'ev': 'complex', 'text': text})
                continue
            b, d = pm
            if b in ('rip',):
                continue
            if b in ('rbp', 'rsp'):
                if use_slot and mn == 'mov' and i == 0 and len(ops) == 2:
                    if canon(ops[1]):
                        slots[f'{b}{d:+d}'] = set(regs.get(canon(ops[1]), set()))
                    else:
                        slots.pop(f'{b}{d:+d}', None)
                elif i == 0 and mn not in ('cmp', 'test', 'push'):
                    slots.pop(f'{b}{d:+d}', None)
                continue
            bt = regs.get(canon(b), set())
            if not bt:
                continue
            is_write = i == 0 and mn not in ('cmp', 'test', 'push')
            origins = [t for t in bt if t.startswith('GCP@')]
            if origins and d == 0:
                kind = 'gcp_byte' if 'byte ptr' in o else 'gcp_other'
                for t in origins:
                    ev.append({'va': va, 'ev': kind, 'rw': 'write' if is_write else 'read',
                               'origin': t[4:], 'text': text})
            if d == 0 and any(t.startswith('FLD@') for t in bt):
                if is_write:
                    ev.append({'va': va, 'ev': 'fld_write', 'rw': 'write', 'origin': next(t[4:] for t in bt if t.startswith('FLD@')), 'text': text})
                else:
                    ev.append({'va': va, 'ev': 'fld_read', 'rw': 'read', 'origin': next(t[4:] for t in bt if t.startswith('FLD@')), 'text': text})
        # 2) 値の伝播
        if mn == 'lea' and len(ops) == 2 and canon(ops[0]):
            new = set()
            pm = parse_mem(ops[1])
            if pm and pm[0] not in ('rbp', 'rsp', 'rip'):
                b, d = pm
                bt = regs.get(canon(b), set())
                if 'OBJ' in bt and d == GOFF:
                    new = {f'FLD@{va:x}'}
                elif d == 0:
                    new = {t for t in bt if t.startswith(('FLD@', 'GCP@', 'OBJ'))}
            if is_r64(ops[0]):
                regs[canon(ops[0])] = new
            else:
                regs.pop(canon(ops[0]), None)
        elif mn in ('mov', 'movzx', 'movsx', 'movsxd', 'movabs') and len(ops) == 2 and canon(ops[0]):
            new = set()
            s = ops[1]
            if canon(s):
                new = set(regs.get(canon(s), set()))
            elif 'rip' in s and rip_target_of(s, x) == GSLOT:
                new = {'GS'}
            else:
                pm = parse_mem(s)
                if pm and pm[0] in ('rbp', 'rsp'):
                    new = set(slots.get(f'{pm[0]}{pm[1]:+d}', set())) if use_slot else set()
                elif pm and pm[0] != 'rip':
                    b, d = pm
                    bt = regs.get(canon(b), set())
                    if 'OBJ' in bt and d == GOFF and is_r64(ops[0]):
                        new = {'GCP@d'}
                    elif 'GS' in bt and d == 0:
                        new = {'OBJ'}
                    elif d == 0 and is_r64(ops[0]):
                        new = {f'GCP@{t[4:]}' for t in bt if t.startswith('FLD@')}
            if is_r64(ops[0]):
                regs[canon(ops[0])] = new
            else:
                regs.pop(canon(ops[0]), None)
        elif mn not in ('cmp', 'test', 'push') and canon(ops[0]) and mn != 'mov':
            regs.pop(canon(ops[0]), None)
    return ev


def rip_target_of(s, x):
    import peidx
    m = peidx.RIP.search(s)
    if not m:
        return None
    d = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
    return x.address + x.size + d


def main(use_slot=True):
    t0 = time.time()
    im = Image()
    results = {}
    n_func = 0
    for lo, hi, ins in im.iter_insns():
        if not any(rip_target(i) == GSLOT and i.mnemonic == 'mov' and i.op_str.startswith('r') for i in ins):
            continue
        n_func += 1
        ev = run_func(ins, use_slot)
        if ev:
            results[lo] = ev
    return im, n_func, results, time.time() - t0


if __name__ == '__main__':
    use_slot = '--no-slot' not in sys.argv
    im, n_func, results, dt = main(use_slot)
    esc = {}
    lea_sites = set()
    for f, evs in results.items():
        for e in evs:
            if e['ev'] in ('gcp_byte', 'gcp_other', 'fld_write', 'fld_read') and e.get('origin') not in ('d', None):
                esc.setdefault(f, []).append(e)
            if e['ev'] in ('fld_read', 'fld_write'):
                lea_sites.add(e['origin'])
    n_esc = sum(len(v) for v in esc.values())
    cplx = sum(1 for evs in results.values() for e in evs if e['ev'] == 'complex')
    _, _, res0, _ = main(False)
    neg = sum(1 for evs in res0.values() for e in evs if e.get('origin') not in (None, 'd') and e['ev'] in ('gcp_byte', 'gcp_other'))
    byte_esc = {f: [e for e in v if e['ev'] in ('gcp_byte', 'gcp_other')] for f, v in esc.items()}
    byte_esc = {f: v for f, v in byte_esc.items() if v}
    summary = {'walked_funcs': n_func, 'escaped_byte_funcs': len(byte_esc),
               'escaped_byte_read': sum(1 for v in byte_esc.values() for e in v if e['rw'] == 'read'),
               'escaped_byte_write': sum(1 for v in byte_esc.values() for e in v if e['rw'] == 'write'),
               'complex_events_unresolved': cplx, 'negctl_no_slot_escaped_byte': neg,
               'elapsed_s': round(dt, 2)}
    print(json.dumps(summary))
    ok = (summary['escaped_byte_read'], summary['escaped_byte_write'], summary['complex_events_unresolved'],
          summary['negctl_no_slot_escaped_byte']) == (207, 69, 0, 0)
    print(('PASS ' if ok else 'FAIL ') + '#1220 退避経由 gradeChar 追跡の期待値 (read 207 / write 69 / 複合 0 / ネガコン 0)')
    if not ok:
        sys.exit(1)
    if '--write' in sys.argv:
        out = os.path.join(HERE, 'results')
        os.makedirs(out, exist_ok=True)
        rows = {f'0x{f:x}': sorted({(e['ev'], e.get('rw'), e.get('origin'), e['va']) for e in v}) for f, v in esc.items()}
        json.dump({'summary': summary, 'escaped_funcs': {k: [list(t) for t in v] for k, v in rows.items()}},
                  open(os.path.join(out, 'escaped_1220.json'), 'w'), indent=1)
