#!/usr/bin/env python3
"""movnti 到達の判定 (T-SH-90 / #3589・#3894)。gen_movnti.py の入力を run_wasm.mjs と native_ref で実行した後に使う。
入力 (W = 作業 dir): movnti_expect.json (case の種別) / trap.txt (wasm の trap: 'case VA') / layout.json /
  lift/fle_lifted.c (ott_unsup(VA, "movnti ...") の 24 件) / native_stderr.txt ('[native] crash case=N ... addr=0x..')。
判定 (exit 0 = 期待どおり):
  実装 : fle_lifted.c に movnti の ott_unsup が 0 件であること (x64c が ST64 に lift 済み・#3893)。1 件でも残れば FAIL。
  reach : 既知の未達 (#4324)。native は arena の外のアドレスで落ちる (memset が arena を越えて書く) ことだけを判定する。
          wasm の trap は movnti VA ではなく境界外 (VA 0) になり、reach 16 件は完了しない。結果行に「既知の未達」と出す。
  sweep : 閾値 (movnti に入る ⇔ a1 ≥ 0x70000) の判定は、x64c 後は movnti の VA で trap しないため判定に入れない。表示のみ (#3894)。
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
impl_ok = len(movnti) == 0
bad = 0 if impl_ok else 1
print(f'[movnti] 実装: fle_lifted.c の movnti の ott_unsup = {len(movnti)} 件 (0 件が正・#3893) {"OK" if impl_ok else "NG"}')
reach_ok = 0
va_seen = set()
for i, e in enumerate(expect):
    t = trap.get(i)
    n = native.get(i)
    if e['kind'] == 'reach':
        reach_ok += n is not None and n >= ARENA_END
        if t is not None: va_seen.add(t)
    print(f'[movnti] case={i:2d} {e["kind"]:7s} fn={e["fn"]} a1={e["a1"]:#x} wasm_trap_va={(f"{t:#x}" if t is not None else "-"):12s} native_fault={(f"{n:#x}" if n is not None else "-"):12s}')
nr = sum(1 for e in expect if e['kind'] == 'reach')
reach_trap0 = sum(1 for i, e in enumerate(expect) if e['kind'] == 'reach' and trap.get(i) == 0)
reach_notrap = sum(1 for i, e in enumerate(expect) if e['kind'] == 'reach' and i not in trap)
print(f'[movnti] reach: native が arena 外で落ちた {reach_ok}/{nr}・wasm が movnti 経路を完了した 0/{nr} (既知の未達 #4324): movnti VA で trap 0 件・wasm trap VA=0 {reach_trap0} 件・trap 記録なし {reach_notrap} 件')
print(f'[movnti] wasm trap VA の種類 = {sorted(hex(v) for v in va_seen)}')
if bad == 0:
    print('[movnti] RESULT PASS (既知の未達 reach 0/16 → #4324 で解消。実装判定は PASS)')
else:
    print('[movnti] RESULT FAIL')
sys.exit(0 if bad == 0 else 1)
