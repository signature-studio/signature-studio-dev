#!/usr/bin/env python3
"""frames_check.py pre.json post.json : survey_units.mjs の oob frames 修正 (#663: .slice(1, 30) → .slice(0, 30)) の検収.
規則 (942 unit 全部): (1) kind が一致 (2) kind != oob の unit は全欄が完全一致 (3) oob の unit は frames 以外の欄が一致し、
post.frames[1:] == pre.frames[:len(post.frames)-1] かつ len(post.frames) == min(len(pre.frames)+1, 30) (= 最上位 frame が 1 段戻る).
違反 0 かつ oob 件数 > 0 のときだけ exit 0 (対象 0 件の空判定は不合格)。違反は unit 単位で表示して exit 1."""
import json, re, sys
pre = {r['unit']: r for r in json.load(open(sys.argv[1]))}
post = {r['unit']: r for r in json.load(open(sys.argv[2]))}
if set(pre) != set(post): sys.exit('unit 集合が異なる: %d vs %d' % (len(pre), len(post)))
# 末尾の JS frame (file:///…/survey_units*.mjs:行:列) は survey スクリプトの置き場所だけで決まるので比較から外す
def canon(x): return re.sub(r'file://\S*', 'file://<survey>', json.dumps(x, sort_keys=True))
viol, n_oob, n_changed = [], 0, 0
for u in sorted(pre):
    a, b = pre[u], post[u]
    if a['kind'] != b['kind']: viol.append((u, 'kind %s -> %s' % (a['kind'], b['kind']))); continue
    if a['kind'] != 'oob':
        if canon(a) != canon(b): viol.append((u, 'non-oob record differs'))
        continue
    n_oob += 1
    ra = {k: v for k, v in a.items() if k != 'frames'}; rb = {k: v for k, v in b.items() if k != 'frames'}
    if canon(ra) != canon(rb): viol.append((u, 'oob fields other than frames differ')); continue
    fa = [re.sub(r'file://\S*', 'file://<survey>', f) for f in a.get('frames', [])]
    fb = [re.sub(r'file://\S*', 'file://<survey>', f) for f in b.get('frames', [])]
    if fa != fb: n_changed += 1
    if len(fb) != min(len(fa) + 1, 30) or fb[1:] != fa[:len(fb) - 1]:
        viol.append((u, 'frames not shifted by one: pre %d / post %d' % (len(fa), len(fb))))
print('oob unit %d / frames が変わった unit %d / 違反 %d' % (n_oob, n_changed, len(viol)))
for u, why in viol: print('  VIOLATION unit %d: %s' % (u, why))
ok = n_oob > 0 and not viol
print('RESULT ' + ('PASS' if ok else 'FAIL'))
sys.exit(0 if ok else 1)
