#!/usr/bin/env python3
"""f4_judge.py — #564 判定。pre (F4 無し) / post (F4 有り) / noand (F4 の consumer 復元だけ無し) の実測 JSON を突き合わせる。
FAIL が 1 つでもあれば exit 1。ネガコンは f4_e2e.sh が「壊した入力」で本スクリプトを呼び exit 1 + 期待した FAIL 行を要求する。
  f4_judge.py --dir DIR [--post post.json] [--min-reg-delta N]"""
import argparse, json, os, sys
ap = argparse.ArgumentParser()
ap.add_argument('--dir', required=True)
ap.add_argument('--post', default='post.json')
ap.add_argument('--min-reg-delta', type=int, default=1)
a = ap.parse_args()
J = lambda f: json.load(open(os.path.join(a.dir, f)))
pre, post, noand, aud = J('pre.json'), J(a.post), J('noand.json'), J('audit.json')
res = []
g = lambda n, ok, d: res.append((n, bool(ok), d))
need = {'52a7f0', '71dd80'}
g('F1 F4 repairs 52a7f0 and 71dd80', need <= set(post['f4_vas']) and pre['f4_fns'] == 0, 'post f4_vas=%s pre f4_fns=%s' % (post['f4_vas'], pre['f4_fns']))
g('F2 post IR: 52a7f0 has no use of xor-0-0 value, has ldf4 load', post['ir_52a7f0_xor_used'] is False and post['ir_52a7f0_ldf4'] is True,
  'xor_used=%s ldf4=%s (pre xor_used=%s)' % (post['ir_52a7f0_xor_used'], post['ir_52a7f0_ldf4'], pre['ir_52a7f0_xor_used']))
d = post['reg_calls'] - pre['reg_calls']
g('D1 AllocateHWnd reaches RegisterClassW (directed probe)', d >= a.min_reg_delta and post['util_ret'] not in (None, '0x0') and pre['util_ret'] in (None, '0x0'),
  'RegisterClassW calls pre %s -> post %s (delta %s, need >= %s); function_52a7f0 ret pre %s -> post %s' % (pre['reg_calls'], post['reg_calls'], d, a.min_reg_delta, pre['util_ret'], post['util_ret']))
g('D2 repair needs the consumer fix too (load-only variant does not reach)', noand['reg_calls'] == pre['reg_calls'] and noand['util_ret'] in (None, '0x0'),
  'noand RegisterClassW=%s ret=%s' % (noand['reg_calls'], noand['util_ret']))
keys = ('units_run', 'init_count', 'ok', 'noproc', 'miss', 'trap', 'icall_miss')
g('P1 boot/survey parity (no regression)', all(post[k] == pre[k] for k in keys), ' '.join('%s %s/%s' % (k, pre[k], post[k]) for k in keys) + ' (pre/post)')
g('A1 audit: 52a7f0 and 71dd80 classified FRAME_IN_ESCAPED', need <= set(aud['frame_in_escaped_fns']), 'sites=%s by_class=%s' % (aud['sites_total'], aud['by_class']))
w = max(len(n) for n, _, _ in res)
for n, ok, dd in res:
    print('%-*s  %s  %s' % (w, n, 'PASS' if ok else 'FAIL', dd))
sys.exit(0 if all(ok for _, ok, _ in res) else 1)
