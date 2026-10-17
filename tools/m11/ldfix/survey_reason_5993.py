#!/usr/bin/env python3
# survey_reason_5993.py — #5993: survey で到達しない 10 関数の理由を、IR の直接 call 閉包で関数ごとに出す。
# 使い方: python3 survey_reason_5993.py IR.ll UNITVA.txt [OUT.json]
#   IR.ll      : boot_final3.ll (既定 $M11_WORK/boot_final3.ll)
#   UNITVA.txt : unitva.mjs が出す 942 行の unit init proc VA (16 進、0 は proc 無し)
# 出力: 関数ごとに 直接呼び出し元 / 直接 call 閉包の大きさ / 閉包の根 (呼び出し元が IR に無い関数) /
#       閉包に unit proc が含まれるか / 根が call 以外 (関数ポインタ・m11_tr) で参照されるか。
import re, sys, json, collections

TARGETS = ['101d180', '1050f90', '10626e0', '10628d0', '12f9730',
           '5c44b0', '6905f0', '75a180', '786d50', '787380']
IR, UNITS = sys.argv[1], sys.argv[2]
OUT = sys.argv[3] if len(sys.argv) > 3 else None

define = re.compile(r'^define [^@]*@(\S+?)\(')
call_re = re.compile(r'call [^@]*@function_([0-9a-f]+)\(')
ref_re = re.compile(r'@function_([0-9a-f]+)\b')
tr_re = re.compile(r'@m11_tr_function_([0-9a-f]+)\b')

callers = collections.defaultdict(set)   # callee -> direct callers
noncall_ref = set()                      # function_X が call 以外で参照される
tr_ref = set()                           # m11_tr_function_X の参照 (ICALL テーブル等)
cur = None
with open(IR, errors='replace') as f:
    for line in f:
        m = define.match(line)
        if m:
            name = m.group(1)
            cur = name[len('function_'):] if name.startswith('function_') else None
            continue
        if line.startswith(('}', 'declare')):
            cur = None if line.startswith('}') else cur
            continue
        cs = set(call_re.findall(line))
        if cur is not None:
            for c in cs:
                callers[c].add(cur)
        for r in ref_re.findall(line):
            if r not in cs:
                noncall_ref.add(r)
        for r in tr_re.findall(line):
            tr_ref.add(r)

units = set(l.strip() for l in open(UNITS) if l.strip() and l.strip() != '0')

result = {}
for t in TARGETS:
    seen, frontier = {t}, [t]
    while frontier:
        nxt = []
        for x in frontier:
            for c in callers.get(x, ()):
                if c not in seen:
                    seen.add(c)
                    nxt.append(c)
        frontier = nxt
    anc = seen - {t}
    roots = sorted(x for x in anc if not callers.get(x))
    result[t] = {
        'direct_callers': sorted(callers.get(t, ())),
        'closure_size': len(anc),
        'unit_procs_in_closure': sorted(anc & units),
        'roots': roots,
        'roots_noncall_ref': sorted(r for r in roots if r in noncall_ref),
        'roots_tr_ref': sorted(r for r in roots if r in tr_ref),
    }
    print('%s direct=%s closure=%d units_in_closure=%d roots=%d roots_tr_ref=%d' % (
        t, len(result[t]['direct_callers']), len(anc), len(anc & units),
        len(roots), len(result[t]['roots_tr_ref'])))

if OUT:
    json.dump(result, open(OUT, 'w'), indent=1)
