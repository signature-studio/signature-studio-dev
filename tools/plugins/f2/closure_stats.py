#!/usr/bin/env python3
"""PLG-F2 (#199): batch_lift.sh の出力 (work/batch/<block>/p.final.ll) と work/closure/<block>.json から、
プラグインごとの閉包統計を出す。差分試験の入口になる関数 (入口スロット / leaf) の把握が目的。

  python3 tools/plugins/f2/closure_stats.py [--json out.json] <block> ...

列の定義 (すべて p.final.ll の機械集計):
  defines   = `^define` 行数        / closure = closure JSON の unique_funcs (一致を assert)
  leaf      = 閉包内の他 function_* も `__asm_*` 以外の外部関数も呼ばない define
  asm       = `__asm_*` helper を 1 回以上呼ぶ define 数 (SSE/SIMD 命令の helper 化)
  icall     = レジスタ経由の間接 call (`call ... %reg`) を持つ define 数
  fr_call   = framework frontier (閉包外 function_*/sub_*) への直接 call を持つ define 数
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, '..', 'work')
M = {p['name']: p for p in json.load(open(os.path.join(HERE, '..', 'PLUGIN_MATRIX.json')))['plugins']}
BLOCK_NAME = {m['block']: p['name'] for p in M.values() for m in p['win']['modules']}

DEF = re.compile(r'^define [^@]*@(\w+)\(([^)]*)\)')
CALL = re.compile(r'\bcall\b[^@\n]*?(@[\w.]+|%[\w.]+)\(')


def parse(ll):
    funcs = {}
    cur = None
    for line in open(ll):
        m = DEF.match(line)
        if m:
            cur = funcs[m.group(1)] = {'args': m.group(2), 'calls': [], 'icall': 0, 'lines': 0}
            continue
        if cur is None:
            continue
        if line.startswith('}'):
            cur = None
            continue
        cur['lines'] += 1
        for c in CALL.finditer(line):
            t = c.group(1)
            if t.startswith('%'):
                cur['icall'] += 1
            else:
                cur['calls'].append(t[1:])
    return funcs


def stats(block):
    d = os.path.join(WORK, 'batch', str(block))
    clo = json.load(open(os.path.join(WORK, 'closure', 'block%05d.json' % block)))
    F = parse(os.path.join(d, 'p.final.ll'))
    names = set(F)
    leaf, asm, icall, frc = [], 0, 0, 0
    for n, f in F.items():
        ext = [c for c in f['calls'] if not c.startswith('__asm_') and not c.startswith('llvm.')]
        inner = [c for c in ext if c in names]
        outer = [c for c in ext if c not in names]
        if not inner and not outer and not f['icall']:
            leaf.append(n)
        asm += any(c.startswith('__asm_') for c in f['calls'])
        icall += bool(f['icall'])
        frc += bool(outer)
    entry_va = {v: k for k, v in clo['entries'].items()}
    return {
        'block': block, 'name': BLOCK_NAME.get(block, '?'),
        'defines': len(F), 'closure': clo['unique_funcs'], 'closure_bytes': clo['unique_bytes'],
        'entries': clo['entries'], 'leaf': len(leaf), 'asm': asm, 'icall': icall, 'fr_call': frc,
        'frontier_funcs': clo['framework_frontier_funcs'],
        'leaf_funcs': [{'fn': n, 'args': F[n]['args'].count('%'), 'lines': F[n]['lines'],
                        'entry': entry_va.get('0x' + n.split('_')[1])} for n in sorted(leaf)],
    }


def main():
    a = sys.argv[1:]
    out = None
    if a[:1] == ['--json']:
        out, a = a[1], a[2:]
    R = [stats(int(b)) for b in a]
    for r in R:
        assert r['defines'] == r['closure'], (r['block'], r['defines'], r['closure'])
    print('| block | plugin | defines(=closure) | closure x86 B | leaf | asm | icall | fr_call | frontier |')
    print('|--:|---|--:|--:|--:|--:|--:|--:|--:|')
    for r in R:
        print('| %d | %s | %d | %d | %d | %d | %d | %d | %d |' % (
            r['block'], r['name'], r['defines'], r['closure_bytes'], r['leaf'], r['asm'], r['icall'],
            r['fr_call'], r['frontier_funcs']))
    if out:
        json.dump(R, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main()
