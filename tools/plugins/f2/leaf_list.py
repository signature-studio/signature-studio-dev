#!/usr/bin/env python3
"""PLG-F2-3 (#515): 関数単位差分の対象 = 「lift 後 IR で leaf かつ機械語にも非 IAT 間接 call が無い」関数を列挙する。

  python3 tools/plugins/f2/leaf_list.py [--expect 23] <block> ...

入力 (f2_step1.sh の出力): work/f2_stats.json (IR leaf), work/f2/<block>.icall.json (audit_icall.py の関数別静的件数),
                           work/closure/block<N>.json / .ranges.txt (閉包の関数範囲・入口スロット)
出力: work/f2/leaf.json (block, plugin, va, 機械語バイト数, IR 仮引数数, 入口スロット), stdout に表
定義:
  IR leaf        = closure_stats.py の leaf (他 function_*・__asm_*/llvm.* 以外の外部関数・レジスタ間接 call を呼ばない define)
  機械語 間接なし = audit_icall.py の per_fn_cmp に va が無い (= 非 IAT の間接 call 命令が 0 件)
  対象           = 上記の積。 --expect を渡すと件数が一致しなければ exit 1
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, '..', 'work')
M = {m['block']: p['name'] for p in json.load(open(os.path.join(HERE, '..', 'PLUGIN_MATRIX.json')))['plugins']
     for m in p['win']['modules']}


def fn_sizes(block):
    """閉包 ranges ('0xA-0xB,...', 終端を含む) から {va: bytes}"""
    s = open(os.path.join(W, 'closure', 'block%05d.ranges.txt' % block)).read().strip()
    out = {}
    for r in s.split(','):
        a, b = r.split('-')
        out[int(a, 16)] = int(b, 16) - int(a, 16) + 1   # ranges は終端を含む (t0_balance: 0x5dee90-0x5df03f = 432 B)
    return out


def main():
    a = sys.argv[1:]
    expect = None
    if a[:1] == ['--expect']:
        expect, a = int(a[1]), a[2:]
    S = {r['block']: r for r in json.load(open(os.path.join(W, 'f2_stats.json')))}
    rows = []
    for b in map(int, a):
        ic = json.load(open(os.path.join(W, 'f2', '%d.icall.json' % b)))
        cmp_ = {r['fn']: r for r in ic['per_fn_cmp']}
        sz = fn_sizes(b)
        ent = {int(v, 16): k for k, v in S[b]['entries'].items()}
        for l in S[b]['leaf_funcs']:
            va = int(l['fn'][len('function_'):], 16)
            c = cmp_.get('0x%x' % va)   # per_fn_cmp は非 IAT 間接 call を 1 件以上持つ関数だけを列挙する (無い = 0 件)
            if c is None or c['static_call_ind'] == 0:
                rows.append({'block': b, 'plugin': M[b], 'va': '0x%x' % va, 'bytes': sz.get(va), 'ir_params': l['args'],
                             'ir_lines': l['lines'], 'entry': ent.get(va)})
    json.dump(rows, open(os.path.join(W, 'f2', 'leaf.json'), 'w'), indent=1)
    print('| # | block | plugin | VA | 機械語 B | IR 仮引数 | IR 行 | 入口スロット |')
    print('|--:|--:|---|---|--:|--:|--:|---|')
    for i, r in enumerate(rows, 1):
        print('| %d | %d | %s | %s | %s | %d | %d | %s |' % (i, r['block'], r['plugin'], r['va'], r['bytes'], r['ir_params'], r['ir_lines'], r['entry'] or '-'))
    print('対象 %d 関数 / %d block' % (len(rows), len({r['block'] for r in rows})))
    if expect is not None and len(rows) != expect:
        print('FAIL: 期待 %d 件 != 実測 %d 件' % (expect, len(rows)), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
