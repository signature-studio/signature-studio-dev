#!/usr/bin/env python3
"""classify_err_cand_4972.py — #4972 (CI-201): COPY ERR_CAND 57 件の窓による人手判定を表にする。

使い方: python3 classify_err_cand_4972.py JUDGE.json --md OUT.md
  JUDGE.json: judge_copy_3382.py --out の出力 (verdict == ERR_CAND の行を対象)
  判定の根拠は show_site_2555.py の窓 (機械語 6 命令 + IR 対応行) を読んだ結果を SITE_VERDICT に書いたもの。
  窓で決まらなかった行は『判定不能』とし、理由の類型を付ける。
"""
import argparse
import json
import re
from collections import Counter

# (fn, call_va) -> (判定, 窓で見た根拠)
SITE_VERDICT = {
    ('0x414120', '0x414194'): ('正常な参照', '0x414186-0x41418e で同関数が [rbp+0x28]+0x10 を [rbx] に格納し、0x414191 でそれを読んで渡す。読む値は呼出し元の *argK ではなく自関数の書込みで、ERR_CAND の前提 (*argK を渡す) に当たらない。IR の stack_var_-48 との同一性は窓外で未確認'),
    ('0x414ad0', '0x414b4c'): ('正常な参照', '0x414b3e-0x414b46 で同関数が [rbp+0x28]+0x10 を [rbx] に格納し、0x414b49 でそれを読んで渡す。読む値は自関数の書込みで *argK ではない。IR の stack_var_-48 との同一性は窓外で未確認'),
    ('0x1280250', '0x12802e2'): ('誤り (候補・静的読み)', '0x12802dd の `mov rcx,[rsi]` は *arg2 を読む。0x12802dd に至るのは *arg2 が null の経路だけで、そこで 0x128028f が *arg2 ← 0x7372a0 の戻り値 X を格納する。0x7372a0 (dl=1) は 0x410320 経由で *(obj-0x30) = 0x40f960(obj) を呼び、その戻り値 X を返す (0x410360 は引数をそのまま返す)。X は 0x409410(0x500) の割当結果で、X=0 になるのは割当失敗 (0x409730) のときだけ。X の実行時値は PE の静的像からの読みで未実測。IR の定数 0 は X と一致しない見込み。詳細は tools/m11/ldfix/REPORT_5491.md'),
}

CONST_RE = re.compile(r'^-?\d+$')


def reason_class(x):
    a = x['ir_arg']
    if CONST_RE.match(a) or a.startswith(('ptrtoint', 'inttoptr')):
        return '判定不能 (IR 引数が定数・定数式)', '機械語は [argK] を読んで渡す。IR は定数。argK が常に定数と同値かは呼出し元の窓外'
    return '判定不能 (IR 引数が別引数・計算式由来)', '機械語の [argK] と IR 引数の対応が窓の定義閉包で決まらない。呼出し先の引数の意味を見る必要がある'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('judge')
    ap.add_argument('--md', required=True)
    a = ap.parse_args()
    rows = [x for x in json.load(open(a.judge)) if x['verdict'] == 'ERR_CAND']
    out = []
    cnt = Counter()
    for i, x in enumerate(rows, 1):
        key = (x['fn'], x['call_va'])
        if key in SITE_VERDICT:
            v, why = SITE_VERDICT[key]
        else:
            v, why = reason_class(x)
        cnt[v.split(' (')[0]] += 1
        out.append('| %d | %s | %s | %s | %s | %s | %s |' % (i, x['fn'], x['deref_va'], x['call_va'], x['callee'], v, why))
    head = ['| # | 関数 | deref | call | 呼出し先 | 判定 | 窓の根拠 |', '|---|---|---|---|---|---|---|']
    with open(a.md, 'w') as f:
        f.write('\n'.join(head + out) + '\n')
    print('[classify_err_cand_4972] ERR_CAND %d 件: %s' % (len(rows), dict(cnt)))


if __name__ == '__main__':
    main()
