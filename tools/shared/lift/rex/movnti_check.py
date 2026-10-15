#!/usr/bin/env python3
"""movnti 到達の判定 (T-SH-90 / #3589・#3894)。gen_movnti.py の入力を run_wasm.mjs と native_ref で実行した後に使う。
入力 (W = 作業 dir): movnti_expect.json (case の種別) / trap.txt (wasm の trap: 'case VA') / layout.json /
  lift/fle_lifted.c (ott_unsup(VA, "movnti ...") の 24 件) / native_stderr.txt ('[native] crash case=N ... addr=0x..')。
判定 (exit 0 = 期待どおり):
  実装 : fle_lifted.c に movnti の ott_unsup が 0 件であること (x64c が ST64 に lift 済み・#3893)。1 件でも残れば FAIL。
  reach : arena を 0x80000 にした (lift_x64c.sh movnti・#4324)。reach 16 件は native と wasm の両方が trap せず完了し、arena が一致し、
          arena[0:a1] が全 0 (memset が走った証拠。gen_movnti.py の番兵 [0x10000, 0x70000) が非ゼロのため、走らなければ FAIL)。
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
RES_REC = 16 + lay['arena_sz'] + lay['data_sz']
nat_rec = open(f'{W}/res_native.bin', 'rb').read()
was_rec = open(f'{W}/res_wasm.bin', 'rb').read()
CRASH = 0xC2A5C2A5C2A5C2A5
reach_ok = 0
va_seen = set()
memset_ok = 0
for i, e in enumerate(expect):
    t = trap.get(i)
    n = native.get(i)
    if e['kind'] == 'reach':
        a = nat_rec[i * RES_REC:(i + 1) * RES_REC]
        b = was_rec[i * RES_REC:(i + 1) * RES_REC]
        a1 = e['a1']
        zero = not any(a[16:16 + a1]) and not any(b[16:16 + a1])
        memset_ok += zero
        done = n is None and t is None and a[:8] != CRASH.to_bytes(8, 'little') and a[16:16 + lay['arena_sz']] == b[16:16 + lay['arena_sz']] and zero
        reach_ok += done
        if t is not None: va_seen.add(t)
    print(f'[movnti] case={i:2d} {e["kind"]:7s} fn={e["fn"]} a1={e["a1"]:#x} wasm_trap_va={(f"{t:#x}" if t is not None else "-"):12s} native_fault={(f"{n:#x}" if n is not None else "-"):12s}')
nr = sum(1 for e in expect if e['kind'] == 'reach')
reach_bad = nr - reach_ok
print(f'[movnti] reach: arena 内で完了 (native と wasm が arena を一致・trap なし) {reach_ok}/{nr}・不一致 {reach_bad}')
print(f'[movnti] reach: memset 通過 (native と wasm の両方で arena[0:a1] が全 0) {memset_ok}/{nr}')
print(f'[movnti] wasm trap VA の種類 = {sorted(hex(v) for v in va_seen)}')
reach_pass = reach_bad == 0
if bad == 0 and reach_pass:
    print('[movnti] RESULT PASS (reach 16 件は arena 内で完了 #4324・実装判定 PASS)')
else:
    print('[movnti] RESULT FAIL')
sys.exit(0 if bad == 0 and reach_pass else 1)
