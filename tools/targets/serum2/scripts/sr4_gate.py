#!/usr/bin/env python3
"""SR-4 判定 gate。
usage: sr4_gate.py <sr4_summary.json> <pilot_results.json> [--pilot]
各 pilot は次を全て満たすとき PASS: result=bit-exact かつ最終 IR に未対応 SIMD helper の呼びが残らない かつ fp_alu_cov==1.0。
p1_unsupported>0 (P1 が直せなかった comis 分岐。偽陽性もある) は FAIL にせず警告表示 (その分岐は差分ハーネスの入力分布が両結果を踏むことだけが証拠)。
- 既定 (strict): 第 1 段 (WT osc / filter / voice の vtable root 56 関数) が全て PASS しない限り exit 1。
- --pilot: pilot ごとの期待 (pilots.tsv の expect) と観測が一致するかだけを判定 (exit 0 = 期待通り。期待 fail が PASS に化けたら exit 1 =
  期待表の陳腐化 / gate の検出力喪失を疑う)。
exit code: 0 = 判定通過 / 1 = 不合格 / 2 = 入力不正。"""
import sys, json
args = [a for a in sys.argv[1:] if not a.startswith('--')]
pilot_mode = '--pilot' in sys.argv
try:
    summ = json.load(open(args[0])); res = json.load(open(args[1]))
    assert isinstance(res, list) and res
except Exception as ex:
    print('FAIL(input): %s' % ex); sys.exit(2)

def verdict(d):
    why = []
    if d.get('result') != 'bit-exact': why.append('result=%s' % d.get('result'))
    if d.get('simd_unsupported_called'): why.append('simd_unsupported_called=%s' % d['simd_unsupported_called'])
    cov = d.get('fp_alu_cov')
    if cov is None or cov < 1.0: why.append('fp_alu_cov=%s' % (None if cov is None else '%.4f' % cov))
    return ('PASS', []) if not why else ('FAIL', why)

bad = 0
roots = sorted(set(sum(summ['root_funcs'].values(), [])))
passed_roots = set()
print('%-18s %-6s %-6s %s' % ('pilot', 'expect', 'obs', 'detail'))
for d in res:
    v, why = verdict(d)
    exp = d['expect'].upper()
    ok = (v == exp)
    if v == 'PASS' and d['begin'] in roots: passed_roots.add(d['begin'])
    if pilot_mode and not ok: bad += 1
    warn = ' [warn: p1_unsupported=%s]' % d['p1_unsupported'] if d.get('p1_unsupported') else ''
    print('%-18s %-6s %-6s %s%s%s' % (d['name'], exp, v, '; '.join(why) or 'bit-exact %s/%s, fp_alu %s/%s' % (d.get('match'), d.get('steps'), d.get('fp_alu_in_ir'), d.get('fp_alu')),
                                      warn, '' if ok else '   <-- EXPECTATION MISMATCH'))
print('stage1 roots bit-exact: %d/%d (wt_osc %d / filter %d / voice %d roots; union %d)' % (
    len(passed_roots), len(roots), len(summ['root_funcs']['wt_osc']), len(summ['root_funcs']['filter']), len(summ['root_funcs']['voice']), len(roots)))
if pilot_mode:
    print('PILOT GATE %s (%d expectation mismatches)' % ('OK' if not bad else 'FAIL', bad))
    sys.exit(1 if bad else 0)
if len(passed_roots) < len(roots):
    print('STAGE1 GATE FAIL: %d/%d roots not lifted bit-exact' % (len(roots) - len(passed_roots), len(roots))); sys.exit(1)
print('STAGE1 GATE OK'); sys.exit(0)
