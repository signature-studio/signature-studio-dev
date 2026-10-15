#!/usr/bin/env python3
"""movnti 到達の判定 (T-SH-90 / #3589)。gen_movnti.py の入力を run_wasm.mjs と native_ref で実行した後に使う。
入力 (W = 作業 dir): movnti_expect.json (case の種別) / trap.txt (wasm の trap: 'case VA') / layout.json /
  lift/fle_lifted.c (ott_unsup(VA, "movnti ...") の 24 件) / native_stderr.txt ('[native] crash case=N ... addr=0x..')。
判定 (exit 0 = 期待どおり):
  reach   : wasm が movnti の VA で trap し、native は arena の外のアドレスで落ちる (memset が arena を越えて書く)。
  info    : 閾値未満の対照。判定に入れず、trap の有無を表示する。
usage: movnti_check.py W
"""
import json, re, sys

W = sys.argv[1]
expect = json.load(open(f'{W}/movnti_expect.json'))
lay = json.load(open(f'{W}/layout.json'))
ARENA_END = lay['arena'] + lay['arena_sz']
movnti = {int(m.group(1), 16) for m in re.finditer(r'ott_unsup\(0x([0-9a-f]+)ULL, "movnti', open(f'{W}/lift/fle_lifted.c').read())}
trap = {}
for ln in open(f'{W}/trap.txt'):
    c, va = ln.split()
    trap[int(c)] = int(va, 16)
native = {}
for ln in open(f'{W}/native_stderr.txt'):
    m = re.search(r'\[native\] crash case=(\d+) .* addr=0x([0-9a-f]+)', ln)
    if m:
        native[int(m.group(1))] = int(m.group(2), 16)

print(f'[movnti] movnti VA = {len(movnti)} 件 (fle_lifted.c)・arena 末尾 = {ARENA_END:#x}')
bad = 0
reach_ok = ctrl_ok = 0
va_seen = set()
for i, e in enumerate(expect):
    t = trap.get(i)
    n = native.get(i)
    if e['kind'] == 'reach':
        ok = t in movnti and n is not None and n >= ARENA_END
        reach_ok += ok
        if t is not None: va_seen.add(t)
    else:
        # sweep: movnti に入る ⇔ a1 ≥ 0x70000 (静的読み count>>6 ≥ 0x1c00)。入るなら movnti の VA で trap、入らないなら movnti 以外で trap (VA 0 = memory OOB)
        ok = (t in movnti) == (e['a1'] >= 0x70000)
        ctrl_ok += ok
    bad += not ok
    t_s = f'{t:#x}' if t is not None else '-'
    n_s = f'{n:#x}' if n is not None else '-'
    print(f'[movnti] case={i:2d} {e["kind"]:7s} fn={e["fn"]} a1={e["a1"]:#x} wasm_trap_va={t_s:12s} native_fault={n_s:12s} {"OK" if ok else "NG"}')
nr = sum(1 for e in expect if e['kind'] == 'reach')
nc = sum(1 for e in expect if e['kind'] == 'sweep')
print(f'[movnti] reach {reach_ok}/{nr} (wasm trap at movnti VA・native が arena 外で落ちる)・sweep 閾値 (movnti に入る ⇔ a1 ≥ 0x70000) 一致 {ctrl_ok}/{nc}')
print(f'[movnti] wasm trap VA の種類 = {sorted(hex(v) for v in va_seen)}')
print(f'[movnti] RESULT {"PASS" if bad == 0 else "FAIL"}')
sys.exit(0 if bad == 0 else 1)
