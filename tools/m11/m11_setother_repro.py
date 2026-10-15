#!/usr/bin/env python3
"""set_other 非 imm 58 件の判定 (#3141 / M11-N173) の再現・基準との突合.

入力: m11_argrecover.py の台帳 FIXES.json (work-m11 の pads.json・fixes.json 由来)・PE (fl-win64)・IR (既定 work/boot_final.ll)。
分類器 (m11_setother_nonimm_class.py・HEAD) と基準 (git の --base-rev 版・既定 68eb512cd) を同じ入力で走らせ、次を出す。
  (1) HEAD の区分別件数 (実値化 / 復元不能 / 未決)
  (2) 基準の理由が N171 の 58 件候補 (call_ret・chain>call_ret・arith・chain>arith・stack_narrow) の行の、基準→HEAD の理由対応
  (3) 対象外 (上記以外) の行で理由が変わった件数 (期待 0)
  (4) 直接 call の callee (台帳の matched 行) に ret_value を適用した終端の分布 (REPORT_N173 §4)
使い方: python3 m11_setother_repro.py FIXES.json --pe PE [--ir work/boot_final.ll] [--base-rev 68eb512cd]
注意: 分類器は実行のたび FIXES.json と同じ dir に nonimm_class_rows.json を書く。基準を先に走らせ HEAD を後に走らせるため、
      終了後のファイルは HEAD の行。
"""
import argparse, collections, contextlib, io, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'ldfix')); sys.path.insert(0, HERE)
import ldmach

CLS = os.path.join(HERE, 'm11_setother_nonimm_class.py')
BASE_REV = '68eb512cd'
N171_58 = {'call_ret', 'chain>call_ret', 'arith', 'chain>arith', 'stack_narrow'}


def classify(src_text, fixes_path, pe, ir=None, machine=None):
    """分類器 (ソース文字列) を実行し、名前空間 (rows・ret_value・fn を含む) を返す。
    ir は HEAD 版だけが受け取る (基準版 68eb512cd に --ir は無い)。machine を渡すと ldmach.Machine の代わりに使う (合成機械語の対照検査用)。"""
    orig = ldmach.Machine
    if machine is not None:
        ldmach.Machine = lambda _pe: machine
    argv = sys.argv
    sys.argv = [CLS, fixes_path, '--pe', pe] + (['--ir', ir] if ir else [])
    g = {'__name__': 'm11_setother_nonimm_class', '__file__': CLS}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(src_text, CLS, 'exec'), g)
    finally:
        sys.argv = argv
        ldmach.Machine = orig
    return g


def direct_callees(g, fixes):
    """matched 行のうち、台帳 k 番目の直接 call が機械語で見つかる callee の VA 集合 (main 経路と同じ条件)。"""
    out = set()
    for r in fixes['site_detail']:
        if r['status'] != 'matched':
            continue
        cva = int(r['caller'].split('_')[1], 16)
        tva = int(r['callee'].split('_')[1], 16)
        ins = g['fn'](cva).ins
        calls = [i for i, x in enumerate(ins) if x.mnemonic == 'call' and x.operands
                 and x.operands[0].imm == tva]
        if r['k'] < len(calls):
            out.add(tva)
    return sorted(out)


def run(fixes_path, pe, ir, base_src, machine=None, out=print):
    """(1)-(4) を実行して結果 dict を返す。base_src は基準版の分類器ソース文字列。"""
    fixes = json.load(open(fixes_path))
    base = classify(base_src, fixes_path, pe, None, machine)
    head = classify(open(CLS).read(), fixes_path, pe, ir, machine)
    bkey = {(r['caller'], r['callee'], r['k'], r['pos']): r for r in base['rows']}
    res = {'head_counts': collections.Counter(r['class'] for r in head['rows']),
           'head_total': len(head['rows']), 'pairs58': collections.Counter(), 'n58': 0,
           'other_changed': 0, 'other_total': 0}
    for h in head['rows']:
        b = bkey.get((h['caller'], h['callee'], h['k'], h['pos']))
        if b is None:
            continue
        if b['reason'] in N171_58:
            res['n58'] += 1
            res['pairs58'][(b['reason'], h['reason'])] += 1
        else:
            res['other_total'] += 1
            res['other_changed'] += int(b['reason'] != h['reason'])
    ends = collections.Counter()
    callees = direct_callees(head, fixes)
    for va in callees:
        cls, why, _val, _da = head['ret_value'](va, 'rax')
        ends['ret_const' if cls == '実値化' else why.replace('ret>', '', 1)] += 1
    res['callees'] = len(callees)
    res['ret_ends'] = ends
    out('[repro] HEAD 台帳非 imm %d 件: %s' % (res['head_total'], dict(res['head_counts'])))
    out('[repro] 基準 %s の N171 58 候補 (call_ret・chain>call_ret・arith・chain>arith・stack_narrow): %d 件 (期待 58)'
        % (BASE_REV, res['n58']))
    for (b, h), v in sorted(res['pairs58'].items()):
        out('[repro]   基準 %-16s → HEAD %-30s %d' % (b, h, v))
    out('[repro] 対象外 %d 件のうち理由が変わった件: %d (期待 0)' % (res['other_total'], res['other_changed']))
    out('[repro] §4 直接 call の callee: %d 件 (期待 202)。ret_value 終端 (ret> を除く):' % res['callees'])
    for k, v in ends.most_common():
        out('[repro]   %-22s %d' % (k, v))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fixes'); ap.add_argument('--pe', required=True)
    ap.add_argument('--ir', default='work/boot_final.ll')
    ap.add_argument('--base-rev', default=BASE_REV)
    a = ap.parse_args()
    base_src = subprocess.run(['git', 'show', '%s:tools/m11/m11_setother_nonimm_class.py' % a.base_rev],
                              cwd=HERE, capture_output=True, text=True, check=True).stdout
    run(a.fixes, a.pe, a.ir, base_src)


if __name__ == '__main__':
    main()
